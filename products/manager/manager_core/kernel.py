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

    def run(self,run_id:str,problem: Problem,plan: InterventionPlan,grant:Grant,
            signature:str,adapter,sensor,now:datetime,*,causal_support:bool=False) -> RunResult:
        _aware(now)
        if not isinstance(problem,Problem) or not isinstance(plan,InterventionPlan):
            raise ValueError("typed problem and NO_ACTION plan required")
        m=StateMachine()
        for o in problem.observations:
            self.audit.append(run_id,"source",{"source_id":o.source.source_id})
            self.audit.append(run_id,"observation",{"measure_id":o.measure_id})
        m.transition(State.HYPOTHESIZED)
        for h in problem.causal_hypotheses:
            self.audit.append(run_id,"hypothesis",{"hypothesis":h.claim})
        m.transition(State.PROPOSED)
        m.transition(State.RISK_CHECKED)
        choice=plan.choose(supports_causal=causal_support)
        self.audit.append(run_id,"proposal",{"option_id":choice.option_id})
        if choice.no_action:
            m.transition(State.NO_ACTION)
            self.audit.append(run_id,"decision",{"status":"NO_ACTION","reason":"causal evidence insufficient or costs outweigh effect"})
            return RunResult("NO_ACTION","P0",reason="No credible authorized net-positive action")
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
        self.audit.append(run_id,"authorization",{"grant_id":grant.grant_id,"status":"OFFLINE_FIXTURE"})
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
            "readback_ref":verification.evidence_ref,"proof_level":verification.proof_level})
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
