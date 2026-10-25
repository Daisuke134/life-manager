"""K014: domain-independent orchestration, DENYING all real-world effects.

The fixture planner's causal_support is an explicit test input, NOT a claim
that a generative prediction established causal efficacy. No automatic
source crawling, authority issuance or self-modifying policy is available.
"""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from .audit import AuditTrail
from .authority import AuthorityVerifier,Grant
from .outbox import DurableOutbox
from .reconcile import Reconciler
from .state_machine import State,StateMachine
from .verifier import verify_outcome
from .evaluator import evaluate_outcome
from .models.problem import Problem
from .models.intervention import InterventionPlan
from .models.source import _aware


@dataclass(frozen=True)
class RunResult:
    status: str
    proof_level: str
    effect_key: str | None = None
    reason: str | None = None


class ManagerKernel:
    def __init__(self,outbox: DurableOutbox,authority: AuthorityVerifier,audit: AuditTrail):
        self.outbox=outbox
        self.authority=authority
        self.audit=audit

    def review_public_advice(self, run_id, context, model_response):
        """Audit a bounded provider proposal as P0; never call outbox or adapter.

        This is the only bridge from collaborator inference into the kernel.
        It does not establish causal support, authority, or execution eligibility.
        """
        from .collaboration import PlannerContext, safe_advisory
        if type(context) is not PlannerContext:
            raise ValueError("typed public context required")
        result = safe_advisory(model_response, context)
        for fact in context.facts:
            source = fact.source
            self.audit.append(run_id, "source", {
                "source_id": source.source_id,
                "source_url": source.url,
                "license_id": source.license_id,
                "rights": source.rights,
                "content_hash": source.content_sha256,
                "privacy_class": source.privacy_class,
                "retrieved_at": source.retrieved_at.isoformat(),
            })
        self.audit.append(run_id, "proposal", {
            "status": result.status,
            "decision": result.decision,
            "reason": "PROPOSAL_ONLY_NO_EXECUTION",
            "proof_level": "P0",
            "benefit_status": "NOT_MEASURED",
        })
        self.audit.append(run_id, "decision", {
            "status": "NO_ACTION",
            "decision": "NO_ACTION",
            "proof_level": "P0",
        })
        return result

    def prepare_owned_change(self, context, assessment, standing_scope, now):
        from .digital_handoff import prepare_owned_change
        result=prepare_owned_change(context,assessment,standing_scope,now)
        self.audit.append(result.run_id,'authorization',{
            'status':result.status,'reason':result.reason,
            'grant_id':result.scope_id,'content_hash':result.context_hash,
            'benefit_status':'NOT_MEASURED','proof_level':'P0'})
        return result

    def prepare_digital_release(self, run_id, baseline, candidate, now, *, source_ref=None):
        """Plan an inert handoff; only the separate owned CI job can publish.

        The fixture outbox and fixture signing authority are deliberately not
        used. A technical page comparison is not causal evidence about people.
        """
        from .digital_handoff import SOURCE_REF, plan_release
        source_ref=SOURCE_REF if source_ref is None else source_ref
        packet=plan_release(baseline,candidate,now,source_ref=source_ref)
        self.audit.append(run_id,'observation',{
            'source_url':packet['target'],'content_hash':packet['baseline_sha256'],
            'recorded_at':now.isoformat(),'unit':'public_artifact_bytes'})
        self.audit.append(run_id,'proposal',{
            'effect_key':packet['effect_key'],'decision':packet['decision'],
            'content_hash':packet['candidate_sha256'],'option_cost':0,
            'reason':'Tested owned artifact; NO_ACTION alternative retained'})
        self.audit.append(run_id,'authorization',{
            'status':'EXTERNAL_PLATFORM_AUTHORITY_REQUIRED',
            'grant_target':packet['target'],'grant_expires_at':packet['expires_at'],
            'benefit_status':'NOT_MEASURED','proof_level':'P0'})
        return packet

    def run(self,run_id:str,problem: Problem,plan: InterventionPlan,grant:Grant,
            signature:str,adapter,sensor,now:datetime,*,causal_support:bool=False) -> RunResult:
        _aware(now)
        if not isinstance(problem,Problem) or not isinstance(plan,InterventionPlan):
            raise ValueError("typed problem and NO_ACTION plan required")
        m=StateMachine()
        source_stale=False
        for o in problem.observations:
            src=o.source
            self.audit.append(run_id,"source",{
                "source_id":src.source_id,"source_url":src.url,
                "license_id":src.license_id,"rights":src.rights,
                "content_hash":src.content_sha256,"privacy_class":src.privacy_class,
                "retrieved_at":src.retrieved_at.isoformat()})
            self.audit.append(run_id,"observation",{
                "measure_id":o.measure_id,"unit":o.unit,
                "recorded_at":o.recorded_at.isoformat(),
                "value":o.value,"missing_reason":o.missing_reason})
            try:
                src.require_fresh(now, max_age_hours=48)
            except ValueError:
                source_stale=True
        if source_stale:
            m.transition(State.NO_ACTION)
            self.audit.append(run_id,"decision",{"status":"NO_ACTION","reason":"source stale or future dated"})
            return RunResult("NO_ACTION","P0",reason="Stale or future-dated public evidence")
        m.transition(State.HYPOTHESIZED)
        for h in problem.causal_hypotheses:
            self.audit.append(run_id,"hypothesis",{"hypothesis":h.claim,
                "evidence_refs":",".join(h.evidence_refs)})
        for alt in problem.alternative_explanations:
            self.audit.append(run_id,"hypothesis",{"alternative":alt})
        m.transition(State.PROPOSED)
        m.transition(State.RISK_CHECKED)
        choice=plan.choose(supports_causal=causal_support)
        for option in plan.options:
            self.audit.append(run_id,"proposal",{
                "option_id":option.option_id,"option_cost":option.cost,
                "option_risk":option.risk,"expected_interval":str(option.expected_effect),
                "decision":"SELECTED" if option==choice else "ALTERNATIVE"})
        if choice.no_action:
            m.transition(State.NO_ACTION)
            self.audit.append(run_id,"decision",{"status":"NO_ACTION","reason":"causal evidence insufficient or costs outweigh effect"})
            return RunResult("NO_ACTION","P0",reason="No credible authorized net-positive action")
        if (choice.domain,choice.action,choice.target)!=(adapter.domain,adapter.action,adapter.target):
            m.transition(State.REJECTED)
            self.audit.append(run_id,"decision",{"status":"REJECTED","reason":"adapter scope does not match chosen intervention"})
            return RunResult("REJECTED","P0",reason="adapter scope mismatch")
        effect_key=sha256(f"{run_id}|{choice.option_id}|{choice.domain}|{choice.target}|{choice.action}".encode()).hexdigest()
        self.audit.append(run_id,"risk",{"status":"fixture_only"})
        try:
            # The outbox performs both scoped authorization and budget reservation.
            receipt=self.outbox.execute(effect_key,grant,signature,self.authority,adapter,choice.cost,now)
        except (ValueError,PermissionError) as exc:
            m.transition(State.REJECTED)
            self.audit.append(run_id,"authorization",{"status":"REJECTED","reason":type(exc).__name__})
            return RunResult("REJECTED","P0",effect_key,reason=type(exc).__name__)
        m.transition(State.AUTHORIZED)
        self.audit.append(run_id,"authorization",{"grant_id":grant.grant_id,
            "grant_domain":grant.domain,"grant_action":grant.action,
            "grant_target":grant.target,"grant_budget":grant.limit,
            "grant_expires_at":grant.expires_at.isoformat(),"status":"OFFLINE_FIXTURE"})
        self.audit.append(run_id,"execution",{"effect_key":effect_key,"status":receipt.status,
                                             "receipt_ref":receipt.receipt_ref})
        if receipt.status in ("UNKNOWN","DISPATCHING"):
            r=Reconciler(self.outbox).reconcile(effect_key,adapter)
            self.audit.append(run_id,"reconciliation",{"status":r.status,"receipt_ref":r.receipt_ref})
            if r.status!="PRESENT":
                m.transition(State.UNKNOWN_EFFECT)
                return RunResult("UNKNOWN_EFFECT","P0",effect_key,reason="not independently reconciled")
            receipt=self.outbox.record(effect_key)
        if receipt.status not in ("SUBMITTED","PRESENT"):
            m.transition(State.UNKNOWN_EFFECT)
            return RunResult("UNKNOWN_EFFECT","P0",effect_key,reason="uncertain provider status")
        m.transition(State.EXECUTED)
        try:
            rb=sensor.readback(effect_key,now)
        except Exception:
            rb=None
        verification=verify_outcome(receipt,rb)
        self.audit.append(run_id,"verification",{"status":verification.status,
            "readback_ref":verification.evidence_ref,"proof_level":verification.proof_level,
            "readback_timestamp":rb.recorded_at.isoformat() if rb is not None else None})
        if verification.status!="VERIFIED_FIXTURE_ONLY":
            m.transition(State.MEASUREMENT_MISSING)
            return RunResult("MEASUREMENT_MISSING","P0",effect_key)
        m.transition(State.VERIFIED)
        # No preregistered comparator/observed harms exist in these fixtures.
        evaluation=evaluate_outcome(0,0,0,choice.cost,None,None,"welfare")
        m.transition(State.EVALUATED)
        self.audit.append(run_id,"evaluation",{"status":evaluation.status,"benefit_status":"NOT_MEASURED",
            "proof_level":"P0"})
        # Policy promotion is deliberately a separate gated heldout/shadow operation.
        return RunResult("VERIFIED_FIXTURE_ONLY","P0",effect_key,"Independent FIXTURE readback; no net-benefit claim")
