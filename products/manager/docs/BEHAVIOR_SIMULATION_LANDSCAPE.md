# Behavioral simulation: source map (2026-10-20)

This is a curated map, not an exhaustive or independently ranked list. Companies' claims remain attributed to them. No outreach has been sent.

| Layer | People / work | What to study / possible reuse | Original source | Reading scope |
|---|---|---|---|---|
| Research instruments | Robin Horton, John Horton; Expected Parrot / EDSL | Structured instruments; agent/scenario/model separation; cache; human validation | https://docs.expectedparrot.com/en/latest ; https://github.com/expectedparrot/edsl | Official docs, README, MIT license |
| Individual cognition | Binz et al.; Centaur / Psych-101 | Predict choice trajectories; compare held-out tasks and cognitive baselines | https://www.nature.com/articles/s41586-025-09215-4 | Main methods/results |
| Responses across experiments | Kolluri, Wu, Park, Bernstein; SocSci210 | Study-level splits; distribution vs individual accuracy | https://arxiv.org/html/2509.05830v1 | Paper and author repo |
| Generative agents | Park et al. | Memory, reflection, planning; not welfare validation | https://arxiv.org/abs/2304.03442 ; https://github.com/joonspk-research/generative_agents | Abstract and author repo |
| Social environment | Vezhnevets et al.; Concordia | Action proposals vs environment resolution | https://github.com/google-deepmind/concordia | Official README and prior report |
| Population interaction | Chopra; AgentTorch | Differentiable, scalable agent-based models; inspect empirical calibration | https://github.com/AgentTorch/AgentTorch | Official README; not installed |
| Behavioral model plus confidence | Simile; Wesel, Chen, Liang | Held-out errors and error prediction; proprietary data | https://www.simile.com/blog/confidence | Full original article |
| Population and purchase simulation | Aaru | Survey repeatability; purchase validation; not merely LLM persona | https://aaru.com/publications/population-simulation-at-the-replication-floor-research | Company evaluation; not independently reproduced |
| Networked grounded AI audiences | Artificial Societies / Radiant; James K. He, Felix P. S. Wallis, Edoardo Chidichimo, Min Jun Jung | Three-stage persona genesis / social graph / simulation; survey, interview, focus groups; compare to human panels and measure wording shifts | https://societies.ai/radiant ; https://societies.ai/eval ; https://arxiv.org/abs/2609.30030 | Product and evaluation pages plus original paper; company 2026 scores not independently reproduced; 12 vs 20 minimum inconsistency |
| Intervention evaluation | Klasnja, Murphy and collaborators; HeartSteps | Micro-randomization; outcome windows; missingness; attenuation | https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/ | Original plus prior appendix/code |
| Critical review | Larooij, Törnberg | Operational validity and calibration; follow references | https://link.springer.com/article/10.1007/s10462-025-11412-6 | Original review |
| Causal forecasting audit | Li, Ji | Descriptive fidelity vs treatment-effect accuracy | https://arxiv.org/html/2604.02458v1 | Original with reported limitations |
| Unknown entity | User-spoken Persuade Lab | Resolve identity before comparison or outreach | Not established | Searches insufficient |

Manager overlap: research instruments, simulation, held-out evaluation. Proposed difference: public-information welfare objective, authorized macro actuation, cost/harm-aware independent outcomes. This integration is not yet empirically proven. Public documentation cannot establish every competitor's entire capabilities or that no other company has the same objective.

## Radiant updated research note (2026-10-21)

The existing Artificial Societies company entry now links the **Radiant** research interface and methodological work; it is one company, not a new brand counted as a separate firm. The staged pipeline—real-world evidence → validated belief profiles → influence networks → simulations / qualitative follow-ups—has notable overlap with Simile and Expected Parrot. The in-house October benchmark (68,280 model answers from 2,796 respondent profiles) compares against nine LLMs and reports mean population TVD 0.08 vs 0.31, but independent deployment welfare or intervention causal accuracy is **not established** by that benchmark. [Deep Japanese source audit](research/societies/RADIANT_2026-10-21_JA.md).
