# D011 — Public-source HTTPS authority preflight (2026-11-01 JST)

## Progress authority and boundary
Read `products/manager/docs/roadmap/tasks.json` on `research/manager-product-r006-20261020` at blob SHA `ad26ddcde0a091aaa7224414bc0e1b635b96d58c`: 113 tasks, 69 done, 41 todo, 3 blocked. D011 depends on completed D010 and stays **todo**, not verified income. H005 stays **blocked**: missing public HeartSteps 2019 study-day selection data. F004 and F007 require third-party permission. No change to this canonical state.

## Imozuru chain: question, counter-hypotheses, falsification
- Question: Can a URL that appears to be public HTTPS evidence hide local or ambiguous authority through an empty userinfo prefix, percent-encoded host, root-dot spelling, or noncanonical IPv4 numeric notation?
- Unsafe hypothesis: `https://@example.org`, `https://%6cocalhost`, `https://localhost.`, `https://127.1` can be admitted because a parser yields a nonempty hostname.
- Counter-hypothesis: a rooted public DNS hostname (`example.org.`) or canonical globally routable IPv4/IPv6 literal can be legitimate as a source *identifier*. The validator must not reject these simply because they differ cosmetically.
- Falsification: synthetic unit tests reject 11 ambiguous/private host examples and retain 5 syntactically acceptable global examples. No DNS query or network fetch; this is a structure and policy test, **not** a claim that the URLs exist or are safe for network access.

## First-party primary references
1. IETF RFC 9110 §4.2.4, userinfo deprecation and parsing userinfo as an error for untrusted HTTP(S) URIs: https://www.rfc-editor.org/rfc/rfc9110.html#section-4.2.4
2. IETF RFC 3986 §3.2.2, reg-name syntax, internationalized names and IDNA preference; percent encoding is syntactically allowed for UTF-8, so rejecting *all* percent-encoded hostnames here is an **explicit conservative Manager policy**, not an RFC requirement: https://www.rfc-editor.org/rfc/rfc3986.html#section-3.2.2
3. OWASP-maintained SSRF Prevention Cheat Sheet, alternative IP encodings (hex/octal/dword) and strict IP validation: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
4. CPython urllib.parse docs: parsing preserves percent escapes, and hostname/port should not be treated as fully validated network endpoints: https://docs.python.org/3/library/urllib.parse.html

## Implementation, reproducibility, and limits
- `manager_core/evidence.py::_url`: reject `@` even when username is empty, percent-encoded hostnames, rooted `localhost`/internal suffixes, malformed repeated trailing root dots, and noncanonical numeric hosts. Preserve canonical global IP literals, ordinary public hostnames, and one optional root dot. Reject private/non-global literal addresses as before.
- `tests/test_opportunity_outcomes.py`: two new regression methods with 11 negative and 5 positive synthetic cases; exercises the real `Source` construction used by D011 without personal data or financial APIs.
- Local isolated Python validation of equivalent authority rules: 16/16 synthetic inputs behaved as expected; not a replacement for repository tests.
- Hosted checks to inspect: `python3 -m unittest discover -s tests`, `python3 scripts/check_boundaries.py`, `python3 scripts/make_roadmap.py --check .`, and GitHub Actions on the final commit.
- This change is only an offline input gate. It is **not** a comprehensive SSRF defense, cannot validate DNS resolution, redirects, DNS rebinding, payment receipt authenticity, independent received income, animal/human welfare, or causal impact. Future network access requires separate explicitly authorized network-layer defenses.

No change to Life Manager execution, main, personal information, third-party equipment, communications, or transactions. End suffering is the objective; P0 engineering is not P1–P5 impact evidence.
