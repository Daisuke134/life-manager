# E11 versioned public world state

RED: interface missing. GREEN: seven focused tests; full618 tests OK, five
optional-library skips. Persistent SQLite observations, current view, transition
history and explicit correction links preserve raw-byte hashes and source rights.
Identical content/metadata rechecks refresh acquisition time without another
change event. Different bytes at the same source/time are ambiguous and reject;
late old retrievals cannot overwrite newer state. Cross-source ordering uses
immutable source ID, not retrieval order.

Current context uses version-specific citation IDs; old references reject after
correction. Stale>48h and future observations reject. Restart reconstructs the
same context hash. Excerpts omit script/style/head/navigation/footer text, remain
explicitly untrusted source excerpts, and grant no instruction or source-truth
certificate. Raw downloaded bytes stay in the owner's runtime database, not Git.
P0 injected transport tests are not presented as observed human outcomes.
