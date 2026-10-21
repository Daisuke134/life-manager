"""A/B and off-policy causal-evaluation *diagnostics* on public Open Bandit Dataset.

The available GitHub excerpt comprises first 10,000 policy/campaign rows, not
a randomly drawn sample. Report observational estimates and uncertainty,
never certify full-trial causal effect or human welfare improvement.
"""
from __future__ import annotations
from math import sqrt, isfinite

CATALOG_SIZE = {"all":80,"men":34,"women":46}


def _mean(vals):
    return sum(vals) / len(vals)


def _safe_rate(x):
    if type(x) is not int or x not in (0,1):
        raise ValueError("binary click required")
    return x


def summarize_policy(rows, *, catalog_size):
    """Rows are sanitized ephemeral triples (click, known logging p, item_id)."""
    if not rows or not 2 <= catalog_size <= 1000:
        raise ValueError("nonempty valid policy data required")
    direct = 0
    weighted = []
    all_weights = []
    for click,p,item in rows:
        _safe_rate(click)
        if type(item) is not int or not 0 <= item < catalog_size:
            raise ValueError("unknown action / catalog")
        if type(p) not in (float,int) or not isfinite(p) or not 0 < p <= 1:
            raise ValueError("unsupported logging propensity")
        w=(1/catalog_size)/p
        direct+=click
        weighted.append(click*w)
        all_weights.append(w)
    n=len(rows);rate=direct/n
    ips=_mean(weighted)
    # Self-normalized estimand is often biased but less variable; report BOTH.
    snips=sum(weighted)/sum(all_weights)
    error=sqrt(rate*(1-rate)/n)
    ips_se=sqrt(sum((x-ips)**2 for x in weighted)/(n*(n-1))) if n>1 else None
    return {
        "n":n,"clicks":direct,"click_rate":round(rate,9),
        "click_rate_normal95":[round(max(0,rate-1.96*error),9),round(min(1,rate+1.96*error),9)],
        "random_target_ips":round(ips,9),"random_target_snips":round(snips,9),
        "ips_naive_row_se":round(ips_se,9) if ips_se is not None else None,
        "importance_weights":{"min":round(min(all_weights),7),
                              "max":round(max(all_weights),7),
                              "ess":round((sum(all_weights)**2)/sum(w*w for w in all_weights),3)},
    }


def compare_policies(data):
    """Consumes 6 * 10k ephemeral rows with pre-registered campaign subsets."""
    if set(data) != {f"{p}/{c}" for p in ("bts","random") for c in CATALOG_SIZE}:
        raise ValueError("all randomized and deterministic policy arms needed")
    cases=[]
    for campaign,k in CATALOG_SIZE.items():
        b=summarize_policy(data["bts/"+campaign],catalog_size=k)
        r=summarize_policy(data["random/"+campaign],catalog_size=k)
        delta=b["click_rate"]-r["click_rate"]
        se=sqrt(b["click_rate"]*(1-b["click_rate"])/b["n"]+
                r["click_rate"]*(1-r["click_rate"])/r["n"])
        cases.append({
            "campaign":campaign,"actions":k,
            "bts":b,"random":r,
            "bts_minus_random_observed":round(delta,9),
            "bts_minus_random_normal95":[round(delta-1.96*se,9),round(delta+1.96*se,9)],
            "off_policy_random_target_ips_on_bts":b["random_target_ips"],
            "off_policy_random_target_snips_on_bts":b["random_target_snips"],
            "direct_random_policy_observed":r["click_rate"],
            "off_policy_error_abs_ips_vs_random_direct":round(abs(b["random_target_ips"]-r["click_rate"]),9),
            "off_policy_error_abs_snips_vs_random_direct":round(abs(b["random_target_snips"]-r["click_rate"]),9)
        })
    return {
        "schema":"manager.phase04.zozo-open-bandit-public-ab-eval.v1",
        "basis":"REAL_PUBLIC_RANDOMIZED_POLICY_LOGS_FIRST_10000_ROWS_EACH",
        "source":"st-tech/zr-obp@8cbd5fa4558b7ad2ba4781546d6604e4cc3e07c4",
        "campaign_results":cases,
        "limitations":{
          "subset_selection":"first 10000 rows per policy/campaign, NOT randomly sampled full A/B trial",
          "propensity":"source propensity_score per position used; item catalog counts from upstream README",
          "randomization":"original company says policies randomized A/B; first-row subsets and user duplication may invalidate textbook iid intervals",
          "small_click_counts":True,
          "ips_heavy_tails_unclipped":True,
          "confidence_intervals":"naive independent Bernoulli approximations; exploratory only",
          "causal_benefit_claim":False,
          "manager_deployed_intervention":False,
          "personalized_user_intervention":False,
          "socsci210_semantic_task_benchmark":False,
        },
        "privacy":{"raw_rows_committed":False,"profile_features_used":False,"person_identifiers_saved":False},
    }
