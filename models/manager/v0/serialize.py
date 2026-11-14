"""Canonical serialization for Manager v0 (Hillstrom two-arm schema).

One prompt format, used identically for SFT training, base-model scoring and
post-trained scoring. The completion is the observed outcome under the arm
actually delivered (1 = visited, 0 = did not visit), so at scoring time the
model's next-token distribution over {0, 1} under each arm is an outcome
model P(visit | x, arm), and the uplift score is
P(visit | x, treated) - P(visit | x, control).

This module was validated against the shipped training file: rendering the
frozen train split reproduces all 2,000 (prompt, completion) pairs in
sft_train.jsonl exactly (validate_serialize.py, 2000/2000).
"""

TREATED_TEXT = "send a promotional e-mail featuring women's products."
CONTROL_TEXT = "send no e-mail."

QUESTION = (
    "Will the person visit the website within two weeks? "
    "Answer 1 for yes, 0 for no.\nAnswer:"
)


def render_prompt(recency, history, mens, womens, zip_code, newbie, channel,
                  treated) -> str:
    """Prompt for one person under one arm (treated=True/False)."""
    iv = TREATED_TEXT if treated else CONTROL_TEXT
    return (
        f"History: recency={recency}; spend={history}; mens={mens}; "
        f"womens={womens}; zip={zip_code}; newbie={newbie}; channel={channel}.\n"
        f"Intervention: {iv}\n"
        f"{QUESTION}"
    )


def render_prompt_from_row(row, treated) -> str:
    return render_prompt(row["recency"], row["history"], row["mens"],
                         row["womens"], row["zip_code"], row["newbie"],
                         row["channel"], treated)


def render_completion(visit) -> str:
    return f" {int(visit)}"


def render_eval_prompt(row, treated) -> str:
    """Scoring prompt: the SFT prompt plus the single space that precedes the
    digit, so the next-token distribution is read at the digit position."""
    return render_prompt_from_row(row, treated) + " "
