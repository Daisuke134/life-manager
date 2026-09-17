#!/usr/bin/env python3
"""Scan the writing rulebook for contradictions between its own rule
sources, mechanically, with no model calls -- the piece that keeps the
rulebook from rotting between training runs.

Why this exists: spec 47 section 19-4b / section 20. "The scanner never
edits anything and never says which side should die -- beat rate decides
that." This script's whole output is a list of TICKETS for a human or the
trainer to look at; it is not a fixer and it is not a judge. Every finding
is `{"class": "direct"|"drift"|"dead", "side1": "file:line",
"side2": "file:line"|None, "subject": "...", "quote1": "<=15 words",
"quote2": "<=15 words"|None}`.

Three detections, all mechanical (string/regex over the rule sources, no
LLM):

  1. DIRECT CONFLICT -- a statement that BANS something and a statement
     that RECOMMENDS something share AT LEAST TWO "distinctive" subject
     terms (a term appearing in AT MOST 3 statements across the whole
     corpus -- an absolute ceiling, not a relative one; see ROUND-3
     RECALIBRATION below). Capped at the top 20 pairs by shared-term
     count, with a suppressed-count reported alongside.
  2. DRIFTED PARAPHRASE -- two statements in DIFFERENT files share a
     majority of their distinctive terms, but one carries an absolute
     qualifier (must/always/never/only/唯一/必ず/non-negotiable) the other
     lacks: the same rule, restated with a stricter edge than the
     original measured claim.
  3. DEAD REFERENCE -- a referenced script/artifact path that does not
     resolve under ANY of several candidate roots (see ROUND-3
     RECALIBRATION), or a `gates/<name>.json` pattern that no script in
     scripts/ ever writes (checked by grepping scripts/ for the name, per
     the coordinator's spec -- this is intentionally the simple decision
     procedure asked for, not a static-analysis writer-tracker).

ROUND-3 RECALIBRATION (real scan against the actual rulebook: 1205 direct /
2 drift / 19 dead -> 20 direct + 23 suppressed / 1 drift / 17 dead):
  1. 1205 direct findings is the same as zero findings -- nobody reads
     1205 tickets. Root cause: the original spec's relative threshold
     ("appears in fewer than 20% of statements") is far too loose on a
     179-statement corpus -- a word appearing 30 times still clears 20%,
     so every ban paired with every recommend sharing ONE such word,
     quadratically. Three-part fix, all implemented: (a) the bar is now
     ABSOLUTE -- a term is distinctive only if it appears in at most 3
     statements total, not a fraction of the corpus; (b) a pair is
     reported only when it shares AT LEAST 2 distinctive terms, not 1 --
     one rare word in common is coincidence, two is a subject; (c) output
     is capped at the top 20 pairs by shared-term count descending, with
     `direct_suppressed` reporting how many more exist. The same absolute-
     rarity fix (a) applies to detection 2 automatically, since both share
     compute_distinctive_terms -- this is what turned drift's subjects
     from generic vocabulary ("image", "code") into a genuinely rare term.
  2. The dead detector resolved every relative reference against ONE root
     (the skill directory), producing a false positive: note-publish/
     publish-paid.py is real, but lives under scripts/note-publish/, not
     directly under the skill root. Fixed: a relative reference is now
     tried against four candidate roots -- the skill root, skill root +
     scripts/, the directory of the file that mentioned it, and the
     repository root -- and is only "dead" when it resolves under NONE of
     them (see _candidate_paths).

ROUND-4 FIX (gates evidence was incomplete: 19 dead -> 7 after adding run-
directory evidence): "no script writes it" was the ONLY evidence detect_
dead_gates used, and it was incomplete -- the daily prompt orders the MODEL
to write several of these gates directly (STEP 0.6: "copy each gate JSON
verdict there as gates/<gate-name>-<lang>.json"), so absence from scripts/
proves nothing about whether the gate is actually produced. Checked against
the real run directories: reader-questions-{ja,en}.json and platform-
dispatch(-results).jsonl are present in the most recent runs (something
produces them) despite no script constructing those paths -- both were
false positives. rubric-judge-{en,ja}.json is ALSO present as of the
latest run, reversing the round-3 conclusion that it was dead; that
conclusion rested on script evidence alone. self-improve-application.json
is genuinely absent from every recent run -- the one true positive that
was buried among the false ones. Fix: a gate reference is dead only when
no script writes it AND it is absent from all of the RECENT_RUNS_TO_CHECK
(3) most-recently-modified run directories under state/runs (see
_gate_present_in_recent_runs). A second, necessary fix: detect_dead_paths
(the general path detector) was independently re-extracting the same
gates/<name> tokens as ordinary path references and declaring them dead
via its own root-resolution logic, which has no concept of "produced by a
recent run" -- silently re-introducing the same false positives through a
different detector even after detect_dead_gates was fixed. extract_path_
references now excludes any token that is a gates/ artifact reference;
gates/ evidence belongs to detect_dead_gates exclusively.

Rule sources (paths relative to skills/writer-agent, all overridable via
--sources): reference/title-best-practices.md, SKILL.md, article-daily.sh
(only its lines longer than LONG_LINE_THRESHOLD chars -- article-daily.sh
is mostly shell plumbing; the actual prompt text lives in a handful of very
long lines. Generalised to ANY .sh file passed via --sources, not
hardcoded to this one filename, so a future second prompt script is
covered without a code change).

Design choices made because the spec left them open (simplest option,
noted here rather than asked about):
  * Term extraction: contiguous hiragana/katakana/kanji runs (len>=2) and
    English word tokens (len>=3, casefolded), minus a small standard
    English function-word stopword list (_EN_STOPWORDS). The spec's own
    reasoning is that the <20%-of-statements threshold alone suppresses
    "the"/common words; a first implementation trusted that literally and
    ran with zero stopword list. Running it against the actual bilingual
    rulebook and reading the output surfaced two real, sequential bugs
    (see compute_distinctive_terms's docstring for the first): even after
    fixing the population to be same-DOMINANT-language statements, "from"
    still measured at 18% (under the 20% floor) because ordinary English
    connectives are genuinely reused across many unrelated rule
    statements at this corpus size -- the literal reading of the spec's
    own stated mechanism does not, empirically, fully suppress function
    words on its own. A minimal standard stopword list (articles,
    prepositions, common pronouns/auxiliaries -- not a hand-tuned list
    reverse-engineered from this corpus) closes that gap and is the
    smallest fix that made the "the"/"from" example the spec itself gives
    actually hold.
  * Short, common English ban/recommend/qualifier words (never, always,
    only, must, works) are matched as WHOLE TOKENS via the same word-split
    approach goodhart.py uses -- bare substring matching would false-hit
    inside ordinary words ("network"/"framework" both contain "works").
    Longer, more distinctive markers (banned, rewarded, proven, non-
    negotiable, "do not", "must not", "use this") are matched as plain
    casefolded substrings, same trade-off goodhart.py already documents.
  * Detection 2's "share a majority of their distinctive terms" is
    implemented as an overlap coefficient: |shared| / min(|A|, |B|) > 0.5
    -- majority relative to the SMALLER statement's term set, which is
    what "majority" means when comparing two sets of different size.
  * Referenced-path resolution: a token starting with ~ is expanded to the
    real home directory and a token starting with / is absolute as given
    -- both tried directly, one root, since they are already unambiguous.
    Everything else (must contain at least one "/", i.e. look like an
    actual path rather than a bare filename mentioned in passing prose --
    "meta.json" used as a generic example is not a reference to a specific
    file) is tried against FOUR candidate roots (round-3 fix, see
    _candidate_paths): the skill directory, skill directory + scripts/,
    the directory of the file that mentioned it, and the repository root
    -- dead only if none of the four resolve. A path immediately wrapped
    in <...> (the CLI-argument-placeholder convention used throughout
    these prompts, e.g. "<original.md>") is excluded -- it is documenting
    a parameter shape, not naming a real file. One known remaining false-
    positive class, accepted rather than chased further: a bare relative
    reference whose intended root is a DIFFERENT project entirely (e.g.
    article-daily.sh's docs/loop-engineering/47-....md, which resolves
    under a different project checkout, not any of the four roots tried) still shows
    up dead -- none of the four roots the coordinator specified cover an
    arbitrary sibling project, and guessing at other projects' locations
    would be scope creep beyond the specified fix.
  * quote1/quote2 are capped at 15 whitespace-delimited tokens when the
    text actually has word-spacing (English), or 90 characters when it
    does not (dense Japanese prose has no inter-word spaces to split on,
    so a literal "15 words" cap would return the entire clause).
  * A finding's `subject` for "direct" lists EVERY shared distinctive term
    (comma-joined, alphabetical), not just one -- showing more than one is
    the point of the round-3(b) >=2-shared-terms requirement, so hiding
    all but the first would defeat the purpose of raising the bar.
    "drift" still uses a single term (the alphabetically-first), since
    the coordinator's round-3 fix for detection 2 was the rare-term
    ceiling only, not a multi-term subject or a >=2 floor.
  * Findings are deduplicated: dead-reference findings by (class, subject)
    globally (the same missing script mentioned on 20 lines is one ticket,
    not 20); direct/drift findings are naturally unique per (side1, side2)
    pair since each statement pair is only compared once.

Known true positive (per the coordinator's spec): SKILL.md's former
blanket self-reference ban versus reference/title-best-practices.md's
First-person confessional pattern. As of this writing SKILL.md line 171-173
documents that this exact collapse was ALREADY split into two separate,
non-conflicting rules (identity vs craft) on a prior pass, so detection 1
does not currently surface that specific pair from the live files -- the
detector is proven against a synthetic fixture of that shape instead in
tests/rule-conflicts-contract.sh (a ban statement and a recommend
statement sharing two rare terms, "self"/"reference" plus "author"/
"naming"/"voice"), and this is stated here rather than silently working
around it. The round-3 recalibration (a stricter absolute rarity bar plus
a >=2-shared-terms floor) is specifically checked NOT to have silenced
this fixture -- a detector that reports nothing is exactly as broken as
one reporting 1205, and this is the test that tells the two apart.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LONG_LINE_THRESHOLD = 400
DISTINCTIVE_MAX_OCCURRENCES = 3
MIN_SHARED_TERMS = 2
MAX_DIRECT_FINDINGS = 20
OVERLAP_THRESHOLD = 0.5
QUOTE_MAX_WORDS = 15
QUOTE_MAX_CHARS = 90
RECENT_RUNS_TO_CHECK = 3

DEFAULT_SOURCES = (
    "reference/title-best-practices.md",
    "SKILL.md",
    "article-daily.sh",
)

BAN_SUBSTRING = ("禁止", "禁則", "してはならない", "must not", "do not", "banned")
BAN_WORD = ("never",)

RECOMMEND_SUBSTRING = ("推奨", "手本", "効いていた", "rewarded", "proven", "use this")
RECOMMEND_WORD = ("works",)

QUALIFIER_SUBSTRING = ("必ず", "唯一", "non-negotiable")
QUALIFIER_WORD = ("always", "never", "only", "must")

_JP_RUN_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿]{2,}")
_EN_WORD_RE = re.compile(r"[A-Za-z]{3,}")
_GATES_REF_RE = re.compile(r"gates/[A-Za-z0-9_.$<>{},-]+")

_VALID_EXTS = (".sh", ".py", ".jsonl", ".json", ".md")
_EXT_COUNT_RE = re.compile(r"\.(?:sh|py|jsonl|json|md)")
_PATH_CHARS_RE = re.compile(r"^[A-Za-z0-9_./~-]+$")
_WORD_SPLIT_RE = re.compile(r"[\s,`'\"()]+")

# Minimal standard English function-word list -- articles, prepositions,
# common pronouns/auxiliaries/conjunctions. NOT hand-tuned against this
# corpus; see the module docstring for why the <20%-of-statements
# threshold alone was not enough on its own.
_EN_STOPWORDS = frozenset({
    "the", "a", "an", "of", "to", "in", "on", "at", "for", "from", "with",
    "by", "as", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "it", "its", "we", "you", "your",
    "our", "not", "no", "do", "does", "did", "has", "have", "had",
    "can", "will", "would", "should", "could", "may", "might",
    "if", "so", "but", "and", "or", "what", "which", "who", "whom",
    "own", "into", "out", "up", "down", "than", "then", "there", "here",
    "one", "two", "all", "any", "each", "every", "other", "same",
})


# ---------------------------------------------------------------------------
# Small pure functions -- these are what the contract test drives directly,
# with in-memory fixtures instead of the real files.
# ---------------------------------------------------------------------------

def _english_tokens(text: str) -> set:
    return {word.lower() for word in _EN_WORD_RE.findall(text)}


def _has_substring_marker(text: str, markers: tuple) -> bool:
    lowered = text.casefold()
    return any(marker.casefold() in lowered for marker in markers)


def _has_word_marker(text: str, markers: tuple) -> bool:
    return bool(_english_tokens(text) & set(markers))


def is_ban(text: str) -> bool:
    return _has_substring_marker(text, BAN_SUBSTRING) or _has_word_marker(text, BAN_WORD)


def is_recommend(text: str) -> bool:
    return _has_substring_marker(text, RECOMMEND_SUBSTRING) or _has_word_marker(text, RECOMMEND_WORD)


def has_qualifier(text: str) -> bool:
    return _has_substring_marker(text, QUALIFIER_SUBSTRING) or _has_word_marker(text, QUALIFIER_WORD)


def extract_terms(text: str) -> set:
    """All candidate subject terms in one statement: JP kana/kanji runs
    (len>=2) and EN word tokens (len>=3, casefolded), minus a small
    standard English function-word stopword list. (Marker detection --
    is_ban/is_recommend/has_qualifier -- uses the unfiltered
    _english_tokens separately; stopwording only affects subject-term
    matching for detections 1 and 2.)"""
    return set(_JP_RUN_RE.findall(text)) | (_english_tokens(text) - _EN_STOPWORDS)


def scannable_lines(rel_path: str, text: str) -> list:
    """(lineno, line) pairs to consider from one source. .sh files only
    contribute lines longer than LONG_LINE_THRESHOLD (the prompt text,
    not shell plumbing); every other source type is read in full."""
    is_shell = rel_path.endswith(".sh")
    out = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if is_shell and len(line) <= LONG_LINE_THRESHOLD:
            continue
        out.append((lineno, line))
    return out


def extract_statements(sources: dict) -> list:
    """One statement per qualifying line across all sources: a line is a
    statement only if it matches a ban or a recommend marker (or both)."""
    statements = []
    for rel_path, text in sources.items():
        for lineno, line in scannable_lines(rel_path, text):
            stripped = line.strip()
            if not stripped:
                continue
            ban = is_ban(stripped)
            rec = is_recommend(stripped)
            if not ban and not rec:
                continue
            statements.append({
                "file": rel_path, "line": lineno, "text": stripped,
                "is_ban": ban, "is_recommend": rec,
            })
    return statements


def compute_distinctive_terms(statements: list, max_occurrences: int = DISTINCTIVE_MAX_OCCURRENCES) -> list:
    """Per statement (by index), the subset of its terms that appear in AT
    MOST `max_occurrences` statements ACROSS THE WHOLE CORPUS. Returns a
    list parallel to `statements`.

    Round-3 fix: the original spec used a RELATIVE threshold ("appears in
    fewer than 20% of all statements"). On the real 179-statement
    bilingual corpus that bar was far too loose -- a term appearing 30
    times still clears 20%, so ordinary vocabulary ("fail", "runs",
    "image", "code") kept qualifying as "distinctive" and every ban got
    paired with every recommend that happened to share one, producing
    1205 findings nobody could read. This is an ABSOLUTE bar instead: a
    term is only distinctive if it appears in at most 3 statements, full
    stop, regardless of corpus size. Rare terms are what made the real
    historical case detectable (一人称/self-reference genuinely occur a
    handful of times; "fail" does not), so the bar is tightened to only
    keep terms that are actually rare, not merely under-represented
    relative to a large denominator. A prior version of this function
    also bucketed the population by each term's dominant-language
    statements plus a stopword list to fight a bilingual false-positive
    (ordinary English words looking rare only because most of the corpus
    is Japanese) -- with an absolute, small, language-agnostic ceiling
    like 3, that machinery is no longer needed: a genuinely common word in
    either language will trivially exceed 3 occurrences in a corpus this
    size, so it is filtered without having to reason about which
    language's population to measure it against."""
    per_statement_terms = [extract_terms(s["text"]) for s in statements]
    doc_count: dict = {}
    for terms in per_statement_terms:
        for term in terms:
            doc_count[term] = doc_count.get(term, 0) + 1
    return [
        {term for term in terms if doc_count[term] <= max_occurrences}
        for terms in per_statement_terms
    ]


def make_quote(text: str, max_words: int = QUOTE_MAX_WORDS, max_chars: int = QUOTE_MAX_CHARS) -> str:
    """<=15 words when the text has real word-spacing (English); a
    character cap when it does not (unsegmented Japanese prose)."""
    normalized = " ".join(text.strip().split())
    words = normalized.split(" ") if normalized else []
    if len(words) > 1:
        truncated = " ".join(words[:max_words])
        if len(truncated) <= max_chars:
            return truncated
        return truncated[:max_chars].rstrip() + "…"
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars].rstrip() + "…"


def detect_direct_conflicts(statements: list) -> tuple:
    """Ban statements paired with recommend statements that share at least
    MIN_SHARED_TERMS (2) distinctive subject terms (spec 47 19-4b
    detection 1, round-3 recalibration).

    Returns (findings, suppressed_count). findings is capped at
    MAX_DIRECT_FINDINGS (20), ranked by number of shared distinctive terms
    descending (ties broken by side1 then side2 for determinism);
    suppressed_count is how many additional qualifying pairs exist beyond
    the cap, so the report says what it is not showing rather than
    silently truncating. Requiring >=2 shared terms (not the original
    spec's >=1) is the second half of the round-3 fix: one rare word in
    common can be coincidence, but two shared rare terms is what actually
    distinguished the real historical case (self-reference AND
    first-person, together) from noise. `subject` lists every shared term
    (comma-joined), not just one, since showing more than one is the
    point of the >=2 requirement."""
    distinctive = compute_distinctive_terms(statements)
    candidates = []
    ban_idxs = [i for i, s in enumerate(statements) if s["is_ban"]]
    rec_idxs = [i for i, s in enumerate(statements) if s["is_recommend"]]
    for bi in ban_idxs:
        for ri in rec_idxs:
            if bi == ri:
                continue
            shared = distinctive[bi] & distinctive[ri]
            if len(shared) < MIN_SHARED_TERMS:
                continue
            b, r = statements[bi], statements[ri]
            candidates.append({
                "class": "direct",
                "side1": f"{b['file']}:{b['line']}",
                "side2": f"{r['file']}:{r['line']}",
                "subject": ", ".join(sorted(shared)),
                "quote1": make_quote(b["text"]),
                "quote2": make_quote(r["text"]),
                "_shared_count": len(shared),
            })
    candidates.sort(key=lambda f: (-f["_shared_count"], f["side1"], f["side2"]))
    total = len(candidates)
    top = candidates[:MAX_DIRECT_FINDINGS]
    for finding in top:
        del finding["_shared_count"]
    return top, total - len(top)


def detect_drifted_paraphrases(statements: list) -> list:
    """Cross-file statement pairs with high distinctive-term overlap where
    exactly one side carries an absolute qualifier (detection 2).

    Inherits the round-3 rare-term recalibration automatically via
    compute_distinctive_terms (same function detection 1 uses) -- the
    coordinator's fix for detection 1's noise ("appears in at most 3
    statements", not "under 20%") applies here without a separate code
    path, which is what turned this detector's subjects from generic
    vocabulary ("image", "code") into genuinely rare shared terms. No
    >=2-shared-terms floor or cap is added here; the existing majority-
    overlap requirement (overlap > 0.5 of the smaller side's distinctive
    terms) was not the defect the coordinator identified for this
    detector, only the term-rarity calibration was."""
    distinctive = compute_distinctive_terms(statements)
    n = len(statements)
    findings = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = statements[i], statements[j]
            if a["file"] == b["file"]:
                continue
            terms_a, terms_b = distinctive[i], distinctive[j]
            if not terms_a or not terms_b:
                continue
            shared = terms_a & terms_b
            if not shared:
                continue
            overlap = len(shared) / min(len(terms_a), len(terms_b))
            if overlap <= OVERLAP_THRESHOLD:
                continue
            a_qual, b_qual = has_qualifier(a["text"]), has_qualifier(b["text"])
            if a_qual == b_qual:
                continue
            findings.append({
                "class": "drift",
                "side1": f"{a['file']}:{a['line']}",
                "side2": f"{b['file']}:{b['line']}",
                "subject": sorted(shared)[0],
                "quote1": make_quote(a["text"]),
                "quote2": make_quote(b["text"]),
            })
    return findings


def _gate_base_name(token: str):
    """gates/<name> -> a bare comparable name, stripping extension and a
    trailing lang/var placeholder. None if the token is itself a pattern
    description (contains "<...>") rather than a concrete reference."""
    name = token[len("gates/"):] if token.startswith("gates/") else token
    if "<" in name or ">" in name:
        return None
    for ext in (".jsonl", ".json", ".log"):
        if name.endswith(ext):
            name = name[: -len(ext)]
            break
    name = re.sub(r"-(\$[A-Za-z_]+|\{[^}]*\}|en|ja)$", "", name)
    name = name.rstrip(".,")
    return name or None


def _is_path_reference(word: str) -> bool:
    return bool(word) and "/" in word and word.endswith(_VALID_EXTS) and bool(_PATH_CHARS_RE.match(word))


def extract_path_references(sources: dict) -> list:
    """(file, line, token, quote_line) for every plain .sh/.py/.json/.md
    path reference in the scannable lines of every source.

    Works word-by-word (split on whitespace/comma/quote/backtick/parens),
    not via one monolithic regex over the raw line -- a single regex
    cannot reliably tell "one path with an internal /" from "two filenames
    joined by / in prose shorthand" (e.g. "article-ja.md/article-en.md",
    "deslop-gate.sh/eval-gate.sh"), a real false-positive class only found
    by running this against the actual source files and reading the
    output; a lookbehind-based regex fix was tried first and still let the
    regex engine start a bogus match mid-token. A word containing the
    recognised-extension pattern MORE THAN ONCE is treated as such a
    joined mention and split on "/"; each half is then re-tested on its
    own, and since neither half of a joined mention has a "/" of its own
    any more, both are correctly excluded as bare filenames (see
    _is_path_reference's "/" requirement) rather than checked as paths.

    Skips <...>-wrapped CLI placeholders ("<original.md>" documents a
    parameter shape, not a real file), bare filenames (no "/"), any word
    containing "$" -- a shell variable expansion (e.g. "$ARTICLE_RUN_DIR/
    gates/x.json") names a dynamic, per-run path, not a fixed reference
    this scanner can check for existence -- and any token that IS a
    gates/<name> artifact reference (contains "/gates/" or starts with
    "gates/"), round-4 fix: gate artifacts are per-run generated files
    that never exist as a static path under any of detect_dead_paths's
    four candidate roots, so without this exclusion the same token got
    double-extracted and re-flagged dead here even after
    detect_dead_gates correctly learned to check recent run directories
    for it -- gates/ references are detect_dead_gates's evidence rule
    exclusively, never detect_dead_paths's."""
    refs = []
    for rel_path, text in sources.items():
        for lineno, line in scannable_lines(rel_path, text):
            for raw_word in _WORD_SPLIT_RE.split(line):
                if not raw_word:
                    continue
                is_placeholder = raw_word.startswith("<") and raw_word.endswith(">")
                word = raw_word.strip("<>").rstrip(".,;:")
                if not word or is_placeholder or "$" in word:
                    continue
                candidates = word.split("/") if len(_EXT_COUNT_RE.findall(word)) > 1 else [word]
                for candidate in candidates:
                    if candidate.startswith("gates/") or "/gates/" in candidate:
                        continue
                    if _is_path_reference(candidate):
                        refs.append((rel_path, lineno, candidate, line))
    return refs


def extract_gate_references(sources: dict) -> list:
    """(file, line, token, quote_line) for every gates/<name> reference,
    one entry per first-seen distinct base name. Trailing sentence
    punctuation ("gates/foo.json.") is stripped from the raw match before
    any further processing -- left in place it defeats _gate_base_name's
    exact-suffix extension stripping."""
    seen = set()
    refs = []
    for rel_path, text in sources.items():
        for lineno, line in scannable_lines(rel_path, text):
            for match in _GATES_REF_RE.finditer(line):
                token = match.group(0).rstrip(".,")
                base = _gate_base_name(token)
                if not base or base in seen:
                    continue
                seen.add(base)
                refs.append((rel_path, lineno, token, base, line))
    return refs


# ---------------------------------------------------------------------------
# Disk access (impure) -- everything above this line is what the contract
# test drives directly with in-memory fixtures, no filesystem involved.
# ---------------------------------------------------------------------------

def load_sources(source_specs: list, skill_dir: Path) -> dict:
    sources = {}
    for spec in source_specs:
        path = skill_dir / spec
        if not path.exists():
            continue
        try:
            sources[spec] = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
    return sources


def _candidate_paths(token: str, mentioning_rel_path: str, skill_dir: Path) -> list:
    """Every root a bare relative reference is tried against before being
    declared dead.

    Round-3 fix: single-root resolution (skill_dir / token) produced a
    false positive -- note-publish/publish-paid.py is a real file, but it
    lives under scripts/note-publish/, not directly under the skill root,
    so resolving only against the skill root missed it even though the
    reference is genuinely alive. ~ and absolute (/) tokens are resolved
    directly, unaffected by this -- they are already unambiguous about
    their root and were never the source of this false positive."""
    if token.startswith("~"):
        return [Path(token).expanduser()]
    if token.startswith("/"):
        return [Path(token)]
    mentioning_dir = (skill_dir / mentioning_rel_path).parent
    repo_root = skill_dir.parent.parent
    return [
        skill_dir / token,
        skill_dir / "scripts" / token,
        mentioning_dir / token,
        repo_root / token,
    ]


def _resolves_anywhere(token: str, mentioning_rel_path: str, skill_dir: Path) -> bool:
    return any(candidate.exists() for candidate in _candidate_paths(token, mentioning_rel_path, skill_dir))


def detect_dead_paths(sources: dict, skill_dir: Path) -> list:
    """Referenced .sh/.py/.json/.md paths that resolve under NONE of the
    candidate roots (detection 3, first half; see _candidate_paths for
    why there is more than one root)."""
    seen_subjects = set()
    findings = []
    for rel_path, lineno, token, line in extract_path_references(sources):
        if token in seen_subjects:
            continue
        if _resolves_anywhere(token, rel_path, skill_dir):
            continue
        seen_subjects.add(token)
        findings.append({
            "class": "dead", "side1": f"{rel_path}:{lineno}", "side2": None,
            "subject": token, "quote1": make_quote(line), "quote2": None,
        })
    return findings


def _any_script_mentions(scripts_dir: Path, name: str) -> bool:
    if not scripts_dir.exists() or not name:
        return False
    for path in scripts_dir.rglob("*"):
        if not path.is_file() or path.suffix not in (".sh", ".py"):
            continue
        try:
            if name in path.read_text(encoding="utf-8", errors="ignore"):
                return True
        except OSError:
            continue
    return False


def _recent_run_dirs(runs_dir: Path, count: int = RECENT_RUNS_TO_CHECK) -> list:
    """The `count` most-recently-modified run directories under state/runs,
    newest first."""
    if not runs_dir.exists():
        return []
    dirs = [p for p in runs_dir.iterdir() if p.is_dir()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs[:count]


def _gates_dir_has_base(base: str, gates_dir: Path) -> bool:
    """Whether any file in one run's gates/ directory belongs to `base` --
    matched by filename STEM (extension stripped) equal to `base`, or
    starting with `base` plus "-" or "." (covers lang suffixes AND the
    attempt/terminal/revision suffixes real run artifacts carry, e.g.
    "rubric-judge-en-attempt-1.json", "rubric-judge-en.terminal.json" --
    a stricter exact-match-after-_gate_base_name check missed these real
    filenames on the first pass)."""
    if not gates_dir.is_dir():
        return False
    for entry in gates_dir.iterdir():
        if not entry.is_file():
            continue
        stem = entry.name
        for ext in (".jsonl", ".json", ".log"):
            if stem.endswith(ext):
                stem = stem[: -len(ext)]
                break
        if stem == base or stem.startswith(base + "-") or stem.startswith(base + "."):
            return True
    return False


def _gate_present_in_recent_runs(base: str, runs_dir: Path, count: int = RECENT_RUNS_TO_CHECK) -> bool:
    return any(_gates_dir_has_base(base, run_dir / "gates") for run_dir in _recent_run_dirs(runs_dir, count))


def detect_dead_gates(sources: dict, scripts_dir: Path, runs_dir: Path) -> list:
    """gates/<name>.json patterns that no script in scripts/ ever writes
    AND that do not appear in any of the RECENT_RUNS_TO_CHECK (3) most
    recent run directories under state/runs (detection 3, second half).

    Round-4 fix: "no script writes it" was incomplete on its own -- the
    daily prompt orders the MODEL to write several of these gates
    directly (STEP 0.6: "copy each gate JSON verdict there as
    gates/<gate-name>-<lang>.json"), so their absence from scripts/ proves
    nothing about whether they are actually produced. Verified against
    the real run directories: reader-questions-{ja,en}.json and
    platform-dispatch(-results).jsonl are present in the most recent runs
    (something produces them, model or otherwise) even though no script
    constructs those paths -- both were false positives under the
    script-only rule. rubric-judge-{en,ja}.json is ALSO present as of the
    latest run (daily-2026-07-26), reversing the round-3 conclusion that
    it was dead -- that conclusion was based on incomplete evidence (only
    scripts/, never the run directories), and self-improve-application
    .json is the one that is genuinely absent from every recent run, i.e.
    a true positive. "Present in a recent run" is decided the same simple
    way the coordinator's spec decided script-writing: existence, not
    static analysis of who or what produces it."""
    findings = []
    for rel_path, lineno, token, base, line in extract_gate_references(sources):
        if _any_script_mentions(scripts_dir, f"gates/{base}"):
            continue
        if _gate_present_in_recent_runs(base, runs_dir):
            continue
        findings.append({
            "class": "dead", "side1": f"{rel_path}:{lineno}", "side2": None,
            "subject": token, "quote1": make_quote(line), "quote2": None,
        })
    return findings


def scan(source_specs: list, skill_dir: Path) -> dict:
    scripts_dir = skill_dir / "scripts"
    runs_dir = skill_dir / "state" / "runs"
    sources = load_sources(source_specs, skill_dir)
    statements = extract_statements(sources)
    direct_findings, direct_suppressed = detect_direct_conflicts(statements)
    findings = []
    findings.extend(direct_findings)
    findings.extend(detect_drifted_paraphrases(statements))
    findings.extend(detect_dead_paths(sources, skill_dir))
    findings.extend(detect_dead_gates(sources, scripts_dir, runs_dir))
    return {
        "sources_scanned": sorted(sources.keys()),
        "statement_count": len(statements),
        "findings": findings,
        "direct_suppressed": direct_suppressed,
    }


def format_table(findings: list) -> str:
    if not findings:
        return "(no findings)"
    header = f"{'class':<8} {'side1':<40} {'side2':<40} subject"
    lines = [header]
    for f in findings:
        side2 = f["side2"] or "-"
        lines.append(f"{f['class']:<8} {f['side1']:<40} {side2:<40} {f['subject']}")
        lines.append(f"    quote1: {f['quote1']}")
        if f["quote2"]:
            lines.append(f"    quote2: {f['quote2']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _default_skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def cmd_scan(args: argparse.Namespace) -> int:
    skill_dir = _default_skill_dir()
    source_specs = args.sources if args.sources else list(DEFAULT_SOURCES)
    try:
        result = scan(source_specs, skill_dir)
    except Exception as exc:  # noqa: BLE001 -- a documentation scan must never block publishing
        result = {"sources_scanned": [], "statement_count": 0, "findings": [], "direct_suppressed": 0, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    if not args.json:
        print()
        print(format_table(result["findings"]))
        suppressed = result.get("direct_suppressed", 0)
        if suppressed:
            print(f"\n({suppressed} additional direct-conflict pairs suppressed past the top {MAX_DIRECT_FINDINGS})")
    return 0


def main(argv: list = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="scan the rule sources for conflicts, drift, and dead references")
    p_scan.add_argument("--sources", nargs="*", default=None, help=f"default: {' '.join(DEFAULT_SOURCES)}")
    p_scan.add_argument("--json", action="store_true", help="print only the JSON object, skip the human table")

    args = parser.parse_args(argv)
    if args.command == "scan":
        return cmd_scan(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
