from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.dml import MSO_THEME_COLOR
from pathlib import Path
import textwrap, os

OUT=Path(os.environ.get('MANAGER_DECK_OUTPUT', 'Manager_Behavior_Simulation_Research_Lab_v2_2026-10-21.pptx'))
HERO=Path(os.environ.get('MANAGER_DECK_HERO', 'manager_city_hero_2026-10-21.png'))
prs=Presentation(); prs.slide_width=Inches(13.333); prs.slide_height=Inches(7.5)
NAVY=(11,19,43); DEEP=(15,31,52); PANEL=(25,51,75); PANEL2=(30,69,85); GREEN=(75,213,180); TEAL=(24,148,146); SKY=(126,197,236); BLUE=(89,164,227); WHITE=(247,251,255); LIGHT=(215,230,237); MUTED=(153,180,191); GOLD=(255,188,99); RED=(252,129,120); SLATE=(63,87,107); PURPLE=(174,147,242)
FONT='Liberation Sans'

def rgb(col): return RGBColor(*col)
def box(slide,x,y,w,h,color=PANEL,r=.08,stroke=None,outline=1):
    sh=slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if r else MSO_SHAPE.RECTANGLE,Inches(x),Inches(y),Inches(w),Inches(h))
    sh.fill.solid();sh.fill.fore_color.rgb=rgb(color)
    if stroke: sh.line.color.rgb=rgb(stroke);sh.line.width=Pt(outline)
    else: sh.line.fill.background()
    if r: sh.adjustments[0]=r
    return sh

def line(slide,x1,y1,x2,y2,color=GREEN,width=2):
    s=slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,Inches(x1),Inches(y1),Inches(x2),Inches(y2));s.line.color.rgb=rgb(color);s.line.width=Pt(width);return s

def txt(slide,msg,x,y,w,h,size=17,color=WHITE,bold=False,align=None,margin=.025,spacing=1.12):
    s=slide.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h));tf=s.text_frame;tf.clear();tf.word_wrap=True
    tf.margin_left=tf.margin_right=Inches(margin);tf.margin_top=Inches(.01);tf.margin_bottom=0
    for i,row in enumerate(str(msg).split('\n')):
        p=tf.paragraphs[0] if i==0 else tf.add_paragraph();p.text=row;p.font.name=FONT;p.font.size=Pt(size);p.font.bold=bold;p.font.color.rgb=rgb(color);p.space_after=Pt(4);p.line_spacing=spacing
        if align is not None:p.alignment=align
    return s

def base(title,kicker='',ref='',subtitle='',light=False):
    s=prs.slides.add_slide(prs.slide_layouts[6]);box(s,0,0,13.333,7.5,NAVY,r=0)
    box(s,.66,.48,.075,.39,GREEN,r=0)
    txt(s,kicker.upper(),.89,.45,10.8,.22,11,GREEN,True)
    txt(s,title,.84,.94,11.8,.70,28,WHITE,True)
    if subtitle:txt(s,subtitle,.88,1.60,11.6,.34,13,MUTED)
    box(s,.88,7.02,11.5,.012,SLATE,r=0)
    txt(s,'ANICCA / MANAGER  •  BEHAVIOR × AGI RESEARCH   •   OCT 21, 2026',.88,7.10,8.9,.23,9,MUTED)
    txt(s,f'{len(prs.slides):02d}',12.06,7.08,.36,.23,10,GREEN,True,PP_ALIGN.RIGHT)
    if ref:txt(s,ref,.89,6.72,11.50,.24,9,MUTED)
    return s

def card(slide,x,y,w,h,head,body,accent=GREEN,fs=15,hs=17):
    box(slide,x,y,w,h,PANEL,r=.06);box(slide,x+.22,y+.20,.067,.32,accent,r=0)
    txt(slide,head,x+.41,y+.21,w-.65,.36,hs,WHITE,True)
    txt(slide,body,x+.25,y+.77,w-.5,h-.85,fs,LIGHT)

def smallcard(slide,x,y,w,h,head,body,accent=GREEN):
    box(slide,x,y,w,h,PANEL,r=.06);txt(slide,head,x+.18,y+.15,w-.3,.30,15,accent,True);txt(slide,body,x+.18,y+.55,w-.36,h-.62,13,LIGHT)

def badge(slide,t,x,y,w,col=TEAL):
    box(slide,x,y,w,.36,col,r=.20);txt(slide,t,x+.02,y+.058,w-.04,.25,11,WHITE,True,PP_ALIGN.CENTER)

def metric(slide,x,y,w,big,label,color=GREEN):
    box(slide,x,y,w,1.28,PANEL,r=.07);txt(slide,big,x+.21,y+.19,w-.42,.54,30,color,True);txt(slide,label,x+.22,y+.85,w-.44,.25,12,LIGHT)

def rows(slide,items,y=2.0,left=.85,width=11.6,rowheight=.72):
    for i,(a,b) in enumerate(items):
        yy=y+i*rowheight;box(slide,left,yy,width,rowheight-.09,PANEL,r=.035)
        txt(slide,a,left+.19,yy+.10,3.1,.42,15,GREEN,True)
        txt(slide,b,left+3.35,yy+.10,width-3.60,.45,14,WHITE)

def horizontal(slide,labels,y=3.05,start=.90,width=11.5,cols=None):
    n=len(labels);gap=.15;unit=(width-(n-1)*gap)/n
    for i,(title,body) in enumerate(labels):
        x=start+i*(unit+gap);smallcard(slide,x,y,unit,1.49,title,body,GREEN if i<3 else GOLD)
        if i<n-1: line(slide,x+unit,y+.73,x+unit+gap,y+.73,SKY,2)

def notes(slide,narration,sources):
    try:
        tf=slide.notes_slide.notes_text_frame
        tf.text='PRESENTER NOTES\n'+narration+'\n\nSOURCES\n'+'\n'.join(sources)
    except Exception:pass

def bar(slide,x,y,w,h,label,val,maxval,col=GREEN):
    txt(slide,label,x,y,w*.42,.35,15,WHITE)
    box(slide,x+w*.42,y+.06,w*.48,.28,SLATE,r=.1)
    box(slide,x+w*.42,y+.06,max(.035,w*.48*val/maxval),.28,col,r=.1)
    txt(slide,str(val),x+w*.92,y,w*.08,.32,13,col,True)

# Slide 1 – open
s=prs.slides.add_slide(prs.slide_layouts[6])
if HERO.exists():s.shapes.add_picture(str(HERO),0,0,width=prs.slide_width,height=prs.slide_height)
box(s,0,0,7.6,7.5,NAVY,r=0);box(s,.76,.97,.11,.59,GREEN,r=0)
txt(s,'MANAGER / ANICCA',1.06,1.00,5.4,.33,16,GREEN,True)
txt(s,'Human Behavior\nSimulation &\nWorld Engineering',1.02,1.89,6.3,2.73,41,WHITE,True,spacing=1.00)
txt(s,'From fundamentals and existing research to a falsifiable Manager research proposal.',1.09,5.18,5.65,1.03,19,LIGHT)
txt(s,'A LIVING RESEARCH-LAB PRESENTATION  •  21 OCTOBER 2026',1.09,6.82,6,.3,10,GREEN,True)
notes(s,'A long-form lab talk for newcomers and technical peers; end with a proposal, not a product victory.',['https://societies.ai/radiant','https://www.simile.com/blog/what-if-machine'])

# 2 outline
s=base('The journey: fundamentals → research → proposal','READING MAP','Sources listed on each slide and in the final reference section.')
for i,(num,head,body) in enumerate([
('I','BUILDING BLOCKS','Population, choice, LLM agents, network models'),('II','SCIENTIFIC METHOD','Validation, causal inference, uncertainty and replication'),('III','FIELD LANDSCAPE','Research groups, Simile, Aaru, Radiant, Expected Parrot'),('IV','WHAT WE VERIFIED','HeartSteps limitations, observed mobility benchmark, mock agents'),('V','MANAGER RESEARCH','Autonomous public benefit, transparent blessings, experiments'),('VI','OPEN SCIENCE','Newsletter → articles → reusable slides → books')]):
    x=.85+(i%3)*4.13;y=1.93+(i//3)*2.19
    smallcard(s,x,y,3.92,1.94,num+'   '+head,body,GREEN if i<3 else GOLD)
notes(s,'This is an updated end-to-end research seminar, not a 14-slide management philosophy talk.',[])

# 3 motivation
s=base('The problem: a world we cannot safely test','WHY STUDY BEHAVIOR?',subtitle='Pricing, policies, healthcare, public services and communications depend on how people respond.')
card(s,.86,2.19,5.65,3.70,'Without simulation','A policy launches; people react; only then do we discover hidden costs, unequal effects, feedback and unintended incentives.',GOLD,20)
card(s,6.71,2.19,5.65,3.70,'With scientific simulation','Generate a scenario and predicted outcomes; check the forecast against human data; discard or improve failed models before acting.',GREEN,20)
notes(s,'Never equate cheap simulation with verified welfare improvement.',['https://www.simile.com/blog/what-if-machine'])

# 4 hierarchy
s=base('Five objects that must never be confused','FUNDAMENTALS')
for i,(a,b) in enumerate([
('POPULATION','Who exists; which traits and weights?'),('BEHAVIOR','What will a person choose?'),('SOCIETY','How do people interact and influence?'),('INTERVENTION','What changes if we alter conditions?'),('WELFARE','Did conditions become better in reality?')]):
    yy=1.90+i*.93;box(s,.99,yy,10.95,.80,PANEL,r=.04);badge(s,f'{i+1:02d}',1.23,yy+.2,.62,GREEN if i<3 else TEAL)
    txt(s,a,2.13,yy+.23,2.34,.33,17,WHITE,True);txt(s,b,4.7,yy+.23,6.9,.35,16,LIGHT)
notes(s,'Moving to the next object requires evidence, not just adding agent count.',[])

# 5 observed dataset
s=base('Observations are not individuals','DATA CONTRACT',subtitle='A rigorous study defines a population, context, available actions, assigned treatment and outcome.')
rows(s,[('x : CONTEXT','Public environment, timing, resources, baseline data'),('a : ACTION','Available alternatives, not only the one chosen'),('y : OUTCOME','Measured later with units, windows and missingness'),('p : PROPENSITY','Randomization probability when known'),('s : PROVENANCE','Source, license, version, privacy and selection rules'),('g : GROUP','Repeated person / experiment / site / time split')],y=2.06,rowheight=.72)
notes(s,'Do not infer individual identities or consent from a public URL.',['https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/'])

#6 probabilities
s=base('First equation: predict a distribution, not just a story','PREDICTION 101')
metric(s,.92,2.09,3.38,'0.60','P(choose A | context)',GREEN)
metric(s,4.80,2.09,3.38,'0.40','P(choose B | context)',SKY)
metric(s,8.68,2.09,3.38,'1.00','Total probability',GOLD)
box(s,.93,3.73,11.46,1.40,PANEL,r=.07)
txt(s,'P(Y = a | X = x) = estimated frequency or probability of action a given observed context x',1.27,4.07,10.85,.68,23,WHITE,True)
txt(s,'These figures are made-up teaching numbers, not measured human results.',.93,5.55,10.8,.35,15,MUTED)
notes(s,'Introduce conditional probability and basic distributions before using behavioral foundation models.',[])

#7 population
s=base('Population synthesis: who is represented?','GENERATING POPULATIONS')
card(s,.85,1.92,3.80,3.65,'Simple statistical baselines','Proportions, joint tables, IPF or reweighting. Interpretable but limited by available cross-tabs.',GREEN,17)
card(s,4.76,1.92,3.80,3.65,'Generative tabular models','Bayesian networks, VAEs, GANs and diffusion learn statistical combinations.',SKY,17)
card(s,8.67,1.92,3.80,3.65,'LLM persona construction','Language-rich biographies and memories; fluency alone cannot validate demographic or behavioral fidelity.',GOLD,17)
txt(s,'Test population margins, dependence, geography, relationships, coverage and fairness separately.',.94,6.10,11.6,.43,16,LIGHT,True)
notes(s,'Simulating a plausible census is different from predicting what its residents do.',['https://arxiv.org/abs/2304.03442'])

#8 classic choice
s=base('Behavior models: three increasingly rich families','BEHAVIORAL PREDICTION')
rows(s,[('Rule / utility','Interpretable features, constraints, discrete choice / stated preferences'),('Statistical ML','Forecasts learned from logged behavior; careful temporal/study splits'),('LLM / agents','Language conditioned on personas, memory and scenes; measure answers'),('Hybrid','Bayesian / network / learned components with explicit empirical calibration'),('No-action','Include abstention when uncertainty, support or rights are inadequate')],y=2.08,rowheight=.87)
notes(s,'The most complex model is not automatically best; compare to cheap baselines.',[])

#9 agents
s=base('Generative agents: memory, reflection, planning','AGENT ARCHITECTURE','Reference: https://arxiv.org/abs/2304.03442')
horizontal(s,[('MEMORY','Events and observations'),('REFLECTION','Compressed inferences'),('PLANNING','Next decisions'),('ACTION','Proposed behavior')],y=2.60)
box(s,1.15,4.81,11.05,.95,PANEL,r=.07);txt(s,'A believable simulation can fail to predict human choices, treatment effects or lived welfare.',1.42,5.06,10.55,.55,20,GOLD,True)
notes(s,'Generative Agents uses memory, reflection and planning; do not conflate a believable agent with measured human validity.',['https://arxiv.org/abs/2304.03442'])

#10 graph
s=base('Networks change individual choices','SOCIETY / INFLUENCE',subtitle='An audience is not a bag of independent questionnaire respondents.')
coords=[(2.02,2.7),(3.15,3.55),(2.07,4.66),(4.58,2.48),(5.55,3.52),(4.5,5.12),(7.18,2.64),(8.26,3.68),(7.05,5.14),(9.69,2.92),(10.39,4.79)]
edges=[(0,1),(1,2),(0,3),(3,4),(4,5),(3,6),(4,7),(6,7),(6,9),(7,9),(7,8),(8,10),(9,10),(5,8),(2,5)]
for a,b in edges:line(s,*coords[a],*coords[b],SLATE,2)
for i,(x,y) in enumerate(coords):
    col=GREEN if i<3 else SKY if i<7 else GOLD
    box(s,x-.17,y-.17,.35,.35,col,r=.50)
box(s,.90,5.82,11.48,.54,DEEP,r=.03);txt(s,'Homophily, contagion, persuasion and selection require different validation designs.',1.07,5.96,11.1,.28,17,WHITE,True)
notes(s,'Radiant Society Assembly models influence links; a graph is a hypothesis until compared with observed network effects.',['https://societies.ai/knowledge/the-science-behind-artificial-societies','https://doi.org/10.1111/bjop.12764'])

#11 environments
s=base('The engine updates the simulated world','AGENT–ENVIRONMENT LOOP','Code: https://github.com/google-deepmind/concordia')
horizontal(s,[('OBSERVE','What an agent sees'),('DECIDE','Action from model'),('RESOLVE','World rule / GM'),('FEEDBACK','New observation')],y=2.74)
card(s,1.24,4.86,10.82,1.17,'Crucial distinction','A Game Master can resolve events inside a simulation, not exercise authority over real systems.',GOLD,15,15)
notes(s,'Concordia has entity/player and Game Master roles. GM resolution is not execution on other people or infrastructure.',['https://github.com/google-deepmind/concordia'])

#12 counterfactual
s=base('“What if?” changes the conditions','COUNTERFACTUAL SIMULATION')
card(s,.91,1.93,5.6,3.55,'Scenario A','Price stays at $10\nMessage stays neutral\nCurrent hours continue\nPredict purchase, wait time, complaints.',SKY,19)
card(s,6.75,1.93,5.6,3.55,'Scenario B','Price rises to $12\nA new message is shown\nService hours extend\nPredict the distribution again.',GREEN,19)
txt(s,'Difference in simulated outcomes ≠ identified causal effect in the real world.',1.17,5.88,11.1,.70,23,GOLD,True)
notes(s,'Simile and Radiant both offer scenario / what-if simulation. A within-model contrast is not automatically a real-world counterfactual estimate.',['https://www.simile.com/blog/what-if-machine','https://societies.ai/solutions'])

#13 confounding
s=base('Correlation is not an intervention effect','CAUSALITY BASICS')
smallcard(s,1.1,2.00,3.15,1.40,'WEATHER (Z)','An unmeasured cause',GOLD)
smallcard(s,1.1,4.35,3.15,1.40,'CYCLE PROMOTION (A)','Who receives message?',SKY)
smallcard(s,8.92,3.19,3.22,1.43,'CYCLING (Y)','Observed behavior',GREEN)
line(s,4.29,2.74,8.90,3.65,GOLD,3);line(s,4.29,5.0,8.90,3.65,SKY,3);line(s,2.67,3.43,2.67,4.31,GOLD,3)
txt(s,'If weather affects promotion and cycling, a naive association can be misleading.',4.76,5.07,7.1,.85,17,LIGHT)
notes(s,'Illustrative causal DAG, not observed dataset estimates.',['https://www.pywhy.org/dowhy/'])

#14 effects
s=base('Causal effect: comparing potential outcomes','CAUSAL ESTIMANDS')
box(s,.95,2.12,11.45,1.17,PANEL,r=.04);txt(s,'ATE = E[Y(1) − Y(0)]',1.41,2.35,10.4,.64,32,WHITE,True,PP_ALIGN.CENTER)
rows(s,[('Y(1)','Outcome if the intervention is applied'),('Y(0)','Outcome for the same unit without intervention'),('Why hard?','Only one potential outcome is observed for each unit'),('Possible designs','Randomization, valid quasi-experiments, causal models with assumptions')],y=3.63,rowheight=.65)
notes(s,'Experimental effects, confidence intervals and harms must be estimated separately from response prediction.',['https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/'])

#15 study designs
s=base('Study designs: from prediction to randomized effects','MEASURING CONSEQUENCES')
card(s,.85,1.97,3.76,3.78,'Observed behavior','What people did; useful for forecasting. Confounding, missingness and sampling remain.',SKY,18)
card(s,4.75,1.97,3.76,3.78,'Randomized experiment','Random treatment with known probabilities; compare outcomes after exposure.',GREEN,18)
card(s,8.66,1.97,3.76,3.78,'Real-world readback','External confirmations and lasting outcomes under actual authority; welfare requires harms and costs.',GOLD,18)
notes(s,'A trial of simulated personas is not a real RCT of human impact.',['https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/'])

#16 metrics
s=base('No single number measures “human-like”','PREDICTION METRICS')
rows(s,[('Accuracy','How many categorical predictions matched?'),('TVD','0.5 × sum |predicted option share − observed option share|'),('Brier','Mean squared probability error for binary outcomes'),('Calibration','When model says p=0.7, how often does outcome occur?'),('Ordinal Wasserstein','How far predicted ordinal response mass must move?'),('Treatment effect error','Predicted randomized contrast vs measured human contrast')],y=2.09,rowheight=.70)
notes(s,'Scores refer to different estimands; Brier and TVD alone cannot evaluate causal fidelity.',['https://arxiv.org/html/2609.30030','https://www.simile.com/blog/confidence'])

#17 11 bench
s=base('Radiant researchers proposed an 11-test benchmark','ARTIFICIAL SOCIETIES BENCHMARK 2026','Source: https://arxiv.org/html/2609.30030')
card(s,.87,1.95,3.75,3.95,'INTERNAL · 4 tests','IV-1 Repeated items\nIV-2 Linked logic\nIV-3 Paraphrases\nIV-4 Survey perturbations',GREEN,17)
card(s,4.78,1.95,3.75,3.95,'CONSTRUCT · 3 tests','CV-1 Item covariance\nCV-2 Held-out criteria\nCV-3 Distinct traits',SKY,17)
card(s,8.69,1.95,3.75,3.95,'EXTERNAL · 4 tests','EV-1 Distributions\nEV-2 Groups / individuals\nEV-3 Experimental effects\nEV-4 Latent structure',GOLD,17)
notes(s,'Read the primary arXiv:2609.30030v2; 11 tests across three validity families, designed around use-specific evidence. The preprint is authored in part by company researchers.',['https://arxiv.org/html/2609.30030'])

#18 evidence ladder
s=base('The evidence ladder: what can a claim support?','SCIENTIFIC ACCOUNTABILITY')
levels=[('P0','Theory / simulation'),('P1','Real external execution receipt'),('P2','Independent state change'),('P3','Substantive beneficiary improvement'),('P4','Credible causal net benefit'),('P5','Replicated safe benefit')]
for i,(a,b) in enumerate(levels):
    yy=1.87+i*.79;box(s,1.22,yy,10.65,.68,PANEL if i<3 else PANEL2,r=.04)
    badge(s,a,1.50,yy+.15,.67,GREEN if i<3 else GOLD)
    txt(s,b,2.54,yy+.18,8.9,.34,17,WHITE,True)
notes(s,'Manager-specific evidence-level design—not a universal published metric or claim that project has achieved any upper level.',[])

#19 audience
s=base('Industry: useful capabilities overlap, not a one-winner list','COMPANY / RESEARCH MAP')
for i,(name,body) in enumerate([
('SIMILE','Behavior foundation model; transactions + interviews; confidence'),
('AARU','Population and consumer decisions, research-validation claims'),
('ARTIFICIAL SOCIETIES','Radiant: grounded audiences, society graphs, 11-test framework'),
('EXPECTED PARROT','EDSL: surveys/scenarios/agents/models, real human panels'),
('GOOGLE DEEPMIND','Concordia: action/GM/world simulation engine'),
('RESEARCH LABS','Stanford Generative Agents, SocSci210, AgentTorch, AgentSociety')]):
    x=.84+(i%2)*6.17;y=1.85+(i//2)*1.54
    smallcard(s,x,y,5.90,1.37,name,body,GREEN if i in (0,2,3) else SKY)
notes(s,'Comparisons are directional; no claim that vendors never validate, or share one benchmark.',['https://societies.ai/radiant','https://www.simile.com/blog/what-if-machine','https://docs.expectedparrot.com/en/latest','https://github.com/google-deepmind/concordia'])

#20 Simile
s=base('Simile: model behavior + predict model error','COMPANY DEEP DIVE','Sources: https://www.simile.com/blog/what-if-machine · /blog/confidence')
horizontal(s,[('REAL DATA','Transactions, apps'),('BEHAVIOR MODEL','Population distributions'),('CONFIDENCE','Predict expected TVD'),('WHAT-IF','Simulate alternatives')],y=2.35)
metric(s,1.16,4.33,3.25,'~8,600','held-out eval questions',GREEN)
metric(s,5.05,4.33,3.25,'0.73','reported probe AUROC',SKY)
metric(s,8.95,4.33,3.25,'0.16','internal TVD threshold',GOLD)
notes(s,'Simile uses real observed data and held-out validation; proprietary company-reported 2026 metrics are not our replication. It already evaluates what-if scenarios and confidence.',['https://www.simile.com/blog/confidence','https://www.simile.com/blog/what-if-machine'])

#21 Aaru
s=base('Aaru: grounded simulations of population decisions','COMPANY DEEP DIVE','Source: https://aaru.com/simulation')
card(s,.89,1.95,5.68,3.91,'Research target','How may consumer segments react to choices and conditions? Models compare markets, opinions and potential purchase decisions.',SKY,19)
card(s,6.78,1.95,5.68,3.91,'Evidence boundary','Validate on real observations where documented. Public product descriptions and published company evaluations do not establish universal causal fidelity.',GOLD,19)
notes(s,'Avoid characterizing Aaru as a text-only synthetic-person generator or denying that it validates. Check source at time of talk.',['https://aaru.com/simulation','https://aaru.com/publications/population-simulation-at-the-replication-floor-research'])

#22 Radiant architecture
s=base('Artificial Societies / Radiant: how it is built','PRODUCT MECHANISM','Source: https://societies.ai/eval · /knowledge/the-science-behind-artificial-societies')
for i,(head,body) in enumerate([
('REAL OBSERVATIONS','Public speech, reviews, data; optional enterprise data'),
('PERSONA GENESIS','Psychometrics / inferred beliefs, internal validation'),
('SOCIETY ASSEMBLY','Similarity and influence network'),
('SIMULATION ENGINE','Responses to prices, messages and scenarios'),
('RESEARCH OUTPUT','Survey, segment cuts, interviews, focus groups')]):
    x=.78+i*2.55;card(s,x,2.18,2.42,3.54,head,body,GREEN if i<3 else GOLD,13,15)
notes(s,'Their internal model architecture is proprietary. Do not assert exact weights, training code or personalized consent from public marketing materials.',['https://societies.ai/eval','https://societies.ai/knowledge/the-science-behind-artificial-societies'])

#23 Radiant product
s=base('Five research actions inside Radiant','PRODUCT WORKFLOW','Source: https://societies.ai/radiant')
rows(s,[('SOCIETIES','2D/3D audience network, filter and explore'),('SURVEYS','Response proportions, choices, segments and explanations'),('INTERVIEWS','Follow up with one modeled persona'),('FOCUS GROUPS','Simulated discussion, persuasion and participation'),('ASSISTANT','Cross-project research summarization and reports')],y=2.04,rowheight=.86)
notes(s,'The 38% / 31% / 19% / 12% ticket-pricing split on Radiant is illustrative simulated product output, not a publicly verified human survey.', ['https://societies.ai/radiant'])

#24 Radiant 2026 measured claims
s=base('Radiant: what the company reports—not our result','2026 VENDOR BENCHMARK','Source: https://societies.ai/as-benchmark')
metric(s,.91,1.93,3.38,'2,796','synthetic respondents',SKY)
metric(s,4.80,1.93,3.38,'68,280','synthetic answers',SKY)
metric(s,8.69,1.93,3.38,'7','human survey sources',SKY)
txt(s,'Mean population-answer TVD (lower is better)',.96,3.63,8.5,.43,19,WHITE,True)
bar(s,1.09,4.37,10.4,.35,'Artificial Societies',.08,.50,GREEN)
bar(s,1.09,5.06,10.4,.35,'Best generic LLM',.31,.50,GOLD)
txt(s,'Same respondent profiles, items and reported scoring code; independently replicated? NO.',1.14,5.95,10.8,.51,16,MUTED)
notes(s,'Published October 1, 2026 by vendor, mean TVD AS 0.08 vs best Qwen3.8 0.31. Different metrics from Jan 2026 86% overlap. On benchmark tests, do not imply external real-world welfare.',['https://societies.ai/as-benchmark'])

#25 Radiant evidence boundaries
s=base('Radiant: what the evidence supports—and does not','CLAIM AUDIT','Sources: https://societies.ai/eval · arxiv.org/html/2609.30030')
card(s,.88,1.94,5.70,3.95,'SUPPORTED / ATTRIBUTED','2024 peer-reviewed simulation of 33,299 bots shows homophily patterns.\n2026 internal studies report survey distribution agreement and experiments.\n11-test paper proposes rigorous validation.',GREEN,17)
card(s,6.76,1.94,5.70,3.95,'NOT YET ESTABLISHED','All commercial clients experienced correct future human decisions.\nEvery prediction is causally valid across new populations.\nA real public-benefit intervention reduced suffering.',GOLD,17)
notes(s,'Key point: independent academic paper is about homophily, not the whole proprietary model. January overlap 86% vs human self-replication 91% belongs to corporate internal report.',['https://doi.org/10.1111/bjop.12764','https://societies.ai/eval','https://arxiv.org/html/2609.30030'])

#26 EDSL
s=base('Expected Parrot: make research reproducible','RESEARCH INSTRUMENTS','Sources: https://github.com/expectedparrot/edsl · https://docs.expectedparrot.com/en/latest')
horizontal(s,[('QUESTION','Instrument'),('AGENT','Traits'),('SCENARIO','Context'),('MODEL','Inference'),('RESULT','Reproducible data')],y=2.48)
card(s,.91,4.57,11.49,1.36,'Why it matters','An instrument must be replayed, cached, compared with human respondents and separated from the models that answer it.',GREEN,16,18)
notes(s,'EDSL supports model-run and human-fielded research; it is not just generated people.',['https://github.com/expectedparrot/edsl'])

#27 Concordia
s=base('Concordia: a simulation engine, not an oracle','SOCIAL WORLD MODEL','Source: https://github.com/google-deepmind/concordia')
card(s,.93,1.95,5.61,3.91,'Agent / entity','Persona, memory, instructions, proposed action. Interaction order and contextual observation matter.',SKY,19)
card(s,6.75,1.95,5.61,3.91,'Game Master / environment','World state, action resolution, rules, new observations. Does not confer permission over real facilities or funds.',GOLD,19)
notes(s,'We actually ran a tiny two fictional-agent upstream mock. A running engine proves software integration, not social validity.',['https://github.com/google-deepmind/concordia'])

#28 SocSci210 and other research
s=base('SocSci210 and behavioral foundation models','HUMAN RESPONSE DATA','Sources: https://arxiv.org/html/2509.05830v2 · Hugging Face SocSci210')
metric(s,.94,2.03,3.29,'210','social-science studies',GREEN)
metric(s,5.01,2.03,3.29,'170 / 40','seen / unseen studies',SKY)
metric(s,9.04,2.03,3.29,'0','split study-ID overlap',GOLD)
card(s,.93,3.79,11.47,1.77,'Critical method','Validate held-out studies with human answers; aggregate performance and individual/group effects differ. Access to respondent data requires source-specific rights and appropriate processing.',GOLD,17)
notes(s,'This slide reports externally verified split metadata, not human-response model benchmark. Project operator reports dataset permissions, but licenses and grant scope still need a source-specific record.',['https://huggingface.co/datasets/socratesft/SocSci210','https://arxiv.org/html/2509.05830v2'])

#29 simulation industry long tail
s=base('Broader research and infrastructure','BEYOND THE CORE COMPANIES')
for i,(a,b) in enumerate([
('STANFORD GENERATIVE AGENTS','Memory / reflection / planning and interview-grounded behavior'),
('AGENTTORCH / MIT','Differentiable agent-based population simulation'),
('AGENTSOCIETY','LLM-driven large-population social simulation'),
('OASIS / TINY TROUPE','Open-source social and persona simulation tools'),
('AI ECONOMIST','Economic agents with rules set by a planner'),
('DOWHY / ECONML','Causal estimands, falsification, heterogeneity')]):
    x=.80+(i%2)*6.2;y=1.82+(i//2)*1.53
    smallcard(s,x,y,5.95,1.35,a,b,SKY if i%2 else GREEN)
notes(s,'All are relevant but solve different pieces. Avoid equating synthetic economic policy learning with measured real-world effect.',['https://github.com/salesforce/ai-economist','https://github.com/py-why/dowhy','https://github.com/AgentTorch/AgentTorch','https://github.com/tsinghua-fib-lab/AgentSociety'])

#30 old results
s=base('What our HeartSteps replication actually taught us','PHASE 03 EVIDENCE','Source: https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/')
metric(s,.94,2.11,3.23,'8,274','public CSV decision rows',SKY)
metric(s,4.99,2.11,3.23,'6,061','original available decisions',SKY)
metric(s,9.00,2.11,3.23,'6,330','different analysis sample',GOLD)
card(s,.90,3.72,11.48,1.82,'NOT a reproduction of the original paper','H005 was skipped with evidence: required original study-day mapping is missing or ambiguous in the later public release. Nonidentical exploratory associations were reported—not human causal replication.',GOLD,17)
notes(s,'The scientific honesty of a negative reproduction result is an input to the Manager evidence policy.', ['https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/'])

#31 field observed
s=base('Observed demand, unseen year: an independent holdout','PHASE 04: REAL AGGREGATE DATA')
metric(s,.94,2.10,3.24,'365','2011 training days',GREEN)
metric(s,5.01,2.10,3.24,'366','2012 holdout days',SKY)
metric(s,9.02,2.10,3.24,'0','human RCT effects estimated',GOLD)
box(s,.99,3.71,11.18,1.80,PANEL,r=.06)
txt(s,'Global-mean MAE 2,488.67 vs season-only 2,303.65 rentals/day',1.28,4.07,10.55,.53,20,WHITE,True)
txt(s,'Paired week-block uncertainty crosses zero. Predictive fit does not measure societal benefit.',1.30,4.78,10.48,.57,17,GOLD)
notes(s,'Official UCI day.csv source verified byte-identical, held-out 2012 real observations. No treatment or individual prediction evidence.',['https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset'])

#32 limitations
s=base('Five recurring scientific failure modes','LIMITS AND FAILURE ANALYSIS')
rows(s,[('Leakage','Training data accidentally includes unseen study/participant context'),('Unfair segments','Average prediction hides errors or harm to a smaller group'),('Confounding','A correlational trend is misread as a treatment effect'),('Simulation theater','Model prediction or API success presented as achieved welfare'),('Model drift','New contexts, time periods or policies invalidate old metrics')],y=2.06,rowheight=.87)
notes(s,'For each failure type preserve a test, an evidence card, and an abstention/repair path.',['https://arxiv.org/html/2609.30030'])

#33 industry matrix
s=base('No vendor wins every axis','RESEARCH ECOSYSTEM COMPARISON',subtitle='Qualitative comparison of published product focus—not a shared, independently scored benchmark.')
headers=['Capability / focus','Simile','Aaru','Radiant','EDSL','Concordia']
col=[.82,4.04,5.75,7.46,9.17,10.88];width=[3.2,1.68,1.68,1.68,1.68,1.68]
for j,h in enumerate(headers):box(s,col[j],1.99,width[j]-.06,.48,PANEL2,r=.02);txt(s,h,col[j]+.06,2.12,width[j]-.12,.24,11,WHITE,True)
mat=[('Behavior / scenarios','YES','YES','YES','USAGE','WORLD'),('Human research','VALIDATE','REPORT','BENCH','FIELD','ADD-ON'),('Social interaction','SELECT','SELECT','FOCUS','STRUCT.','CORE'),('Open tool / SDK','NO','NO','NO','YES','YES'),('Real welfare acts','NOT CORE','NOT CORE','NOT CORE','NOT CORE','NO')]
for i,row in enumerate(mat):
    y=2.57+i*.63
    for j,v in enumerate(row):
        box(s,col[j],y,width[j]-.06,.56,DEEP if i%2 else PANEL,r=.015)
        txt(s,v,col[j]+.05,y+.15,width[j]-.14,.28,13 if j==0 else 11,WHITE if j==0 else (GOLD if v in ('NO','NOT CORE') else GREEN),j==0,PP_ALIGN.LEFT if j==0 else PP_ALIGN.CENTER)
txt(s,'“Not core” ≠ not possible. Recheck source and date for each vendor-specific claim.',.91,6.28,11.5,.34,14,MUTED)
notes(s,'The matrix classifies published product focus, not a scientific ranking. Simile and Radiant already use observed data and validation.',['https://societies.ai/radiant','https://www.simile.com/blog/what-if-machine','https://docs.expectedparrot.com/en/latest','https://github.com/google-deepmind/concordia'])

#34 differentiator
s=base('The research gap is the full real-world loop','MANAGER RESEARCH PROPOSAL')
card(s,.85,1.92,5.7,3.94,'What the field already has','Population inference, behavioral foundation models, agent societies, decision-scenario testing, real survey/experimental validation, and some established field interventions.',SKY,18)
card(s,6.76,1.92,5.7,3.94,'What Manager proposes','A domain-general public-benefit objective, bounded autonomous intervention selection/execution, independent verification of net effects, transparent evidence cards and accountable rollback.',GREEN,18)
notes(s,'This proposed integration remains unproven. Do not assert no competitor has impact work or counterfactuals.',['https://www.simile.com/blog/what-if-machine','https://societies.ai/eval'])

#35 kernel
s=base('Manager kernel: the public-benefit cycle','PROPOSED SYSTEM ARCHITECTURE')
steps=[('PUBLIC','Read lawful data'),('MODEL','Causal hypotheses'),('OPTIONS','NO_ACTION included'),('GATE','Rights + risk + budget'),('ACT','Limited executor'),('READBACK','Independent source'),('EVALUATE','Effect + harm'),('LEARN','Version / rollback')]
for i,(name,body) in enumerate(steps):
    col=i%4;row=i//4;x=.80+col*3.12;y=1.96+row*2.18
    smallcard(s,x,y,2.88,1.89,name,body,GREEN if i<4 else GOLD)
txt(s,'Every claim carries a source, uncertainty, permission and evidence tier.',.93,6.50,11.55,.36,17,WHITE,True)
notes(s,'A design diagram, not proof the live ecosystem exists. NO_ACTION is the correct option if a permission or outcome is uncertain.',[])

#36 blessing
s=base('Transparent Blessings: open audit, not just open source','EVIDENCE CARD SPECIFICATION')
rows(s,[('BASELINE','Which public observation? What was wrong?'),('CAUSAL QUESTION','Which option and valid alternative?'),('AUTHORITY','Who may act; cost, scope, revocation?'),('REAL ACTION','Receipt, idempotence and observed provider state'),('READBACK','Independent, timestamped outcome measurement'),('NET BENEFIT','Magnitude, uncertainty, harms, distribution'),('CONTEST','Challenge, failure, correction and rollback')],y=1.86,rowheight=.675)
notes(s,'No public beneficiary count until P1-P4 evidence exists. Real-world net benefit must consider displacement and harms.',[])

#37 experiments
s=base('Falsifiable research questions','RESEARCH PROPOSAL / RQ')
card(s,.83,1.93,3.82,4.00,'RQ1 — BEHAVIOR','Does adding social-network context improve held-out response prediction over frequency, statistical and LLM baselines?',GREEN,17)
card(s,4.75,1.93,3.82,4.00,'RQ2 — CAUSAL','Does the same model reproduce human randomized treatment contrasts across subgroups and settings?',SKY,17)
card(s,8.67,1.93,3.82,4.00,'RQ3 — IMPACT','Under legitimate standing authority, do selected interventions improve independent welfare outcomes versus NO_ACTION?',GOLD,17)
notes(s,'Do not use synthetic-only RCTs as a real causal confirmation. Preregister protocol, statistical power, intervention harm review.',[])

#38 protocol
s=base('Proposed experimental protocol','HOW WE WOULD TEST OUR HYPOTHESES')
rows(s,[('DATASET 1','Rights-cleared real response/experiment, source manifest and frozen split'),('BASELINES','Class frequencies / statistical prediction / simple model / LLM'),('VALIDITY','TVD, Brier, ordinal scores, 11-test subset, subgroup error'),('CAUSAL','Prespecified human randomized contrasts; report sign & magnitude error'),('AUTHORIZE','Only legitimate public/safe intervention domain, NO_ACTION control'),('EXTERNAL','Independent measurements, costs, uncertainty and side effects'),('REPORT','Open failures, negative effects, replication and versioned code')],y=1.88,rowheight=.676)
notes(s,'S002 use of SocSci210 participant data is not completed just because the operator asserts blanket permission. Source license scope and purpose must be documented and data minimized.', ['https://arxiv.org/html/2609.30030','https://www.pywhy.org/dowhy/'])

#39 progress
s=base('Current maturity and the next honest milestone','RESEARCH STATUS · OCT 2026')
metric(s,.86,2.09,3.54,'184/184','Previous hosted unit tests',GREEN)
metric(s,4.86,2.09,3.54,'5 / 8','Phase 04 scoped tasks',SKY)
metric(s,8.85,2.09,3.54,'0','Verified Manager welfare effects',GOLD)
card(s,.92,3.67,11.48,2.16,'Not finished','Human held-out studies, licensed model comparison and independent welfare causal tests remain unverified. The project has published preliminary aggregate data and software demonstrations—not a general-purpose world-changing AI.',GOLD,17)
notes(s,'Numbers as of observed GitHub run 39546654088. Never promote source-only tests to end-to-end scientific completion.',['https://github.com/Daisuke134/life-manager/actions/runs/39546654088'])

#40 publishing/research
s=base('Research compounds when it is reusable and inspectable','OPEN SCIENCE & EDUCATION LOOP')
horizontal(s,[('DAILY WATCH','Papers, releases, people'),('SOURCE MAP','Versioned citations'),('DEEP DIVE','English article + visuals'),('LAB DECK','Living presentation'),('BOOK / COURSE','Chapters + exercises')],y=2.32)
card(s,.95,4.52,11.40,1.29,'No content without provenance','One verified result should produce reusable diagrams, article and book chapter—not three disconnected summaries. Publish only after editorial checks and live readback.',GREEN,15,16)
notes(s,'Content productization is a business hypothesis, not earned revenue. Subscriber growth, paid conversion and refunds are real metrics, not simulated readership.',[])

#41 editorial/nl
s=base('Behavior × AGI Daily: a research product hypothesis','DISTRIBUTION, TRANSPARENCY, BUSINESS')
card(s,.86,1.94,5.66,3.81,'FREE PUBLIC ISSUE','Today: what changed, why it matters, primary source, limitations, Manager research implication. Include one English X idea.',GREEN,18)
card(s,6.75,1.94,5.66,3.81,'OPTIONAL PREMIUM LAYER','Deeper reproducible digests, source datasets, full tutorials, slides, benchmark notebooks and book editions. Verify readers and paid demand first.',GOLD,18)
txt(s,'No promises of billions in revenue, historical subscribers or posted tweets without actual receipts.',1.07,6.16,11.1,.43,16,MUTED)
notes(s,'The daily automation was configured Oct 21 JST for Oct 22 onward. Distribution and business validation remain separate.',[])

#42 research sources
s=base('Primary sources · behavioral foundations','SELECTED REFERENCES / I')
rows(s,[('Generative Agents','arxiv.org/abs/2304.03442'),('Socrates / SocSci210','arxiv.org/html/2509.05830v2'),('HeartSteps V1','pmc.ncbi.nlm.nih.gov/articles/PMC6401341/'),('Simile What-If Machine','simile.com/blog/what-if-machine'),('Simile Confidence','simile.com/blog/confidence'),('Concordia','github.com/google-deepmind/concordia'),('Expected Parrot','github.com/expectedparrot/edsl')],y=1.88,rowheight=.66)
notes(s,'Links are publicly available first-party sources, as checked October 21, 2026.',[])

#43 sources
s=base('Primary sources · Radiant and the broader field','SELECTED REFERENCES / II')
rows(s,[('Artificial Societies / Radiant','societies.ai/radiant'),('Company evaluation','societies.ai/eval'),('Company benchmark Oct 2026','societies.ai/as-benchmark'),('11-test preprint','arxiv.org/html/2609.30030'),('2026 fairness/counterfactual paper','arxiv.org/abs/2609.27690'),('Peer-reviewed homophily','doi.org/10.1111/bjop.12764'),('Aaru / AgentTorch / AI Economist','aaru.com/simulation · github.com/AgentTorch/AgentTorch · github.com/salesforce/ai-economist')],y=1.88,rowheight=.66)
notes(s,'If these figures are used in a journal article or pitch, check versions and independent replications first.',[])

#44 closing
s=base('Our hypothesis: intelligence must become accountable benefit','MANAGER  ·  END SUFFERING')
txt(s,'Observe carefully.\nPredict humbly.\nAct only with authority.\nVerify independently.\nShare the evidence.',1.21,1.82,10.8,3.99,34,WHITE,True,spacing=1.17)
badge(s,'A RESEARCH PROPOSAL — NOT AN ACHIEVED WORLD-IMPACT RESULT',1.22,6.15,10.65,TEAL)
notes(s,'Final take-home: candidate system is general purpose and pro-human accountability, not omniscient or self-authorizing.',[])

# Basic powerpoint QA
assert len(prs.slides)==44, len(prs.slides)
for i,slide in enumerate(prs.slides):
    assert len(slide.shapes)>0,i
prs.save(OUT)
print('SAVED',OUT,OUT.stat().st_size,'slides',len(prs.slides))