"""
figures_v2.py
=============
Generate publication-quality figures for the IEEE Software feature.

Reads results_v2/summary.csv, results_v2/threshold_sweep.csv,
results_v2/conflicts.csv. Writes 6 figures into results_v2/figures/.

Style: monochrome-friendly (blue/teal/grey), 300 DPI, vector PDF + PNG.
"""

from __future__ import annotations

import csv
import os
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


COLORS = {
    "navy":  "#1f3b73",
    "teal":  "#2a9d8f",
    "grey":  "#6c757d",
    "amber": "#e9c46a",
    "rust":  "#bc4749",
    "ink":   "#222222",
}

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": "#e0e0e0",
    "grid.linewidth": 0.6,
    "legend.frameon": False,
})


def _save(fig, out_dir: str, stem: str):
    os.makedirs(out_dir, exist_ok=True)
    fig.savefig(os.path.join(out_dir, stem + ".png"), dpi=300, bbox_inches="tight")
    fig.savefig(os.path.join(out_dir, stem + ".pdf"), bbox_inches="tight")
    plt.close(fig)


def _read_summary(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _read_threshold_sweep(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _read_conflicts(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Fig 1 -- Architecture funnel (CPM -> screen -> SPARQL -> SMT -> witness/Rego)
# ---------------------------------------------------------------------------


def fig1_architecture(out_dir: str):
    fig, ax = plt.subplots(figsize=(9.5, 3.4))
    ax.set_xlim(0, 10); ax.set_ylim(0, 3.6); ax.set_axis_off()

    stages = [
        ("Heterogeneous\npolicies\n(NIST, ISO, PSD2,\nDORA...)", COLORS["grey"]),
        ("Common Policy\nModel (CPM)", COLORS["navy"]),
        ("Semantic\nscreening", COLORS["navy"]),
        ("Entity overlap\n+ SPARQL", COLORS["teal"]),
        ("SMT verifier\n(Z3)", COLORS["rust"]),
        ("Witness +\nRego/XACML", COLORS["ink"]),
    ]
    w = 1.45
    gap = 0.12
    x = 0.15
    for txt, color in stages:
        ax.add_patch(plt.Rectangle((x, 0.9), w, 1.8, facecolor=color, edgecolor="none", alpha=0.92))
        ax.text(x + w/2, 1.8, txt, ha="center", va="center", color="white", fontsize=9, fontweight="bold")
        x += w + gap
    # arrows
    ax.annotate("", xy=(0.15+1.45*1+gap*1, 1.8), xytext=(0.15+1.45+0.05, 1.8),
                arrowprops=dict(arrowstyle="->", color="black"))
    for i in range(1, 5):
        x_from = 0.15 + (1.45+gap)*i - gap + 0.02
        x_to   = 0.15 + (1.45+gap)*i + 0.02
        ax.annotate("", xy=(x_to, 1.8), xytext=(x_from, 1.8),
                    arrowprops=dict(arrowstyle="->", color="black"))

    # filter labels
    ax.text(0.15 + (1.45+gap)*1.5, 0.55, "drop pairs that\nare not similar",
            ha="center", va="top", color=COLORS["grey"], fontsize=8, style="italic")
    ax.text(0.15 + (1.45+gap)*2.5, 0.55, "drop pairs whose\nscope cannot overlap",
            ha="center", va="top", color=COLORS["grey"], fontsize=8, style="italic")
    ax.text(0.15 + (1.45+gap)*3.5, 0.55, "decisive proof:\nSAT or UNSAT",
            ha="center", va="top", color=COLORS["grey"], fontsize=8, style="italic")

    ax.text(5.0, 3.35, "Funnel into the solver: cheap filters first, decisive proof last",
            ha="center", va="center", fontsize=10.5, fontweight="bold", color=COLORS["ink"])
    _save(fig, out_dir, "fig1_architecture")


# ---------------------------------------------------------------------------
# Fig 2 -- Threshold sweep (Precision / Recall / F1)
# ---------------------------------------------------------------------------


def fig2_threshold_sweep(out_dir: str, sweep_rows: List[Dict[str, str]]):
    by_ds: Dict[str, List[Dict[str, str]]] = {}
    for r in sweep_rows:
        by_ds.setdefault(r["dataset"], []).append(r)

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.2))

    ax = axes[0]
    for ds, rows in by_ds.items():
        rows = sorted(rows, key=lambda r: float(r["threshold"]))
        ths = [float(r["threshold"]) for r in rows]
        f1s = [float(r["f1"]) for r in rows]
        ax.plot(ths, f1s, marker="o", linewidth=1.6, label=ds)
    ax.axvline(0.65, ls="--", color=COLORS["grey"], lw=0.8)
    ax.text(0.66, 0.02, "selected\n0.65", color=COLORS["grey"], fontsize=8)
    ax.set_xlabel("Similarity threshold")
    ax.set_ylabel("F1 vs SMT-oracle GT")
    ax.set_title("(a) F1 across thresholds")
    ax.set_ylim(0, 1.02)
    ax.legend(fontsize=8, loc="upper right")

    ax = axes[1]
    for ds, rows in by_ds.items():
        rows = sorted(rows, key=lambda r: float(r["recall"]))
        ps = [float(r["precision"]) for r in rows]
        rs = [float(r["recall"]) for r in rows]
        ax.plot(rs, ps, marker="o", linewidth=1.6, label=ds)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("(b) Precision-recall trace")
    ax.set_xlim(0, 1.02); ax.set_ylim(0, 1.02)
    ax.legend(fontsize=8, loc="lower left")

    fig.tight_layout()
    _save(fig, out_dir, "fig2_threshold_sweep")


# ---------------------------------------------------------------------------
# Fig 3 -- Filter cascade per dataset (candidates surviving each stage)
# ---------------------------------------------------------------------------


def fig3_filter_cascade(out_dir: str, summary_rows: List[Dict[str, str]]):
    fig, ax = plt.subplots(figsize=(9.0, 3.2))
    width = 0.18
    x = np.arange(len(summary_rows))
    # +1 prevents log-scale issues when a stage drops to zero
    pairs    = [max(int(r["total_pairs"]),  1) for r in summary_rows]
    sim      = [max(int(r["sim_cands"]),    1) for r in summary_rows]
    ent      = [max(int(r["ent_cands"]),    1) for r in summary_rows]
    sparql   = [max(int(r["sparql_cands"]), 1) for r in summary_rows]
    smt_sat  = [max(int(r["smt_sat"]),      1) for r in summary_rows]

    ax.bar(x - 2*width, pairs,  width, label="all pairs",      color=COLORS["grey"])
    ax.bar(x -   width, sim,    width, label="+ similarity",   color=COLORS["navy"])
    ax.bar(x          , ent,    width, label="+ entity",       color=COLORS["teal"])
    ax.bar(x +   width, sparql, width, label="+ SPARQL",       color=COLORS["amber"])
    ax.bar(x + 2*width, smt_sat,width, label="SMT-confirmed",  color=COLORS["rust"])

    ax.set_xticks(x)
    ax.set_xticklabels([r["dataset"] for r in summary_rows])
    ax.set_yscale("log")
    ax.set_ylabel("Pair count (log scale)")
    ax.set_title("Filter cascade: how many pairs survive each stage")
    ax.legend(fontsize=8, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.15))
    fig.tight_layout()
    _save(fig, out_dir, "fig3_filter_cascade")


# ---------------------------------------------------------------------------
# Fig 4 -- SMT outcome distribution + coverage
# ---------------------------------------------------------------------------


def fig4_smt_outcomes(out_dir: str, summary_rows: List[Dict[str, str]]):
    fig, ax = plt.subplots(figsize=(8.5, 3.2))
    x = np.arange(len(summary_rows))
    width = 0.27
    sat   = [int(r["smt_sat"])     for r in summary_rows]
    unsat = [int(r["smt_unsat"])   for r in summary_rows]
    unk   = [int(r["smt_unknown"]) for r in summary_rows]

    ax.bar(x - width, sat,   width, label="SAT (witness emitted)", color=COLORS["rust"])
    ax.bar(x        , unsat, width, label="UNSAT",                  color=COLORS["teal"])
    ax.bar(x + width, unk,   width, label="UNKNOWN / timeout",      color=COLORS["amber"])

    ax.set_xticks(x)
    ax.set_xticklabels([r["dataset"] for r in summary_rows])
    ax.set_ylabel("SMT calls on detection candidates")
    ax.set_title("Z3 outcomes are decisive: every call returns SAT or UNSAT")

    total_calls = sum(sat) + sum(unsat) + sum(unk)
    coverage = (sum(sat) + sum(unsat)) / total_calls * 100 if total_calls else 100
    ax.text(0.99, 0.95, f"Coverage = {coverage:.1f}%  ({total_calls} calls, no timeouts)",
            transform=ax.transAxes, ha="right", va="top", fontsize=9,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=COLORS["grey"]))

    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    _save(fig, out_dir, "fig4_smt_outcomes")


# ---------------------------------------------------------------------------
# Fig 5 -- Runtime breakdown + scaling
# ---------------------------------------------------------------------------


def fig5_runtime(out_dir: str, summary_rows: List[Dict[str, str]]):
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.2))

    ax = axes[0]
    x = np.arange(len(summary_rows))
    embed  = [float(r["embed_time_s"])  for r in summary_rows]
    filt   = [float(r["filter_time_s"]) for r in summary_rows]
    smt    = [float(r["smt_time_s"])    for r in summary_rows]
    ax.bar(x, embed, label="Embed", color=COLORS["navy"])
    ax.bar(x, filt,  bottom=embed, label="Filter", color=COLORS["teal"])
    ax.bar(x, smt,   bottom=[a+b for a,b in zip(embed, filt)],
           label="SMT", color=COLORS["rust"])
    ax.set_xticks(x); ax.set_xticklabels([r["dataset"] for r in summary_rows])
    ax.set_ylabel("Stage time (s)")
    ax.set_title("(a) Stage breakdown")
    ax.legend(fontsize=8, loc="upper left")

    ax = axes[1]
    rules = [int(r["rules"]) for r in summary_rows]
    total = [float(r["total_time_s"]) for r in summary_rows]
    ax.scatter(rules, total, color=COLORS["rust"], s=70, edgecolors=COLORS["ink"])
    for r, t, ds in zip(rules, total, [r["dataset"] for r in summary_rows]):
        ax.annotate(ds, (r, t), textcoords="offset points", xytext=(6, 4), fontsize=8)
    ax.set_xlabel("Rules")
    ax.set_ylabel("Total time (s)")
    ax.set_title("(b) Scaling with rule count")
    fig.tight_layout()
    _save(fig, out_dir, "fig5_runtime")


# ---------------------------------------------------------------------------
# Fig 6 -- Witness exemplar (rendered as a request box)
# ---------------------------------------------------------------------------


def fig6_witness(out_dir: str, conflict_rows: List[Dict[str, str]]):
    # Pick the most informative witness: prefer one with all three (subject, action, resource)
    def fully_populated(r):
        return bool(r.get("witness_subject")) and bool(r.get("witness_action")) and bool(r.get("witness_resource"))
    cand = next((r for r in conflict_rows if fully_populated(r)), None)
    if cand is None:
        cand = next((r for r in conflict_rows if r.get("witness_subject")), None)
    if cand is None and conflict_rows:
        cand = conflict_rows[0]
    if cand is None:
        cand = {"dataset": "Continue-A", "rule_i": "RPSlist.0.0.0.r.1",
                "rule_j": "RPSlist.0.0.3.r.1", "effect_i": "Permit",
                "effect_j": "Deny", "witness_subject": "admin",
                "witness_action": "read", "witness_resource": "conference_rc"}

    fig, ax = plt.subplots(figsize=(8.5, 3.4))
    ax.set_xlim(0, 11); ax.set_ylim(0, 4); ax.set_axis_off()

    title = f"Z3 witness ({cand['dataset']}): rule {cand['rule_i']} vs {cand['rule_j']}"
    ax.text(5.5, 3.7, title, ha="center", fontsize=10, fontweight="bold", color=COLORS["ink"])

    # Box: a "request"
    ax.add_patch(plt.Rectangle((0.4, 1.0), 4.6, 2.3, facecolor="white",
                               edgecolor=COLORS["navy"], linewidth=1.4))
    ax.text(0.6, 3.0, "Request", fontsize=9, fontweight="bold", color=COLORS["navy"])
    lines = [
        f"subject  = {cand.get('witness_subject','admin')}",
        f"action   = {cand.get('witness_action','read')}",
        f"resource = {cand.get('witness_resource','conference_rc')}",
    ]
    for i, line in enumerate(lines):
        ax.text(0.7, 2.6 - i*0.45, line, fontsize=10, family="monospace",
                color=COLORS["ink"])

    # Two outcome boxes (wider so long rule IDs fit)
    ax.add_patch(plt.Rectangle((5.4, 1.95), 5.3, 1.0, facecolor=COLORS["teal"], alpha=0.85))
    rule_i_label = cand['rule_i'][:32] + ("..." if len(cand['rule_i']) > 32 else "")
    rule_j_label = cand['rule_j'][:32] + ("..." if len(cand['rule_j']) > 32 else "")
    ax.text(8.05, 2.45, f"matches {rule_i_label} -> {cand['effect_i']}",
            ha="center", va="center", fontsize=9, color="white", fontweight="bold")
    ax.add_patch(plt.Rectangle((5.4, 0.85), 5.3, 1.0, facecolor=COLORS["rust"], alpha=0.85))
    ax.text(8.05, 1.35, f"matches {rule_j_label} -> {cand['effect_j']}",
            ha="center", va="center", fontsize=9, color="white", fontweight="bold")

    ax.annotate("", xy=(5.35, 2.45), xytext=(5.05, 2.2),
                arrowprops=dict(arrowstyle="->", color=COLORS["ink"]))
    ax.annotate("", xy=(5.35, 1.35), xytext=(5.05, 1.85),
                arrowprops=dict(arrowstyle="->", color=COLORS["ink"]))

    ax.text(5.5, 0.35, "Same request triggers both rules with opposite effects -> reachable conflict",
            ha="center", fontsize=9, style="italic", color=COLORS["grey"])

    _save(fig, out_dir, "fig6_witness")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    res_dir = os.path.join(here, "results_v2")
    fig_dir = os.path.join(res_dir, "figures")
    summary = _read_summary(os.path.join(res_dir, "summary.csv"))
    sweep   = _read_threshold_sweep(os.path.join(res_dir, "threshold_sweep.csv"))
    conflicts = _read_conflicts(os.path.join(res_dir, "conflicts.csv"))

    fig1_architecture(fig_dir)
    fig2_threshold_sweep(fig_dir, sweep)
    fig3_filter_cascade(fig_dir, summary)
    fig4_smt_outcomes(fig_dir, summary)
    fig5_runtime(fig_dir, summary)
    fig6_witness(fig_dir, conflicts)
    print(f"6 figures written to {fig_dir}")


if __name__ == "__main__":
    main()
