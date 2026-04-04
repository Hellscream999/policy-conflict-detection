# Unified Framework for Detecting and Resolving Policy Conflicts

A Python implementation of a multi-stage pipeline for detecting and resolving conflicts in access control policies (XACML). The framework uses semantic similarity screening, entity validation, SPARQL structural checks, and SMT (Z3) formal verification to identify conflicting Permit/Deny rules across heterogeneous policy datasets.

> **Paper:** *Unified Framework for Detecting and Resolving Policy Conflicts*  
> **Author:** Rabea Al Haj Eid  
> **Institution:** Princess Sumaya University for Technology (PSUT)  
> **Year:** 2026

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/policy-conflict-detection.git
cd policy-conflict-detection

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the complete experiment (all 10 claims)
python prove_paper.py

# 4. View the generated figures and results
# Figures → figures/
# Results → results/summary.csv and results/conflicts.csv
```

**On Windows**, you can also double-click `run_proof.bat` to run the full experiment automatically.

---

## Project Structure

```
policy-conflict-detection/
│
├── prove_paper.py              # MAIN ENTRY POINT — Proves all 10 research claims
├── evaluate_datasets.py        # Dataset-only evaluation (simpler version)
├── generate_figures.py         # Standalone figure generation
├── run_proof.bat               # Windows batch runner
├── requirements.txt            # Python dependencies
├── LICENSE                     # MIT License
├── README.md                   # This file
│
├── src/                        # Core source code
│   ├── models/
│   │   └── cpm.py              # Common Policy Model (CPM) data structures
│   ├── parsers/
│   │   └── xacml_parser.py     # XACML 3.0 policy file parser
│   ├── detection/
│   │   ├── semantic_screener.py    # Stage 2.1: BERT semantic similarity screening
│   │   ├── entity_validator.py     # Stage 2.2: Entity overlap validation
│   │   └── sparql_validator.py     # Stage 2.3: SPARQL structural checks
│   ├── verification/
│   │   └── smt_verifier.py     # Stage 3: Z3 SMT formal verification
│   ├── resolution/
│   │   └── resolver.py         # Conflict resolution strategies
│   ├── codegen/
│   │   └── generator.py        # Rego & XACML code generation
│   ├── exporters/
│   │   └── rego_generator.py   # OPA Rego policy export
│   ├── testing/
│   │   └── opa_harness.py      # OPA test harness
│   └── pipeline.py             # End-to-end pipeline orchestrator
│
├── datasets/                   # XACML test datasets
│   ├── GEYSERS.xml             # EU GEYSERS project (15 rules)
│   ├── continue-a-xacml3.xml   # Continue-A access control (298 rules)
│   ├── KMarket.xml             # E-commerce marketplace (5 rules)
│   └── synthetic360.xml        # Synthetic benchmark (360 rules)
│
├── figures/                    # Generated proof figures (PNG)
│   ├── 01_conflict_definition_proof.png
│   ├── 02_similarity_distribution.png
│   ├── 03_threshold_justification.png
│   ├── 04_05_pipeline_stages.png
│   ├── 06_smt_coverage.png
│   ├── 07_runtime_performance.png
│   ├── 08_baseline_comparison.png
│   └── 09_dataset_generalization.png
│
└── results/                    # Experiment output data
    ├── summary.csv             # Per-dataset precision/recall/F1 metrics
    └── conflicts.csv           # All detected conflicts with SMT witnesses
```

---

## How the Experiment Works

The experiment is executed by running `prove_paper.py`. It performs the following steps in sequence:

### 1. Dataset Loading
The script locates XACML policy files in the `datasets/` folder. Four public datasets are used: **GEYSERS** (15 rules), **Continue-A** (298 rules), **KMarket** (5 rules), and **Synthetic360** (360 rules). Each file is parsed by `src/parsers/xacml_parser.py`, which extracts individual `<Rule>` elements and converts them into a **Common Policy Model (CPM)** representation defined in `src/models/cpm.py`.

### 2. Ground Truth Computation
For each dataset, the script computes a **ground truth** set of conflicts. Two rules are considered ground-truth conflicts if: (a) they have **opposite effects** (one Permit, one Deny), and (b) they have **overlapping scope** (same resource type or action). This is a conservative heuristic used as a baseline for evaluating the pipeline's precision and recall.

### 3. Three-Stage Detection Pipeline
For each dataset, the script runs the full detection pipeline through three stages:

| Stage | Module | Description |
|-------|--------|-------------|
| **2.1 Semantic Screening** | `semantic_screener.py` | Computes BERT embeddings (or TF-IDF fallback) for each rule's text summary, then selects candidate pairs with cosine similarity ≥ threshold (default 0.5). Only Permit vs. Deny pairs are considered. |
| **2.2 Entity Validation** | `entity_validator.py` | Computes Jaccard overlap of Subject, Action, and Resource entities between candidates. Pairs below the entity overlap threshold (default 0.3) are discarded. |
| **2.3 SPARQL Validation** | `sparql_validator.py` | Performs structural checks: verifies opposite effects, shared resources, and builds an RDF graph (if `rdflib` is installed) to validate relationships. |
| **3.1 SMT Verification** | `smt_verifier.py` | Uses the Z3 SMT solver (or fallback) to formally verify each remaining candidate. A **SAT** result means the conflict is real, with a **witness request** (subject, action, resource) that triggers both rules simultaneously. |

### 4. Baseline Comparison
The script also runs two baseline methods on the same datasets:
- **TF-IDF Baseline**: Uses TF-IDF vectors and cosine similarity (threshold 0.3) to find candidates.
- **Keyword Overlap Baseline**: Uses Jaccard similarity of extracted keywords (threshold 0.2).

### 5. Metrics Computation
For each pipeline stage and baseline, the script computes **Precision**, **Recall**, and **F1 Score** against the ground truth. Results are aggregated across datasets.

### 6. Figure Generation
Nine figures are generated into `figures/` proving each of the 10 research claims (see table below).

### 7. CSV Export
Two CSV files are saved to `results/`:
- `summary.csv`: Per-dataset metrics (precision, recall, F1, timing) for each pipeline stage.
- `conflicts.csv`: Every detected conflict with rule IDs, similarity scores, SMT results, and witness requests.

---

## 10 Research Claims Proven

| # | Claim | Evidence |
|---|-------|----------|
| 1 | **Conflict Definition Correctness** | `01_conflict_definition_proof.png` — Z3 SAT witnesses proving each conflict |
| 2 | **Semantic Similarity Works** | `02_similarity_distribution.png` — Score distribution histogram |
| 3 | **Threshold 0.65 Justified** | `03_threshold_justification.png` — Precision-Recall curve, F1 vs. threshold |
| 4 | **Entity Overlap Improves Precision** | `04_05_pipeline_stages.png` (left) — Before/after entity filtering |
| 5 | **SPARQL Improves Accuracy** | `04_05_pipeline_stages.png` (right) — Before/after SPARQL filtering |
| 6 | **SMT 100% Coverage** | `06_smt_coverage.png` — Pie chart of SAT/UNSAT outcomes |
| 7 | **Runtime Feasibility** | `07_runtime_performance.png` — Timing breakdown, scalability, solve times |
| 8 | **Beats Baselines** | `08_baseline_comparison.png` — Our pipeline vs. TF-IDF vs. Keyword |
| 9 | **Dataset Generalization** | `09_dataset_generalization.png` — F1 and runtime across 4 datasets |
| 10 | **Reproducibility** | `results/conflicts.csv` + random seed 42 → deterministic output |

---

## Reproducing the Experiment

### Prerequisites

- **Python 3.10+**
- **pip** (Python package manager)

### Step-by-Step Instructions

```bash
# 1. Install core dependencies (required)
pip install matplotlib numpy

# 2. (Optional) Install full dependencies for maximum accuracy
pip install z3-solver rdflib sentence-transformers torch

# 3. Run the complete experiment
python prove_paper.py

# 4. Examine outputs
#    - Figures are saved to figures/
#    - CSV results are saved to results/
#    - Console output shows per-dataset metrics
```

> **Note:** The framework includes **fallback implementations** for all optional dependencies. If `sentence-transformers` is not installed, it uses TF-IDF word overlap for similarity. If `z3-solver` is not installed, it uses a deterministic heuristic for SMT verification. If `rdflib` is not installed, it uses structural string matching for SPARQL checks. The results will be qualitatively similar but not identical to the full-dependency run.

### Running Individual Components

```bash
# Common Policy Model demonstration
python src/models/cpm.py

# Semantic screening only
python src/detection/semantic_screener.py

# SMT verification only
python src/verification/smt_verifier.py

# Resolution strategies
python src/resolution/resolver.py

# Full pipeline with sample policies
python src/pipeline.py

# Standalone figure generation
python generate_figures.py

# Dataset evaluation (without claim proofs)
python evaluate_datasets.py
```

---

## Datasets

| Dataset | Rules | Permit | Deny | Source |
|---------|------:|-------:|-----:|--------|
| **GEYSERS** | 15 | 15 | 0 | EU GEYSERS project — network infrastructure policies |
| **Continue-A** | 298 | 238 | 60 | Continue-A — access control benchmark |
| **KMarket** | 5 | 1 | 4 | E-commerce marketplace policies |
| **Synthetic360** | 360 | 179 | 181 | Synthetic benchmark with mixed conflicts |

All datasets are in **XACML 3.0** format and sourced from the [XACs-DyPol](https://github.com/) public access control policy repository.

---

## Key Results

### Pipeline Achieves High Precision on Continue-A

| Stage | Precision | Recall | F1 |
|-------|----------:|-------:|---:|
| Similarity Only | 0.32 | 1.00 | 0.49 |
| + Entity Overlap | 0.32 | 1.00 | 0.49 |
| **+ SPARQL** | **1.00** | **1.00** | **1.00** |

### Beats All Baselines (Average F1 Across Datasets)

| Method | F1 |
|--------|---:|
| TF-IDF Baseline | 0.10 |
| Keyword Overlap | 0.43 |
| **Our Pipeline** | **0.65** |

---

## Dependencies

| Package | Required | Purpose |
|---------|----------|---------|
| `matplotlib` | ✅ Yes | Figure generation |
| `numpy` | ✅ Yes | Numerical computation |
| `sentence-transformers` | ❌ Optional | BERT embeddings for semantic screening |
| `torch` | ❌ Optional | Required by sentence-transformers |
| `z3-solver` | ❌ Optional | SMT formal verification |
| `rdflib` | ❌ Optional | RDF/SPARQL structural validation |

---

## Citation

```bibtex
@thesis{alhajeid2026unified,
  title   = {Unified Framework for Detecting and Resolving Policy Conflicts},
  author  = {Al Haj Eid, Rabea},
  school  = {Princess Sumaya University for Technology},
  year    = {2026},
  type    = {Master's Thesis}
}
```

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
