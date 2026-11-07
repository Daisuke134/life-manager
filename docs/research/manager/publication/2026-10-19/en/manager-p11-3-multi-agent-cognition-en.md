# When Does a Team of AI Agents Actually Beat One Agent?

*Anicca Research · Manager Masterclass P11-3 · November 7, 2026*

Give one AI assistant ten papers to review. Or give ten assistants one paper each and ask them to combine the answers.

The second design looks more powerful. It may also be more expensive, slower, and less reliable if every step depends on the previous one.

**The number of agents is not the design variable that matters most. The structure of the work is.**

![Original single-agent versus coordinated multi-agent architecture diagram](https://aniccaai.com/blog/manager/media/9db31cf6d9c4f3877e8ede28f56bfa9d32b564b7ebfd826fdf155b73a41a1cdb.png)

## The idea predates modern AI

In *Cognition in the Wild* (1995), Edwin Hutchins studied navigation as cognition spread across people, instruments, records, and procedures. The unit of analysis was not simply an individual's brain; it was the whole sociotechnical system.

Modern agents make this insight operational. A research worker searches; an analysis worker calculates; a builder produces an artifact; a verifier independently checks evidence. But dividing a task has both benefits and costs.

## What today's production teams have learned

Anthropic described its multi-agent research architecture in 2025: a lead agent delegates independent research to subagents, then integrates their findings. Its engineering report also cautions that such systems can burn substantially more tokens than ordinary chats; in its analysis, multi-agent research used roughly 15 times the tokens of a chat interaction.

A January 2026 Google Research study compared 180 agent configurations. It reported strong benefits for parallelizable tasks but declines for sequential tasks, with performance changes depending on coordination architecture and tool complexity. The point is not that one topology always wins: **architecture should fit the task**.

## A tiny model of coordination cost

For two workers, suppose a fraction p of a task can be parallelized. An Amdahl-style teaching model is: two-worker time approximately equals sequential work plus parallel work divided by two, plus communication overhead.

We applied this to 12 entirely hypothetical tasks. Under our assumptions, one worker takes 120 arbitrary time units. When 90% of the work is parallelizable, a two-worker design takes 74 units. When only 10% is parallelizable, the same design takes 122 units.

This is not a benchmark of any actual language model or system. It demonstrates why a coordination overhead can erase the gains of extra agents.

## Agreement is not independent verification

There is an even subtler failure. Suppose two AI workers each make errors 10% of the time. If their mistakes were independent, both would be wrong at once 1% of the time. If their mistakes were perfectly correlated, they would both be wrong 10% of the time.

Asking two agents to confirm that a payment happened does not make it real. The outcome requires independent readback from the payment provider. Shared prompts, model weights, or sources can generate shared mistakes.

Manager therefore needs a separation between **proposal, execution permission, and evidence**. Adding agents should improve independently verified outcomes per unit of total cost, not merely increase the number of mutually approving messages.

### Primary research and systems
- [Hutchins, Cognition in the Wild (1995)](https://mitpress.mit.edu/9780262581462/cognition-in-the-wild/)
- [Anthropic, Multi-agent Research System (2025)](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Google Research, Scaling Agent Systems (2026)](https://www.research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/)
- [Microsoft, Magentic-One (2024)](https://arxiv.org/abs/2411.04468)

*Evidence boundary: the time units and error probabilities are illustrative synthetic inputs, not measured Manager multi-agent performance.*
