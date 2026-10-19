# What Andon Labs teaches us about benchmark-first AI

A useful benchmark gives an AI a world it cannot improve just by saying that it has succeeded. There are resources, time, constraints, actions, and outcomes that exist outside its prose.

Andon Labs’ Vending-Bench is a concrete example. An agent manages a simulated vending-machine business over a long horizon. It needs to make operational decisions, preserve state, and deal with the consequences. The business ledger is more informative than an agent’s confident description of its progress.

The chronology matters. Andon was in YC Winter 2024. Its own account places the start of Vending-Bench in late 2024, and the public benchmark followed in 2025. This does not support the claim that Vending-Bench got Andon into YC. It does support a different lesson: the evaluation work led to a proposal for a real installation with Anthropic, which became Project Vend.

The bridge from simulation to reality is what interests me. A controlled world exposes failures cheaply and repeatably. A real installation then reveals failures the simulation did not represent: social interactions, operational details, tool limitations, and the cost of human support. Neither stage replaces the other.

For Manager, the benchmark has to ask a broader question than how much a business earns. The ambition is to improve conditions that shape people’s health, time, financial security, and access. An agent can maximize its own revenue while making those outcomes worse. A world-engineering benchmark needs to detect that.

I am designing four separate tracks: prediction, intervention choice, execution, and real outcomes. Prediction asks whether the model understands how people respond. Intervention choice compares structural changes under the same budget. Execution checks actual state changes and failure recovery. Real-outcome evaluation compares independently measured results, including costs and harms.

The architecture should separate the agent, environment, and evaluator. The agent can observe and act through bounded tools. It cannot change the hidden scoring rule, invent resources, or grade its own success. The environment holds resource quantities and transitions. The evaluator records outcomes against frozen baselines and a preregistered protocol.

Inspect AI offers a useful pattern for separating datasets, solvers, and scorers. METR shows the value of measuring tasks with explicit horizons and controlled conditions. Melting Pot tests behavior with different social settings and background populations. AI Economist separates a planner’s institutional decisions from economic agents’ responses. These patterns are reusable without adopting every framework at once.

Commercially, a benchmark-first approach could produce paid evaluation environments, model-comparison reports, or shadow studies for operators. That is a hypothesis to test with buyers. A public leaderboard does not establish demand, and a large synthetic dataset does not become valuable simply because it is large.

Manager is still at the design stage. The next evidence is working code, reproducible runs, fair baselines, and useful failure analysis. There is no need to train a new foundation model to begin. There is a need to build a world and an evaluation that resist flattering answers.

Sources: [Andon YC profile](https://www.ycombinator.com/companies/andon-labs), [Andon: Why we built Pion](https://www.andonlabs.com/blog/why-we-built-pion), [Vending-Bench](https://arxiv.org/abs/2502.15840), [Project Vend](https://www.anthropic.com/research/project-vend-1), [Inspect](https://inspect.aisi.org.uk/tasks.html), [METR](https://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks/), [Melting Pot](https://github.com/google-deepmind/meltingpot), [AI Economist](https://github.com/salesforce/ai-economist). See the accompanying Andon research report for source scope and code snapshots.
