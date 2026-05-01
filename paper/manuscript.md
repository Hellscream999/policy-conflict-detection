# Don't Trust Similarity, Verify It: Solver-Backed Witnesses for Multi-Framework Policy Conflicts

Rabea Al Haj Eid, Mu'awya Al-Dala'ien (Princess Sumaya University for Technology, Amman, Jordan); Mohammad Al Haj Eid (Higher Colleges of Technology, Fujairah, UAE).

## Abstract

Organisations subject to overlapping security and privacy frameworks (NIST CSF, ISO/IEC 27001, PSD2, DORA, GDPR, and UAE AML/CFT obligations) routinely run rules that contradict each other at run time, yet auditors detect these reachable contradictions only after incidents. We present a four-stage pipeline that normalises heterogeneous XACML rules into a Common Policy Model, screens candidate pairs with sentence-embedding similarity, filters them with entity overlap and a SPARQL structural check, and verifies the survivors with the Z3 SMT solver. Every reported conflict is accompanied by a concrete witness request that an auditor can replay against the live policy decision point. On four public XACML datasets, the funnel narrows tens of thousands of pairs to seconds of solver work, with 100 percent SMT coverage (no unknowns, no timeouts) across 6,988 calls. The contribution is the funnel, not any single stage.

## Actionable Insights for Practitioners

- Treat semantic similarity as triage, not proof — pair it with structural filters and a solver before any conflict claim.
- Require every reported conflict to ship with a replayable witness request the auditor can dispatch against the live policy decision point.
- Put solver-backed policy checks into CI before policy-as-code changes reach production; a regression from `unsat` to `sat` should fail the build the same way a unit test does.

## Why this matters

Compliance teams rarely answer to one framework. A bank in Europe lives under PSD2 [3] and DORA [4]. A health provider in the US may use the NIST Cybersecurity Framework [1] alongside HIPAA-driven controls. A multinational adds ISO/IEC 27001 [2] on top of either, then has a board-driven internal control catalogue on top of that. Each framework normally has its own access-control rules, often written in slightly different vocabularies, and those rules end up enforced together by the same authentication, authorisation, and policy-decision services.

That overlap is where reachable contradictions get born. One rule from the PSD2 set says a customer may read their own account data when authenticated. An internal control says reads of account data are denied outside business hours. An auditor working from a control-mapping spreadsheet does not catch that conflict, because the spreadsheet only tells you that both controls are about "access to account data." A semantic-similarity model trained on policy text will tell you the two rules look alike, which is true but not actually useful — looking alike is not the same as colliding at run time. What an organisation actually needs is proof that *some real request* triggers both rules and gets contradictory answers, plus the request itself in a form that an engineer can replay against the live system.

We built a pipeline that produces exactly that: a concrete request, generated automatically, that simultaneously triggers two policy rules with opposite effects. The headline shape is deliberately conservative — cheap filters first, decisive proof last. There is no machine-learning classifier in the conflict-detection loop. Every conflict the pipeline reports is accompanied by a witness request that an auditor or compliance engineer can run through the real Policy Decision Point (PDP) and watch the contradiction happen.

This article walks through what we built, what surprised us when we measured it (including a ground-truth-counting bug that we caught and want to share publicly), and the practitioner takeaways for anyone shipping policy-as-code today.

## Why now

Two things changed in the last few years that made this work tractable. First, regulated-services frameworks moved from PDF-and-spreadsheet artefacts toward machine-readable forms — XACML 3.0 [7], OSCAL, and the recent practice of treating internal control catalogues as version-controlled YAML or JSON. That gives us a structured input format, which is the precondition for any kind of automated reasoning over policy. Second, SMT solvers got fast enough on the kinds of formulas access-control rules produce that you can call them in a tight loop on a laptop. Z3 [6] returning a sat/unsat answer in single-digit milliseconds for a typical XACML rule pair means a verification stage is no longer a quarterly audit ritual — it is something the build can do on every pull request.

What did not change is the gap between control mappings and run-time enforcement. Auditors still spend most of their time correlating control-catalogue entries from one framework to another, and most of those correlations are valid at the *intent* level but say nothing about whether the actual XACML or Rego [8] rules implementing those intents will collide at run time. The pipeline we describe is meant to live inside that gap: it takes the rules as they are actually written, normalises them, and tells you, with a witness or with a proof, whether two of them collide.

A practitioner reading this should care because the alternative is one of two failure modes that we have both seen in the wild. One is shipping a similarity-based "AI policy linter" that produces confident false positives and trains operators to ignore it. The other is leaving the cross-framework reasoning to spreadsheet triage, which works until a regulator asks for a defensible answer about a specific reachable contradiction. Solver-backed witnesses dodge both failure modes by giving you the artefact regulators ask for: a concrete request that demonstrates the conflict.

## What we built

The pipeline has three filtering stages followed by one solver stage. Figure 1 shows the funnel.

The Common Policy Model (CPM) normalises rules from XACML files [7], NIST/ISO control catalogues [1], [2], PSD2/DORA mappings [3], [4], and internal documentation into a tuple of subject attributes, action verb, resource type and identifiers, environment conditions, effect (Permit or Deny), framework origin, and priority. Semantic screening uses a sentence-transformer [15] to score every pair of rules for textual similarity; pairs below the chosen threshold are dropped. The entity-overlap stage uses Jaccard similarity on extracted subject roles and resource identifiers, and the SPARQL stage queries an RDF view [14] of the policy graph to confirm that the two rules can plausibly reach the same scope. Finally, every pair that survives is encoded as a satisfiability problem and handed to Z3 [6]. If Z3 returns `sat`, the model is a concrete request that triggers both rules; if `unsat`, the pair is provably non-conflicting.

The point is not that any single stage is novel. Sentence transformers, RDF/SPARQL, and SMT-backed XACML analysis [9], [10], [11], [12] have all been done separately. The contribution is the funnel: the filters cut solver work by orders of magnitude, and the solver is the only stage we trust for ground truth. Detection without verification gives you opinions; verification without filtering gives you a stalled pipeline.

### How it works in practice

Each rule, after CPM normalisation, carries a set of attribute constraints inherited down the XACML PolicySet -> Policy -> Rule hierarchy. The hierarchy matters: a rule's own `<Target>` element is often empty, and the actual scope is supplied by the parent Policy and PolicySet. We walk the tree, accumulate constraints, and respect XACML's `AnyOf`/`AllOf` semantics — `AnyOf` is a disjunction, `AllOf` is a conjunction, and a rule's full applicability formula is the AND of its inherited `AnyOf` groups.

Two rules conflict iff there exists an assignment to the attribute variables in the request `q` such that the applicability formulas of both rules are simultaneously satisfied **and** the rules disagree on effect. The SMT encoder turns each rule's applicability into a Z3 formula, with a single fresh variable per attribute (so equality and comparison constraints on the same attribute interact properly). Same-effect pairs short-circuit instantly. Cross-effect pairs are handed to Z3, which either returns a model or a proof of unsatisfiability.

A few engineering details matter in practice. We share the Z3 variable environment between the two rules in a conflict check, so equality and comparison constraints on the same attribute interact correctly inside the solver — earlier versions of our encoder created independent variables for `string-equal` and `string-less-than-or-equal` constraints, which silently dropped the interaction and let pairs slip through as false negatives. We pre-compute per-rule scope satisfiability once before running the cross-product, so a rule whose own constraints are unsatisfiable (dead-code under the current XACML hierarchy) short-circuits every pair it participates in. And we deduplicate candidate pairs before the SMT step, since the upstream filters can emit the same pair more than once.

### How the funnel relates to prior tools

Researchers have been chasing pieces of this problem for over a decade. Margrave [11] used MTBDDs to analyse firewall configurations; XEngine [9] was a fast XACML evaluation engine; ACPT [10] modelled and verified XACML policies; Turkmen et al. [12] put XACML into SMT directly; Caserio et al. [13] formally validated XACML policies. Each of those tools is good at its layer of the problem, but each treats a single policy set as the input. The cross-framework problem is where the existing tooling falls short, because nobody normalised the inputs first. The CPM is the layer where we make the inputs comparable; the funnel is what makes verification affordable across the combined input.

The honest comparison is not "we beat Margrave's runtime." It is: the prior tools were right about the value of formal analysis, but limited to one policy set at a time; our contribution is to put that formal analysis behind a similarity-and-graph funnel so it can run across heterogeneous standards in a build pipeline.

## What we measured

We evaluated the pipeline on four public XACML datasets:

- **GEYSERS** (15 rules, EU cloud infrastructure project),
- **KMarket** (5 rules, e-commerce marketplace),
- **Continue-A** (298 rules, healthcare access control),
- **Synthetic360** (360 rules, synthetic benchmark).

Ground truth comes from running Z3 on every cross-effect rule pair. Same-effect pairs cannot collide on effect, so we skip them. For Continue-A this is 44253 total pairs, of which 482 are real conflicts under the SMT oracle. For Synthetic360, every rule's accumulated scope under the strict XACML hierarchy turned out to be unsatisfiable on its own — the synthetic generator stacks so many `AnyOf` groups that no concrete request can satisfy them all. That dataset has zero reachable conflicts in the strict sense, which is itself an interesting finding: synthetic stress-test data does not always behave like real policy.

### Headline numbers

The full pipeline reaches macro Precision = 0.89, Recall = 0.18, F1 = 0.30 against the SMT oracle across the datasets that have non-zero ground truth (KMarket and Continue-A). On Continue-A specifically, the funnel narrows from 44,253 raw pairs down to 70 candidates, and SMT confirms 55 of those 70 as real conflicts (a per-call precision of 0.79 at the verification step). The solver returned a definite answer on every pair we handed it — no `unknown` outcomes, no timeouts — across 6988 calls in total. End-to-end runtime for all four datasets together was 105 seconds on a Windows 11 laptop with no GPU. Z3 [6] was reliable for the XACML-shaped rules in our evaluation; we do not generalise that claim to richer schemas with non-linear arithmetic.

Two things to read here. First, the detector is moderate. Similarity-only retrieves a lot of false positives because rule text reuses the same vocabulary; entity overlap and SPARQL drop those, but recall pays a price. Second, the verifier is decisive. There is no "we think this is a conflict, confidence 0.83" output anywhere in the pipeline. Every reported conflict has a witness request attached and every cleared pair has a `unsat` proof. That is the contribution: not a strong detector, but a detector deliberately calibrated to feed a strong verifier.

The threshold sweep (Figure 2) shows that F1 is fairly flat in a 0.5-0.7 band, which is a good sign for transferability — you are not balanced on a knife-edge. The main results are in Table 1; supplemental figures (filter cascade, SMT outcome distribution per dataset, runtime breakdown) are in `results_v2/figures/` in the public repository [16].

## What we learned

**1. Similarity is not enough.** Two policy rules can have ~0.9 cosine similarity and still target completely different scopes. The reverse also happens: two rules with ~0.4 similarity can be hard contradictions because the wording is different but the underlying semantics collapse. The semantic stage is best understood as a recall-preserving funnel, not as a classifier.

**2. The SPARQL filter is cheap and load-bearing.** It cut solver candidates by roughly an order of magnitude on Continue-A. Without it the SMT stage still works, but with it the pipeline runs in seconds rather than tens of seconds on a laptop.

**3. Z3 on XACML-shaped rules is fast and decisive in our evaluation.** Median solve time per pair was a few milliseconds. We observed zero `unknown` outcomes and zero timeouts under a five-second per-call budget on the four datasets we tested. This will not scale to richer attribute-based access-control schemas with non-linear arithmetic or recursion over policy sets, but for the equality-and-comparison scope of typical XACML rules, the solver was a tool we could plan budget around.

**4. Ground truth by arithmetic is a trap.** Our first labeller counted "every Permit-Deny pair where the rules share resource type" as a conflict. On Continue-A, where every rule shares the same resource type, that collapsed to "every Permit-Deny pair." The number it produced — 14,280 — was exactly Permits (238) times Denies (60). On Synthetic360 the same pattern produced 32,399, exactly 179 times 181. We caught it because both numbers factored too cleanly. The fix was to use the SMT result as the source of truth. The lesson generalises: any "ground truth" that is an arithmetic identity over your input is suspect.

**5. Synthetic stress-test data does not always behave like real policy.** The Synthetic360 dataset stacks so many `AnyOf` constraints that under strict XACML semantics every rule's scope is unsatisfiable on its own. The verifier correctly identifies this; under the original wildcard-leaky encoder, every cross-effect pair looked like a conflict.

**6. Witness-as-request makes audit defensible.** When a reviewer asks how we know a conflict is real, the witness gives reviewers concrete evidence to inspect — a request they can dispatch against the live PDP and observe two enforcement answers come back. We have found witness rendering to be the single most important interface decision in the pipeline.

### Threats to validity

Two we want to flag up front. First, our datasets are public XACML benchmarks; they are not the kind of cross-framework policy mix that a real bank or healthcare organisation operates. The conflict-detection numbers we report are honest measurements against a strict XACML oracle on these datasets, but they should not be over-generalised. Second, the SMT encoder currently ignores XACML obligations and advice. A pair that the solver labels `unsat` could still produce contradictory obligations at run time even when the effect is consistent, and we do not yet model that. Both threats are limitations of scope rather than of the approach.

We also want to be transparent about a non-finding: the detection F1 we report is moderate (around 0.30 macro across the two datasets with non-zero ground truth), and we are not claiming the detector is the contribution. Earlier versions of this work reported much higher F1 numbers against a permissive ground-truth definition that turned out to be the bug we describe in the GT-counting sidebar. With the corrected oracle, the honest detection numbers are lower — but the verification step is what compliance teams need, and the verification step is decisive.

## What's next

The current encoding handles equality and basic comparison operators on string and numeric attributes. Three pragmatic next steps:

- **Regex and obligation reasoning.** XACML's regex predicates and obligation/advice machinery are not yet in the encoder. Both are pragmatic additions; neither requires a fundamentally different solver back-end.
- **CI gate.** A policy-as-code change that introduces an `unsat` -> `sat` regression on a previously cleared pair should fail the build the same way a unit test does. We are working on a thin GitHub Action that runs the pipeline on changed rules and posts the witness as a PR comment.
- **Live PDP integration.** The witness request is currently a text artefact; the obvious next step is to dispatch it against the live PDP automatically and show the auditor the two enforcement answers side by side.

For practitioners shipping policy-as-code today, the takeaway is simpler. Do not trust a similarity model to tell you whether two rules contradict. Use cheap filters to cut the search space, then let a solver give you a witness or a proof of non-conflict. The solver is fast enough on XACML-shaped rules for it to be a routine part of the build, not a quarterly audit ritual. And whenever a "conflict count" looks like a clean factorisation of two rule subtotals, look again — you may be measuring an arithmetic identity instead of a fact about your policy.

### How to adopt this in your own pipeline

Start with normalisation: pick or invent a Common Policy Model that covers every framework you care about, and write the importers — XACML, Rego, OSCAL, internal YAML — so they all land in the same shape. Going broad and shallow on the CPM beats going narrow and deep — the marginal correctness from a richer CPM is usually less than the marginal coverage you get from supporting a third or fourth framework.

Next, plug in a sentence-transformer for similarity screening. We used `all-MiniLM-L6-v2` because it is small, fast on CPU, and good enough for the triage role. Tune the threshold on a validation slice of your own data; the 0.65 we report is a reasonable starting point.

Then add the structural filters. Entity overlap is the cheap one and gives you most of the precision improvement; a SPARQL or graph-query layer adds another order-of-magnitude reduction in solver candidates if you can afford the engineering cost of an RDF view.

Finally, run Z3 on the survivors with a fixed per-call budget. Render every `sat` model as a request the auditor can replay. Persist the witnesses; they are the only artefact you need to defend a conflict claim to a regulator. Treat unsat-scope rules as dead code and surface them to the rule author. And if you are tempted to write your own "ground-truth" labeller for evaluation, do not — the SMT result is the ground truth.

## Data and code availability

All code, datasets (XACML files), v2 pipeline, figure-generation scripts, and the IEEE Software manuscript source are available at the public repository [16]. The four datasets used in this article are public XACML benchmarks distributed with prior work in the field. The corrected v2 pipeline reproduces every number reported in this article in approximately 100 seconds on a Windows 11 laptop without a GPU.

## Funding

This work received no external funding.

## Conflict of interest

The authors declare no conflict of interest.

## The Authors

**Rabea Al Haj Eid** is a research student at Princess Sumaya University for Technology in Amman, Jordan. He works on policy reasoning and applied formal methods for governance, risk, and compliance pipelines. Contact: rab20248091@std.psut.edu.jo.

**Mu'awya Al-Dala'ien** is a faculty member at Princess Sumaya University for Technology in Amman, Jordan. His research focuses on cybersecurity governance, regulated digital services, and the engineering of compliance automation. Contact: m.aldalaien@psut.edu.jo.

**Mohammad Al Haj Eid** is a faculty member at the Higher Colleges of Technology in Fujairah, UAE. His work spans secure software engineering, access-control automation, and applied AI for cybersecurity. Contact: Malhajeid@hct.ac.ae.
