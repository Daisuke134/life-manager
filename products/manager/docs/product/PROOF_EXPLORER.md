# Read-only digital proof explorer

The existing six-page public service includes `proof.html`, which explains the
evidence boundary and links to the source. Each successful new release additionally
generates a self-contained `proof-explorer.html` and machine-readable
`kernel-public-proof.json` in the existing GitHub Actions readback artifact.
These are views of independently collected public evidence, with no forms,
tracking, participant records or write operations.

Run `scripts/phase06_kernel_release.py prove` with the verified release intent and
the exact Pages commit. The collector fetches the public GitHub commit receipt,
seven files at that SHA, seven files at its single parent SHA, and all six live
pages plus manifest. It rejects a different commit, wrong parent baseline,
unlisted/extra changed paths, mismatched hashes, stale live content and a future
receipt. Supplied JSON alone is only matched data; the pure validator does not
authenticate evidence.

The report distinguishes the original provider transition from the newest
observation. A retry keeps the original committed timestamp and changed pages;
an observation that proposes `NO_ACTION` does not erase that history or pretend
that another release occurred. The effect key is stable for the same candidate,
independent of run ID and observation time.

## What a reader can verify

1. Follow the exact GitHub receipt URL to inspect its commit, single parent and
   seven-path scope. This is the execution occurrence.
2. Read both immutable bundles at their SHA URLs and recompute page SHA-256
   values. Compare the actual changed file set with the provider receipt.
3. Fetch the public service and compare each page's bytes with the candidate.
   A later version is a different observation, not evidence that the prior
   receipt was false or that it should be retried.
4. Keep the outcome fields separate: `P2_ARTIFACT_ONLY` refers to digital bytes.
   Mental, physical and financial human outcomes remain `NOT_MEASURED`.

The report records observations at a timestamp, not a promise that a mutable URL
will never change. Its CI artifacts have bounded retention; immutable source and
provider commit URLs remain the reproducibility anchors. This implementation is
U005 preparation; original U003 interview/selection prerequisites are not closed.
