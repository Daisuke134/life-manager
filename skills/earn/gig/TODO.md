# Gig revenue program — current execution SSOT

## Current checkpoint — 2026-09-23

This checkpoint supersedes older prose below when it conflicts with the latest
runtime/provider readback.

### Runtime checkpoint — 2026-09-24 00:24 JST

- [x] Coconala, CrowdWorks, and Lancers Paid owners are
  `scheduled`/`loaded-idle` with `last_exit=0`; no restart or duplicate provider
  effect was issued.
- [ ] CrowdWorks host-capacity `admission_effect_unknown` fence remains open.
  The durable snapshot is unchanged at `observed=5`, `effect=0`, `readback=4`,
  `failed=0`, `pending=1`; `63568785` still waits for admissible buyer material.
- [ ] Advance the working cursor to Lancers production promotion/readiness while
  preserving the CrowdWorks wait/fence. Upwork remains blocked on approved
  provider authorization, fresh authentication, and a funded contract.

### Lancers checkpoint — 2026-09-24 00:31 JST

- [x] Lancers Paid natural wake returned `observed=0`, `effect=0`,
  `readback=0`, `failed=0`, `pending=0`, `last_exit=0`; no funded contract
  exists and no external effect was attempted.
- [x] Focused Lancers Paid adapter/owner tests: `14 passed`; contract and doctor
  gates remain PASS.
- [ ] Keep production on the current immutable release until the all-platform
  main-release gate is met; then run one Lancers canary when a funded contract
  exists.
- [ ] For the first funded Lancers ContractReceipt, derive the official formal
  delivery surface from the live contract DOM/API, add a failing test first,
  implement one idempotent delivery/readback path, and verify replay-zero.

### Runtime checkpoint — 2026-09-24 00:37

- [x] Coconala and Lancers Paid loops are still `scheduled`/`loaded-idle` with
  `last_exit=0`; no restart or duplicate send was issued. Lancers has no funded
  contract, so zero effect is expected.
- [ ] CrowdWorks remains scheduled but the latest wake is blocked before child
  execution by `resource_capacity_busy` (`last_exit=75`). Its provider snapshot
  remains `observed=5/effect=0/readback=4/failed=0/pending=1`, with `63568785`
  waiting for admissible buyer material. Keep the historical unknown-effect
  fence; the exact old zero-effect marker is not enough to resolve a non-claimed
  current admission state.
- [ ] Continue with Lancers readiness and the first funded ContractReceipt;
  do not claim cross-platform completion or replay any client from this state.

### Runtime checkpoint — 2026-09-24 00:38

- [x] Coconala remains `scheduled`/`loaded-idle`/`pass` with `last_exit=0`.
- [ ] Lancers remains enabled and scheduled, but its newest wake is waiting at
  `resource_fifo_wait` (`last_exit=75`); this is a retryable shared-capacity
  wait with no provider effect, not a client failure.
- [ ] CrowdWorks returned to `scheduled`/`loaded-idle`/`pass`; retain its
  historical unknown-effect fence until a canonical resolver state is present.

### Runtime checkpoint — 2026-09-24 00:43

- [x] Ryu `18211957` remains seller-last under the durable manual-owner record;
  latest known official seller receipt is `js-talkroomMessage-222245383` and
  formal delivery is off. Live read-only probes did not mutate anything but
  returned `dm_thread_unavailable` and then `no close frame received or sent`;
  keep the existing receipt and do not resend.
- [x] Branch source gates are green: Paid boundary `265 passed`, Coconala
  adapter/readback/release/disk/cadence `62 passed`, `lm-loop-contract`, and
  `lm-loop doctor`.
- [ ] Production promotion and all-platform canary remain open; source tests
  do not count as provider completion. Continue to the next platform cursor
  without replaying any seller-last Coconala room.

### Runtime checkpoint — 2026-09-24 00:47

- [x] Reconciled CrowdWorks occurrence
  `18d7f38ac37d59b0-85238` with the exact `completed/effect=0` marker;
  canonical pre-effect resolution returned `resolved=true`, with no provider
  mutation or replay.
- [ ] Keep historical occurrence `18d62cf32eb0c678-48194` fenced: no exact
  no-effect marker or current official receipt exists. The loop remains
  scheduled; its latest wake is retryable `resource_fifo_wait` and the durable
  snapshot is `observed=5/effect=0/readback=4/failed=0/pending=1`.
- [ ] Work `63568785` still needs buyer-provided material before formal
  delivery. Do not clear the owner-wide fence or resend any completed item.

### Runtime checkpoint — 2026-09-24 00:48

- [x] CrowdWorks Paid adapter/owner/reconciliation suites: `131 passed`; no
  external mutation was performed. Four contracts retain official readback;
  `63568785` remains buyer-material wait.
- [x] Lancers Paid adapter/owner suites: `14 passed`; current natural snapshot
  is zero funded contracts and zero effect/readback. Formal delivery remains
  gated on the first real ContractReceipt.
- [ ] Production promotion and funded live canaries remain open. Tests are
  source evidence only and must not be reported as provider sends.

### Runtime checkpoint — 2026-09-24 00:50

- [x] Upwork authorization/delivery/transport/offer-gate suite: `27 passed`.
  Current live gate remains `API_INELIGIBLE` with browser/API automation
  disabled, CDP `9233` disabled, and zero funded contracts; no owner or send
  was created.
- [ ] Remaining end-state gates are explicit: Coconala production promotion;
  the one historical CrowdWorks official reconciliation; first funded Lancers
  formal-delivery canary; and approved Upwork authorization plus a funded
  contract. Keep all loops fail-closed until their provider evidence exists.

### Runtime checkpoint — 2026-09-24 00:52

- [x] Rechecked the live Paid owners without restarting them: Coconala and
  Lancers are `loaded-running`/`pass`; Lancers' authoritative inventory is
  `source_complete=true` with `contract_candidate_count=0`, so no provider
  send is admissible and no effect was fabricated.
- [x] Advanced the working cursor to Lancers. The next funded
  `ContractReceipt` must be read from its official detail surface before any
  formal-delivery mutation; the current adapter remains fail-closed until that
  surface is observed.
- [ ] CrowdWorks remains in its existing FIFO/effect-unknown fence; preserve
  the pending `63568785` buyer-material wait and do not force a wake or replay.

### Runtime checkpoint — 2026-09-24 01:02

- [x] Coconala Paid had been failing closed on `disk_headroom_low` while
  writing its evidence receipt. Five validated, non-Git temporary directories
  (no open handles) were removed without touching worktrees, provider state, or
  immutable JSONL. Available Data-volume space returned to about `980MiB`.
- [x] A targeted lifecycle restart then produced a natural Coconala result of
  `observed=4`, `effect=0`, `readback=3`, `failed=0`; Ryu remains
  `reserved_for_owner` and the other three rooms remain `awaiting_buyer`.
- [x] Lancers occurrence `18d7f457f1b9b080-94365` had an exact
  `completed/effect=0` marker. The canonical resolver released it and the
  admission readback now shows `effect_unknown=0`; no provider mutation was
  performed.
- [ ] CrowdWorks still has only the historical occurrence
  `18d62cf32eb0c678-48194` without an exact proof. Keep it fenced and do not
  clear it broadly.

### Runtime checkpoint — 2026-09-24 01:07

- [x] The shared finite-run cap temporarily blocked Paid wakes after the
  headroom fix. One `effect_class=none` maintenance owner,
  `verify-loops-audit`, was suspended only long enough to release its reserved
  slot; the Coconala Paid owner then completed a natural wake and the audit
  owner was restarted immediately afterward.
- [x] Post-retry Coconala status is `loaded-idle`/`pass`, with the authoritative
  result still `observed=4`, `effect=0`, `readback=3`, `failed=0`, and no Ryu
  or other client mutation.
- [x] CrowdWorks also completed a natural wake with
  `observed=5`, `effect=0`, `readback=4`, `pending=1`; only `63568785` remains
  buyer-material-gated. Its historical unknown occurrence remains the sole
  unresolved admission fence.
- [ ] Do not repeat the maintenance suspension unless a fresh capacity probe
  shows the same full-reservation condition; allow the scheduled Paid owners
  to wake naturally now.

### Source checkpoint — 2026-09-24 01:15

- [x] Fixed the Lancers Paid queue-starvation source: the registry now sets
  `coalesce_queued_wakes=true` and `coalesce_reserved_wakes=true`, matching the
  Coconala/CrowdWorks Paid lanes. Added a regression test and regenerated the
  launchd fixture; `154 passed, 143 subtests`, `lm-loop-contract` PASS.
- [ ] The fix is pushed on the dedicated branch at `5193ff0171`; production
  remains on its immutable main-derived release until the cross-platform gate,
  so do not report the source fix as a live provider canary yet.

### Runtime checkpoint — 2026-09-24 01:16

- [x] Re-read the live fleet: Coconala, CrowdWorks, and Lancers Paid owners are
  `scheduled`/`loaded-idle`/`pass`; no restart or provider mutation was needed.
- [x] Advanced the active cursor to Lancers' first real funded contract. The
  authenticated inventory is source-complete but currently has zero funded
  candidates, so no Lancers submission is admissible.
- [ ] When a funded Lancers `ContractReceipt` appears, read the official detail
  and completion surface, then implement/verify one quality-bound answer and
  formal-delivery effect with official readback and replay-zero. Do not guess an
  endpoint or manufacture a contract.

### Runtime checkpoint — 2026-09-24 01:26

- [x] Shared admission/release-reconciler recovery completed naturally; CrowdWorks
  and Lancers returned to `scheduled`/`loaded-idle`/`pass` without restart.
- [x] CrowdWorks readback remains `observed=5/effect=0/readback=4/failed=0/pending=1`;
  `63568785` is still buyer-material-gated and no replay was issued.
- [x] Lancers readback remains `observed=0/effect=0/readback=0/failed=0/pending=0`;
  official inventory is complete but has zero funded contracts, so the next
  mutation cursor remains the first real funded contract.

### Runtime checkpoint — 2026-09-24 01:29

- [x] Coconala owner-scoped wake completed after disk recovery with
  `observed=4/actionable=0/effect=0/readback=3/failed=0/pending=0`; no provider
  effect or duplicate send occurred. Ryu remains manual-only and the other
  three rooms are buyer-waiting.
- [x] Removed two exact temporary Git clones only after proving clean state,
  origin/main ancestry, and no open handles. Data-volume free space is about
  `1.3GiB`, and the follow-up Coconala evidence write succeeded without
  `disk_headroom_low`.
- [ ] Keep the next cursor on the first new admissible buyer event or funded
  contract; do not replay existing Coconala/CrowdWorks/Lancers work.

### Source checkpoint — 2026-09-24 01:32

- [x] Fixed CrowdWorks Paid wake accumulation in source: registry now coalesces
  queued and reserved wakes, with a regression test and regenerated launchd
  fixture. Verification: `155 passed, 143 subtests`, `lm-loop-contract PASS`.
- [ ] Promote this source fix only through the main-derived immutable release
  gate; the branch test result must not be reported as a live provider canary.

### Superseding cross-platform readback — 2026-09-24

- [x] **Ryu manual exception:** direct seller message
  `js-talkroomMessage-222245383` is officially read back; the durable owner
  record remains `mode=manual`, `owner_id=dais`, `permanent_manual_exception`.
  The latest Coconala Paid result is `observed=4`, `effect=0`,
  `readback=3`, `pending=0`; Ryu is `reserved_for_owner`,
  `send_performed=false`, and `formal_delivery_checkbox=false`.
- [x] **Coconala runtime:** `hf-gig-paid-direct` is
  `scheduled`/`loaded-idle`/`pass`; no provider effect was created by the
  natural wake. The source branch still carries the immutable Ryu fence and
  must be promoted only through the all-platform release gate.
- [x] **CrowdWorks runtime:** `crowdworks-revenue-paid` is
  `scheduled`/`loaded-idle`/`pass`; latest result is
  `observed=5`, `effect=0`, `readback=4`, `failed=0`, `pending=1`.
  Contract `63568785` is the sole pending item and remains
  `buyer_task_detail_required`; its prior answer receipt is durable and
  replay-zero. The historical unknown-effect fence remains held.
- [x] **Lancers runtime/source:** `lancers-revenue-paid` is
  `scheduled`/`loaded-idle`/`pass` with zero funded contracts. The branch
  implementation composes quality-checked answers, binds a SHA-256 quality
  digest at the provider boundary, and prevents replay; fresh verification is
  `427 passed, 17 subtests`, but production promotion and a funded canary are
  still open.
- [ ] **Upwork:** no Paid owner or live CDP. A direct Upwork credential exists
  in the private SSOT, but all current browser authorization receipts are
  denied and no funded contract is present. Do not register an automated owner
  or fabricate a send until written/approved provider authorization, fresh
  authentication, and a funded contract exist.

### Fresh natural wake and source verification — 2026-09-24 00:12 JST

- [x] Ryu `18211957` remains manual-only with official seller readback
  `js-talkroomMessage-222245383`; no duplicate or formal-delivery action.
- [x] CrowdWorks natural wake passed (`observed=5`, `effect=0`, `readback=4`,
  `pending=1`). The sole pending work `63568785` is waiting for admissible
  buyer-provided material; its existing answer receipt is replay-zero.
- [x] Lancers natural wake passed with zero funded contracts. Source verification
  passed `427 tests, 17 subtests`, `lm-loop-contract`, and `lm-loop doctor`.
- [ ] Lancers production promotion and funded canary remain open; production still
  runs the prior immutable release.
- [ ] Upwork owner readiness remains gated on an approved design, provider
  authorization, fresh authentication, and a funded contract. The current official
  help center also confirms that unapproved browser automation has no exception and
  can trigger restrictions; do not re-enable the retired UI/browser owners.

### Paid fulfillment checkpoint — 2026-09-24 03:00 JST

- [x] CrowdWorks contract `63568785` was checked through the official message
  API without sending: after buyer event `426855154`, the permission request
  exists once as seller message `428634040`. No duplicate request or formal
  delivery was sent.
- [x] The linked Google Form is readable, but it requests LINE contact and
  sensitive identity/demographic information. No external form or LINE action
  was submitted; the provider boundary keeps the job waiting instead of
  inventing a completion receipt.
- [x] Source fix added a recovery transition: once a permission-request answer
  is verified and the artifact later becomes readable, Paid composes a new
  quality-checked answer instead of treating the old permission request as the
  work product. CrowdWorks suite passes `222` and `lm-loop-contract` passes.
- [ ] Promote this source fix only through the main-derived immutable release
  gate and verify one real CrowdWorks canary; the branch test result is not a
  production receipt.

### Runtime gate correction — 2026-09-23

- [x] Reproduce and fix the stop/reservation starvation bug: `lm-loop stop` now
  suspends the queued owner after successful bootout, releasing its reservation
  without deleting occurrence history; start/restart resumes it only after
  launchd readback. Focused suites pass (124 admission, 6 lifecycle, 75 loop
  boundary tests), `git diff --check` is clean, and `./bin/lm-loop-contract`
  passes.
- [x] Apply the suspension state to the live `hf-gig-paid-direct` owner and
  verify no reservation for more than 80 seconds (`next_eligible_at=inf`).
- [ ] Promote this code through an immutable release and target-apply it; read
  back installed SHA and loaded argv before any Coconala wake.
- [ ] Keep Ryu `18211957` manual-only; run one stable-headroom Coconala natural
  wake, official four-room readback, and replay-zero. Do not resend Chii or the
  NPO `18250352` room while its evidence says buyer-waiting. `18223833` had a
  newer actionable buyer reply and was handled once manually below; do not replay
  that send.
- [ ] After Coconala closes, repair and prove CrowdWorks, Lancers, then Upwork;
  unknown-effect occurrences remain fenced and no platform is declared done
  from local artifacts alone.

- Latest official Coconala readback (2026-09-23 20:35 JST) is split by client:
  Ryu `18211957` has the manual seller message
  `js-talkroomMessage-222245383` (18:38 JST), including editable WEB予約
  wording, management preview, and management URL. Chii `18180857` remains
  buyer-waiting with no newer request. NPO `18223833` had a newer actionable
  buyer reply and now has exactly one manual progress send,
  `js-talkroomMessage-222253171`, with
  `特定非営利活動法人まくとぅー_沖縄県NPOプラザ提出書類_レビュー版_v16b.zip`
  (978,061 bytes, SHA-256
  `588f05d96b28028b2472ee7dbe7933505741e0fccf8d8cbe5dbb410d77a8f615`) and
  formal delivery OFF. NPO `18250352` remains buyer-waiting and was not resent.
  The latest Paid producer result before this manual recovery was
  `observed=4/actionable=0/effect=0/readback=2/pending=1`; it does not include
  this manually recorded effect. Do not replay `18223833` or copy Ryu's
  site-specific wording to the other rooms.

- Ryu `18211957` is the only permanent manual exception. The five newer official
  buyer events (`222215345`, `222215354`, `222218450`, `222218603`, `222218678`)
  were handled directly. The live site and management screen now show current
  campaign images, 12 registered profiles with no fixed people limit, normal
  option `写真撮影1枚〜`, the five requested paid options in order/prices, a
  preserving paid-option save/readback, and a versioned WEB予約 management
  preview without the public age gate. Public age verification remains enabled.
  The ordinary seller reply was sent once with formal delivery OFF and read back
  officially as `js-talkroomMessage-222245383` at 2026-09-23 18:38 JST;
  evidence is `projects/18211957/delivery/ryu-v697-manual-send-readback.json`.
  Ryu is now buyer-waiting; the loop remains prohibited from creating, replying,
  attaching, or formally delivering for Ryu.
- NPO `18223833` revision send: after buyer events
  `222226516`/`222226563` introduced the annual officer/member roster, the
  prepared review package v16b passed acceptance and archive checks (29 regular
  files, ASCII member names, supplied roster hash preserved). It was sent once
  through the paid-progress browser path at 2026-09-23 20:34 JST with formal
  delivery OFF. The official selected-talkroom readback at 20:35 JST observed
  seller message `js-talkroomMessage-222253171`, attachment size 978,061 bytes,
  and exact URL binding. Evidence is
  `projects/18223833/evidence/manual-npo-revision-20260923/browser-send/paid-queue-evidence.json`
  plus `official-readback-18223833-v16b.json`; the post-send contract gate is
  PASS. The same feedback/package pair is reconciled into the project ledger as
  `paid_work_browser_sent_reconciled` (`next_action=await_buyer_feedback`,
  `resend=false`); the durable receipt is
  `projects/18223833/delivery/coconala-v16b-progress-receipt.json`. This is a
  buyer-visible review/progress artifact, not formal delivery; unresolved
  business-report, audit, and officer-identity facts remain explicit.
- Coconala schedule extraction is repaired and promoted. PR `#5798` merged at
  `6b72c3044b2b590b950c1df18fc876285e2e9f7c`; immutable release
  `20260923T155015-6b72c304` is current and target-applied to
  `hf-gig-paid-direct`. Official status readback is
  `installed_release_sha=6b72c3044b2b590b950c1df18fc876285e2e9f7c`,
  `launchd_state=unloaded`, `pid=null`. The parser now accepts only official
  change/registration events, orders them by provider chronology, and carries
  event provenance into the final queue. No natural wake/provider readback or
  replay-zero proof exists for this SHA yet; do not restart Paid or send any
  additional client package.
- Chii `18180857` is complete for the required campaign and is buyer-waiting. The
  required 300 consists of 12 previously verified sends plus 288 exact-readback
  sends on 2026-09-15; the official Sheet contains 300 unique rows and the workbook
  was sent/read back in Coconala with formal delivery OFF. A stale intermediate
  `delivery/paid-remote-result.json` reported 20/300 and must not reopen the item.
- Before the answered-feedback stop fix reached production, the direct ledger also
  recorded 24 extra sends on 2026-09-22. Preserve those immutable effects as an
  incident; do not resend, undo, or count them as remaining work. The latest queue
  readback is `awaiting_buyer` with `effect=0`, and no Chii ledger row exists after
  the fix. The latest official inbox readback supports 0 eligible positive replies
  and 1 ineligible reply.
- One-by-one Coconala readback at `2026-09-23T03:10:08Z` shows the final
  300-row audit report as the latest seller message and
  `buyer_feedback_answered_by_seller=true`; formal delivery remains OFF. The
  standalone semantic-decision command still sees an older 20/300 remote
  contract because it skips fresh queue readback. The real Paid queue has the
  answered-feedback guard and must return `awaiting_buyer`, `effect=0`,
  `deduplicated=true`; do not resend Chii from the standalone result.
- The latest natural `hf-gig-paid-direct` wake (targeted readback through
  `2026-09-23T01:07:47+00:00`) completed with
  `status=completed`, `effect=0`, `readback=3`, `failed=0`, and `pending=0`.
  It independently reconfirmed Ryu as `reserved_for_owner` and Chii plus both NPO
  rooms as `awaiting_buyer`; no client DM was sent. A later readback found the
  owner stuck on one PID while repeating `control_busy` and disk-write failures;
  the canonical `lm-loop stop hf-gig-paid-direct` path now reports
  `launchd_state=unloaded`, `pid=null`. Chii is not the current work cursor and
  no manual Chii action is needed.
- A prior NPO wake failed closed on a one-character model hash typo even though
  the semantic decision was `await_buyer`; `effect=0` proves no external send.
  Code commit `7244c3e856` now binds each outcome to the exact official message
  ID and canonical provider hash. The next wake accepted the decision as
  `awaiting_buyer`, so this fix is verified locally and by natural readback.
  It is included in main and in the installed `6b72c304` release; only the
  post-apply natural-wake/provider-readback gate remains.
- Shared admission root cause is now narrowed to owner-wide `effect_unknown` fences
  on CrowdWorks/Lancers revenue owners plus host capacity pressure. Commit
  `11dcf8c6f3` adds an explicit `admission_effect_scope` registry field and enables
  occurrence isolation only for item-kernel lanes (CrowdWorks Application/Paid/Reply;
  Lancers Application/Negotiate/Paid). It preserves the old unknown rows and keeps
  Report/Storefront/Telegram owner-scoped. The implementation is merged in main
  and included in the installed `6b72c304` release; the old unknown rows remain
  fenced and no production state was cleared. Follow-up commit `9df3731ccb`
  adds queue/reservation wake coalescing for Coconala Paid so repeated safe no-op
  wakes do not build an unbounded owner queue. The follow-up identity-binding
  fix is `7244c3e856`; both are in the same installed release.
- The coalescing branch now includes the matching admission expectation test at
  `e012343e94`. Focused runtime tests pass `528` with `174` subtests, the loop
  contract gate passes, and the resulting code is merged in main and included in
  installed release `20260923T155015-6b72c304`. No natural wake, provider
  readback, or replay-zero proof exists for this installed SHA yet.
- The follow-up lifecycle fix `470c7b3160` makes `paid_direct.py` re-raise a
  received stop signal after terminating active child groups, so a Paid parent
  cannot survive bootout and retain `.paid-direct.lock`. Its regression and
  related loop tests pass (`263` paid-remote-wait, `70` loop-boundary); it is
  merged in main and included in installed release `20260923T155015-6b72c304`.
- The targeted status-read fix `313915e0a5` makes `_last_event()` stop at the
  newest requested loop report instead of scanning all older shared-state rows.
  Follow-up `2d2417bd5b` covers targeted cache results across shared state roots;
  runtime tests pass `517`, the loop contract and adapter tests pass, and
  `lm-loop doctor` is clean. These fixes are included in installed release
  `20260923T155015-6b72c304` and target-applied to the Paid owner. The owner
  remains unloaded and no new natural wake/readback has run.
- Read-only host verification at `2026-09-23T03:57:38Z` found 2.9 GiB free,
  no Paid parent/child process, and a 0.18-second targeted status response.
  `admission_effect_unknown=true` remains fenced; do not clear it or restart
  production from this observation alone.
- A later read-only CrowdWorks check at `2026-09-23T07:24:24Z` found
  `crowdworks-revenue-paid` running PID `10759` on the older `f01c612d` release.
  Its current occurrence `18d7e1fd55967df8-10759` has host admission
  `resource_slot_acquired`, entrypoint `pre_effect_failure`, and `effect=0`;
  `paid-latest.json` still reports four completed contracts and
  `63568785=pending`. The owner logs repeat `No space left on device`,
  `database is locked`, and `control_busy`. No official provider effect or
  receipt was claimed, but the owner-wide unknown fence remains. Do not kill,
  clear, or replay this occurrence without an exact official readback and the
  required high-risk stop approval.
- CrowdWorks provider-lock detail readback at `2026-09-23T04:00:55.856173Z`
  confirmed five funded contracts. Source preflight decisions were
  `63712784=submit`, `63659463=formal_delivery_after_forms`,
  `63657015=submit`, `63570481=revision_submit`, and
  `63568785=wait_for_buyer_artifact`; at that observation point no provider
  effect or receipt had occurred yet.
- One-by-one manual canary `63712784` was then completed on 2026-09-23 under the
  CrowdWorks provider lock: the common test and Web Ads forms returned official
  `回答を記録しました` confirmations at `04:39:36Z` and `04:39:41Z`, followed by
  one formal delivery for milestone `13833587`. Official readback at
  `04:45:32Z` verified the exact seller message, `納品=done`, `検収=current`, and
  `provider_state=delivered`; no duplicate form POST or delivery occurred.
  This manual contract effect is separate from the unresolved Paid occurrence
  `18d62cf32eb0c678-48194`, which remains `claimed/effect_unknown=1` and fenced.
  Source commit `5876390fe6` fixes the hydration/hidden-disabled-form readback
  race; 611 focused tests pass, but production Paid remains unloaded.
- Cursor reorder at `2026-09-23T04:45:32Z`: old order was host/lifecycle gate →
  Paid-loop promotion → CrowdWorks canary; new order is the same system gates,
  with the contract-bound `63712784` canary completed manually before them because
  its official deadline was the current day. The unresolved Paid occurrence was
  not cleared or replayed. Current cursor remains host/lifecycle gate, then
  occurrence reconciliation and immutable loop promotion.
- The next one-by-one contract `63659463` was completed at `2026-09-23T04:50:38Z`:
  its existing official receipts for the common test and Web Ads forms were
  re-read, the video form was explicitly excluded per the buyer instruction,
  and milestone `13820867` was delivered once. Official readback returned
  `provider_receipt_id=contract:63659463:milestone:13820867` and the contract
  context is now `provider_state=delivered`/client inspection. No form was
  reposted and the Paid unknown occurrence remains fenced.
- The next one-by-one contract `63657015` was completed at `2026-09-23T05:13:08Z`:
  the non-designer hearing sheet was attached once (official message `428631900`,
  attachment `59259436`), the common test returned an official Google confirmation
  bound to buyer event `427403807`, and milestone `13820268` was delivered once.
  Formal-delivery readback returned
  `provider_receipt_id=contract:63657015:milestone:13820268`; a fresh context read
  returned `provider_state=delivered` with seller message `428632173`. The anonymous
  survey and designer-only test were explicitly excluded. No form, attachment, or
  delivery was replayed; the unresolved Paid occurrence remains fenced.
- The next one-by-one contract `63570481` was corrected and completed at
  `2026-09-23T05:24:53Z`: buyer correction event `427573234` was bound to one
  revised Google Form receipt (`confirmation_sha256=168b142a4781d25be8f7807a780239d1e4eb269c03ded584c199a0cd3f163a57`),
  and milestone `13798056` was formally delivered once. Readback returned
  `provider_receipt_id=contract:63570481:milestone:13798056`; a fresh context read
  returned `provider_state=delivered` with seller message `428633469`. The original
  form receipt was retained and not replayed; the unresolved Paid occurrence remains
  fenced. Source fix `471f3c6a97` retains durable form history when CrowdWorks hides
  a submitted form link; CrowdWorks tests passed `116`.
- `63568785` remains `funded` at milestone `13797948` with buyer event
  `426855154`. Its linked Google Doc exposes an official permission-request
  surface, so one permission request was sent and verified as seller message
  `428634040` / `contract:63568785:answer:cw-63568785-permission-426855154`.
  No artifact or formal delivery was claimed; wait for access or pasted content
  before doing work. Source fix `f8a57184c5` polls delayed document-access surfaces
  and uses the official message API when seller threads are folded; CrowdWorks
  tests passed `118`.
- Lancers official read-only inventory at `2026-09-23T04:05:08Z` was
  authenticated/source-complete with 14 boards, one unread, zero working or
  monthly contracts, zero incoming offers, zero storefront contract candidates,
  and 0 JPY balance. No Lancers Paid client is currently eligible; the Paid
  mutation path remains unimplemented for future funded work.
- Final status readback at `2026-09-23T04:28:10Z` kept CrowdWorks and Lancers
  `loaded-idle` with `pid=null`, terminal `blocked`, and
  `host_admission_deferred:resource_effect_unknown`; the exact unresolved rows
  remain `crowdworks-revenue-paid:18d62cf32eb0c678-48194` and
  `lancers-revenue-paid:18d67a28e56c4b58-6829`. Coconala
  `hf-gig-paid-direct` remains `unloaded` with `pid=null`. No unknown effect
  was cleared and no provider receipt was created.
- A shared-host incident is also open: the Paid owner recorded `No space left on
  device` while writing its result, followed by `control_busy`/database-lock
  symptoms. Headroom later recovered to about 1.27 GiB (above the 512 MiB floor),
  while the disk-cleanup owner still reclaimed `0` bytes because all four
  candidates were open. The canonical stop unloaded Paid (`pid=null`), but its
  bootout left owner-scoped children from interrupted room `18223833`; those
  children and their lock were terminated only within the Paid owner scope.
  Official readback then showed no new seller message or formal delivery. The
  owner remains intentionally unloaded until child reaping, durable-write, and
  natural-wake gates pass. Do not delete protected releases, provider state, or
  unknown-effect rows by hand.
- One-by-one direct check of room `18223833` regenerated the canonical semantic
  decision and remains `await_buyer` with `effect=0`, `readback=1`. Four buyer
  facts are still missing (第3期実績、社員名簿不足分、総会・理事会、監査情報).
  The 2026–2028 ちむどんどん budget artifact is locally accepted, but it does
  not satisfy the separate NPO package contract; never bypass this decision or
  send a partial package as complete. Evidence:
  `paid-direct/items/item-18223833-decision-repair.json` and
  `official-readback-18223833-after-stop.json`.
- New official buyer events `js-talkroomMessage-222226516` and
  `js-talkroomMessage-222226563` changed room `18223833`: ① the current
  ちむどんどん budget is accepted, ② the buyer supplied
  `MKT年度別役員・会員.xlsx` and requested the まくとぅー deadline be extended
  to the end of September. The seller changed the schedule to 2026-09-30;
  provider system receipt `js-talkroomMessage-222233402` confirms it. A single
  seller acknowledgement was sent and read back with message SHA
  `25f79a480d4109fd731691e4e4d7a5afb98c35c4021e39a9f29b3946567a0ac7`.
  Formal delivery remains OFF. Next action is to wait for the promised source
  materials, then reconcile the four missing fact groups before building the
  final NPO package. Do not mark the combined order complete from the accepted
  ① budget alone.
- Google Docs rule: use authenticated `gog drive get` plus
  `gog drive download --format=txt` (or an authenticated connector/plugin) before
  any browser Docs path. Do not request browser permission when the CLI already
  has Drive scope; use browser only when CLI/connector readback fails.
- The 18223833 stale first-match schedule gap is closed. The parser selects the
  latest official change/registration event by provider message chronology,
  ignores non-event body labels, and updates an existing order only when the
  date came from an official event. Regression coverage includes the observed
  2026-09-18 and 2026-09-30 events plus the quoted registration form. The fix is
  merged/released/applied as recorded in the current checkpoint above; only the
  natural-wake/provider-readback gate remains.
- One-by-one official readback of room `18250352` at `2026-09-23T03:09:04Z`
  confirms the v15 review package is already visible, formal delivery is OFF,
  and no buyer reply followed it. Its actionable file decision still awaits
  three facts (河原氏の正式氏名、追加/退任役員の発効日・本人情報、R6/R7事業報告).
  The latest seller message already asks for these facts; do not replay the same
  package. Evidence: `official-readback-18250352-one-by-one.json`.
- Cursor reorder: the old order began with host recovery → Coconala loop promotion
  → CrowdWorks. The new order began with the newly observed Ryu manual revision
  (now complete), then host recovery → Coconala loop promotion → CrowdWorks →
  Lancers → Upwork.
  Reason: the official provider readback created a genuinely newer Ryu event;
  client safety takes precedence over system-only work. Chii remains closed and
  is not reopened by this change.

## Remaining work — outcome order

1. **Close the host/lifecycle gate.** The repaired release is installed but the
   Paid owner remains intentionally unloaded. Host headroom is near the floor and
   admission contention (`control_busy`) remains observable while another owner
   is active. Prove a small production state write, owner-child reaping, and a
   natural Coconala no-op wake. Keep all protected releases and provider ledgers
   intact; do not clear unknown-effect fences or restart Paid before this gate.
2. **Prove the promoted queued-wake safety fix.** The full loop/host acceptance
   set for `e012343e94` (occurrence-scoped marketplace admission plus Coconala
   Paid queued and reserved wake coalescing) is merged, released, and applied in
   `20260923T155015-6b72c304`. After item 1, verify one natural Coconala wake
   with official readback and replay-zero. Do not edit the admission database by
   hand or clear old unknown rows.
3. **CrowdWorks occurrence fences and loop promotion.** The manually completed
   contracts `63712784`, `63659463`, and `63657015` are not proof for the unresolved
   Paid occurrence. Reconcile each existing `effect_unknown` occurrence against
   provider inventory and durable child/effect receipts, keep every uncertain effect
   fenced, then prove a natural canary/replay-zero without replaying `63712784`.
   The gog-first adapter fix is already merged in PR `#5796`, cut as immutable
   release `20260923T150246-b939af53`, and target-applied to
   `crowdworks-revenue-paid`; the old unknown-effect fence remains and no natural
   wake has been triggered.
4. **CrowdWorks remaining funded contract.** `63568785` is now readable through
   `gog drive get`/`gog drive download --format=txt`; the prior permission request
   remains verified and was not replayed. A single buyer clarification requesting
   the five LINE/Note materials or their text is verified as seller message
   `428636540` (`contract:63568785:answer:cw-63568785-line-artifact-426855154-v1`).
   Continue only after those materials or an accessible LINE session arrive; then
   complete all five forms, verify correct work, submit formal delivery, and read
   back inspection/acceptance/settlement/payout with replay-zero. Do not claim the
   contract complete from the Google Doc read alone. The delivered rows `63712784`,
   `63659463`, `63657015`, and `63570481` still need acceptance/settlement/payout
   readback.
5. **Lancers.** Keep the current browser/work-sync owners running; implement the
   missing Paid provider mutation/readback (`lancers_paid_effect_not_implemented`),
   prove one canary, then complete the funded inventory and payout receipts.
6. **Upwork.** Register a Paid owner, obtain a live authenticated contract
   inventory, and close the same official delivery/payment/replay-zero gates. Do not
   count historical adapters as live revenue proof.
7. **Fleet gate.** Run the cross-platform no-starvation, crash recovery, browser
   lease, 24-hour cadence, revision, settlement and duplicate-zero checks. Only then
   promote the full release; Chii and Ryu are not blockers for this system work.

This file contains only current truth and remaining work. Completed incident detail is preserved in Git
history through commit `e2b30b8e10`; it must not be copied back into the active TODO. Evidence lives in
durable runtime ledgers and receipts, not in duplicated historical checklists.

## Account 1 restart cursor

This is the only restart cursor for the next Codex session. Re-check every value against Git and official
runtime/provider readback before acting; conversation claims are not completion evidence.

- Canonical local repository checkout: `$LIFE_MANAGER_REPO`, remote
  `Daisuke134/life-manager`. The folder name on this Mac is **`life-manager-main`**. No separate project or
  repository named `life-manager/` was created.
- Current task worktree: `<task-worktree>`, branch
  `docs/coconala-paid-apply-proof-20260916`, lease
  `ac1f02d45387233d8866ce7dbd62c01a5b1a28987c9e2614a873535c1d766f69`. This is a linked Git worktree of
  the same `life-manager-main` repository, not another project. The main checkout is currently on the unrelated
  Capify branch `capafy/account-plan-deck-offline-20260912`, so it remains read-only for this workstream.
- Canonical runtime source is `origin/main` at `0401cb6a34e89b32c5c1a7e637df0062b791e13c`. The newest
  immutable release is `$LIFE_MANAGER_RELEASES/20260916T165426-0401cb6a`; Apply is exact-loaded from it.
  Paid is exact-loaded from `2e0716c7`. PR `#5283` normalizes structured independent verifier evidence without
  weakening identity validation. PR `#5284` keeps older effect-started uncertain applications duplicate-fenced
  for background reconciliation instead of repeatedly deep-scanning them in the revenue foreground.
  PR `#5281` requires the owner to read the official buyer message before treating a redacted value as missing.
  PR `#5279` adds model-owned
  `required_outcomes` and deterministic owner/verifier `outcome_coverage`, so every current buyer outcome needs
  official effect/readback evidence before Coconala send. PR `#5276` makes each
  Apply refresh collect both `single:new` and `retainer:new`; PR `#5274` fills mandatory retainer screening
  answers through the existing shared application lifecycle; PR `#5275` moves the repeated full-history scan
  out of the foreground wake. PR `#5258` adds the
  official seller-last attachment wait reducer; PRs `#5252` and `#5254`
  add the revenue floor, legacy-reservation migration fence and Paid Account 1→2 Codex route; `#5250`
  browser/child-cleanup remains an ancestor. Reply and Storefront retain `0aba1191`.
  A natural Reply wake passed and a bounded Paid decision
  selected `codex/acct1/gpt-5.6-terra`.
  Do not create another runtime worktree or use the Capify checkout as source.
- Phase 2 replaces the v2 JSON scan with stdlib SQLite, adds durable FIFO reservations, child-PID claim
  handoff, same-owner/crash recovery, exact loaded-idle dispatch, retired/missing-owner cancellation, a
  default-v1 mixed-release gate and `lm-loop admission-v2-enable`. Final evidence is 500 sequential enqueues in
  1.872 seconds, 39/39 simultaneous enqueues persisted, 69 host tests, 464 loop tests plus 470 subtests, 67
  registry tests plus 100 subtests, exact stdlib CI discovery 434 tests, fresh read-only `ship`, and GitHub CI
  8/8 PASS. Earlier JSON 500-enqueue evidence was 35.93 seconds.
- Current spec file in this worktree:
  `<task-worktree>/skills/earn/gig/TODO.md`. Its repository-relative
  canonical path is `skills/earn/gig/TODO.md`; after merge the same file is available under
  `skills/earn/gig/TODO.md`. Do not create a second live TODO.
- Coconala is not complete. Ryu's latest three-message buyer cycle was completed with one ordinary Coconala
  seller message, formal delivery OFF and official talkroom readback. The next natural Paid wake observed all
  four active rooms with `effect=0`, `readback=4`, `failed=0`; Ryu was `deduplicated=true`. The earlier orphaned
  browser lease was released manually, so automatic orphan-lease recovery remains a separate shared-runtime
  acceptance gap. Chii's direct execution ledger contains
  288 exact-readback sends,
  the previously verified ledger contains 12, and the official Sheet contains 300 unique rows. The 300-row
  workbook was sent to Coconala with formal delivery OFF and read back in talkroom `18180857`. Chii is now
  buyer-waiting and no existing recipient or completion message may be resent. The pre-batch `12/288` file is
  superseded historical state, not another client-work project.
- Paid now tries the existing Account 1 Codex profile first and falls back to Account 2 through the shared
  runner; the first bounded Account 1 receipt is proved. Preserve both accounts and all unrelated sessions.
- First safe action: let the `0401cb6a` Apply owner finish and prove replay-zero for its four new official
  effects on the next natural wake. Continue both `single:new` and `retainer:new`; the latter had zero active
  cards in the last authenticated observation, so a screening-answer effect cannot yet be claimed. Then resume
  shared admission/cadence and owner-scoped browser teardown, including natural orphan-lease recovery. A natural
  earlier `6e1dcc42` wake observed both
  `single:new` and `retainer:new` in one snapshot, found the current retainer page empty, and completed six
  eligible one-off applications with six official applied-list readbacks, zero failures and zero pending.
  The prior ULID retainer attempt remains duplicate-fenced; retry it only if a fresh official listing makes it
  active and the old no-click evidence reconciles safely.
  The durable full-history cursor is page 29 after 28 pages, 527 cards and 14 hash-bound chunks, with all 54
  uncertain intents unchanged. Paid's current four-client set is closed by a natural
  `172d3f2e` replay-zero pass. Admission protocol `2` is live and one four-lane overlap is proved, but the
  24-hour/seven-day fairness and no-starvation gates remain open.

## Outcome

Life Manager autonomously earns attributable revenue across Coconala, Lancers, CrowdWorks, Mercor,
Freelancer.com, Upwork and newly discovered platforms. Every supported lifecycle runs 24/7 without Dais or
Codex babysitting, shares one runtime and marketplace kernel, resumes from durable state, verifies official
effects, prevents duplicates, heals failures and improves itself. The first measured revenue gate is USD
10K MRR; applications, health checks and projected value do not count as revenue.

## Gig-platform As-Is / To-Be

This table is the compact platform truth. “Registered” means a loop exists in the registry; it does not mean
that the provider currently has an authenticated account, a verified external effect, or attributable revenue.

| Platform | As-Is now | To-Be finish condition |
|---|---|---|
| Coconala | Apply is exact-loaded from `0401cb6a`; Reply and Storefront retain `0aba1191`; Paid is exact-loaded from `2e0716c7`. Ryu's latest ordinary message is officially read back and a natural Paid wake replayed zero across four rooms. Apply's current `0401cb6a` run observed both one-off and continuous sources; four eligible one-off applications have official exact-ID readbacks, zero failures, while old uncertain intents stayed duplicate-fenced for background reconciliation. The continuous page had zero active cards. Reply's latest retained pass observed 179 threads with 164 official readbacks and 15 pending. Static five-finite-run capacity, only two durable revenue-priority owners, and manual orphan-lease recovery leave 24/7 no-starvation/self-heal unproved. | Every active client has its own durable work item, newest-buyer coverage, provider effect/readback, replay-zero and payout attribution; every lane meets its cadence without a fixed global-slot bottleneck, and one client's failure never pauses another lane. |
| Lancers | Application, browser, negotiation, paid, storefront, work-sync and report owners are registered. Production fixes exist in main, but durable login and the full Apply→Paid→payout proof are not closed. | One persistent account/browser owner runs the complete lifecycle with official proposal, work, payment and payout receipts. |
| CrowdWorks | Application, Reply, Paid and Report owners are registered. Reply is proposal-only after the contract-ID handoff; Paid owns post-contract work and effects. The latest Paid owner run is admission-blocked before child execution with zero provider effect/readback. A fresh read-only provider inventory returns five exact funded contracts; historical delivery receipts remain replay-fenced until current milestone state is read back. | Apply owns proposals; Reply owns pre-contract negotiation/acceptance; one Paid owner owns all post-contract replies, work, quality, external submit, formal delivery and revision for each contract ID. Report remains internal. Each item reaches exact official receipt, acceptance, payout and replay-zero; Storefront is `not_applicable` unless officially observed. |
| Mercor | Application, Reply and Paid owners are registered, but repeated-login/authentication and full contract proof remain open. | Persistent authenticated account state, application, reply/interview handoff, contract, paid work and payout are independently evidenced. |
| Freelancer.com | Runtime work is registered in the fleet, but current provider account/policy and end-to-end revenue proof are not closed. | Official account/policy state plus Apply→Reply→Paid→payout, with Storefront only if officially supported. |
| Upwork | Browser/application/report infrastructure and historical evidence exist, but current account/policy and paid attribution are not a closed revenue loop. | Official proposal, reply, contract, delivery/payment and payout receipts with duplicate-zero replay. |
| Writer / other gig surfaces | Writer owners and shared publication/payment ledgers exist; each provider still needs current authenticated opportunity, submission and payment proof. | The same shared observe→decide→act→verify→persist loop drives every provider; only thin provider adapters differ. |
| New platforms | Discovery and adapter-generation owners exist, but no platform is promoted merely because it was found. | A new provider is promoted only after policy qualification, thin shared-contract adapter, canary, official effect/readback, replay-zero and positive unit economics. |

### Two finish-line differences

1. **External work versus canonical truth:** Chii's external workbook message is sent and buyer-waiting; its
   old `12/288` file is historical evidence only. Ryu's verified live-site result and later Coconala seller
   message are now bound by an exact official readback and replay fence.
2. **One client versus the fleet:** Coconala's Chii send is one client-level milestone. The program is finished
   only when every applicable platform/client independently passes the same effect, readback, replay-zero,
   payout and long-run self-healing gates. They run concurrently; the completion criteria are not collapsed into
   one serial queue.

## Non-negotiable contracts

- Scheduler registration and a PID are not health. Every wake ends with a bounded terminal receipt.
- Each client is an independent work item. Clients, lanes and platforms run concurrently.
- Every external mutation uses prepare -> effect fence -> official readback -> terminal receipt -> replay-zero.
- Uncertain effects are reconciled officially before retry. Never guess and never duplicate.
- Buyer conversation, files, requirements and decisions are cumulative durable context.
- Shared runtime, browser leasing, Telegram, Calendar, receipts, evals and marketplace lifecycle are reused.
  Providers implement only thin official-surface adapters.
- KYC, interviews and person-bound media may use typed minimal-human Telegram handoffs. Everything else is
  autonomous. Meetings are added to Google Calendar with the join URL and a five-minute reminder.
- Never fake applications, messages, delivery, spreadsheets, revenue or readback.
- Do not apply for work whose required numerical outcome cannot be delivered within the paid scope. Prefer
  concrete artifacts and services whose completion is controllable.
- A historical seller message is never proof that a talkroom is currently handled. Completion requires the
  newest official buyer event to be covered by a later seller effect and official readback. If durable
  `next_action` conflicts with a newer buyer-event digest, the buyer event wins and the item returns to work.
- Chii is buyer-waiting after the official room read back the 300-row workbook. Never invent recipients,
  sends or spreadsheet rows, and never replay an existing recipient or completion message.

### Evidence correction for the earlier “300 complete” report

The earlier report mixed two different snapshots: the canonical Paid result still said `12/300` while a later
manual owner run wrote 288 `sent` rows with per-recipient official TikTok readback to
    `$LIFE_MANAGER_GIG_ROOT/projects/18180857/delivery/tiktok-message-effects.jsonl`. Together with the prior 12
verified effects, the execution evidence supports 300 total sends; the official Sheet readback contains 300
unique rows. The ordinary Coconala message and workbook were then sent and read back in
    `$LIFE_MANAGER_GIG_ROOT/projects/18180857/evidence/paid-direct-live/paid-direct/18180857/answer/chii-300-send/`,
with `formal_delivery_control_checked=false`. The older `12/288` files remain historical input, not permission
to reopen work. The official later seller message and existing effect fences make the next action buyer-waiting
and replay-zero. Never resend an existing recipient or completion message.

## Shared architecture

The real repository folder is `$LIFE_MANAGER_REPO`. The tree below is a
**repository-relative To-Be ownership map**, not a new `life-manager/` folder and not a second project. The
current task worktree exposes the same relative paths under
  `<task-worktree>`.

```text
config/
runtime/
  scheduler/ admission/ queue/ workers/ effects/ browser/
  receipts/ observability/ self_healing/ self_improvement/
domains/
  marketplace/{apply,reply,paid,storefront}/
providers/
  {coconala,lancers,crowdworks,mercor,freelancer,upwork}/
loops/
  {revenue,platform_discovery,loop_builder,self_heal,self_improve}/
evals/
  {conformance,replay,fault_injection,revenue}/
skills/
docs/
```

## Fundamental scalability repair

### 1. Overview — what failed and why temporary fixes did not hold

The intended Loop Engineering contract is still authoritative: platforms and the four marketplace lanes
remain independent owners; each lane advances independent applications, talkrooms, listings or orders with
bounded workers; only the same exact provider resource/effect is serialized. Shared runtime owns resource
accounting, model routing, browser leases, receipts and recovery, but it must not become a business queue that
allows one lane or maintenance owner to pause an unrelated lane.

The current failure is architectural, not one Coconala selector bug. The fleet first allowed too many heavy
wakes to run concurrently and exhausted CPU, memory, browser and disk resources. The response added one global
finite admission ceiling. That protected the host from unbounded fan-out, but it also allowed unrelated
maintenance owners to consume every slot. Revenue wakes then terminated safely before provider code, so the
system changed from "work until the host crashes" to "do no work while reporting bounded deferrals." Later
release/reconciler fixes improved individual boundaries but did not restore the primary invariant: every funded
client and active buyer thread must keep making durable progress while unrelated work continues.

Observed evidence for this failure class:

| Boundary | Current evidence | Why it prevents revenue |
|---|---|---|
| Fleet | 165 registered loops; host load remained about 192--222 with more than 100 runnable and zombie processes in observed snapshots | Many cadence-aligned Python/browser wakes compete before useful work begins |
| Host | macOS displayed application-memory exhaustion; ChatGPT and multiple Chromium processes consumed multi-gigabyte memory; disk reached 99%. Fresh owner-level RSS showed TikTok Chromium about 2.6 GiB, daily-driver about 1.8 GiB and gig-daily-driver about 0.6 GiB. CrowdWorks had two Chromium roots for the same profile/port `9228`, only one listener, and `/json/version` timed out. Three two-day-old orphaned Capafy Google Chrome headless process groups were terminated owner-scoped while their profiles were preserved. | Startup, browser and memory probes stall or time out; duplicated or orphaned browser owners retain memory after their useful work ends |
| Permission | A Python 3.14 cross-application data-access prompt was visible | A runtime child may wait for an unresolved TCC decision instead of producing a receipt |
| Admission | Protocol `1`, total finite capacity `3`; observed slots were owned by non-Coconala maintenance/work owners while Coconala repeatedly returned `resource_control_busy`, `resource_capacity_busy` or `memory_headroom_unavailable` | A global safety primitive became a cross-lane wait and violated outer parallelism |
| Release | Current is `b8cff053`; all four Coconala lanes remained installed from `3fbe7554`; the current reconciler had a running receipt but no terminal result | Safety fixes exist in main but have not reached the revenue owners |
| Paid | Latest provider-level summary failed at `orders_observation` with `observed=0`, `effect=0`, `readback=0`, `failed=1`; later wakes stopped at admission | Paid has no current order inventory or buyer-visible progress |
| Inner parallelism | Paid implementation still states one order per pass because evidence paths are lane-global, while the Paid recipe requires project-scoped concurrent orders | One client can monopolize or block the lane; evidence cannot safely coexist |
| Retained context | A Coconala room received a review ZIP acknowledging 15 attachments and was later asked to upload the same attachments again | Durable attachment references and verified bytes were not carried into the next decision |
| Contract execution | A CrowdWorks buyer supplied a work link after contract acceptance while the reply/upload form remained empty | Contract acquisition did not create a durable fulfillment work item that reached submit/readback |

### 2. As-Is / To-Be

```mermaid
flowchart LR
  subgraph ASIS[AS-IS: safe starvation]
    A[165 cadence wakes] --> H[Shared host pressure]
    H --> G[One global 3-slot admission]
    M[Maintenance and reporting] --> G
    G -->|busy| AP[Apply exits 75]
    G -->|busy| RP[Reply exits 75]
    G -->|busy| PD[Paid exits 75]
    G -->|busy| SF[Storefront exits 75]
    PD --> O[No orders observation\nNo client worker\nNo official effect]
  end
```

```mermaid
flowchart TD
  subgraph TOBE[TO-BE: independent lanes, bounded item concurrency]
    L[launchd on-demand wakes] --> AP2[Apply owner]
    L --> RP2[Reply owner]
    L --> PD2[Paid owner]
    L --> SF2[Storefront owner]

    C[Shared host capacity broker] --> AP2
    C --> RP2
    C --> PD2
    C --> SF2
    C --> MM[Maintenance uses borrowable capacity only]

    PD2 --> Q[Per-order durable queue]
    Q --> C1[Client A project worker]
    Q --> C2[Client B project worker]
    Q --> CN[Client N project worker]

    C1 --> B[Paid-owned authenticated BrowserContext]
    C2 --> B
    CN --> B
    B --> F[Same-resource effect fence]
    F --> E[Provider mutation]
    E --> R[Same-session official readback]
    R --> T[Project terminal receipt + replay-zero]
  end
```

TO-BE preserves the existing independent launchd owners. It does not add a fifth business scheduler or one
global marketplace queue. The shared host broker performs resource accounting only. Every revenue lane owns a
non-stealable minimum budget; maintenance may borrow unused capacity but is preemptible and may never consume a
funded-client guarantee. Within a lane, workqueue fairness, per-item backoff and project-scoped claims bound
physical concurrency without destroying logical concurrency.

Every client/order owns its own state, run namespace, attachment registry, artifact, effect intent, lease,
heartbeat, terminal receipt and official readback. Artifact building, reasoning and reconciliation may proceed
concurrently. Only the short authenticated mutation against the same provider resource is serialized. A browser
lease may delay that mutation without changing an unrelated client to failed or blocking its non-browser work.

launchd remains an on-demand alarm. Every wake performs one bounded durable transition and exits. Long waits are
persisted as `next_eligible_at`; they do not retain a Python process, browser tab, admission slot or Telegram
send. Runtime health uses process identity plus heartbeat plus durable progress, never PID existence alone.

### 3. Non-negotiable architecture and ownership contracts

1. `runtime/loop` MUST remain the only lifecycle, admission, retry, receipt and recovery implementation.
2. Each platform/lane MUST keep an independent owner, state root, BrowserContext and lease identity. No sibling
   lane may wait for or restart another lane.
3. Host admission MUST enforce a measured hard ceiling and independent reserved minimums. Maintenance,
   reporting, Telegram, cleanup and discovery MUST be borrow-only and preemptible.
4. Every work item MUST remain visible when deferred. Capacity may change `next_eligible_at`; it MUST NOT drop
   the item, hide it from aggregates or turn it into a successful no-op.
5. Paid MUST use project-scoped claims and bounded concurrent workers. Lane-global evidence files and a
   lane-wide order lock MUST NOT define the unit of work.
6. Retained official attachment references and verified bytes MUST be cumulative. Missing local bytes trigger
   internal official recovery; the buyer MUST NOT be asked again for an attachment already received.
7. Browser memory MUST be owner-accounted. Context/tab cleanup is owner-scoped; no global Chromium, GUI,
   WindowServer, loginwindow or host restart is a valid recovery action.
8. A memory probe timeout MUST be classified separately from observed low memory. Both remain effect-zero, but
   only measured pressure may drive capacity reduction. Control-plane probes and TCC preflight remain bounded.
9. Release handoff MUST be terminal-driven per label. A completed owner moves to the next compatible immutable
   release before its next wake; the fleet must not depend on a reconciler finding a tiny idle polling window.
10. Completion MUST be buyer-visible/provider-visible effect plus official readback and replay-zero. Scheduling,
    PID, start receipt, queue selection, draft, click or Telegram report is not progress.
11. A funded client or fresh buyer event that has no official seller progress for two intended cadences MUST
    trigger a shared repair event, reclaim only stale owned resources, prioritize that item and continue without
    human babysitting.
12. Local and hosted variants MUST use this same logical loop, schema, recipe, effect fence and tests. Only the
    host supervisor, durable store, secret store and browser transport may differ.
13. Every continuation MUST read the active goal before repository work and verify expected worktree path,
    branch, upstream, commit floor, lease and dirty state. A shared checkout or mismatched branch is read-only
    and MUST fail closed before edits. Missing files in that checkout MUST NOT be treated as absent from
    `origin/main`.

### 4. Acceptance criteria and test matrix

| # | Acceptance criterion | Required test/evidence |
|---|---|---|
| 1 | One slow or failed lane cannot alter another lane's schedule, state, BrowserContext or progress | `test_one_lane_failure_does_not_pause_siblings` plus four concurrent natural wakes |
| 2 | Maintenance cannot consume a revenue lane's reserved minimum; unused capacity remains borrowable | `test_maintenance_capacity_is_borrow_only` and saturated-host canary |
| 3 | Global host load remains bounded without converting pressure into fleet-wide revenue starvation | `test_partitioned_admission_preserves_revenue_progress` plus measured CPU/memory/process trend |
| 4 | Different Paid orders own different namespaces and run concurrently; the same order is stingy/exactly-once | `test_paid_orders_use_project_scoped_concurrent_claims` |
| 5 | One blocked Paid order remains represented while another order reaches official readback | `test_blocked_paid_order_does_not_block_ready_order` |
| 6 | A previously received attachment is never requested again; missing bytes use internal recovery | `test_retained_attachment_is_recovered_without_buyer_reask` using the observed 15-attachment case |
| 7 | A contracted CrowdWorks instruction becomes a fulfillment item and reaches submit/readback | `test_contract_instruction_creates_fulfillment_work_item` plus exact provider receipt |
| 8 | Probe timeout, real low memory, TCC denial and TCC pending are distinct terminal reasons | `test_host_preflight_failure_classes_remain_distinct` |
| 9 | Terminal release handoff updates one exact idle label without restarting siblings or losing state | `test_terminal_release_handoff_is_label_scoped` plus loaded argv/readback |
| 10 | Every active client independently covers its newest buyer event, official effect and replay-zero | Client-by-client official matrix for Ryu, both Kokoro contracts, Chii and Atsugi |
| 11 | Apply, Reply, Paid and Storefront continue across reboot and one owner crash | Four-lane reboot/fault-injection canary |
| 12 | The same contracts hold at fleet scale | 500-loop admission test, 24-hour canary, then seven-day soak with zero starvation and zero duplicate effects |
| 13 | A handover resumes only in its named worktree/branch and refuses the Capafy/shared checkout | `test_handover_worktree_route_fails_closed` plus HEAD/upstream/dirty-state receipt |

E2E judgment:

| Item | Value |
|---|---|
| UI change | None in the shared runtime repair; provider UI is the official effect/readback surface |
| Maestro | Not applicable; required E2E is natural launchd wake plus real provider readback because this is a macOS/background marketplace system |

### 5. Boundaries

- DO NOT replace the four lane owners with one monolithic business scheduler.
- DO NOT create Coconala-, CrowdWorks-, Lancers- or Mercor-specific admission/retry/receipt frameworks.
- DO NOT raise global concurrency or create more browser processes as a substitute for ownership and fairness.
- DO NOT kill unrelated processes, global Chromium, ChatGPT/Codex, the GUI session or the host to pass a test.
- DO NOT weaken effect fences, official readback, formal-delivery authorization, attachment integrity or
  replay-zero to increase throughput.
- DO NOT mix Capafy work, its branch or its dirty files into this workstream.
- DO NOT create another implementation worktree while the existing runtime-admission worktree is clean,
  same-task owned, process-free, PR-free and safely fast-forwardable to `origin/main`.
- DO NOT activate admission protocol `2` until its capacity model satisfies the lane-independence and
  maintenance-borrow-only contracts above.

### 6. Execution order and rollout rule

Order change reason: the previous cursor was fleet convergence -> protocol `2` activation -> natural fairness
proof -> Coconala. Live evidence now proves the current global admission semantics can starve every revenue
lane. Activating them unchanged would make the regression durable. The new cursor repairs the shared capacity
and per-client progress invariants before activation while leaving independent provider effects uninterrupted.

Old order:

```text
finish release convergence -> activate protocol 2 -> prove fairness -> resume Coconala
```

New order:

```text
freeze protocol 1
-> capture three production regression fixtures
-> partition host capacity and remove maintenance/revenue coupling
-> restore project-scoped Paid concurrency and attachment retention
-> prove Coconala four-lane/client canary
-> activate the corrected protocol 2
-> 24-hour and seven-day fleet proof
-> continue platform revenue order
```

Current cursor: main `172d3f2e` is exported as immutable release `20260916T073615-172d3f2e`; Paid is
exact-loaded from it while the unaffected Coconala labels retain `0aba1191`. A four-owner overlap was observed,
Reply later terminated `pass`, and Paid
selected `codex/acct1/gpt-5.6-terra`. The authenticated orders-only snapshot contains four open rooms: Chii,
Ryu and the two Kokoro contracts. Chii's 300-row workbook is later than its buyer complaint; both Kokoro rooms
have later independent seller artifacts; Atsugi has buyer acceptance plus formal-delivery readback. Ryu's latest
buyer event is now covered by one later ordinary seller message, exact official readback and a standard replay
fence. Kokoro `18250352` also completed its newer email request: Gmail SENT and all 11 attachments passed
independent byte-for-byte readback, then Coconala received one later report with formal delivery OFF. A natural
Paid wake at `2026-09-15T23:09:25Z` observed all four open rooms with `actionable=0`, `effect=0`, `readback=4`,
`failed=0`, `pending=0` and terminal `pass`. Apply's planner schema defect (`required` incomplete, then unsupported
`allOf`) is fixed by PR `#5262`, live Codex output-schema probe PASS, and immutable release
`20260916T082615-427972bf` is loaded. Four idle CrowdWorks revenue labels were reconciled to the same protocol-2
release, removing the observed mixed-release borrower gate. A later natural Apply wake passed, judged five
new listings correctly as prohibited, and retained exactly 54 duplicate-fenced intents. PRs `#5265`-`#5268`
add CAS-frozen, ledger-first, contiguous and resumable official-history reconciliation. Two incorrect page-1
absence runs changed 54 intents; both were restored exactly from their CAS-bound recovery archives before the
resumable release was loaded. Production scan state is now page 3 with all 54 still PREPARED.
Do not create another worktree, edit the Capify checkout, globally kill browsers/apps, or call a process receipt
a provider effect.

### Ideal steady state

```text
launchd wake (each lane, 1–5 min)
        ↓
shared host broker: hard ceiling + revenue floor (maintenance borrows only)
        ↓
lane owner: one persistent browser owner per platform/account
        ↓
client work item: observe → model decides → effect fence → official readback
        ↓
terminal receipt + durable cursor → next wake
```

The four Coconala lanes and every future platform lane remain independent owners. A slow or failed client
only returns its own item to durable retry; it does not hold another client's browser, state, slot or effect
fence. “24/7” means these bounded wakes keep resuming forever; it does not mean one immortal process or
unbounded simultaneous Chromium tabs. Capacity is increased only after measured headroom and replay-zero,
never by deleting the guard.

## Current measured state

### Live correction (re-read before every mutation)

- `origin/main` is `172d3f2eaa4fedb815d0b8515f6454ab55ebe9a1`; Paid is exact-loaded from
  `$LIFE_MANAGER_RELEASES/20260916T073615-172d3f2e`. Other Coconala labels retain their already-loaded
  `0aba1191` release because this patch changes only Paid.
- Admission protocol `2` is live. A four-Coconala-owner overlap is observed; Reply has a natural `pass`, and
  Paid selected Account 1. This proves one recovery slice, not 24-hour fairness or provider completion.
- Reply observed 179 threads, produced 164 official readbacks and left 15 pending with effect zero. Apply and
  Storefront are running current-release provider passes. Their eventual terminal/provider receipts remain open.
- PR `#5258` fixes Chii's stale-state reopen defect and passes the complete Paid test file (`211 passed`). It is
  loaded in production. The current wake did not spawn Ryu or Chii work owners. Ryu's verified ordinary message
  was sent once with formal delivery OFF and a later exact selected-talkroom readback; its standard handoff
  receipt now resolves to `awaiting_buyer`. Kokoro `18250352` completed its Gmail effect, independent verifier,
  Coconala report and exact readback; the same digest resolves `completed` with no replay.
- The canonical runtime repair is now in main through PRs `#5244`, `#5246`, `#5247`, `#5248` and `#5249`; do not report the old
  `b8cff053`/protocol-1 snapshot below as current.

### Shared host/runtime

- PRs `#5194` through `#5199` are merged. Current main is
  `b8cff053255f840cc02405c886bd4974005586cc`, published as full immutable release
  `$LIFE_MANAGER_RELEASES/20260915T061515-b8cff053`. The release reconciler now covers both complete
  provider routes, changes only loaded-idle labels, skips running and unloaded labels, runs outside saturated
  data-plane admission, reconciles the local complete release before any remote fetch, bounds fetch with the
  existing portable process-group timeout, narrows Git negotiation to `origin/main`, and uses the release-pinned
  Python for its nested `lm-loop` CLI. Each PR passed its focused tests and GitHub CI 8/8. Production proved the
  old unbounded fetch could run beyond ten minutes, the bounded replacement emitted `entrypoint_exit_124` with
  no orphan Git children, and `control_plane_exempt` wrote an effect-zero host receipt. The first natural wake
  of the final `b8cff053` release is currently running; its two route summaries, terminal receipt and resulting
  exact fleet mismatch count remain open and must be read back before protocol activation.
- Admission remains protocol `1`. The latest read-only snapshot observed three live owners
  (`affiliate-source-refresh`, `writer-opportunity-response`, `job-search-daily`) and one legacy ticket
  (`article-resume`). Host load was about `192`, memory-free readback was `30%`, and the data volume was `99%`
  full with about `2.7 GiB` available. All four Coconala owners remained installed from `3fbe7554`; Apply was
  loaded-idle with last exit `75`, while Reply, Paid and Storefront had running wrappers and last exit `75`.
  The `b8cff053` release reconciler still had only a running event, not a terminal summary. These observations
  supersede the earlier owners `2` / tickets `0` snapshot but may change naturally; re-read before mutation.
- PR `#5193`, main SHA `3fbe75546d720add1bfa465731ddc94353b662b5`, is merged and published as
  immutable release `$LIFE_MANAGER_RELEASES/20260915T025232-3fbe7554`. The safe two-stage rollout keeps
  protocol `1` until every finite label is exact-loaded from this capability-2 release. Initial loaded-idle
  reconciliation completed with failures 0: deterministic had 53 eligible results, 44 changes and nine
  snapshot-race running skips; shared-agent-runner changed 33 labels. A later targeted pass moved Coconala
  Apply, Reply, Paid and Storefront to the new release after each old wake ended naturally. Repeated current-SHA
  natural wakes now write bounded effect-zero `host_admission_deferred:resource_control_busy` terminal events;
  they do not yet prove business recovery or official provider readback. That rollout snapshot reduced finite
  installed mismatches from 51 to 38 and observed protocol `1`, owners `3`, legacy tickets `4`; those counts are
  historical. V2 activation, natural fairness, recovery, replay-zero and 24-hour proof remain open.
- PR `#5192`, main SHA `6a901db5011da29a05ef91422c7ee745c8fa6e51`, is the compatibility-first
  admission rollout. It preserves future-version durable tickets during mixed-release convergence and records
  the exact bounded admission reason instead of collapsing every deferral to `host_admission_deferred`.
  Its exact head passed 31 focused tests, 493 runtime tests plus 470 subtests, all CI and fresh read-only review.
- The first targeted Paid wake on `6a901db5` started normally and terminated without an external effect at
  `2026-09-14T14:02:40.631497+00:00` with
  `host_admission_deferred:memory_headroom_unavailable`. It did not observe or reply to Ryu. This proves precise
  classification, not recovery or client completion.
- Durable fairness implementation is merged, but production activation and natural proof are still open. The
  lock-protected path is `queued -> dispatch_reserved -> claimed -> running -> released`, with monotonic
  sequence, reservation lease recovery, child-PID ownership and out-of-lock target kickstart. Protocol `1`
  remains the correct production mode during mixed-release convergence.

- PR `#5184`, main SHA `b8de9bf2d230514587bb455f59a3e866ec27f658`, fixes scheduled resource
  admission. Busy wakes attempt once, retain no ticket, write effect-zero deferred state and exit `75`.
- PR `#5186`, main SHA `3e7b77714d92e179806970d353f7c9db2f8dfed6`, removes every external
  process-identity probe from the shared admission critical section. It snapshots all identities once outside
  the lock, fails closed on snapshot failure and preserves rows created during the snapshot. Race tests,
  100-ticket scale coverage, 47 host tests, all CI and a fresh read-only review pass.
- PR `#5187`, main SHA `59bd6cddaf2768a98da6373480043672db657713`, makes explicit-loop
  reconciliation read only the requested launchd labels instead of enumerating the full fleet. Production
  read-only latency fell from about 37 seconds to 1.4--2.4 seconds; 70 tests plus 30 subtests, all CI and a
  fresh read-only review pass.
- PR `#5188`, main SHA `d80e7359127a9bc591463ee4b6b3ea2528f8639a`, removes synchronous evidence
  garbage collection from Apply's revenue-critical path. The observed old run spent about 28 minutes scanning
  412 MiB and reclaimed zero bytes because it was below the 400 MiB high watermark. GC now has an independent
  six-hour deterministic owner, and active evidence is protected by a PID plus process-start-identity pin.
- PR `#5189`, merge SHA `0a7b8c8b75899137bf28236e3c2e47fe1a3a0a91`, removes recursive run-tree
  cleanup from every business wake. Per-run scratch is created through state-root-anchored directory FDs;
  terminal evidence is protected before business execution; only exact PID plus process-start identities are
  reclaimed by the central owner. Ancestor symlink, run replacement, terminal-write failure and no-clobber
  races are covered. Targeted 45 tests, the 425-test runtime suite, all CI and fresh Terra architecture review
  pass.
- Immutable release `$LIFE_MANAGER_RELEASES/20260914T211512-0a7b8c8b` is current. The preceding
  `3e7b7771` loaded-idle rollout reconciled 57 deterministic and 40 shared-agent-runner labels with zero
  failures; target-only convergence to `59bd6cdd` has begun and running owners are skipped, not restarted.
- Idle rollout succeeded cumulatively for 96 label installs with zero reconcile failures. The latest
  convergence pass updated 11 deterministic and 12 shared-agent-runner labels; old-release running owners
  were skipped, not restarted, and continue draining naturally.
- Legacy root cause is proved: blocking waiters retained one process and ticket per wake; a waiter could hold
  the global control lock while an unbounded `/bin/ps ... lstart=` identity probe stalled every resource
  class. The new release bounds that probe to two seconds and fails conservatively as live.
- Read-only process sampling confirmed that the legacy drain, rather than the new release, caused the long
  wait: Paid PID `6856` and Apply PID `42143` spent every sampled stack in blocking `flock` on the shared
  `control.lock`. Paid then exited naturally, reconciled to `3e7b7771`, and its first natural new-release wake
  ended with bounded `host_admission_deferred`. Apply PID `42143` subsequently acquired the agent resource and
  now runs its real `application_direct.py --all-eligible` child; it is no longer blocked on `flock` but remains
  on old release `d74258a8` until that business run ends naturally.
- Coconala Reply and Paid are installed on current `d80e7359` and are executing natural wakes. Their previous
  wakes independently ended exit `75`,
  `host_admission_deferred`, loaded-idle, with no retained new-release ticket. Contention safety passes;
  later natural resume and official business readback remain open.
- Coconala Storefront is installed on current `59bd6cdd`. Its first natural current-release wake
  `18d526f7b56f7b80-33558` emitted started and bounded terminal `host_admission_deferred` receipts in 16.6
  seconds with no external effect. Target reconciliation applied exactly this idle label with zero failures;
  later natural resource acquisition, official listing readback and replay-zero remain open.
- The legacy queue is draining rather than growing: read-only polls measured `19`, `18`, `11`, then `10`
  retained tickets. Current memory admission itself passes at
  `free_percent=31` against `minimum_free_percent=15`; the remaining backlog is legacy process/ticket drain,
  not evidence of current physical-memory rejection. Coconala Storefront PID `60168` ended naturally and
  the lane is installed on `b8de9bf2`; two new-release wakes ended with bounded terminal deferral and retained
  no legacy ticket or owner. Paid is now reconciled; Apply PID `42143` remains live on an older release and
  must end naturally before target-only loaded-idle reconciliation.
- Disk availability recovered from `1.1 GiB` to `4.0 GiB`. Only clean, unused, regenerable external clones,
  main-contained temporary clones, three completed merged worktrees/branches/owned leases, and one missing-worktree
  registration were removed. Codex/cloud sessions, credentials, browser profiles, memory, state, ledgers,
  receipts, active evidence and other agents' worktrees were untouched. The retained legacy ticket count later
  fell to `7`; zero remains the completion gate.
- The dedicated `hf-gig-apply-evidence-gc` owner is installed on `d80e7359`, loaded-idle with exit `0` and a
  six-hour cadence. Apply PID `42143` remains on `d74258a8` and continues its pre-deployment business run; it
  is not interrupted. Storefront likewise remains running on `59bd6cdd` until its wake ends naturally.
- Target rollout of `0a7b8c8b` succeeded for Paid, Reply, Apply-evidence-GC and disk-cleanup without restarting
  a running owner. Paid then started from launchd without a kick and wrote a start receipt followed 16.3 seconds
  later by an effect-zero `host_admission_deferred` terminal receipt. It retained no admission ticket.
- A second shared startup bottleneck is now measured rather than inferred: Paid took about 149.7 seconds from
  launch to its start receipt while a one-second stack sample remained in Python import/compile. Immutable
  releases cannot write adjacent bytecode, so every wake recompiles shared runtime modules under host pressure.
  Disk-cleanup separately exited `78` before its start receipt because `process_start()` could not obtain the
  owner identity. These are the next shared-runtime cursor; neither is a Coconala-specific selector problem.
- PR `#5191` is merged at main `3a21ba280931757fbfd9adb4f3695ec36ab48b47` and release
  `20260914T220710-3a21ba28` is current. It builds checked-hash bytecode before sealing each immutable release,
  records and pins the exact runtime Python, verifies its cache tag during apply, obtains Darwin process-start
  identity through native `proc_pidinfo`, and removes fleet-wide `ps` enumeration from every admission wake.
  Fresh Astra review returned `ship`; the exact head passed 492 tests plus 470 subtests and every required CI
  check. Reply and disk-cleanup reconciled while idle; Apply, Paid and Storefront were observed running and were
  deliberately left on their installed releases to drain naturally.
- Reply's first observed natural wake on `3a21ba28` launched successfully but terminated at
  `2026-09-14T13:11:39.278302+00:00` with `host_admission_deferred`, exit `75`, and external effect zero.
  Therefore release startup identity/bytecode is shipped, but natural pressure recovery is not yet proved and
  the 15 nonterminal talkrooms have not advanced on this wake.

### Coconala

The matrix below is the durable client set. The authenticated orders-only snapshot currently reports four open
rooms; Atsugi remains listed because its accepted formal delivery is still settlement-relevant. Ryu `18211957`
is buyer-waiting after the latest ordinary seller message and a natural zero-effect replay.

#### Current active-client inventory

This is the retained official-state candidate set, not a claim that every newest message has been handled.
The next admitted Paid/Reply observation must refresh each row from the official talkroom before any completion
claim. One buyer may own multiple independent contracts.

| Buyer | Talkroom | Retained official state | Current unresolved condition |
|---|---:|---|---|
| Ryu0820119 | `18211957` | `取引中`; latest correction report sent, formal delivery OFF | Buyer-waiting. The latest three-message cycle has owner/verifier outcome coverage, one later ordinary seller message, official exact talkroom readback and a natural zero-effect replay. Reopen only for a newer buyer event. |
| こころ支援 NPO法人まくとぅー | `18223833` | `取引中` | Independent v4 seller artifact is later than the retained buyer input. Buyer-waiting; replay zero unless a newer buyer event appears. Never ask again for retained files. |
| こころ支援 NPO法人まくとぅー | `18250352` | `取引中`; email effect and Coconala report completed, formal delivery OFF | Gmail SENT readback proves 11 buyer-source attachments, the independent verifier downloaded and byte-matched all 11, and the later Coconala seller message matches the current buyer digest. Replay-zero passes for the same digest. |
| Chii【CK protect】 | `18180857` | `取引中`; 300-row workbook sent, formal delivery OFF | Buyer-waiting. Do not resend any recipient or completion message; reopen only for a newer buyer event. |
| あつぎ | `18171850` | `納品確認待ち`, formal delivery confirmed | Buyer explicitly accepted delivery and the later seller formal-delivery message is read back. Settlement/payout attribution remains; reopen work only for a newer buyer event. |

`逃げ因子` talkroom `18211838` is excluded because retained official state is `取引完了`. Historical
projects with `unknown` state are not promoted into the active set; an authenticated orders observation must
do that.

- Apply one-off `single:new` and continuous `retainer:new` are implemented through the same lifecycle.
- Shared browser acquisition is already repaired by merged PR `#5175` (`833b55b6`) and PR `#5177`
  (`6a9f3aa4`): slow CDP I/O stays outside the ledger lock and unrelated owners acquire under distinct
  task locks. The current `b8de9bf2` release contains that exact main implementation. Latest read-only
  health is `/json/version` in `0.025s`, `/json/list` in `0.017s`, and one lease against capacity `16`.
- Latest discovery failed before observation at the shared CDP lease boundary; this is not proof of empty
  inventory, logout or selector failure. Its 160-second timeout occurred on release `6a9f3aa4`; current
  health does not prove recovery until a later natural Apply wake completes official readback.
- Exactly 54 application intents are `prepared_unconfirmed`. Frozen source result:
  `gig-apply-direct-1789367873154753000-28060`; sorted IDs `5207298` through `5267876`; newline-list SHA-256
  `cd0610bb8daaf78c11ffd143a4688fad30edeff34188725aaa6867d935b8b2e5`. Reconcile every member
  against the official applied state before retry. Retained official readbacks match zero of these 54 IDs,
  so none can be confirmed or safely retired without one fresh authenticated official-history scan.
- PR `#5183`, main SHA `d74258a8ce25a834e1fff31b7e3dc01ac0b816ba`, makes Paid fail closed as
  `buyer_attachment_recovery_pending` instead of asking a buyer to re-upload when official attachment
  references exist but verified bytes are missing. Kokoro resumes only after all 15 files are verified.
- Latest durable Reply snapshot observed 179 talkrooms: 164 have official replay-zero/closed/no-reply
  readback, while 15 remain nonterminal (`pending=5`, `failed=10`). The ten failures are predominantly
  historical CDP context-creation timeouts; a fresh admitted Reply wake must reconcile them independently.
  A historical Ryu seller effect exists, but a newer buyer event is reported and is not covered by a later
  officially verified seller effect. Reconcile the newest digest before deciding whether to send; never resend
  a confirmed effect and never suppress a genuinely newer request.
- Coconala is not revenue-complete until Apply, Reply, Paid, Storefront and payout attribution all have fresh
  official effect/readback and replay-zero receipts.

## Remaining execution order

Platform/client owners remain concurrent. This list selects the engineering cursor; it does not serialize
independent production effects.

### Plain current checklist — authoritative summary

**Done:** Ryu, both Kokoro rooms and Chii are seller-last with official Coconala readback and replay fences;
Atsugi is settlement-only. Paid's later natural wake read back all four open rooms with no duplicate effect.
Reply has a natural terminal pass. Apply's earlier six one-off effects and the next four and three effects
each replayed zero on later natural wakes. Release `0401cb6a` produced seven new eligible one-off effects
across two runs, each with exact-ID official readback and no failure or pending result.

**Not done:** the prior ULID retainer attempt has no official submit/readback and remains duplicate-fenced;
the current continuous source had zero eligible candidates in the latest natural wake, so a fresh
screening-answer effect remains unproved. Fifty-four historical uncertain applications remain a
preemptible background reconciliation; Reply has 15 pending threads. Storefront's page-2 retirement
fix is loaded but its first natural run failed before the effect with browser WebSocket HTTP 500;
official Storefront effect/readback, demand and payout
attribution, 24-hour cadence, no-starvation, zombie-free browser teardown and every later platform remain open.

**24/7 acceptance:** every registered loop remains scheduled, but that alone is not success. Each applicable
lane must start within its declared 1–30 minute cadence, perform one bounded durable transition, write a terminal
receipt and exit. When one wake releases capacity, the next eligible revenue wake must start automatically.
Light deterministic work must not consume the same scarce capacity as browser/model work. Apply, Reply, Paid and
Storefront must all be revenue-priority owners. Maintenance may borrow unused capacity only. The static default
of five finite runs is not accepted as the final architecture; production must use measured resource-class
capacity and prove 24 hours without a missed revenue cadence or fleet starvation.

**Next order:** (1) keep one-off/retainer refresh live and prove a fresh eligible retainer screening-answer
effect when one exists, (2) repair shared admission/cadence and owner-scoped tab teardown, including
the currently failing Storefront browser connection and exact provider readback,
(3) resolve Reply 15 and Coconala payout, (4) reconcile the 54 historical
uncertain intents as preemptible background work without blocking current revenue, (5) prove all four Coconala
lanes for 24 hours, then (6) CrowdWorks paid contracts, Lancers, Mercor,
Freelancer.com and Upwork in that order.

### 1. Shared runtime production convergence and account 1 cutover — current cursor

- [x] Reuse the existing runtime worktree instead of creating another one. The APFS clone detector is merged
  as PR `#5244` and Storefront's inner-cadence removal as PR `#5246`; both are in `origin/main`.
- [ ] Finish the `0aba1191` four-lane canary. All four labels are exact-loaded and one four-owner overlap is
  proved; Reply has one natural `pass` terminal and Paid has an Account 1 receipt. Apply, Paid and Storefront
  still need their current natural terminal receipts and provider-level effect/readback. Then repeat under
  saturated maintenance and prove no sibling schedule/state/effect changed. PID or scheduler state alone does
  not close this item.
- [x] Chii Paid external delivery: export the official Sheet with 300 unique rows, send it once to talkroom
  `18180857` through the existing Coconala browser path, and read back the attachment and message with
  `formal_delivery_control_checked=false`.
- [x] Chii Paid closure: the 300-row workbook and ordinary Coconala message are read back with formal delivery
  OFF. Treat the client as buyer-waiting and rely on existing effect fences; do not build another adapter,
  reconciliation framework, recipient send or completion message for this one-off contract.
- [x] Merge/release the minimal shared Paid reducer fix that treats an official seller-last attachment as
  buyer-waiting only when buyer-visible artifact=true, pending artifact=false, no later buyer reply and formal
  delivery=false. PR `#5258`, main/release `172d3f2e`, complete Paid file `211 passed`, and the current
  production wake has no Chii owner.
- [x] Merge PR `#5257`, cut immutable release `20260916T070823-0aba1191`, and exact-load all four Coconala
  labels without restarting running siblings.
- [x] Natural Paid replay-zero: release `172d3f2e` observed all four open rooms with `actionable=0`, `effect=0`,
  `readback=4`, `failed=0`, `pending=0`; runtime terminal is `pass`, exit `0`, loaded-idle.
- [ ] Replace the fleet-wide fungible slot rule with shared hierarchical accounting: measured host hard
  ceiling, non-stealable lane/platform minimums, per-item limits, and maintenance/reporting/Telegram capacity
  that is borrow-only and preemptible. The staged `d75794b8a3` floor is the first minimal slice (four revenue
  slots, one borrow slot); it is not complete until the merged release proves no starvation and no hard-cap
  violation under natural wakes.
- [x] Merge/release the runtime floor and Account 1→2 failover. Main/release `0aba1191` is exact-loaded; a
  bounded Paid decision selected `codex/acct1/gpt-5.6-terra`. Account 2 remains the existing automatic fallback;
  neither account/session was deleted or overwritten.
- [ ] Add bounded owner heartbeat and durable-progress leases. A live PID without heartbeat/progress cannot
  retain capacity forever; recovery may reclaim only the exact owned claim after process-identity verification.
- [ ] Separate memory probe timeout, real memory pressure, disk pressure and TCC permission state. Apply
  owner-scoped browser/context/tab limits and recovery; never use global browser or host restart. Require every
  spawned browser child/process group to remain attached to one durable owner receipt and be reaped on every
  terminal path. Retain regression fixtures for the orphaned Capafy Chrome groups and the duplicate/wedged
  CrowdWorks `9228` roots.
- [x] Make Storefront a one-pass owner: launchd's 60-second cadence is the only repetition mechanism, so an
  inner `--auto-cadence` child cannot retain a revenue slot forever.
- [x] Make the disk governor identify closed APFS Chromium clones from one global open-path snapshot; active
  clones remain protected and closed clones are reclaimable.
- [ ] Convert Paid from one-order-per-pass lane-global evidence to project-scoped durable work items and bounded
  concurrent consumers. Serialize only the same exact order/effect and the short authenticated mutation.
- [ ] Make retained attachment references cumulative across wakes. Reuse verified bytes; recover missing bytes
  from the official source; prohibit buyer re-requests for already received files.
- [ ] Make contract acceptance/instructions create durable fulfillment work immediately so the CrowdWorks case
  and future providers cannot stop between contract and delivery.
- [ ] Replace idle-window polling as the release convergence dependency with label-scoped terminal handoff.
  Prove next wake uses the compatible current release without restarting a running owner or sibling.
- [ ] Re-run Coconala Apply, Reply, Paid and Storefront concurrently under saturated maintenance load. Prove one
  owner crash, timeout or blocked client does not change the other lanes' schedules, states or effects.
- [ ] Protocol `2` is already live. Prove FIFO within each lane, sleeping-head dispatch, crash recovery,
  cross-class progress, uncertain-effect reconciliation and duplicate effect zero over 24 hours, then seven
  days; do not treat activation itself as acceptance.
- [ ] Produce continuous terminal receipts and real official progress for 24 hours, then seven days, including
  reboot recovery and measured browser/CPU/memory/process ceilings. Any progress regression fails the rollout
  and restores the last proven release.
- [x] Prove the Paid Account 1→2 Codex route with one bounded invocation and retain both account sessions.
- [x] Roll the repository's Codex task classes to Account 1 first with existing Account 2 failover through
  PR `#5257`; route configuration and 71 agent-runner tests plus 93 subtests passed before merge.

Completed foundation retained as evidence: disk-headroom recovery; off-critical-path cleanup; checked-hash
bytecode and pinned interpreter; native Darwin process identity; SQLite durable reservations/dispatcher;
mixed-release compatibility; PR `#5193` and immutable `3fbe7554`; release-reconciler PRs `#5194`--`#5199` and
immutable `b8cff053`. PR `#5200` adds explicit revenue-before-borrow admission, PR `#5201` removes stale
pre-fetch release reconciliation, PR `#5202` lets revenue owners share the measured host-wide ceiling instead
of the borrow-only `agent=1` limit, and PR `#5203` applies the same rule during the v1 drain. Their natural
`77f80b3a` Paid wake acquired a slot beside unrelated owners, officially observed four rooms, and refreshed
Ryu `18211957` plus Kokoro `18223833`/`18250352` concurrently; it still ended `effect=0`, `readback=0`,
`pending=3` because targeted rows retained `delivery_action=none`. PR `#5204` routes those official targeted
rows back through the existing delivery queue and treats an explicit revision stage as work required;
immutable `287ccb88` is installed for the next natural Paid wake. These are supporting components, not proof
that buyer-visible progress is restored until that wake produces per-client effects and official readback.

PR `#5205` adds the safe protocol-`2` activation preflight: it preserves live protocol-`1` owners only after
every finite loaded program points to a structurally protocol-`2`-capable immutable release, including a mixed
set of compatible SHAs. Production activation correctly remains blocked by the still-running old Lancers
application owner; no active provider effect was killed to force convergence. PR `#5206`, merge SHA
`d2fc0a7bf369368078c04e93034b4e6328075ce3`, fixes the existing authenticated attachment collector without a
second framework: it removes the synthetic-event delay, skips file polling when no trusted control exists,
uses Page plus Browser download behavior, accepts a complete stable download when CDP byte counts agree, and
deduplicates only the same official attachment reference. Its focused Paid suite passed 199 tests. On the first
natural `d2fc0a7b` Paid wake, three targeted Coconala projects ran concurrently and saved fresh non-empty files:
Ryu `18211957` saved five, Kokoro `18223833` saved four in project `5242505`, and Kokoro `18250352` saved six.
The aggregate remains `pending=3`, `effect=0`, `readback=0`; file recovery is measured progress, not a client
submission. The current cursor therefore stays on those three project work items until their terminal receipts
and official effects exist.

The fixed host ceiling of three is a crash-containment baseline, not the target architecture and not proof that
all four Coconala lanes can make simultaneous progress. OSS code review confirms the reusable pattern: Hatchet
durable tasks free worker slots while waiting and attach a per-task slot cost; Temporal separates lightweight
workflow slots from resource-based activity slots; OpenBrowser and Steel broker persistent profile sessions
instead of launching one browser per loop; DBOS reserves polling/control capacity so data-plane saturation does
not starve recovery. Life Manager keeps its existing SQLite ledger and authenticated CloakBrowser path while
copying these small contracts: durable wait eviction, weighted task units, measured CPU/RAM admission, and one
browser broker per platform/account. Steel is the intended hosted browser transport. Installing a second local
workflow engine or replacing the logged-in Coconala profile during recovery is explicitly out of scope.

PR `#5207`, merge SHA `6ca2fc44668993b0ddec22b6a54bd62476d35459`, keeps the existing disk governor
outside finite data-plane slots and makes one malformed LaunchAgent plist fail independently instead of
crashing the whole cleanup pass. The focused cleanup/admission suites passed 111 tests. Immutable release
`20260915T103333-6ca2fc44` is current and only the disk-cleanup label was reconciled immediately. Its first run
crossed the malformed-plist boundary and completed the safe scan, but returned failure because one protected
host probe remained unknown; it reclaimed only 6,409 bytes and left about 7.8 GiB free. A concurrent
`d2fc0a7b` Paid wake recovered all 18 observed attachments for Kokoro `18223833` and 16 of 26 for Kokoro
`18250352`; Ryu retains 42 local files while its distinct-reference and duplicate-filename cases remain
unresolved. Kokoro `18223833` then built its current review artifact, sent it once in progress mode with formal
delivery OFF, and wrote `status=completed`, `effect=1`, `readback=1`; the official selected-talkroom readback
contains the new seller message and attached v3 review ZIP. The Paid aggregate is now `effect=1`, `readback=1`,
`pending=2`, `failed=0`. Ryu and Kokoro `18250352` remain open.

PR `#5208`, merge SHA `6a3d61a0c79f3f82605069766f05755ef2e2e3fc`, removes a permanent
attachment-recovery contradiction. The collector previously skipped every later official reference after one
file with the same filename existed, while the Paid gate rejected every duplicated filename without
reference-level proof. The shared collector now keeps a locked atomic `message reference -> content hash/file`
receipt, reuses a legacy filename only when it is unique in the official room, and stores duplicate bytes only
once. Paid suites passed 225 tests, the exact CI `unittest discover` entry passed 437 tests, and all PR checks
passed. Immutable release `20260915T110135-6a3d61a0` is current and the Paid label is exact-loaded from it. Its
first admitted run recovered five Ryu references and increased retained files from 42 to 46. The same run
replayed completed Kokoro `18223833` as `satisfied_noop`, `deduplicated=true`, `send_performed=false`,
`readback=1`; no duplicate client effect occurred. Ryu and Kokoro `18250352` remain pending.

The host also contained 127 zombie processes owned by one four-day-old unregistered default `agent-browser`
daemon. Its only live browser child belonged to a one-day-old lateness-heartbeat scratch run; no external client
held the socket. Exact owner-group cleanup reduced zombies to two and total processes from 833 to about 704
without touching ChatGPT, CloakBrowser or Coconala port `9223`. Root cause was
`skills/anicca-life-manager/scripts/route_lookup.py`: it used the global default session and never closed it on
success or repeated timeout. PR `#5209`, merge SHA `fcce2565e33e469979bcd29111b7dc7c46c02234`, uses one named
loop session and closes it in `finally`; all PR checks passed. It was subsequently included in the `5d0a813f`
production release described below.

PR `#5210`, merge SHA `5d0a813fe077034577c140eb7b45c68a892b7522`, raises the bounded local finite
worker default from three to five after exact zombie/browser-owner cleanup. A regression proves five revenue
owners acquire and the sixth remains `capacity_busy`; host overrides and memory admission remain active. In
production, five owners then ran concurrently: Coconala Paid, Reply and Storefront plus CrowdWorks Paid and an
affiliate refresh. This is the new local crash-containment baseline, not permission for unbounded processes and
not the final weighted CPU/RAM tuner. The same release exact-loaded lateness-heartbeat with the named-session
teardown from PR `#5209`; the pre-run zombie count was two and no global browser/app restart was used.

The next Ryu diagnosis rejected an incorrect large-video hypothesis before merge. Historical Ryu messages
contain old screenshot/recording references, but they are not inputs to the current revision. The abandoned PR
`#5211` was closed and reverted without production deployment. Root cause is broader context, not file size:
`_buyer_attachment_recovery_pending` scanned every buyer attachment ever observed, so a handled historical
cycle blocked a newer revision forever. PR `#5212`, merge SHA
`d8c6f097401674bd85095d019f5941ea9322657d`, scopes the blocking gate to the current
`live-buyer-reply.json` feedback cycle while retaining historical references for context and background
recovery. All Paid suites passed 225 tests and every PR check passed. Read-only application to current project
state returns recovery-ready for Ryu and both Kokoro projects. Immutable release
`20260915T114149-d8c6f097` is current; Paid remains on its preceding release until its active natural wake
terminates, then it must be exact-reconciled and prove real per-client effects.

PR `#5213`, merge SHA `46c49b19`, makes a confirmed handled buyer digest dominate stale derived
`active_feedback_cycle` and `work_state` fields. A completed room therefore stays a no-op instead of
re-entering build work. In the following production wake, completed Kokoro `18223833` did not spawn another
effect worker; its latest verified outcome remains `effect=1`, `readback=1`, formal delivery OFF, with the v4
review ZIP present in official selected-talkroom readback.

PR `#5214`, merge SHA `fc2549d2`, fixes isolated staged agents so shared registry reads resolve from the
loaded `LIFE_MANAGER_REPO` rather than the temporary staged working directory. PR `#5215`, merge SHA
`0439d7c0`, accepts verifier evidence returned as a structured object and extracts its official
`readback_source` instead of rejecting a valid remote verification. Paid suites passed 227 tests and all CI
checks passed. Immutable release `20260915T122835-0439d7c0` then ran Ryu `18211957` and Kokoro `18250352`
as independent concurrent work items. Ryu reached a fresh v193 remote owner result with authenticated public
and management readbacks, required effect/output satisfied and remaining work empty. Kokoro `18250352` produced
a valid `status=PASS` 50-item source census, but its runner summary incorrectly changed success to failure when
runtime-event emission hit `Operation not permitted` on the immutable release registry.

PR `#5216`, merge SHA `0dd1496f2c63c2c720ceb495aec04c9199e6b58d`, separates observability transport
failure from business-work truth. A runtime-event write error remains visible as `runtime_event_error`, but it
cannot reverse a selected successful agent result or its process exit code. The focused boundary passed five
tests, all agent-runner tests passed 67 tests, and every PR check passed. Immutable release
`20260915T124728-0dd1496f` contains this fix. The older Paid wake was allowed to reach its terminal receipt and
cleanup without interruption; only the Paid label was then reconciled to this release and Kokoro `18250352`
resumed from retained source evidence.

The first `0dd1496f` Paid wake reused Ryu's verified remote answer instead of repeating the site mutation, sent
the ordinary Coconala review message once with formal delivery OFF, and confirmed the exact newer seller message
in authenticated selected-talkroom readback. Its item receipt is `status=completed`, `effect=1`, `readback=1`,
`failed=0`, `send_performed=true`. That transport receipt did not prove the buyer-visible site outcome: the buyer
immediately replied that nothing had changed and that they had waited a day. The room therefore reopened under
new buyer digest `ba9c4cff11f2a29753d5f3d9da22fcbe1857df4de5c2dd14c8eed27af674a6ad`; Ryu is not closed.

The direct root cause was stale browser assets. Production returned `cache-control: max-age=604800` for `app.js`
and `styles.css`, while `index.html` still referenced old fixed query versions after the September 15 asset
update. Raw asset/API readback saw the new code, but a returning buyer browser could retain the old JavaScript
and CSS for seven days. The owner changed the HTML references to content-hash versions, deployed through the
existing authenticated XServer FTPS adapter, and verified the remote hashes. A fresh real browser then completed
the entrance flow and visibly rendered profile `あかり`, age, height, three sizes, cup and six option-availability
rows; screenshots are retained under the Ryu verifier evidence. The active Paid wake now owns the new buyer
digest and must finish a fresh verifier, corrective Coconala message and official talkroom readback before Ryu
can close. Future buyer-visible web effects cannot pass from raw API/asset text alone; acceptance needs a fresh
browser-visible route after entrance/overlay completion and cache-safe asset identity.

The buyer then supplied the five reference screenshots again, which disproved the narrower semantic contract:
the live page had basic measurements and six options but not the complete reference composition. The references
also required attribute badges, a broad tri-state option grid, Q&A, cast message, manager comment, per-profile
schedule, review/recent-view states and previous/list/next navigation. The owner extended only the existing
HTML/JS/CSS and authenticated content document: no new framework or parallel site was introduced. A failing
three-test reference contract became green; JavaScript syntax passed; local and production 390px browser checks
then measured two badges, four measurements, 33 options, seven Q&A rows, both message sections, three schedule
rows, explicit empty review/recent states and three navigation links. The existing XServer FTPS adapter returned
matching hashes, the authenticated content API save/readback returned 200, and the cache-safe asset versions
matched in the real page. The corrective full-profile Coconala message was sent with formal delivery OFF and is
the latest seller message in independent selected-talkroom readback. The current photo count is one; the existing
administration supports up to five distinct uploads, replacement and ordering without fabricating extra cast
photos.

The same Paid kernel subsequently repaired Kokoro `18250352` beyond the first v11 candidate and sent
`makutuu-submission-documents-v12.zip`. The durable item result is `status=completed`, `effect=1`, `readback=1`,
`failed=0`, `send_performed=true`, formal delivery OFF; authenticated selected-talkroom readback contains the
v12 seller message and attachment. This room is now buyer-waiting for that digest. This historical liability
ordering is superseded by the current client matrix above.

PR `#5217`, merge SHA `4cdfcf7879a937e0df989615583bb75e2014ef5b`, generalizes the Ryu failure class
inside the shared Paid kernel. A buyer request to copy/adopt/match visual references now requires a complete
visible component and layout census across every reference rather than only the nearby named subset. A
buyer-visible web PASS now requires a fresh browser after entrance/consent/overlay completion, exact route and
viewport visibility, screenshot evidence and cache-safe loaded asset identity; raw HTML/JS/CSS/API content is
insufficient. Two new regressions, all 204 remote-wait tests, all 229 Paid tests and every PR check passed.
Immutable release `20260915T135937-4cdfcf78` contains the rule. The preceding Paid wake terminated
`status=completed`, `effect=0`, `readback=3`, `failed=0`; the Paid label was then exact-reconciled and started
from this release. Ryu replayed as `satisfied_noop` with no duplicate send.

Reply/Negotiate and Paid must not maintain separate semantic work engines. Their shared kernel is official
observation -> cumulative context -> work-item decision -> text/file/remote execution -> verification ->
provider send -> official readback -> durable dedupe/resume. Thin state/policy adapters remain separate because
pre-contract demo/estimate authority differs from paid progress and buyer-authorized formal delivery. The
observed `juves9718` negotiation demonstrates the remaining gap: a buyer asked for a selection demo, but the
current Reply path acknowledged it without creating and submitting the demo. After open Paid liabilities close,
route substantive Reply/Negotiate requests into the same executor instead of treating them as text-only replies.

Chii `18180857` was completed externally by the manual owner: the official Google Sheet contains 300 unique rows,
the sender identity readback is `@anicca.jp`, and a 300-row workbook was sent to Coconala and read back with
formal delivery OFF. The direct effect ledger contains 288 exact-readback sends plus the prior 12 verified
effects. The later official Coconala message/attachment readback supersedes the stale `12/288` owner result for
workflow routing: Chii is buyer-waiting, and no existing recipient may be resent. A one-off unintended test-text
effect to `@gucci_fuufu` is recorded separately and excluded from the 300 count.

PR `#5222`, merge SHA `131fdc9952b7f6e92ad0c912308ad1e62ab8cc87`, fixes the observed one-owner-per-wake
bottleneck without adding another scheduler. When an owner writes new durable progress, leaves both business
outcome flags false with nonempty self-actionable remaining work, and has no external wait receipt, the existing
three-round Paid review loop spends the next round on more owner work before verifier handoff. Zero progress,
completion, an external wait or the final round still terminates the repetition. Remote-wait tests passed 208 and
all Paid-related tests passed 241 before release `20260915T160937-131fdc99` was loaded.

That release then exposed a separate tool-discovery error: the owner treated a missing Google browser identity as
a Sheets blocker even though the host's existing authenticated `gog sheets` API had already appended and exactly
read back `@we_kouki / 9/15`. PR `#5223`, merge SHA
`05b6790f2025cb7a8a3b885a8635ddc6bc230eb7`, makes the API path explicit in the shared browser skill and Paid
owner prompt: read for dedupe, append one row, atomically retain the response, and get the response's exact updated
range before checkpointing. Browser resolver absence is not API credential absence. All PR checks passed; immutable
release `20260915T162329-05b6790f` is the loaded Paid target. A preceding Chii owner remains allowed to finish; the
next Chii owner must use this release without overlapping the same mutable project state.

PR `#5225`, merge SHA `a5da9dca71bb4ac18843b3d989baa989d7487e0d`, closes the validation edge found by
the next canary: a current-contract checkpoint could be durable while the model left a stale/incomplete builder
result, and the controller previously ended `pending` before its same-run continuation branch. A newly appended
valid checkpoint now spends the next available review round on another owner even when builder-result validation
fails; zero progress and the final round remain fail-closed. Remote tests passed 208 and all PR checks passed.
Immutable release `20260915T163955-a5da9dca` is loaded. Its targeted Chii run performed official TikTok and
`gog sheets` readbacks, removed three non-effective Sheet rows with exact range readback, checkpointed the
reconciled 12-row ledger, then started a second owner round in the same process. That round checked two distinct
unused candidates (`@nanana.206`, `@shakaijin_`); both returned `recipient_message_route_unavailable`, effect zero,
and durable preflight checkpoints. It continued between candidates without a new wake. The immediate campaign
bottleneck is now discovery of eligible profiles whose official TikTok DM route is available, not authentication,
Sheets access, memory admission, static delegation or one-candidate process termination.

The next targeted Chii run proved the full bounded continuation chain. Round one used official TikTok and
`gog sheets` readbacks, removed three non-effective rows with exact range confirmation, and checkpointed the
12-row effective ledger. Round two started in the same process, checked `@nanana.206` and `@shakaijin_` without a
new wake, and checkpointed both as route-unavailable effect zero. Round three then started in the same process.
The same-project model/effect lock serialized a coincident natural Chii worker while Ryu remained independent;
there was no simultaneous mutation of Chii state and no cross-client wait.

Ryu `18211957` completed an earlier management-screen revision, but a still newer buyer event now says
`デモになってます。`. Therefore the earlier buyer-waiting conclusion is superseded. The current owner must send
the newly verified correction once and obtain a later selected-talkroom readback before Ryu can return to
buyer-waiting.

The owner explicitly retired TikTok-adapter development for Chii because this outreach shape will not recur.
Do not add another TikTok adapter or speculative queue framework. Finish this one contract operationally through
the existing authenticated `tiktok-anicca-jp` search/profile reader, shared message transport, exact official
readback and `gog sheets` API. The 12-to-58 ledger paragraphs that follow are historical evidence only. The
current external delivery is represented by the 300-row workbook/readback, but the canonical Paid cursor still
needs its `300/0` promotion; do not resend any existing recipient. Continue only reply monitoring and ordinary
Coconala work, stopping on an actual TikTok warning or provider limit. A profile button without a
recipient-bound conversation is effect zero and must never create a Sheet row.

After sustained profile/search activity, TikTok began returning an official page title with an empty profile body
even under one serial owner. Six consecutive serial profiles reproduced the empty readback. Treat that as current
provider display suppression, not candidate ineligibility and not permission to fabricate rows. Preserve the
remaining 144-URL discovery wave, resume from its first unverified URL when official profile bodies render again,
and keep the single persistent owner/session; do not rotate accounts or browsers to evade the provider state.

The shared runtime admission review then found a separate fleet-wide hang class: `transfer_durable` and
`release_and_reserve` used blocking `flock(LOCK_EX)` after a child or sibling held `control.lock`. The bounded
handoff fix, APFS clone detector, Storefront one-pass fix and stale-release guard are now merged in PRs `#5244`,
`#5246` and `#5247` (main `62716e997b`). Their focused runtime tests pass; production still needs the new
release's natural wake and
24-hour/seven-day proof.

Observability remains a current architecture gap. Existing JSONL events and provider receipts stay the source
of truth, while OpenTelemetry becomes the shared trace envelope rather than a second business ledger. One
trace joins `platform/account/work-item` observe, context capsule, attachment recovery, model work, effect and
official readback; current blocker and previous terminal blocker are separate fields; every running child emits
bounded heartbeat/progress; SLA, repeated failure and orphan-owner alerts derive from those facts. Start with
the OpenTelemetry Python API plus one lightweight Collector/export path. Do not install a full local Grafana,
Loki or Hatchet stack while disk pressure and client work remain open; hosted dashboards consume the same OTLP
later. Completion requires an injected stalled-child fixture to alert, reclaim only its exact owner, resume the
work item and leave a sibling trace unchanged.

### 2. Coconala vertical revenue proof

**Current cursor (2026-09-24 02:49 JST):** The cross-provider SSOT is
`docs/superpowers/specs/2026-09-22-paid-fulfillment-all-platforms-design.md`.
Ryu `18211957` is a permanent manual exception and the latest direct revision
was sent once as seller message `js-talkroomMessage-222245383` with formal
delivery OFF; the seller message is present in the source talkroom history and
the current Paid evidence records Ryu as `reserved_for_owner` with
`send_performed=false`/`deduplicated=true`. Do not reopen or resend Ryu from the
historical entries below. Chii `18180857` and NPO rooms `18223833`/`18250352`
are also buyer-waiting according to their latest official readbacks; the two
NPO packages have unresolved buyer facts, so no additional package may be sent.
`hf-gig-paid-direct` is enabled on its five-minute schedule and its latest
readback is `loaded-idle`/`pass` with `observed=4`, `effect=0`, `readback=3`,
`pending=0`. The older Ryu/Kokoro paragraphs in this section are retained as
evidence history only, not as current work instructions.

- [ ] During the corrected shared-runtime canary, let the current Paid, Apply and Storefront wakes finish and
  persist terminal receipts while unrelated revenue/maintenance owners run; Reply already has one natural
  `pass`. Process start alone is not a client effect.
- [x] Obtain one authenticated `orders-only` observation. It currently contains Chii `18180857`, Ryu
  `18211957`, Kokoro `18223833` and Kokoro `18250352` as four independent open rooms.
- [x] Obtain `selected-talkroom-only` head readback for each open room; Atsugi's latest retained formal-delivery
  head is also recorded. Continue refreshing each digest independently on later wakes.
- [x] Fix the shared queue reducer so a newer unhandled buyer digest always overrides stale
  `await_buyer_feedback`; `buyer_feedback_answered_by_seller` now derives from the ordered
  official history, and regression coverage proves a seller answer closes only the current
  buyer feedback while a newer buyer message reopens work (Ryu-shaped contradiction).
- [x] Route active talkrooms to independent work items and effect fences. The current Paid wake ran Ryu and
  Chii owner processes concurrently while both Kokoro rooms independently replayed buyer-wait state.
- [x] Ryu `18211957`: latest three-message cycle covered both form destinations, grouped easy edit and profile
  editing. A later ordinary Coconala seller message was officially read back with formal delivery OFF; the
  following natural Paid wake reported `send_performed=false`, `deduplicated=true`, effect zero for Ryu and
  readback four across all open rooms. The manually released orphan browser lease remains a separate shared
  self-heal gap; do not claim that class is fixed by this one client outcome.
- [x] Kokoro `18223833`: retained inputs were recovered and the room has its own verified submission; replay zero
  unless a newer buyer event appears.
- [x] Kokoro `18250352`: the newer post-v12 request is complete. Gmail SENT readback and a fresh verifier prove
  11 buyer-source attachments byte-for-byte; one accurate Coconala report is seller-last with formal delivery
  OFF, and the same digest resolves `completed` without replay. Missing business report/member-list originals
  were not invented.
- [x] Chii `18180857` external send: the official Sheet has 300 unique rows, the manual owner ledger has 288
  exact-readback sends plus 12 prior verified effects, and the 300-row workbook was sent to Coconala with
  formal delivery OFF and exact talkroom readback.
- [x] Chii `18180857` is buyer-waiting after exact Coconala message/attachment readback. No further client work
  is scheduled unless a newer buyer event arrives.
- [x] Prevent stale Chii local state from reopening the completed campaign. PR `#5258` is merged, immutable
  release `172d3f2e` is loaded, and the current Paid wake did not create a Chii owner.
- [x] Resume Paid from immutable release `0aba1191` and prove one `codex/acct1` decision receipt. The current
  wake remains active; its provider/client terminal is still required.
- [x] Atsugi `18171850`: latest retained official head contains explicit buyer acceptance and a later formal
  seller message. Keep it settlement/payout-waiting and reopen only for a newer buyer event.
- [x] Ryu and both Kokoro rooms have later official seller effects; Chii has its workbook effect. All four
  independently replayed zero for their then-current digests in the natural Paid wake. Ryu later received a
  newer buyer burst and is reopened above; Atsugi remains settlement-only unless reopened.
- [x] Merge the shared per-outcome Paid completion gate as PR `#5279`, main/release `dde0efae`. Semantic models
  own `required_outcomes`; deterministic code requires exact source-identity coverage, owner/verifier
  `outcome_coverage`, verified official receipt references and semantic-digest binding before Coconala send.
- [ ] Keep the 54 historical uncertain intents duplicate-fenced. PR `#5284`, main/release `0401cb6a`, removed
  old effect-started per-candidate deep scans from foreground Apply; the observed run left four such IDs as
  `background_reconcile_pending` and then confirmed four fresh eligible effects. Reconcile the frozen
  54 as preemptible background work from the durable page-29 cursor; retire an intent only after the final
  official history page proves it absent. Never delete the records blindly or let them delay current revenue.
- [x] Restore authenticated discovery for both `single:new` and `retainer:new`. Release `30a2a2df` observed the
  current single page and the official retainer page; the latter contained one active listing.
- [x] Prove the first `0401cb6a` run's four one-off effects replay zero. The next natural Apply wake
  `gig-apply-direct-1789546429808684000-94897` recognized `5275397`, `5273683`, `5275175` and
  `5266799` as already applied, did not send them again, and instead confirmed three distinct eligible
  applications (`5275054`, `5270900`, `5268989`) with three official readbacks. Its terminal result was
  `status=ok`, `effect=3`, `readback=3`, `failed=0`, `pending=0` under immutable release `0401cb6a`.
- [x] Prove the next three one-off effects replay zero. Natural wake
  `gig-apply-direct-1789547386893730000-13356` recognized `5275054`, `5270900`, and `5268989` as
  already applied and ended `status=ok`, `effect=0`, `failed=0`, `pending=0` without resending them.
- [ ] Keep submitting every eligible high-fit one-off and continuous application. The earlier six,
  subsequent four, and next three one-off effects are duplicate-fenced. The continuous source was observed
  but had zero eligible cards in the latest natural wake; its next eligible listing must exercise the
  screening-answer submit/readback path.
- [ ] Create Calendar events and five-minute Telegram reminders for every accepted meeting.
- [ ] Keep Reply processing every talkroom independently with cumulative context and attachment recovery. Its
  latest pass observed 179 threads, read back 164, and left 15 pending; resolve each pending thread without
  changing already closed/no-reply rows.
- [ ] Recover and verify Kokoro's 15 retained files without another buyer request.
- [ ] Complete every funded Paid work item, deliver exactly once and verify official room state.
- [ ] Keep Storefront published where supported and measure official demand. PR `#5288` merged as main
  `2c8f83c9`; immutable release `20260916T180214-2c8f83c9` is exact-loaded for Storefront only.
  Root cause of repeated `storefront_retire_control_absent_at_submit`: service `4330105` was observed
  on seller-list page 2 while the old executor opened page 1. The focused test was red before the fix;
  50 Storefront tests and CI passed. The first natural run from the new release ended `failed`,
  `effect=0`, `readback=0`, reason `server rejected WebSocket connection: HTTP 500` before the
  archive/readback path; another natural run was live at 2026-09-16 18:13 JST. Do not call the
  provider effect fixed until its terminal receipt and official listing-state readback prove it.
- [ ] Attribute accepted payout and bank receipt to its originating application and contract.

### 3. CrowdWorks vertical proof

**Plan/spec:** docs/superpowers/plans/2026-09-17-crowdworks-contract-fulfillment.md and
docs/superpowers/specs/2026-09-17-crowdworks-contract-fulfillment-design.md.
**Current cursor:** **CW-F1 — four-row admission reconciliation and installed-owner wake**.

**Current authoritative state (read-only):**

- The admission DB has four CrowdWorks rows with effect_unknown=1: Application,
  Paid, and Reply are claimed; Report is released but still unresolved. No row may be
  cleared from the plan by inference or direct SQL.
- Loaded immutable releases are Application 8fbfb3a2f2b1449018d46f1978a500ce77f003a9,
  Paid 56d07a66eaa7c7d173c51314c47fb1c22b3f5610, and Reply/Report
  fed2839db846509585d6ba2d53da626a09dd0cae. Candidate Application release
  501058ec8237c3888d862ed92d0a048e0f2cc1f7 is ready, but target apply correctly refuses
  effect_unknown=1. PR #5634 binds new application receipts to their runtime occurrence while
  historical imports remain unbound.
- Disk-cleanup release `20260919T093130-c320c48f` (main `c320c48f6a`) is exact-loaded for the
  target owner. Its latest wake passed with `errors=0`, `owner_metadata_invalid=4`, `preserved=210`,
  `removed=1`, and `free_after=1931776000`; malformed owner files remain protected and visible.
  Current host headroom is about 1.8 GiB and still PRESSURE. One ownerless legacy Capafy scratch is
  retained because no stale owner identity exists.
- The read-only CrowdWorks inventory contains funded IDs 63712784, 63659463, 63657015,
  63570481, and 63568785. This inventory is not a work submission, delivery, acceptance,
  settlement, payout, or MRR receipt.

**Done (verified):**

- Apply -> Reply (pre-contract) -> one Paid owner (post-contract) is the boundary. Reply has no
  post-contract work or delivery effect; there is no CrowdWorks Storefront owner.
- PR #5594 and PR #5599 are merged, PR #5630 fixed cache open-path probing, and PR #5634
  binds new application receipts to their runtime occurrence while keeping historical imports unbound.
- PR #5594 (Paid buyer-form extraction, answer-URL normalization, and receipt-alias preservation)
  and PR #5599 (Application occurrence binding) are merged and target-applied from immutable releases.
- The focused Paid tests (158) and Application tests (15) passed before their release cuts, and
  ./bin/lm-loop-contract passed. These are code and release gates, not provider-effect proof.
- Read-only provider context is captured for all five funded IDs. Historical confirmed form receipts
  are preserved for 63659463, 63570481, and 63583795; they are replay-fenced and do not prove
  current formal delivery, acceptance, settlement, or payout.
- A fresh owner-locked detail of canary 63712784 originally confirmed
  `provider_state=funded`, milestone 13833587, latest buyer event 428014314, and two required
  Google Forms. The one-by-one manual execution then returned a contract/event-bound official
  confirmation for each form, sent the exact CrowdWorks milestone delivery once, and read back
  `納品=done`, `検収=current`, the seller message, and `provider_state=delivered` at
  `2026-09-23T04:45:32Z`. It is not a Paid-loop receipt and must not be replayed.
- Contract `63659463` was then completed one-by-one without reposting its already
  confirmed common-test and Web Ads receipts. The buyer's video form was excluded
  because the instruction targets Web広告運用者; milestone `13820867` was delivered
  once and read back at `2026-09-23T04:50:38Z` as `納品=done`, `検収=current`,
  `provider_state=delivered`.
- A fresh official readback of 63657015 (2026-09-23T03:20:52Z) confirms `provider_state=funded`,
  contract `63657015`, milestone `13820268`, proposal `305533319`, and message thread `304733788`.
  The buyer's latest instruction (event `427403807`) requires the non-designer hearing sheet and
  common test; the survey link is not part of that instruction. Both current forms are still
  unconfirmed (`completed_form_urls=[]`), so no form or delivery effect was sent in this check.
- Application's latest aggregate has 190 receipts. Reply's latest aggregate is
  observed=61, readback=54, pending=6, failed=1; unresolved items remain fenced. Paid has no
  current provider effect from the latest target wake.

**Not done / blockers:**

- The three claimed rows and the released Report row still have effect_unknown=1. Paid occurrence
  18d62cf32eb0c678-48194 has an official event pair showing `execute/effect_status=started`
  (2026-09-17T17:48:44Z) followed by `report/effect_status=unknown` (2026-09-17T17:50:14Z),
  with no occurrence-bound provider receipt or no-dispatch marker. It must not be released as
  pre-effect merely because the provider-inventory result was later reported with `effect=0`;
  Application occurrence 18d6535f7dfb8910-33974 and Reply occurrence
  18d64a10f2f1f838-83166 also cannot be released from the available evidence. The Reply wake
  contains authoritative-absent, verified-contract, inconclusive, and confirmation-requested siblings.
- Canary 63712784 now has a verified chain through correct work/form completion and formal delivery,
  but buyer acceptance, settlement, and payout are still unverified. Verified USD 10,000 MRR is zero.
- 63657015 has two current forms and no confirmed receipt; its earlier timed-out intent must be
  reconciled before any retry. The prepared work is the hearing-sheet copy plus common test,
  followed by formal delivery; do not submit the buyer's anonymous survey or claim completion
  until the two official confirmations are read back. 63570481 still lacks the corrected customer-address answer and
  formal delivery. 63568785 still lacks permitted document content. 63659463's formal delivery
  is verified, but acceptance, settlement, and payout remain. 63583795 needs acceptance,
  settlement, and payout readback.
- The latest target cleanup pass is green, but headroom remains PRESSURE at about 1.8 GiB free and one
  ownerless legacy scratch remains protected. The shared cleanup fix is merged and loaded; it requires
  current registry `none`, unique run-bound `none` event, and stale PID/start identity before deleting
  an unrecorded no-effect run. Observed zombie processes are separate exited children, and no virus
  evidence was found in the read-only checks.

**Remaining TODO, in order:**

- [ ] **CW-F1 — host capacity:** monitor another clean disk-cleanup wake and stable headroom. Keep the
  ownerless legacy scratch, credentials, browser profiles, receipts, state, and loaded releases until
  exact owner evidence exists; do not delete it by timestamp or guess.
- [ ] **CW-F2 — Application admission:** use the resolver/readback path to bind
  18d6535f7dfb8910-33974 to an exact no-dispatch marker or official receipt; never retry while
  the effect is unknown.
- [ ] **CW-F3 — Paid admission:** reconcile 18d62cf32eb0c678-48194 from an exact provider receipt
  or occurrence-bound no-dispatch marker. The old paid-latest.json without an occurrence ID is
  insufficient.
- [ ] **CW-F4 — Reply admission:** reconcile 18d64a10f2f1f838-83166 item by item, preserve the
  confirmed contract:63712784 effect and confirmation-requested form effects, and do not resend
  uncertain siblings.
- [ ] **CW-F5 — Report fence:** resolve the released Report row's effect_unknown=1 with the
  resolver/readback path before treating reporting as clean.
- [x] **CW-F6 — 63712784 fulfillment:** manually submitted the common test and Web Ads results
  forms once each, read their official confirmations, pressed CrowdWorks 納品する once, and
  verified the exact milestone state (`納品=done`, `検収=current`, provider `delivered`) at
  `2026-09-23T04:45:32Z`. No replay; Paid-loop occurrence fences remain unchanged.
- [x] **CW-F6b — 63659463 fulfillment:** reused the two existing contract-bound form receipts,
  explicitly excluded the video form per the buyer instruction, pressed CrowdWorks 納品する once,
  and verified `納品=done`, `検収=current`, and `provider_state=delivered` at
  `2026-09-23T04:50:38Z`; no form repost or replay.
- [ ] **CW-F7 — remaining funded contracts:** reconcile 63657015, correct and deliver 63570481,
  obtain permitted content and deliver 63568785, and monitor 63659463 plus 63583795 through
  acceptance/settlement/payout. Require correct_work_verified and replay-zero.
- [ ] **CW-F8 — revenue accounting:** count USD 10,000 MRR only from collected/settled recurring
  value with a documented continuation basis; share contract-ID, quality-gate, and receipt lessons
  through the existing shared kernel only after the same boundary is verified on another provider.

### 4. Lancers vertical proof

Current readback (2026-09-23): `lancers-revenue-paid` is `loaded-idle` with no PID and its latest
run is blocked by `host_admission_deferred:resource_effect_unknown`. The admission ledger still has
`lancers-revenue-paid:18d67a28e56c4b58-6829` as `claimed/effect_unknown=1`; the latest `paid-latest.json`
is `observed=0/effect=0` and is not proof that the occurrence had no effect. No Lancers Paid submission
or provider receipt is counted until this fence and the provider mutation/readback path are resolved.

Fresh official read-only inventory is authenticated and source-complete: 14 message boards, unread 1,
working projects 0, monthly contracts 0, incoming monthly offers 0, storefront contract candidates 0,
contract candidates 0, and Lancers balance 0 JPY. Read-only inspection of historical project details
5601892, 5601332, and one ended proposal found only proposal/question forms; no funded-contract
納品・検収 form or provider receipt is available. Do not implement a guessed mutation from those pages.
The next safe cursor is to observe the first real funded contract detail when the official inventory
produces one, then add a red test and the smallest provider-specific mutation/readback path.

- [x] Phone verification.
- [ ] Restore durable browser availability and persistent authentication.
- [ ] Prove Apply -> Reply -> contract -> Paid -> payout; Storefront only if officially supported.

### 5. Mercor vertical proof

- [ ] Stop repeated login by retaining and observing authenticated state.
- [ ] Prove Apply -> Reply -> interview handoff -> contract -> Paid -> payout.
- [ ] Storefront is `not_applicable`.

### 6. Freelancer.com and Upwork

- [ ] Recover official account/policy state and prove Apply -> Reply -> Paid -> payout on each.
  Current local read-only evidence is insufficient: Upwork's stored snapshot is dated 2026-08-26
  with active contracts 0 and proposal/Connects/payment effects 0, its 9233 CDP endpoint is not
  responding, and Freelancer work-sync has no fingerprints or contract candidates. Treat these as
  unverified, not as a current provider logout; do not register a Paid owner or submit anything.
- [ ] Implement Storefront only where an official provider surface supports it.

### 7. New-platform meta loop

- [ ] Search Web/X daily, qualify policy/automation/expected net value and select profitable platforms.
- [ ] Generate thin adapters against the shared conformance contract.
- [ ] Canary, verify official effect/readback/replay-zero and promote only passing adapters.
- [ ] Feed failures to self-heal and successful patterns to shared skills/evals.

### 8. Recursive self-healing and self-improvement

- [ ] Detect missed replies/deliveries, auth expiry, browser faults, resource starvation and revenue regressions
  from events, metrics and receipts.
- [ ] Reproduce the failure, patch in an isolated worktree, run regression/fault-injection evals, canary,
  promote or roll back, and preserve a terminal repair receipt without Dais or Codex babysitting.
- [ ] Rank improvements by verified revenue impact and safely improve existing loops as well as build new ones.

### 9. Phone-only hosted Life Manager

- [ ] Run the same kernel in tenant-isolated cloud browser/computer sessions.
- [ ] Use Telegram as the only required initial UI; local computers are unnecessary.
- [ ] Use managed agent sessions/sandboxes/handoffs where they reduce custom orchestration, while keeping
  identity, authorization, revocation and audit inside the service boundary.
- [ ] Start subscription billing and prove tenant isolation, reliability and unit economics.

### 10. Revenue and YC gate

- [ ] Count only attributable accepted contracts, payouts and bank receipts.
- [ ] Reach verified USD 10K MRR by cloning profitable end-to-end lifecycles and selling the hosted product.
- [ ] Publish accurate traction, retention, margin and automation metrics in README and the product site.
- [ ] Apply to YC Winter 2027 as a solo founder with measured evidence, not projections.

### 11. Documentation and obsolete-artifact convergence

- [ ] Derive the canonical program-spec name and location from current repository conventions and inbound
  references; migrate this SSOT once and replace every old live pointer with one reference to it.
- [ ] Delete only proved-obsolete duplicate specs, completed temporary artifacts, unused clean clones and
  regenerable caches after exact reference/owner checks. Preserve Codex/cloud sessions, credentials, browser
  profiles, durable memory/state/ledgers/receipts, active evidence, and other owners' worktrees.
- [ ] Prove the surviving tree has one execution SSOT, no broken references, a clean owning branch, and remote
  recovery evidence before removing any local handover path.

## Completion gate

This program is complete only when every applicable platform has a continuously operating profitable
lifecycle, unsupported lanes are explicitly proved `not_applicable`, the meta/self-heal/self-improve loops
operate without babysitting, the hosted phone-only product works, and attributable receipts prove USD 10K
MRR. Larger revenue ambitions remain direction, never a substitute for this measured gate.

### Paid fulfillment checkpoint — 2026-09-24 02:18 JST

- [x] Ryu0820119 was delivered manually once and read back officially at 02:04 JST; keep it out of the loop.
- [ ] Recover at least the loop's 512MiB preflight floor through the allow-listed cleanup owner; current Coconala
  Paid state is scheduled but its latest run is `disk_headroom_low`.
- [x] Push the main-derived source candidate with CrowdWorks/Lancers/Mercor wake coalescing and shared no-effect
  reconciliation; focused loop, Lancers, CrowdWorks, and contract gates pass.
- [ ] Do not promote to production until a funded provider canary has an official receipt and replay-zero readback.
- [ ] Next provider cursor is CrowdWorks `63568785` buyer-material completion; otherwise observe Lancers' first
  funded contract and keep Upwork disabled until authorization, fresh authentication, and a funded contract exist.

### Paid fulfillment checkpoint — 2026-09-24 02:25 JST

- [x] Coconala natural wake passed after headroom recovery (`observed=4`, `effect=0`, `readback=3`); Ryu remains manual-only.
- [x] CrowdWorks natural wake passed (`observed=5`, `effect=0`, `readback=4`, `pending=1`); 63568785 remains buyer-material wait.
- [x] Lancers natural wake passed (`observed=0`, `effect=0`); inventory has no funded contract.
- [ ] Obtain the first admissible funded-provider canary before production promotion; Upwork remains disabled pending authorization and fresh authentication.

### Paid fulfillment checkpoint — 2026-09-24 02:28 JST

- [x] CrowdWorks 63568785's Google document is now readable through `gog drive get`.
- [ ] Keep the item waiting: its required LINE/external-form actions are not an admissible provider effect;
  send only after the buyer supplies permitted material or changes the scope inside CrowdWorks.
- [ ] Do not formal-deliver this item from the readable document alone; retain the quality gate and replay fence.

### Paid fulfillment checkpoint — 2026-09-24 02:36 JST

- [x] Verify all four paid owners are enabled and scheduled; latest natural
  wakes for CrowdWorks and Lancers ended `pass` with no provider effect.
- [x] Coconala remains stable after headroom recovery (`observed=4`,
  `effect=0`, `readback=3`, `pending=0`); Ryu stays manual-only and is not
  replayed by the loop.
- [x] CrowdWorks remains `observed=5`, `effect=0`, `readback=4`, `pending=1`;
  only `63568785` is waiting for admissible buyer material.
- [x] Lancers remains `observed=0`, `effect=0`, `pending=0`; no funded contract
  exists, so the loop correctly performs no submission.
- [ ] Obtain the first admissible funded-provider canary (official receipt plus
  replay-zero readback) before production promotion; do not manufacture one.

### Paid fulfillment checkpoint — 2026-09-24 02:49 JST

- [x] Re-started and read back Coconala Paid; it is `loaded-running`/`pass` on
  the five-minute cadence, with `observed=4`, `effect=0`, `readback=3`, and
  no Ryu replay.
- [x] Started Lancers Paid and observed a natural `pass`; its official snapshot
  is `observed=0`, `effect=0`, `readback=0`, `pending=0` because no funded
  contract exists.
- [x] CrowdWorks remains enabled with four official readbacks and one pending
  buyer-material item (`63568785`); no external send or formal delivery was
  attempted.
- [ ] Continue at the first admissible buyer-material/funded-contract event;
  the source branch still needs a funded-provider canary before promotion.

### Paid fulfillment checkpoint — 2026-09-24 03:02 JST

- [x] Coconala Paid completed the deferred wake through `lm-loop` with
  `loaded-idle`, `last_exit=0`, terminal `pass`, and no provider effect or Ryu
  replay (`observed=4`, `readback=3`, `pending=0`).
- [x] CrowdWorks and Lancers Paid remain enabled on their five-minute schedules;
  CrowdWorks has one buyer-material wait (`63568785`), while Lancers has no
  funded contract. No duplicate or formal delivery was issued.
- [ ] Continue at the first admissible buyer-material/funded-contract event and
  obtain an official funded-provider canary before production promotion.

### Paid fulfillment checkpoint — 2026-09-24 03:08 JST

- [x] Fixed the shared no-effect reconciler for legacy `pre_effect` markers
  without an `effect` field; non-zero and `effect_started` markers remain
  fail-closed. CrowdWorks tests `223`, Paid-kernel tests `32`, and the loop
  contract gate pass.
- [x] Released only exact pre-effect fences: three CrowdWorks occurrences and
  two Lancers no-contract occurrences, each with an occurrence-matched marker;
  no Provider mutation or replay was performed.
- [ ] Keep CrowdWorks occurrence `18d62cf32eb0c678-48194` fenced until an
  occurrence-bound Provider receipt or explicit no-dispatch marker is found.
  Continue the next admissible CrowdWorks buyer-material event, then Lancers'
  first funded contract; Upwork remains disabled pending authorization,
  authentication, and a funded contract.

### Paid fulfillment checkpoint — 2026-09-24 03:12 JST

- [x] Coconala's natural wake recovered from the transient host wait and
  passed with `observed=4`, `effect=0`, `readback=3`, `pending=0`; Ryu remains
  manual-only and was not replayed.
- [x] Lancers is `loaded-idle`/`pass` with a source-complete inventory and zero
  funded contracts; its effect-unknown fence is clear.
- [ ] CrowdWorks remains scheduled behind a finite-slot wait after
  `resource_capacity_busy`; keep its single historical unknown occurrence
  fenced and do not replay. The current provider snapshot is still four
  official readbacks plus buyer-material wait `63568785`.

### Paid fulfillment checkpoint — 2026-09-24 03:18 JST

- [x] Kickstarted Coconala once through managed `lm-loop`; it returned
  `loaded-idle`/`pass` with `observed=4`, `effect=0`, `readback=3`, and no Ryu
  replay.
- [x] Kickstarted CrowdWorks and Lancers once; both stayed enabled but were
  deferred by the existing `resource_capacity_busy` boundary. Their official
  snapshots remain CrowdWorks `effect=0/readback=4/pending=1` and Lancers
  `effect=0/readback=0/pending=0`; no provider mutation occurred.
- [ ] Keep the historical CrowdWorks unknown fence and `63568785` material wait;
  continue at the next permitted CrowdWorks event or funded Lancers contract.

### Paid fulfillment checkpoint — 2026-09-24 03:24 JST

- [x] Re-audited Ryu from the official readback: seller message
  `js-talkroomMessage-222245383` follows the newest buyer events and contains
  the complete requested fix; Ryu remains manual-only and is not resent.
- [x] CrowdWorks and Lancers completed after the finite-slot wake and returned
  `loaded-idle`/`pass`; official snapshots are unchanged at CrowdWorks
  `effect=0/readback=4/pending=1` and Lancers `effect=0/readback=0/pending=0`.
- [x] Source verification passed: CrowdWorks `223`, Lancers `196`, Upwork
  `180`, Coconala/Paid `274`, and `lm-loop-contract`.
- [ ] Keep the CrowdWorks historical fence and `63568785` buyer-material wait;
  no funded Lancers contract or authorized Upwork Paid owner exists yet. Do not
  report source tests as external provider sends.

### Paid fulfillment checkpoint — 2026-09-24 03:28 JST

- [x] Re-observed all current inventories: Coconala has no newer actionable
  buyer event; CrowdWorks `63568785` remains funded but buyer-material-gated;
  Lancers has zero funded contracts.
- [x] Confirmed CrowdWorks' existing occurrence-bound permission-answer receipt
  and latest buyer event `426855154`; no duplicate message or formal delivery
  was issued while the artifact remains inadmissible.
- [x] Confirmed the private Upwork authorization store explicitly denies every
  Paid action and no Upwork owner/CDP exists; the denial was not overridden.
- [ ] Continue at the next permitted CrowdWorks artifact event or funded
  Lancers contract, then obtain the official canary gates before promotion.

### Paid fulfillment checkpoint — 2026-09-24 03:35 JST

- [x] Started Coconala Paid through the managed owner and verified
  `last_exit=0`/`pass`; its scheduled `loaded-idle` state is normal and its
  official inventory has no actionable non-Ryu room.
- [x] Started CrowdWorks Paid through the managed owner and verified
  `last_exit=0`/`pass`; the only pending funded item is `63568785`, which is
  still waiting for permitted buyer material and must not be duplicated or
  formally delivered from the external LINE/form request.
- [ ] Continue at the first permitted CrowdWorks artifact or funded Lancers
  contract; keep Upwork disabled until its explicit authorization, fresh
  authentication, and funded canary exist, then promote only after official
  receipt and replay-zero.

### Paid fulfillment checkpoint — 2026-09-24 03:40 JST

- [x] Diagnosed the scheduler backlog from the authoritative admission DB:
  CrowdWorks Paid has 55 queued zero-effect wakes plus one claimed
  `effect_unknown` occurrence (`18d62cf32eb0c678-48194`), and Lancers Paid has
  55 queued zero-effect wakes.
- [x] Confirmed the coalescing fix exists on the pushed source branch but not
  in the installed CrowdWorks/Lancers releases; this is why repeated wakes do
  not yet converge in production.
- [ ] Keep the exact CrowdWorks unknown occurrence fenced until its own
  provider receipt or pre-effect proof exists. Do not clear the DB or replay it;
  finish the funded-provider canary/replay-zero gate before promotion.

### Paid fulfillment checkpoint — 2026-09-24 03:45 JST

- [x] Resolved the exact Lancers occurrence `18d7fb95eaeaa698-4710` through the
  official pre-effect resolver; its matched completed marker proves
  `effect=0`, and the admission row is `released/effect_unknown=0`.
- [x] Kickstarted Coconala Paid through managed `lm-loop` and verified its
  natural `loaded-idle`/`pass` readback with no actionable non-Ryu room and no
  provider effect.
- [ ] CrowdWorks remains the active next cursor: keep the historical unknown
  `18d62cf32eb0c678-48194` fenced and wait for permitted buyer material for
  `63568785`; no duplicate message or formal delivery is allowed.
- [ ] After the CrowdWorks material event, observe a funded Lancers contract;
  keep Upwork disabled until authorization/authentication/funded-canary gates
  exist, then promote only after official receipt and replay-zero.

### Paid fulfillment checkpoint — 2026-09-24 03:55 JST

- [x] Re-ran the source gates after fixing the existing Coconala writer fixture:
  Coconala Paid `297 passed`, CrowdWorks Paid/reconciliation `123 passed`,
  Lancers adapter `13 passed`, Lancers reconciliation `1 passed`, lifecycle
  `162 passed / 143 subtests`, and `lm-loop-contract` all pass.
- [x] Performed a fresh authenticated read-only Lancers inventory: 14 boards,
  zero working/monthly/storefront contracts, zero incoming offers, and zero
  balance. Ended-job pages have no admissible funded delivery surface, so no
  endpoint was guessed.
- [ ] No queued CrowdWorks/Lancers wake has an exact pre-effect marker; do not
  clear the backlog by DB edit or replay. Promote the pushed coalescing source
  only through the main/release lifecycle after the funded-provider gates.
- [ ] Continue at CrowdWorks buyer-material event, then Lancers' first funded
  contract and Upwork's explicit authorization/authentication prerequisite.

### Paid fulfillment checkpoint — 2026-09-24 04:05 JST

- [x] Ryu remains seller-last under the permanent manual fence; the official
  seller receipt `js-talkroomMessage-222245383` covers the current correction,
  so no resend or formal-delivery click is allowed.
- [x] Coconala Paid completed its managed wake with `loaded-idle`,
  `last_exit=0`, terminal `pass`, and the unchanged official inventory
  `observed=4/actionable=0/effect=0/readback=3/pending=0`.
- [x] CrowdWorks Paid remains enabled with the latest wake `last_exit=0`/
  `pass`; its official inventory is still `observed=5/effect=0/readback=4/
  pending=1`. Work `63568785` remains buyer-material-gated; no duplicate
  message or formal delivery was issued.
- [x] Fresh authenticated Lancers `ELZ-L01` two-pass inventory is identical
  (`02cc770e42dafb093407dc4635c870593a48dd58fbb1b82348635a263f4b410d`),
  logged in/source-complete, 14 boards, zero funded contract candidates,
  zero working contracts, and zero incoming offers.
- [ ] Continue at CrowdWorks `63568785` when a permitted buyer artifact
  arrives; otherwise keep Lancers/Upwork fail-closed and do not promote the
  source branch without the official funded-provider receipt and replay-zero
  gates.
- [ ] Lancers' official guide identifies the post-escrow plan action as
  `完了報告`, but the current authenticated inventory has no funded contract
  page. On the first real ContractReceipt, capture that page's exact DOM/API
  control and official readback before adding any delivery mutation; do not
  guess a selector or endpoint. (https://www.lancers.jp/help/guide/lancer/offer/2)

### Paid fulfillment checkpoint — 2026-09-24 04:10 JST

- [x] CrowdWorks Paid remains terminal `pass`; the five funded observations
  are unchanged: four official completed readbacks and `63568785` waiting for
  permitted buyer material. Latest buyer event `426855154` and its one
  permission-answer receipt remain bound; no duplicate or formal delivery.
- [x] Fresh Lancers `ELZ-L01` two-pass official inventory is identical at
  `4b9b5a4369effd92c35d9930ee404e34736ed511f9e2ec4418a9e73d859350b4`, with
  14 boards, one unread non-required message, source complete, zero contract
  candidates, zero working contracts, zero incoming offers, and zero balance.
- [ ] Keep the next mutation cursor at CrowdWorks buyer-material arrival;
  when a funded Lancers ContractReceipt appears, capture and verify the
  official `完了報告` surface before implementing formal delivery.

### Paid fulfillment checkpoint — 2026-09-24 05:35 JST

- [x] Re-audited the enabled Paid loops: Coconala
  `loaded-idle`/`last_exit=0`/`pass` at `1ac87e32ac26cc60b2e2b52cc2ee72ab57adb48f`,
  CrowdWorks `loaded-idle`/`last_exit=0`/`pass` at
  `f01c612d6448bc2850f3ed951f8dd3485e0cb121`, and Lancers
  `loaded-idle`/`last_exit=0`/`pass` at
  `109f2b3966da3940a901014b4d6ce15d71d37560`.
- [x] Confirmed Coconala's official inventory is
  `observed=4/actionable=0/effect=0/readback=3/pending=0`; Ryu remains
  seller-last under the permanent manual fence and the other three rooms are
  buyer-waiting. No duplicate or formal-delivery mutation is allowed.
- [x] Confirmed CrowdWorks' official inventory is
  `observed=5/actionable=1/effect=0/readback=4/pending=1`; `63568785` is still
  `buyer_task_detail_required`, with buyer event `426855154` and one existing
  permission-answer receipt. The historical `effect_unknown` admission stays
  fenced.
- [x] Confirmed the authenticated Lancers inventory at
  `2026-09-23T20:31:27.295826Z`: 14 boards, zero contract candidates, zero
  working contracts, zero incoming offers, and zero balance. No delivery
  surface exists to bind yet.
- [ ] Wait for the next admissible effect in order: CrowdWorks buyer artifact,
  then Lancers' first funded ContractReceipt; keep Upwork disabled until its
  explicit authorization/authentication/funded-contract gate exists.
- [ ] On the CrowdWorks artifact, verify the task, complete the work, submit
  once through the approved provider effect, and capture official receipt plus
  replay-zero. On the first Lancers ContractReceipt, capture the exact
  `完了報告` DOM/API and readback before implementing formal delivery.
- [ ] Promote the source-branch coalescing/reconciliation work only through
  the main-derived immutable release, targeted apply, natural canary,
  official receipt, and replay-zero gates; installed provider releases above
  must not be treated as containing that source fix yet.
- [ ] After a real completion, verify acceptance, settlement/payout, and
  revision handling; do not equate loop `pass` or a message receipt with
  revenue completion.

### Paid fulfillment checkpoint — 2026-09-24 08:09 JST

- [x] Re-read Ryu's live Coconala room and found the three newer requests:
  external-integration status (02:22), concept-specific ranking setup
  (02:25), and aligned paid-option rows with `IMG_6449.png` (03:15).
- [x] Manually deployed `manual-complete-v700`: `rankingByCategory` for all
  six concepts, admin selectors for 総合＋各コンセプト, and public filtering
  for each configured concept ranking. Exact FTPS evidence:
  The exact FTPS readback is recorded in the external delivery evidence for
  `manual-complete-v700`.
- [x] Manually deployed `manual-complete-v701`: paid options now render as
  one aligned row per option with a fixed name/status grid. Public readback
  loaded `styles.css?v=manual-complete-v701` and verified 5 rows.
- [x] Sent two ordinary manual replies and verified official receipts:
  `js-talkroomMessage-222277933` (ranking/integration, 08:07) and
  `js-talkroomMessage-222278017` (paid-option layout, 08:09). Formal delivery
  was not clicked again.
- [ ] Wait for Ryu's next buyer response; do not resend either reply and keep
  the permanent manual fence in place.
- [ ] Obtain provider URLs, management permissions, filing/review state, and
  connector/API requirements for each external integration; connect and
  read back one provider at a time.
- [ ] Keep the Coconala Paid loop enabled for the three buyer-waiting rooms;
  on a new artifact, process idempotently and verify official readback.
- [ ] CrowdWorks `63568785`: wait for permitted buyer material, then perform
  the correct work/quality check/submission with official receipt and replay-
  zero; keep `18d62cf32eb0c678-48194` fenced.
- [ ] Lancers: wait for a funded ContractReceipt and capture the exact
  `完了報告` control/readback before implementing delivery.
- [ ] Keep Upwork disabled until explicit authorization, authentication, and
  a funded contract exist.
- [ ] Promote the source-branch loop fixes only through immutable main-derived
  release, targeted apply, natural canary, official receipt, and replay-zero.

### Paid fulfillment checkpoint — 2026-09-24 08:47 JST

- [x] Merged PR #5818 at `07f76049fdebcd65a4a1182395dd9f09f4eb1d75` and cut
  immutable main-derived release `20260924T082936-07f76049`.
- [x] Targeted only the three Paid owners: Coconala, CrowdWorks, and Lancers.
  Launchd argv and runtime-event readback for all three match the exact
  release SHA; Ryu remains permanently manual and excluded.
- [x] Coconala natural wake is terminal `pass` with
  `observed=4/actionable=0/effect=0/readback=3/pending=0`.
- [x] CrowdWorks natural wake is terminal `pass` with
  `observed=5/actionable=1/effect=0/readback=4/pending=1`; `63568785` is still
  `buyer_task_detail_required`.
- [x] Lancers is loaded on the exact release with zero effect and zero funded
  contracts. Its latest wake deferred on capacity; the effect-unknown fence
  was not cleared and no provider call was forced.
- [x] Fresh Ryu readback found no buyer message after the 03:15 request; the
  existing 08:07/08:09 manual replies remain the seller-last boundary.
- [x] Stale Camoufox scratch from `verify-loops-audit` passed process/open-handle
  checks and was moved to recoverable Trash; host headroom is now above the
  512 MiB floor.
- [ ] Wait for real buyer/contract artifacts: Ryu follow-up, Coconala buyer
  reply, CrowdWorks task material, and a funded Lancers contract.
- [ ] For the first real effect on each provider, capture the official receipt
  and run replay-zero; do not treat a local pass or no-effect snapshot as a
  delivery.
- [ ] Obtain external-integration permissions/URLs and connect one provider at
  a time with official readback.
- [ ] Keep Upwork disabled until authorization, authentication, and funded
  contract gates are all present.

### Paid fulfillment checkpoint — 2026-09-24 08:18 JST

- [x] Re-ran focused source acceptance on the pushed branch: Coconala `326
  passed`, CrowdWorks/reconciliation `134 passed`, Lancers paid adapter/owner
  `15 passed`, loop lifecycle `286 passed / 174 subtests`, and
  `./bin/lm-loop-contract` PASS (`14/167/97`, no shared IDs/errors).
- [x] Confirmed no new admissible provider artifact appeared while testing:
  Ryu remains a manual-only seller-last room, the other Coconala rooms are
  buyer-waiting, CrowdWorks `63568785` remains buyer-material-gated, Lancers
  has no funded contract, and Upwork remains explicitly disabled.
- [ ] Promote this tested branch through `main` and one immutable release;
  targeted-apply the Paid owners, then verify loaded SHA/argv, natural terminal
  readback, official provider state, and replay-zero.
- [ ] After promotion, process the next real buyer/contract artifact one at a
  time with quality evidence and one idempotent provider submission. Never
  treat a local test or loop `pass` as a client delivery receipt.

### Paid fulfillment checkpoint — 2026-09-24 08:55 JST

- [x] Fresh authenticated Coconala readback of Ryu's official room found no
  buyer message after 03:15; the latest seller messages remain the 08:07 and
  08:09 ordinary replies.
- [x] Confirmed no duplicate send is allowed and formal delivery remains
  untouched for Ryu.
- [ ] On the next genuinely newer Ryu request, perform the full manual
  fix/readback/reply once, then record the official message receipt.
- [ ] Continue waiting for Coconala buyer artifacts, CrowdWorks `63568785`
  buyer material, and a funded Lancers contract; submit only after the
  provider-specific quality and official-receipt gates pass.

### Paid fulfillment checkpoint — 2026-09-24 09:15 JST

- [x] Coconala launchd-owned natural run passed on SHA `07f76049`: 4 observed,
  0 actionable, 0 effects, 3 official readbacks; Ryu stayed manual-only.
- [x] CrowdWorks launchd-owned natural run passed: 5 observed, 4 readbacks,
  and `63568785` remains pending because buyer task material is absent.
- [x] Lancers launchd-owned natural run passed with zero observed contracts;
  the current provider snapshot has no funded ContractReceipt.
- [x] Confirmed no provider effect was performed without a real artifact,
  and the failed direct Lancers invocation had no external effect because it
  lacked launchd's managed environment.
- [ ] Keep the canonical launchd owners running; resolve transient host
  ENOSPC/admission contention before the next artifact-bearing wake, then
  capture provider receipt and replay-zero for the first real effect.

### Paid fulfillment checkpoint — 2026-09-24 09:19 JST

- [x] Fresh authenticated Ryu readback observed the three newer buyer requests:
  external integration status (`222273388`), concept-specific ranking setup
  (`222273444`), and paid-option row alignment (`222273899`).
- [x] Verified the corresponding manual seller replies are present in the
  official room: `222277933` and `222278017`. The room is seller-last; no
  duplicate ordinary reply and no formal-delivery click is permitted.
- [x] The live transaction state is `取引完了` with the formal-delivery
  checkbox still off. Ryu remains a permanent manual-only exception; reopen
  only when a genuinely newer buyer message appears.
