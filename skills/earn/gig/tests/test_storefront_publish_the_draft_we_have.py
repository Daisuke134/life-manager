"""A draft whose contract was already sealed must be published, not proposed again.

`_recover_prepared_create_contract` only accepted `prepared`. A draft created before a wake
could fill and publish in one pass never reaches that stage, so its sealed contract was never
offered back and every later wake generated a fresh proposal -- re-rolling the dice against
every content guard. Draft 4387924 sat filled and unpublished through three such rounds,
each one refused by the title guard.

The title guard has now refused three different shapes of the same mistake: a particle
(`...Botを`), a bare noun (`...アプリ`), and a する-verb written as its noun (`...を自動化`).
The prompt must name all three, since a rule the model is never told is one it keeps breaking.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import storefront_direct as direct  # noqa: E402

SOURCE = (SCRIPTS / "storefront_direct.py").read_text(encoding="utf-8")
# `_recover_prepared_create_contract` delegates to the adjacent Coconala Storefront kernel.
# The guard conditions this file pins therefore live in that kernel's source.
KERNEL_SOURCE = (SCRIPTS / "storefront_kernel.py").read_text(encoding="utf-8")


def _recovery_block() -> str:
    start = KERNEL_SOURCE.index("def recover_prepared_create_contract")
    return KERNEL_SOURCE[start:start + 2200]


def test_both_stages_can_be_recovered():
    block = _recovery_block()
    assert '{"prepared", "draft_created"}' in block


def test_a_prepared_draft_still_has_to_have_been_read_back():
    block = _recovery_block()
    assert 'stage == "prepared" and int(draft.get("readback") or 0) != 1' in block


def test_a_published_draft_is_never_recovered():
    assert 'int(draft.get("public_effect") or 0) != 0' in _recovery_block()


@pytest.mark.parametrize("stem, why", [
    ("LINE公式アカウントのFAQ自動応答Botを", "particle"),
    ("iOS/Androidアプリ", "bare noun"),
    ("LINE公式アカウントの定型問合せ応答を自動化", "suru-verb as noun"),
])
def test_every_shape_the_guard_refused_really_is_refused(stem, why):
    assert stem[-1] not in direct.TITLE_STEM_CONTINUATIVE_ENDINGS, why


def test_the_prompt_names_the_suru_verb_case_with_the_observed_stem():
    assert "応答を自動化" in SOURCE
    assert "応答を自動化し" in SOURCE


@pytest.mark.parametrize("fix", ["応答を自動化し", "業務を効率化し", "環境を構築し", "機能を実装し"])
def test_every_repair_the_prompt_offers_passes_the_guard(fix):
    assert fix[-1] in direct.TITLE_STEM_CONTINUATIVE_ENDINGS
