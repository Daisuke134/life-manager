# Upstream imozuru excerpt verifier

`report.py` is an unmodified copy of MaryCache/imozuru's `skills/imozuru/scripts/report.py` at Git blob SHA `493b759fcee8328c3dcfc61ba21148afe5957040`, verified with `git hash-object`. Upstream repository: https://github.com/MaryCache/imozuru (MIT).

This vendored **single** script checks whether claimed snippets exactly occur at the indicated lines in locally stored source excerpts. Upstream's full source downloader and OpenAlex chain script are **not** installed or run here: this container has no outbound DNS/network. Original documents were directly retrieved through the GitHub and Firecrawl tools instead, and citation links followed during that investigation. Our excerpts are short and source URLs point to full original texts to avoid re-distributing copyrighted full papers. Hence **the upstream official `report.py` was actually executed, but the full imozuru pipeline was not**.

```sh
python3 tools/imozuru/report.py research/imozuru/manager-foundations --check
python3 tools/imozuru/report.py research/imozuru/manager-foundations
```
