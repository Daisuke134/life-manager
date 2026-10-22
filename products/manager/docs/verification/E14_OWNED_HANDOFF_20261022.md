# E14 — host-owned narrow publisher handoff

`ManagerKernel.prepare_owned_change` accepts typed host context, recomputes E13 verification, binds the exact public source records and candidate/baseline hashes to the same run, and checks the host scope TTL/revocation/path count. It returns NO_ACTION or an inert `PREPARED_PLATFORM_AUTHORITY_REQUIRED` intent. It does not grant authority.

`phase06_kernel_release.admit_owned` revalidates the source/artifact/scope and original intent lease at admission time, then calls the original seven-file publisher admission. Original repository/ref/workflow identity, immutable source SHA, enabled control, current baseline, fresh source audit and staging guard remain mandatory. SOURCE_REF and the privileged publishing workflow are unchanged. The generic fixture executor remains forbidden for live effects.

RED: new tests failed on absent handoff interface. GREEN: 7 focused tests, 50 existing digital tests, 641 full Python tests (5 optional skips). Existing real-file dry run stages seven allowed files, replays with zero changes, restores the exact old bundle and preserves unrelated.html. Host bridge tests deny missing workflow identity and revoked scope before any staging. These are offline fixture evidence, not authenticated live admission or production deployment.

No external finance task or human effect is completed by this connection. Persistent ownership and a reconciled external occurrence remain E15/E16 gates.
