# If a Million AI Agents Talk to Each Other, Have We Predicted Society?

*Anicca Research · Manager Masterclass P11-2 · November 7, 2026*

A habit spreads through a town. One neighbor adopts it, then two friends, then an entire social circle. It is tempting to call this social contagion.

But perhaps similar people simply became friends in the first place. Their similar behavior could be an association, not the consequence of one person influencing another.

As AI-generated societies grow from a few conversational characters to networks with thousands or millions of agents, **believable social stories and valid social predictions must remain separate scientific claims**.

![Original network diagram explaining homophily versus causal peer influence](https://aniccaai.com/blog/manager/media/b5a3a8a0c705146d9a6defb4ce7eb2b5f082e345f2159f9ebe5e027edb142ee4.png)

## The rise of generative societies

Park and colleagues' *Generative Agents* study in 2023 introduced 25 agents living in a virtual town. Memory, reflection, and planning allowed agents to organize encounters and exhibit plausible social behavior.

OASIS extended this direction toward social-media-like environments with feeds, recommendations, comments, and following. AgentSociety explored simulations with more than 10,000 agents and millions of interactions, including exercises involving polarization and responses to shocks.

These are important systems contributions. Yet none of these demonstrations by itself guarantees accurate prediction of new real-world people, cultures, or long-term social outcomes.

## A mathematical trap in social networks

A simple network model connects people as nodes and relationships as edges. We can compute a person's **neighbor exposure**: the proportion of their contacts who have adopted a behavior.

If adoption correlates strongly with neighbor exposure, there are several explanations. Influence or contagion means one person's behavior changes another's. Homophily means similar people select one another as contacts. Common exposure means friends encounter the same news, policies, or environment.

Without stronger assumptions or an appropriate experiment, these explanations are not interchangeable.

## We built a counterexample

Our fully fictional research exercise creates 12 people of two latent types. The network connects each person only to others of the same type. Using neighbors' behavior, the model classifies the person's behavior with **100% apparent agreement**.

The world generator, however, specifies **zero causal peer influence**. The association is entirely produced by homophily.

We built a separate four-node exercise with explicitly stipulated direct and peer-exposure effects. It illustrates what a defined structural model computes; it is not an empirical estimate of social spillovers.

These examples matter because interventions can violate the usual assumption that one person's assignment cannot affect another person's outcome. In causal notation, an individual's result may depend on their own assignment and the assignments of others.

## How to evaluate a social simulation

A robust evaluation should separate individual response likelihoods, population distribution error, network formation, diffusion over time, and true intervention effects. A correct average can conceal severe errors for underrepresented groups. A system that resembles a real network today may fail after institutions or incentives change.

For Manager, a social simulator should be treated as a hypothesis generator until external observations establish where it predicts well—and where it fails.

### Primary research
- [Park et al., Generative Agents (2023)](https://arxiv.org/abs/2304.03442)
- [Yang et al., OASIS (2024)](https://arxiv.org/abs/2411.11581)
- [Piao et al., AgentSociety (2025)](https://arxiv.org/abs/2502.08691)

*Evidence boundary: the 12-person and four-node calculations are synthetic. They do not establish a real social effect or Manager's predictive validity.*
