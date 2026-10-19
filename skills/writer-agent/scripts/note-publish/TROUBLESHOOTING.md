# note-publish troubleshooting

## extract-note-cookies.py fails with "no note session" or "storage_state unavailable"
`extract-note-cookies.py` copies the note.com cookies from the Writer-owned storage_state
`$WRITER_STATE_DIR/note-measure-storage.json` (0600) into `$WRITER_STATE_DIR/note-work/note-cookies.json`.
That storage_state is written by `measure-sales.py` after its own ephemeral headless CloakBrowser
context reaches the note money dashboard (ordinary login with `NOTE_EMAIL`/`NOTE_PASSWORD` from
`LIFE_MANAGER_ENV_FILE` only when the saved session has expired; a failed login backs off for 24 h in
`note-measure-login-backoff.json`). On failure the existing `note-cookies.json` is left untouched.

Fix: let the next `writer-sales-measure` pass refresh the storage_state, then rerun
`publish-to-note.sh cookies`. Check `note-measure-login-backoff.json` if the session stays missing.
Never read or attach to Dais's personal browser (identity `interactive:dais`) to recover cookies.
