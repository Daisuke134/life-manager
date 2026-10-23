#!/usr/bin/env bash
# Did the live pass actually put the domain skills in front of the model?
#
# Written because the first wiring attempt LOOKED correct and was not: step() carried the
# skills, but run_paid_work() and assess_paid_queue() compose their prompts inline and
# never enter step(), so the live PAID_WORK prompt contained zero of them. Only reading the
# prompt the model was actually handed catches that. A unit test would have passed.
set -uo pipefail

MARK='Site and browser facts this lane already paid for'
EV="${GIG_STATE_DIR:-$HOME/gig}/evidence"
newest="$(ls -td "$EV"/gig-pass-*/ 2>/dev/null | head -1)"

if [ -z "$newest" ]; then
  echo '{"status":"no_evidence_dir"}'
  exit 2
fi

shopt -s nullglob
prompts=("$newest"*.prompt.txt)
if [ ${#prompts[@]} -eq 0 ]; then
  printf '{"status":"no_prompts_yet","pass":"%s"}\n' "$(basename "$newest")"
  exit 2
fi

total=0; hit=0; detail=""
for f in "${prompts[@]}"; do
  total=$((total + 1))
  # grep -c can emit one count per file; force a single integer.
  n="$(grep -c "$MARK" "$f" 2>/dev/null | head -1 | tr -dc '0-9')"
  n="${n:-0}"
  [ "$n" -gt 0 ] && hit=$((hit + 1))
  detail="${detail}${detail:+,}{\"prompt\":\"$(basename "$f")\",\"bytes\":$(wc -c < "$f" | tr -d ' '),\"has_skills\":$([ "$n" -gt 0 ] && echo true || echo false)}"
done

printf '{"pass":"%s","prompts":%d,"with_skills":%d,"detail":[%s]}\n' \
  "$(basename "$newest")" "$total" "$hit" "$detail"

[ "$hit" -eq "$total" ] && exit 0 || exit 1
