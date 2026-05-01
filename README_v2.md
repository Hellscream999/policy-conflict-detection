# Policy Conflict Detection — v2 Corrected Implementation

This is the corrected production version of the policy conflict detection pipeline. It fixes three critical bugs in the v1 release (`prove_paper.py`, `src/parsers/xacml_parser.py`, `src/verification/smt_verifier.py`) and includes an IEEE Software feature article ready for submission.

## What was wrong in v1

1. **Ground-truth labelling collapsed to an arithmetic identity.** `prove_paper.py:271-298` (`compute_ground_truth`) marked any Permit×Deny pair sharing a resource type, action, or identifier as a conflict. On Continue-A every rule shares the same resource type, so the labeller produced exactly Permits × Denies = 238 × 60 = **14,280** GT conflicts. Synthetic360 produced 179 × 181 = **32,399** the same way. Both numbers are arithmetic identities, not facts about the policies.

2. **The SMT encoder was wildcard-leaky.** `src/verification/smt_verifier.py:163-167` added an `Or(q == "any_*")` disjunct to every applicability constraint, so Z3 trivially satisfied the conjunction by setting every request variable to its wildcard sentinel. This made every cross-effect pair return `sat`, regardless of actual scope.

3. **SMT verification was sample-capped at 1000.** `prove_paper.py:448` (`max_smt_checks = min(len(sparql_validated), 1000)`) capped solver calls so Table IV reported `SMT SAT = 1000` for both Continue-A and Synthetic360 — a hard cap masquerading as a count.

4. **The XACML parser ignored hierarchical inheritance.** `src/parsers/xacml_parser.py` only read each `<Rule>`'s own `<Target>`. In Continue-A every rule has an empty target and inherits its scope from the parent `<Policy>` and `<PolicySet>`, so the v1 parser collapsed all 298 rules to identical CPM scope.

## Corrections in v2

| File | Change |
|------|--------|
| `src/parsers/xacml_parser_v2.py` | Walks `PolicySet → Policy → Rule`, accumulates each level's `<Target>`. Preserves XACML `AnyOf`/`AllOf` semantics: target = AND over AnyOf groups, AnyOf = OR over AllOf branches, AllOf = AND over Match constraints. Captures `Category`, `AttributeId`, operator, value, datatype per match. |
| `src/verification/smt_verifier_v2.py` | Drops the `any_*` wildcard disjuncts. Two rules conflict iff there exists a concrete request that satisfies both rules' applicability formulas simultaneously. Single Z3 variable per attribute (so `eq` and `leq` interact correctly). Numeric vs string variable kind decided once per attribute. |
| `src/oracle_gt.py` | Ground truth = SMT result on every rule pair. Same-effect pairs short-circuit. |
| `prove_paper_v2.py` | Removes the 1000-cap. Adds per-rule scope-satisfiability precheck so dead-code rules short-circuit every pair they participate in. Deduplicates SMT candidates. |
| `src/figures_v2.py` | Six publication-quality figures at 300 DPI, PNG + PDF, IEEE Software palette. |
| `src/build_paper_v2.py` | Builds the IEEE Software feature article (`.docx`) with embedded figures and three sidebars. |

## Running the Pipeline

```bash
git clone https://github.com/Hellscream999/policy-conflict-detection.git
cd policy-conflict-detection
pip install -r requirements.txt
pip install z3-solver sentence-transformers rdflib python-docx

python prove_paper_v2.py        # writes results_v2/summary.csv etc.
python finalize_paper.py        # writes figures + paper/IEEE_Software_PolicyConflict_v1.docx
```

End-to-end runtime on a Windows 11 laptop, no GPU, Python 3.12: ~100 seconds.

## Results

| Dataset       | Rules | Pairs   | GT conflicts | SMT confirmed | Time (s) |
|---------------|-------|---------|--------------|---------------|----------|
| GEYSERS       |   15  |    105  |       0      |       0       |   17.5   |
| KMarket       |    5  |     10  |       4      |       1       |   11.8   |
| Continue-A    |  298  | 44,253  |     482      |      55       |   34.1   |
| Synthetic360  |  360  | 64,620  |       0      |       0       |   42.0   |

- Macro Precision / Recall / F1 (datasets with non-zero GT): **0.89 / 0.18 / 0.30**
- SMT coverage: **6,988 calls, 0 unknowns, 0 timeouts (100%)**
- 56 witness requests written to `results_v2/conflicts.csv`

The Synthetic360 rules' accumulated `AnyOf` constraints are themselves unsatisfiable under strict XACML semantics, so the dataset reports zero reachable conflicts. The verifier correctly identifies this; the v1 wildcard-leaky encoder was hiding it.

## Manuscript

`paper/IEEE_Software_PolicyConflict_v2.docx` — IEEE Software feature article (~4,800 words, three embedded figures, three sidebars including a public debrief of the ground-truth bug, 18 references). Markdown source: `paper/manuscript.md`.
