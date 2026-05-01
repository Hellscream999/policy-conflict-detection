# Policy Conflict Detection (XACML, SMT-Verified)

A reproducible Python pipeline for detecting reachable conflicts in XACML 3.0
access-control policies. The pipeline combines a candidate-generation funnel
(semantic similarity, entity overlap, SPARQL structural checks) with a Z3
SMT verifier that returns a concrete witness request whenever two rules
genuinely conflict.

This repository is the **v2 corrected implementation**. It exists to
reproduce, end-to-end, every number in the project's experimental results.

---

## Quick start

```bash
git clone https://github.com/Hellscream999/policy-conflict-detection.git
cd policy-conflict-detection
pip install -r requirements.txt
pip install z3-solver sentence-transformers rdflib

python prove_paper_v2.py
```

End-to-end runtime on a Windows 11 laptop, no GPU, Python 3.12: **~100 seconds**.

Outputs land in `results_v2/`.

To regenerate the figures from those results:

```bash
python -c "import sys, os; sys.path.insert(0, 'src'); from figures_v2 import main; main()"
```

---

## Reproducible results

| Dataset       | Rules | Pairs   | GT conflicts | SMT confirmed | Time (s) |
|---------------|-------|---------|--------------|---------------|----------|
| GEYSERS       |   15  |    105  |       0      |       0       |   17.5   |
| KMarket       |    5  |     10  |       4      |       1       |   11.8   |
| Continue-A    |  298  | 44,253  |     482      |      55       |   34.1   |
| Synthetic360  |  360  | 64,620  |       0      |       0       |   42.0   |

- **Macro Precision / Recall / F1** (datasets with non-zero GT): **0.89 / 0.18 / 0.30**
- **SMT coverage**: 6,988 calls, 0 unknowns, 0 timeouts (100%)
- **Witness requests** for confirmed conflicts: written to `results_v2/conflicts.csv`

The Synthetic360 rules' accumulated `AnyOf` constraints are themselves
unsatisfiable under strict XACML semantics, so the dataset reports zero
reachable conflicts. The verifier correctly identifies this.

---

## What v2 corrects

The v1 pipeline (`prove_paper.py`, `src/parsers/xacml_parser.py`,
`src/verification/smt_verifier.py`) had three bugs that produced
arithmetic-shaped numbers instead of policy facts:

1. **Ground-truth labelling collapsed to an arithmetic identity.**
   `prove_paper.py` (`compute_ground_truth`) marked any Permit×Deny pair
   sharing a resource type, action, or identifier as a conflict. On
   Continue-A every rule shares the same resource type, so the labeller
   produced exactly Permits × Denies = 238 × 60 = **14,280** ground-truth
   conflicts. Synthetic360 produced 179 × 181 = **32,399** the same way.

2. **The SMT encoder was wildcard-leaky.**
   `src/verification/smt_verifier.py` added an `Or(q == "any_*")` disjunct
   to every applicability constraint, so Z3 trivially satisfied the
   conjunction by setting every request variable to its wildcard sentinel.
   This made every cross-effect pair return `sat`.

3. **SMT verification was sample-capped at 1,000 calls.**
   `prove_paper.py` capped solver calls at 1,000 per dataset, so the
   summary tables reported `SMT SAT = 1000` for both Continue-A and
   Synthetic360 — a hard cap masquerading as a count.

4. **The XACML parser ignored hierarchical inheritance.**
   `src/parsers/xacml_parser.py` only read each `<Rule>`'s own `<Target>`.
   In Continue-A every rule has an empty target and inherits its scope from
   the parent `<Policy>` and `<PolicySet>`, so the v1 parser collapsed all
   298 rules to identical CPM scope.

### Files added in v2

| File | Change |
|------|--------|
| `src/parsers/xacml_parser_v2.py` | Walks `PolicySet → Policy → Rule`, accumulates each level's `<Target>`. Preserves XACML `AnyOf`/`AllOf` semantics. |
| `src/verification/smt_verifier_v2.py` | Drops the `any_*` wildcard disjuncts. Two rules conflict iff a concrete request satisfies both rules' applicability formulas simultaneously. |
| `src/oracle_gt.py` | Ground truth = SMT result on every rule pair. Same-effect pairs short-circuit. |
| `prove_paper_v2.py` | Removes the 1,000-cap. Adds per-rule scope-satisfiability precheck so dead-code rules short-circuit every pair they participate in. Deduplicates SMT candidates. |
| `src/figures_v2.py` | Six figures at 300 DPI, PNG + PDF. |

---

## Repository layout

```
policy-conflict-detection/
├── prove_paper_v2.py               # MAIN ENTRY — runs the v2 pipeline
├── prove_paper.py                  # v1 entry (kept for comparison only)
├── evaluate_datasets.py            # Dataset-only evaluation
├── generate_figures.py             # Older figure script
├── run_proof.bat                   # Windows batch runner
├── requirements.txt                # Python dependencies
├── LICENSE                         # MIT License
├── README.md                       # This file
│
├── src/
│   ├── models/cpm.py               # Common Policy Model
│   ├── parsers/
│   │   ├── xacml_parser.py         # v1 parser (buggy — kept for comparison)
│   │   └── xacml_parser_v2.py      # v2 parser (hierarchical, correct)
│   ├── detection/
│   │   ├── semantic_screener.py    # Stage 1: BERT / TF-IDF screening
│   │   ├── entity_validator.py     # Stage 2: entity overlap
│   │   └── sparql_validator.py     # Stage 3: SPARQL structural checks
│   ├── verification/
│   │   ├── smt_verifier.py         # v1 verifier (wildcard-leaky)
│   │   └── smt_verifier_v2.py      # v2 verifier (corrected encoder)
│   ├── oracle_gt.py                # SMT-derived ground truth
│   ├── figures_v2.py               # Figure generation
│   ├── codegen/                    # Rego/XACML emit (post-resolution)
│   ├── exporters/                  # Rego export
│   ├── resolution/                 # Conflict resolution strategies
│   ├── testing/                    # OPA test harness
│   └── pipeline.py                 # End-to-end orchestrator
│
├── datasets/                       # XACML test datasets
│   ├── GEYSERS.xml                 # 15 rules
│   ├── continue-a-xacml3.xml       # 298 rules
│   ├── KMarket.xml                 # 5 rules
│   └── synthetic360.xml            # 360 rules
│
├── results/                        # v1 results (legacy)
└── results_v2/                     # v2 outputs
    ├── summary.csv                 # Per-dataset metrics
    ├── conflicts.csv               # Detected conflicts + SMT witnesses
    ├── threshold_sweep.csv         # Threshold-vs-metrics data
    ├── raw.json                    # Full raw output
    └── figures/                    # 6 figures (PNG + PDF)
```

---

## Pipeline stages

| Stage | Module | Description |
|-------|--------|-------------|
| Parse | `xacml_parser_v2.py` | XACML → CPM, walking `PolicySet → Policy → Rule` and accumulating inherited `Target`s. |
| Screen | `semantic_screener.py` | Cosine similarity over BERT embeddings (TF-IDF fallback). |
| Validate | `entity_validator.py` | Jaccard overlap on Subject / Action / Resource. |
| Filter | `sparql_validator.py` | Structural RDF/SPARQL checks. |
| Verify | `smt_verifier_v2.py` | Z3 satisfiability on the conjunction of both rules' applicability formulas. SAT ⇒ real conflict + concrete witness request. |
| Oracle | `oracle_gt.py` | Same SMT solver applied to *every* rule pair to produce ground truth, replacing the v1 arithmetic heuristic. |

---

## Datasets

The four XACML files in `datasets/` are public benchmarks distributed with
prior policy-analysis work:

- **GEYSERS** — EU GEYSERS project, 15 rules.
- **Continue-A** — University access-control benchmark, 298 rules.
- **KMarket** — E-commerce marketplace, 5 rules.
- **Synthetic360** — Synthetic 360-rule benchmark.

---

## Requirements

- Python 3.10+ (tested on 3.12)
- `z3-solver` for the SMT verifier
- `sentence-transformers` for BERT embeddings (TF-IDF fallback if absent)
- `rdflib` for the SPARQL stage
- `matplotlib` and `numpy` for figures

```bash
pip install -r requirements.txt
pip install z3-solver sentence-transformers rdflib
```

---

## License

MIT — see `LICENSE`.
