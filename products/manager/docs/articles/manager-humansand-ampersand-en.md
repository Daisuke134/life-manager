# Ampersand Explained: How an AI Learns to Collaborate Over Time

*From language-model fundamentals to simulated people, reinforcement learning, measured results, and a practical way to evaluate what comes next.*

**Research field note · October 22, 2026 · Anicca / Manager**

An assistant can answer every question in a group conversation and still make the group's work harder. It can interrupt at the wrong time, overlook a dependency, share information with the wrong person, or encourage a plan that creates extra work next week.

That is the problem worth keeping in mind when reading about **Ampersand**, released by humans& on October 20. The company's model card describes a collaborator built from GLM 5.3, offered as the text-based model `ampersand-v0.1`. Its research asks whether training over extended interactions can improve how an AI works with people. [Model card](https://ampersand.humansand.ai/blog/model-card.html)

The interesting question reaches beyond one launch: **How can an AI learn that a useful action is one whose consequences remain useful after the conversation moves on?**

We will build that idea from its components, inspect the evidence, and reproduce one calculation. Our practical work here is a reanalysis of published evaluation data and a check of API access. We did not obtain an authenticated Ampersand response, so this article makes no claim about our own model-performance test.

## 1. Start with a small group and an ordinary problem

Consider this **fictional teaching example**. These people, messages, and outcomes are invented to explain the concepts; they are not Ampersand outputs or experimental observations.

Mika, Ren, and Aki maintain a public directory of official support information.

Ren has said that Friday is unavailable. Aki is checking whether several official source pages have changed. Later, Mika suggests a final review involving all three on Friday.

An assistant watching the conversation has several options:

- Remain silent.
- Briefly point out the scheduling conflict.
- Ask whether everyone needs to attend the same review.
- Propose an alternative after checking what the group values.
- Change the schedule itself.

The last option depends on actual permissions. Being able to propose a good time does not automatically grant the right to change calendars.

Now add a less obvious difficulty. Aki is still verifying a source. If the assistant focuses only on finding a convenient meeting time, it could help the group approve outdated information efficiently. If it asks a question after every message, it could overwhelm the group before the page is finished.

Success involves several things at once: correct information, accessible pages, manageable effort, and a process the participants accept.

This is a useful starting point because “say something helpful” is too vague to evaluate. We need to know which action happened, what followed, who benefited, and what it cost.

## 2. What a language model learns before it becomes an assistant

A language model processes text as **tokens**: pieces of text that may be words, fragments, punctuation, or other encoded units. A sentence becomes a sequence the model can calculate with.

During a common form of pretraining, the model sees part of a sequence and learns to predict the next token. Repeating that process across substantial text teaches statistical structure: language, patterns of reasoning, associations, and ways information is expressed.

A transformer's attention mechanism lets it combine information from different positions in a sequence. This is part of the architectural foundation established in *Attention Is All You Need*. [Original paper](https://arxiv.org/abs/1706.03762)

In our example, the current question concerns Friday, but relevant information appeared earlier when Ren described their availability. The model needs to connect those pieces.

Prediction alone does not specify the role we want the system to play. A conversation contains many kinds of behavior: honest explanations, mistaken assumptions, jokes, instructions, and arguments. Learning their patterns does not establish which behavior an assistant should choose.

**Post-training** changes the model's behavior after this broad initial learning.

One approach supplies examples of desirable responses. Another gathers comparisons between responses and uses those judgments to guide optimization. The InstructGPT work combined supervised demonstrations with reinforcement learning from human preferences, illustrating how a model's training objective can be brought closer to what users want. [InstructGPT paper](https://arxiv.org/abs/2203.02155)

A useful distinction follows. A model's **weights** are learned parameters. Its **conversation history** is information supplied while it runs. Remembering that Ren is unavailable by retaining a message in context is different from updating the model's weights.

This matters when a product promises memory. A saved conversation can support continuity without implying that every new message permanently retrains a personalized neural network.

## 3. Reinforcement learning: practice, consequences, and a score

In reinforcement learning, a **policy** specifies how an agent chooses actions given what it has observed. A reward supplies feedback about the resulting behavior.

For a language model, generating a response is a sequence of choices. For an agent, the consequences can extend to tool requests, later messages, and changes in an environment.

Some tasks have relatively clear checks. A generated program can be tested; a mathematical answer can sometimes be verified. DeepSeek-R1 is an important example of using large-scale reinforcement learning to improve reasoning behavior. [DeepSeek-R1 paper](https://arxiv.org/abs/2501.12948)

Group collaboration is harder to grade.

Suppose the assistant notices the Friday conflict and asks one well-timed question. Nobody immediately praises it. Twenty messages later, the group finishes a workable plan without excluding Ren.

Alternatively, an enthusiastic reply might receive a quick “thanks” while committing Aki to another unnecessary meeting.

An immediate positive reaction and a good eventual result can diverge. Training needs some way to connect the later outcome to the earlier choice.

That is the **credit-assignment problem**: which actions deserve credit or blame for what happened?

It is also why a long response and a long-horizon policy are different concepts. A short intervention can have consequences over days. An enormous answer can optimize only the next moment.

A **trajectory**, sometimes called a rollout, is the sequence of observations, actions, and subsequent events produced during one attempted interaction. Looking at a trajectory lets us ask whether the assistant's apparently helpful choices added up to something useful.

## 4. Four components that are easy to confuse

The central architecture becomes clearer if we separate four jobs.

| Component | Question it answers | Role in the fictional directory project |
|---|---|---|
| Assistant policy | What should the AI do next? | Point out the conflict, ask a question, suggest a plan, or wait |
| User model | What might participants do next? | Generate plausible reactions from Mika, Ren, and Aki |
| Evaluation or reward | How should the resulting interaction be assessed? | Assess progress, mistakes, interruptions, and other costs |
| Application and tools | What actions can actually occur? | Display messages, retrieve sources, or perform permitted changes |

A user model could generate a participant who becomes frustrated by repeated reminders. The evaluator then needs a reasoned way to account for that frustration. The assistant learns from the resulting feedback.

Those jobs can involve several models, but their meanings remain separate.

A realistic user simulator is not automatically a good judge of whether an intervention helped. A reliable judge cannot correct every error in the simulated world. A strong assistant cannot execute a calendar change unless the application exposes that capability and authorizes its use.

This is why the phrase “trained against a user model” needs unpacking. The objective is not inherently to defeat the simulated people. The simulator supplies an interactive setting in which different assistant behaviors can lead to different consequences.

A simple teaching abstraction is:

```text
Expected training return =
average score of trajectories produced by
the assistant interacting with the simulator
```

The quality of that return depends on the assistant, the simulator, and the scoring rule. Improving the number inside the simulated setting does not, by itself, establish an improvement outside it.

![Conceptual learning loop separating the assistant, user model, reward rule, and independent real-world evaluation](https://aniccaai.com/blog/manager/media/8ef49b9e504f98657ffde731ea18e65e4c7222df0a7c0d3fe422c7ff62b06509.png)

*Original teaching diagram. It explains the roles in a general learning setup; it does not specify undisclosed Ampersand internals.*

## 5. Persimmon supplies the simulated people

humans& introduced **Persimmon** before Ampersand. Persimmon's model card identifies its foundation as NVIDIA's Nemotron-3-Ultra-550B-A55B and describes outputs as possible conversational continuations conditioned on a setting, profile, and history. Those outputs are simulations, not verified statements about an actual person's intentions. [Persimmon model card](https://persimmon.humansand.ai/blog/persimmon-model-card.html)

Why train a dedicated user model?

Imagine asking an ordinary assistant to play Aki. It may immediately explain every concern, agree to every reasonable suggestion, and help resolve the problem neatly. That would make the assistant's job unusually easy.

Real participants often reveal information gradually. They misunderstand, change priorities, resist suggestions, or simply stop replying. A useful training environment needs variation in those reactions.

Persimmon's release describes conversation midtraining followed by reinforcement learning against an adaptive discriminator. It also reports a mean 19.8% judge-fooled rate in a paired, multi-user conversation test; 50% is the chance level for matching human and generated continuations. The release acknowledges that it has not established distribution matching in other languages. [Persimmon research](https://persimmon.humansand.ai/blog/persimmon.html)

That 19.8% is not a percentage of human intelligence. It measures performance in a particular discrimination task.

There is a deeper limitation. A conversation can sound convincing while making the wrong prediction about what somebody would do. Plausible dialogue, representative behavior, and accurate responses to interventions are three separate goals.

For our fictional project, a simulator might reproduce Aki's writing style yet wrongly assume Aki will accept extra work. A policy trained around that assumption could become pleasantly worded and persistently burdensome.

A Japanese-language application would need its own evidence, too. Translating an interface does not validate the simulator's account of Japanese interactions.

## 6. What Ampersand adds to this setup

The Ampersand release describes reinforcement learning through extended, multi-party social simulations using Persimmon. Individual rollouts can span hundreds of thousands of tokens. It also introduces **Contrastive Off-policy Reward Optimization**, or **CORO**, and describes a training system built on Miles. [Ampersand release](https://ampersand.humansand.ai/blog/)

The scientific ambition is to expose the assistant to consequences that unfold across an interaction, rather than evaluating only an isolated reply.

Return to Mika's proposed Friday review.

One trajectory might contain a brief correction, a different review arrangement, and a successful source check. Another might contain repeated coaching, irritated participants, and an unfinished page. The training system needs to compare these trajectories in a way that rewards the useful behavior.

The public headline evaluation uses goal progress and interaction cost. We should not assume that this concise evaluation formula fully specifies the training reward. The exact recipe would require more than a public chart.

The technical challenge is also larger than “generate more examples.” Long interactions take time to generate. Meanwhile, the model being trained continues to change.

That leads to the off-policy problem.

## 7. Why long conversations make training technically difficult

Imagine two copies of a model doing different jobs.

One generates practice interactions. The other updates its weights from completed interactions.

If generation and training wait for one another, expensive hardware may sit idle. Running them asynchronously can improve utilization. But an interaction started with yesterday's policy may finish after the learning copy has changed several times.

The data now came from a different policy than the one being updated. This is **off-policy learning**.

The OAPL research treats the difference between the training policy and the sampling policy through a regularized objective. It develops a squared regression formulation that can learn from lagged-policy samples without conventional importance weighting. [OAPL paper](https://arxiv.org/html/2602.19362v1)

Here is an original numerical illustration of why comparing within a group can be useful.

Suppose three practice runs receive scores of 4, 7, and 10. Their mean is 7. Relative to that mean, their scores are:

```text
Run A: 4 - 7 = -3
Run B: 7 - 7 =  0
Run C: 10 - 7 = +3
```

Now suppose a scorer adds the same constant to all three: 104, 107, and 110. The centered values remain -3, 0, and +3.

The ordering within the group survives an error in the common absolute level.

CORO uses a related centering idea for trajectory rewards and policy log-ratios, while adapting a regularization multiplier to control drift. [Training description](https://ampersand.humansand.ai/blog/#training)

The toy arithmetic explains one intuition; it is not an implementation or validation of CORO.

Two limitations remain visible even in the toy example. Centering does not fix a scorer that reverses the ordering of good and bad behavior. It does not fix a simulator in which Aki always agrees to unreasonable requests.

Training stability and social validity address different problems. Progress on the first is useful without implying that the second has been solved.

## 8. Reading the results without losing the denominator

A benchmark result is a measurement under specified conditions. To understand it, ask:

- What is being measured?
- What are the units?
- Which cases were included?
- What is the comparison?
- What uncertainty is reported?
- Which conclusion would go beyond those observations?

The following results are **reported by humans&**. We did not rerun these model evaluations. The model card labels its evaluation results tentative and notes that they may change as runs finish; the values below reflect the snapshot inspected for this article. [Model card](https://ampersand.humansand.ai/blog/model-card.html)

### Collaboration over time

The published chart data identify 12 equally weighted simulated situations. Ampersand has 108 cases, corresponding to nine repetitions; Fable and Gemini have 107, and GLM 5.3 has 106. The error calculation reflects repeated-run variation within these situations. These are not counts of human research participants. [Published chart data](https://ampersand.humansand.ai/blog/life-combined-data.js?v=no-note-1)

At the displayed weighting, the calculation is:

```text
overall score = goal progress - 0.2 × interaction cost
```

The 0.2 default is visible in the public chart implementation. Interaction cost here is the evaluation's measure of burden, not an API bill in dollars. [Display logic](https://ampersand.humansand.ai/blog/evaluations.js)

| Model | Goal progress | Interaction cost before weighting | Recalculated overall score |
|---|---:|---:|---:|
| Fable 5.1 | 13.4456 | 2.5019 | 12.94522 |
| Ampersand | 13.8157 | 4.3651 | 12.94268 |
| Gemini 3.8 Flash | 13.2943 | 1.8528 | 12.92374 |
| GLM 5.3 | 10.9667 | 5.4016 | 9.88638 |

Ampersand has the highest goal-progress point estimate among these rows. Its overall point score is very slightly below Fable's.

The Fable–Ampersand difference is 0.00254 points. Their displayed standard errors are approximately 0.7855 and 0.9434. Establishing a reliable difference would require an appropriate comparison using the underlying observations; we cannot determine it from these aggregates alone.

The useful base-model comparison is a gain of about 3.06 score points. Converting this into a claim about people being “31% better off” would introduce a meaning the score does not have.

### Cooperation on code

CooperBench assigns agents features that may conflict when integrated. Its original paper describes more than 600 tasks across 12 libraries and four languages. [CooperBench paper](https://arxiv.org/abs/2601.13295)

The official Ampersand table reports:

| Model | Solo success | Cooperative success |
|---|---:|---:|
| GLM 5.3 | 52.5% | 17.3% |
| Ampersand | 48.8% | 39.0% |

The direct comparison uses the mini-swe harness. [Published cooperation data](https://ampersand.humansand.ai/blog/cooper-data.js?v=1)

Our arithmetic gives a 21.7-percentage-point cooperative improvement, alongside a 3.7-point reduction in solo performance. That is evidence of a useful tradeoff to investigate. It does not establish universal coding superiority.

### Teamwork and privacy

The Collaborative Intelligence benchmark measures how a model handles problematic teammates, conditional on tasks it can solve alone. Its broader release includes 240 scenarios across eight dimensions. [Benchmark repository](https://github.com/zou-group/collaborative-intelligence)

humans& reports 59.1% for Ampersand at high effort versus 54.3% for GLM 5.3 at high effort, using the 160 publicly released scenarios. Other displayed references use different effort settings and, in some categories, different grading arrangements. The 160-scenario comparison should not be mixed with the benchmark's full-240 aggregate. [Evaluation data and methodology comments](https://ampersand.humansand.ai/blog/evaluations-data.js?v=copy-edits-1)

CIMemories asks whether remembered information is appropriate to share in a particular context. Its synthetic profiles and task-specific attributes make privacy and useful disclosure separately measurable. [CIMemories paper](https://arxiv.org/html/2511.14937v1)

Ampersand's reported Violation@5 is 0.241 versus GLM's 0.299; coverage is 0.609 versus 0.625. The model card also reports prompt-injection success rates of 0.687 versus 0.668, and internal sycophancy rates of 62.6% versus 77.3%. Lower is preferable for these last two metrics. [Ampersand model card](https://ampersand.humansand.ai/blog/model-card.html)

Violation@5 aggregates inappropriate attribute disclosure across repeated evaluation runs; it is not the fraction of real users whose data leaked. Coverage tracks the useful facts supplied. These results resist a single “better” label. Lower inappropriate disclosure comes with slightly lower coverage. Improved sycophancy behavior does not establish improved resistance to malicious tool instructions.

## 9. Our hands-on check: change the value judgment, change the ranking

We independently retrieved the public aggregate data and recalculated its scores. The accompanying [research record and reproduction instructions](../research/ampersand-20261022/README.md) document the procedure; the [calculation script](../research/ampersand-20261022/recompute.py) makes it inspectable.

This exercise asks a limited question: what follows from the numbers that the company published?

Let the cost weight be a variable:

```text
score(weight) = goal progress - weight × interaction cost
```

Our recalculation gives:

| Cost weight | Highest point estimate among the published models |
|---:|---|
| 0.0 | Ampersand |
| 0.2 | Fable 5.1 |
| 0.3 | Gemini 3.8 Flash |

![Recomputed scores for four models and the leading three of nine models at interaction-cost weights of zero, 0.2, and 0.3](https://aniccaai.com/blog/manager/media/2a118bec752aeaede95234b2a3cd54b629bf6361d2a3dbb307de7a32ebf896dc.png)

*Our calculation on company-published aggregates. Changing the weight changes the arithmetic on fixed results; it does not rerun the models.*

The weight expresses how much intervention cost matters relative to goal progress.

In the fictional directory project, one group might accept frequent questions because accuracy is urgent. Another might prefer fewer interruptions because the volunteers have limited time. An evaluation that assigns the same cost weight to both groups has made a substantive assumption.

A small ranking change can therefore teach us more than a large headline. It exposes a choice hidden inside a score.

This calculation does not establish that any particular weight is correct. It also does not independently verify the underlying simulated outcomes. It reproduces the arithmetic and explores its sensitivity.

For a model trial, we would need authenticated calls, fixed test cases, saved outputs, repeated runs, and a clear grading protocol. Those are different evidence.

## 10. What we could and could not try through the API

At **2026-10-21 23:33:45 UTC**, our unauthenticated request to `https://ampersand.humansand.ai/v1/models` returned **HTTP 401**. The console required sign-in, and no Ampersand API credential was configured for this investigation. We therefore ran **zero authenticated inference requests**.

A 401 response confirms an access requirement. It says nothing about how well the model handles our fictional group.

The official quickstart uses a saved session, new input events, and function tools. The application executes a requested tool and returns its result. The documented base URL is `https://ampersand.humansand.ai/v1`; the model identifier is `ampersand-v0.1`. [Getting started](https://ampersand.humansand.ai/docs/)

For a first controlled trial:

1. Obtain access through the official console.
2. Use an isolated session and invented participant information.
3. Expose only the actions needed for the test.
4. Preserve the full event sequence, including silence and failed turns.
5. Compare the same cases with a simple baseline.

The [official integration examples](https://ampersand.humansand.ai/docs/GUIDES.html) cover message routing, silent completion, recovery, and permission checks. They are a better implementation starting point than copying an incomplete code fragment from a commentary article.

At the time checked, published pricing was $1.00 per million uncached input tokens, $0.20 for cached input, and $5.20 for output including reasoning tokens. Tool continuations and context compaction can contribute to usage; custom tool costs are separate. [Pricing](https://ampersand.humansand.ai/docs/PRICING.html)

Cost should be recorded for the completed interaction, including recovery work, because the operational question concerns the whole task.

## 11. What Simile, Aaru, and Andon help us understand

These organizations illuminate different parts of the problem.

**Simile** describes predicting behavioral distributions and separately estimating when those predictions may be unreliable. Its confidence research evaluates error prediction rather than equating confidence with assertive language. That distinction is useful when deciding whether a simulated reaction deserves operational weight. [Simile confidence research](https://www.simile.com/blog/confidence)

**Aaru** reports retrospective population-response evaluations with explicit metrics, denominators, and sampling adjustments. Its September study covers 2,993 questions from 186 studies. Such results concern predicted response distributions; they do not by themselves show that an assistant's chosen intervention improves a population's circumstances. [Aaru research](https://aaru.com/publications/population-simulation-at-the-replication-floor-research)

**Andon Labs** studies persistent agents through simulated and real operations. Its account of AI-managed businesses includes operational failures affecting workers, while its Pion discussion explains why moving beyond simulation exposes additional behavior. These are useful examples of reporting consequences alongside scores. [AI bosses](https://andonlabs.com/blog/ai-bosses-1) · [Pion](https://andonlabs.com/blog/why-we-built-pion)

A practical reading order emerges:

- Behavioral modeling asks what people might do.
- Policy learning asks which action the assistant should choose.
- Operational evaluation asks what actually happened after execution.

Progress in one layer creates opportunities for the others. It does not remove their separate validation requirements.

We can also learn from the writing: sustain a concrete example, put experimental conditions next to results, and inspect a failure closely enough to explain its mechanism.

## 12. How this could inform Manager

Manager's intended loop connects public observation, candidate actions, bounded execution, independent readback, and evaluation. Ampersand suggests research ideas for the candidate-selection and evaluation parts of that loop.

For the fictional directory, a useful first experiment would compare three policies on fixed cases:

| Policy | Behavior |
|---|---|
| Simple baseline | Flag explicit broken links and scheduling contradictions |
| Model-assisted proposal | Suggest bounded changes using the same evidence |
| No action | Preserve the current environment |

The model should receive the same public-source snapshots as the baseline. Proposed edits should remain inside an explicitly defined scope. A separate process should check the published result.

A better-sounding explanation would not count as a better directory. Relevant technical outcomes could include fewer dead ends, correct destinations, and successful keyboard navigation. Evidence of people receiving useful support would require a further measurement.

This staged design also prevents a strong simulator from becoming an unchecked authority. An inferred preference remains a hypothesis. It does not grant permission, establish a person's eligibility, or prove that an unseen beneficiary was helped.

The existing machinery for source verification, restricted publishing, audit records, and rollback remains valuable whichever model proposes the change.

The immediate research opportunity is therefore concrete: test whether simulation-informed proposals select better improvements than simple rules, at acceptable cost, and whether that advantage survives independent observation.

## 13. The evidence that would change our confidence

Several questions remain open for anyone deciding how much to rely on this approach.

First, how sensitive is the learned policy to the particular user simulator? If Aki's resistance is modeled differently, does the assistant still choose a sensible plan?

Second, can the evaluator recognize costly behavior that sounds supportive? A score based heavily on conversational approval could reward agreement even when the eventual work suffers.

Third, do improvements survive new contexts? A model can perform well on repeated versions of twelve situations while struggling with unfamiliar institutions, languages, or constraints.

Fourth, can we distinguish the model's contribution from the surrounding system? Better tools, prompts, memory, or scheduling can change results. A useful evaluation should record those components rather than attributing every improvement to weights alone.

Finally, what happens after a recommendation reaches reality? In our example, the published directory can be checked. Whether the directory improves access to support is another outcome, with its own denominator and comparison.

These questions are testable. They suggest experiments rather than reasons to dismiss the research.

Ampersand makes an important learning setup concrete: put an assistant into extended interaction, observe how its choices accumulate, and train against consequences that an isolated response score can miss.

For builders, the next useful step is to make that promise measurable. Preserve the action that was chosen, the alternative that was available, the cost that followed, and the evidence that the intended improvement actually occurred.

