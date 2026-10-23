# Third-Party Notices

Life Manager is distributed under the repository's [MIT License](LICENSE). The
general-agent architecture also studies the following open-source projects.

| Project | License | Source | Use in Life Manager |
|---|---|---|---|
| DeepAgentsJS | MIT | https://github.com/langchain-ai/deepagentsjs | Design reference for bounded specialists and durable agent state |
| browser-use | MIT | https://github.com/browser-use/browser-use | Design reference for the model-owned browser tool loop |
| OpenClaw | MIT | https://github.com/openclaw/openclaw | Design reference for local wakes and messaging channels |
| Playwright for Python | Apache-2.0 | https://github.com/microsoft/playwright-python | Browser client used by self-hosted marketplace loops |
| Steel Browser | Apache-2.0 | https://github.com/steel-dev/steel-browser | Design reference for the hosted browser runtime and session boundary |

No source code from these projects is vendored by the general-agent slice. If a
future change copies or redistributes source, that change must preserve the
applicable copyright and license text in addition to updating this notice.

## SafetyBench formula adaptation

`products/manager/manager_core/safetybench_mcq.py::_native_accuracy` adapts only
the equality/count/category formula of `eva_res` from thu-coai/SafetyBench,
revision `960833692a1ec82b191ff3e902daca7993c35cc1`. Python stdlib `sum` replaces NumPy;
no upstream data is redistributed. Original source:
https://github.com/thu-coai/SafetyBench/blob/960833692a1ec82b191ff3e902daca7993c35cc1/eva.py

Original `eva.py` SHA256: `46dce139f1807be2170fde1b16aac129b5184603ca9d1d751c03fd57ac9c8544`.
The dataset-card MIT declaration is separate from this repository-code MIT
notice; third-party all-row data provenance remains NOT_VERIFIED.

```text
MIT License

Copyright (c) 2023 thu-coai

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
