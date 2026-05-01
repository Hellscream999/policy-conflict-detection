"""
prove_paper_v2.py
=================
Corrected v2 pipeline runner that reproduces all experimental results.

Differences from prove_paper.py (v1):
  1. XACML parser now walks PolicySet -> Policy -> Rule and inherits parent
     Targets. AnyOf/AllOf semantics are preserved (OR over branches,
     AND of constraints inside a branch). v1 collapsed everything in
     Continue-A to identical CPM scope.
  2. SMT encoder dropped the "any_*" wildcard disjuncts that made every
     applicability formula trivially satisfiable. The v1 encoder caused
     the bogus 14,280 / 32,399 GT counts.
  3. Ground truth = Z3 result on every cross-effect rule pair (oracle).
     Same-effect pairs short-circuit to UNSAT.
  4. The 1000-cap on SMT verification of detection candidates is removed.
  5. Outputs go to results_v2/ so the originals remain.
"""

from __future__ import annotations

import csv
import json
import os
import random
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, List, Set, Tuple

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

from parsers.xacml_parser_v2 import parse_xacml_v2, HRule
from models.cpm import CPMRule, Effect
from detection.semantic_screener import SemanticScreener
from detection.entity_validator import EntityValidator
from detection.sparql_validator import SPARQLValidator
from verification.smt_verifier_v2 import SMTEncoderV2, SMTResult


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class StageResult:
    name: str
    candidates: int
    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class WitnessRow:
    dataset: str
    rule_i: str
    rule_j: str
    effect_i: str
    effect_j: str
    similarity: float
    smt_result: str
    witness_subject: str
    witness_action: str
    witness_resource: str
    solve_time_ms: float


@dataclass
class DatasetSummary:
    name: str
    total_rules: int
    permit: int
    deny: int
    total_pairs: int
    gt_conflicts: int
    gt_sat: int = 0
    gt_unsat: int = 0
    gt_unknown: int = 0
    gt_time_s: float = 0.0

    sim: StageResult = None
    sim_entity: StageResult = None
    sim_entity_sparql: StageResult = None
    tfidf: StageResult = None
    keyword: StageResult = None

    smt_verified_sat: int = 0
    smt_verified_unsat: int = 0
    smt_verified_unknown: int = 0
    smt_verified_total: int = 0

    embedding_time_s: float = 0.0
    filtering_time_s: float = 0.0
    smt_verify_time_s: float = 0.0
    total_time_s: float = 0.0

    witnesses: List[WitnessRow] = field(default_factory=list)
    threshold_sweep: List[Dict[str, float]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SMT-oracle ground truth (using v2 encoder)
# ---------------------------------------------------------------------------


def _scope_satisfiable(enc: SMTEncoderV2, rule: HRule) -> bool:
    """Return True iff the rule's own scope is satisfiable under XACML semantics."""
    from z3 import Solver, sat as z3sat
    env: Dict[str, object] = {}
    f = enc.encode_rule(rule, env)
    if f is None:
        return False
    s = Solver()
    s.set("timeout", enc.timeout_ms)
    s.add(f)
    return s.check() == z3sat


def compute_oracle_gt(rules: List[HRule],
                      timeout_ms: int = 2000,
                      progress_every: int = 5000
                      ) -> Tuple[Set[Tuple[int, int]], Dict[str, int]]:
    """
    Fast-path: a rule whose scope alone is UNSAT can never conflict with anything
    (no concrete request triggers it). We precompute scope-satisfiability per
    rule, then skip pairs involving any unsat-scope rule.
    """
    enc = SMTEncoderV2(timeout_ms=timeout_ms)
    print(f"    [oracle GT] precomputing per-rule scope satisfiability ...", flush=True)
    t_pre = time.time()
    scope_ok = [_scope_satisfiable(enc, r) for r in rules]
    n_dead = sum(1 for s in scope_ok if not s)
    print(f"    [oracle GT] scope precheck: {len(rules) - n_dead}/{len(rules)} "
          f"applicable, {n_dead} dead-code  ({time.time()-t_pre:.1f}s)", flush=True)

    conflicts: Set[Tuple[int, int]] = set()
    stats = {"sat": 0, "unsat": 0, "unknown": 0, "same_effect": 0,
             "dead_code_skipped": 0, "total": 0}
    t0 = time.time()
    pair_idx = 0
    n = len(rules)
    for i in range(n):
        for j in range(i + 1, n):
            stats["total"] += 1
            pair_idx += 1
            if rules[i].effect == rules[j].effect:
                stats["same_effect"] += 1
                stats["unsat"] += 1
                continue
            if not scope_ok[i] or not scope_ok[j]:
                stats["dead_code_skipped"] += 1
                stats["unsat"] += 1
                continue
            r = enc.verify(rules[i], rules[j])
            if r.result == SMTResult.SAT:
                conflicts.add((i, j))
                stats["sat"] += 1
            elif r.result == SMTResult.UNSAT:
                stats["unsat"] += 1
            else:
                stats["unknown"] += 1
            if pair_idx % progress_every == 0:
                rate = pair_idx / max(time.time() - t0, 1e-6)
                print(f"    [oracle GT] {pair_idx}/{n*(n-1)//2} ({rate:.0f}/s) "
                      f"sat={stats['sat']} unsat={stats['unsat']} "
                      f"unknown={stats['unknown']}", flush=True)
    elapsed = time.time() - t0
    print(f"    [oracle GT] done: {stats['total']} pairs in {elapsed:.1f}s -> "
          f"sat={stats['sat']} unsat={stats['unsat']} unknown={stats['unknown']} "
          f"same_effect_skipped={stats['same_effect']} "
          f"dead_code_skipped={stats['dead_code_skipped']}", flush=True)
    return conflicts, stats


# ---------------------------------------------------------------------------
# Baselines (text-only; reuse v1 logic)
# ---------------------------------------------------------------------------


def _tfidf_pairs(cpm_rules: List[CPMRule], threshold: float = 0.3) -> Set[Tuple[int, int]]:
    import math, re
    docs = [re.findall(r"\w+", r.to_summary().lower()) for r in cpm_rules]
    df = defaultdict(int)
    for doc in docs:
        for t in set(doc):
            df[t] += 1
    n = len(docs)
    idf = {t: math.log(n / (1 + d)) for t, d in df.items()}

    def vec(doc):
        tf = defaultdict(int)
        for t in doc: tf[t] += 1
        total = len(doc) or 1
        return {t: (c/total) * idf.get(t, 0.0) for t, c in tf.items()}

    vecs = [vec(d) for d in docs]
    out = set()
    for i in range(n):
        for j in range(i+1, n):
            keys = set(vecs[i]) | set(vecs[j])
            dot = sum(vecs[i].get(k, 0) * vecs[j].get(k, 0) for k in keys)
            mi = math.sqrt(sum(v*v for v in vecs[i].values()))
            mj = math.sqrt(sum(v*v for v in vecs[j].values()))
            sim = dot / (mi*mj) if mi and mj else 0.0
            if sim >= threshold:
                out.add((i, j))
    return out


def _keyword_pairs(cpm_rules: List[CPMRule], threshold: float = 0.2) -> Set[Tuple[int, int]]:
    def kw(r):
        s = {r.subject.type.lower(), r.action.lower(), r.resource.type.lower()}
        s.update(x.lower() for x in r.subject.roles)
        s.update(x.lower() for x in r.resource.identifiers)
        return s
    kws = [kw(r) for r in cpm_rules]
    out = set()
    for i in range(len(cpm_rules)):
        for j in range(i+1, len(cpm_rules)):
            inter = len(kws[i] & kws[j])
            union = len(kws[i] | kws[j])
            jac = inter/union if union else 0.0
            if jac >= threshold:
                out.add((i, j))
    return out


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _stage(name: str, predicted: Set[Tuple[int, int]],
           gt: Set[Tuple[int, int]]) -> StageResult:
    tp = len(predicted & gt); fp = len(predicted - gt); fn = len(gt - predicted)
    return StageResult(name=name, candidates=len(predicted), tp=tp, fp=fp, fn=fn)


def _to_idx_pairs(candidates, id_to_idx) -> Set[Tuple[int, int]]:
    out = set()
    for c in candidates:
        i = id_to_idx.get(c.rule_i.rule_id, -1)
        j = id_to_idx.get(c.rule_j.rule_id, -1)
        if i >= 0 and j >= 0:
            out.add((min(i, j), max(i, j)))
    return out


def evaluate_dataset(filepath: str, name: str,
                     sim_threshold: float = 0.65,
                     entity_threshold: float = 0.3,
                     gt_timeout_ms: int = 2000) -> DatasetSummary:
    print(f"\n{'='*72}\nDATASET: {name}\n{'='*72}", flush=True)
    t_total = time.time()

    hrules, cpm_rules, _ = parse_xacml_v2(filepath, name)
    id_to_idx = {h.rule_id: i for i, h in enumerate(hrules)}
    rule_id_to_hrule = {h.rule_id: h for h in hrules}

    summary = DatasetSummary(
        name=name,
        total_rules=len(hrules),
        permit=sum(1 for h in hrules if h.effect == "Permit"),
        deny=sum(1 for h in hrules if h.effect == "Deny"),
        total_pairs=len(hrules) * (len(hrules) - 1) // 2,
        gt_conflicts=0,
    )
    print(f"  rules={summary.total_rules}  P={summary.permit} D={summary.deny}  "
          f"pairs={summary.total_pairs}", flush=True)

    if len(hrules) < 2:
        return summary

    # Precompute per-rule scope satisfiability — used by both oracle GT and stage 5
    enc_pre = SMTEncoderV2(timeout_ms=gt_timeout_ms)
    from verification.smt_verifier_v2 import SMTEncoderV2 as _Enc  # ensure import in local scope
    scope_ok_map: Dict[str, bool] = {}
    for h in hrules:
        env = {}
        f = enc_pre.encode_rule(h, env)
        if f is None:
            scope_ok_map[h.rule_id] = False
            continue
        from z3 import Solver, sat
        s = Solver(); s.set("timeout", gt_timeout_ms); s.add(f)
        scope_ok_map[h.rule_id] = (s.check() == sat)
    n_dead = sum(1 for v in scope_ok_map.values() if not v)
    print(f"  scope-applicability: {len(hrules) - n_dead}/{len(hrules)} live, {n_dead} dead-code",
          flush=True)

    # ----- 1. Oracle ground truth -----
    print("  [1/5] SMT-oracle ground truth ...", flush=True)
    t0 = time.time()
    gt_pairs, gt_stats = compute_oracle_gt(hrules, timeout_ms=gt_timeout_ms)
    summary.gt_time_s = time.time() - t0
    summary.gt_conflicts = len(gt_pairs)
    summary.gt_sat = gt_stats["sat"]
    summary.gt_unsat = gt_stats["unsat"]
    summary.gt_unknown = gt_stats["unknown"]
    pct = summary.gt_conflicts / max(summary.total_pairs, 1) * 100
    print(f"    -> {summary.gt_conflicts} oracle conflicts ({pct:.2f}% of pairs)", flush=True)

    # ----- 2. Semantic screening -----
    print("  [2/5] Semantic screening ...", flush=True)
    t0 = time.time()
    screener = SemanticScreener(threshold=sim_threshold)
    sim_cands = screener.generate_candidates(cpm_rules)
    sim_pairs = _to_idx_pairs(sim_cands, id_to_idx)
    summary.embedding_time_s = time.time() - t0
    summary.sim = _stage("similarity", sim_pairs, gt_pairs)
    print(f"    -> {summary.sim.candidates} cand  P={summary.sim.precision:.3f} "
          f"R={summary.sim.recall:.3f} F1={summary.sim.f1:.3f}", flush=True)

    # ----- 3. Entity overlap -----
    print("  [3/5] Entity-overlap validation ...", flush=True)
    t0 = time.time()
    ent_validator = EntityValidator(threshold=entity_threshold)
    ent_cands = ent_validator.validate_candidates(sim_cands)
    ent_pairs = _to_idx_pairs(ent_cands, id_to_idx)
    summary.sim_entity = _stage("similarity+entity", ent_pairs, gt_pairs)
    print(f"    -> {summary.sim_entity.candidates} cand  P={summary.sim_entity.precision:.3f} "
          f"R={summary.sim_entity.recall:.3f} F1={summary.sim_entity.f1:.3f}", flush=True)

    # ----- 4. SPARQL validation -----
    print("  [4/5] SPARQL structural validation ...", flush=True)
    sparql_validator = SPARQLValidator()
    sparql_cands = sparql_validator.validate_structure(ent_cands)
    sparql_pairs = _to_idx_pairs(sparql_cands, id_to_idx)
    summary.filtering_time_s = time.time() - t0
    summary.sim_entity_sparql = _stage(
        "similarity+entity+sparql", sparql_pairs, gt_pairs)
    print(f"    -> {summary.sim_entity_sparql.candidates} cand  "
          f"P={summary.sim_entity_sparql.precision:.3f} "
          f"R={summary.sim_entity_sparql.recall:.3f} "
          f"F1={summary.sim_entity_sparql.f1:.3f}", flush=True)

    # ----- 5. SMT verification of detection candidates (no cap) -----
    # Dedup candidates by (rule_i, rule_j) so we SMT-verify each unique pair once.
    seen = set()
    deduped = []
    for sv in sparql_cands:
        key = (min(sv.rule_i.rule_id, sv.rule_j.rule_id),
               max(sv.rule_i.rule_id, sv.rule_j.rule_id))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(sv)
    print(f"  [5/5] SMT-verifying all {len(deduped)} unique candidates "
          f"(from {len(sparql_cands)} pre-dedup) ...", flush=True)
    t0 = time.time()
    enc = SMTEncoderV2(timeout_ms=gt_timeout_ms)
    smt_sat = smt_unsat = smt_unknown = 0
    smt_dead = 0
    for sv in deduped:
        ri = rule_id_to_hrule.get(sv.rule_i.rule_id)
        rj = rule_id_to_hrule.get(sv.rule_j.rule_id)
        if ri is None or rj is None:
            continue
        # Fast-path: if either rule has unsat scope, the pair is UNSAT.
        if not scope_ok_map.get(ri.rule_id, True) or not scope_ok_map.get(rj.rule_id, True):
            smt_unsat += 1
            smt_dead += 1
            continue
        r = enc.verify(ri, rj)
        if r.result == SMTResult.SAT:
            smt_sat += 1
            wb = (r.witness.bindings if r.witness else {})
            def first(key_substr):
                for k, v in wb.items():
                    if key_substr in k.lower():
                        return v
                return ""
            summary.witnesses.append(WitnessRow(
                dataset=name, rule_i=ri.rule_id, rule_j=rj.rule_id,
                effect_i=ri.effect, effect_j=rj.effect,
                similarity=getattr(sv, "similarity", 0.0),
                smt_result="SAT",
                witness_subject=first("subject") or first("role") or "",
                witness_action=first("action") or "",
                witness_resource=first("resource") or "",
                solve_time_ms=r.solve_time_ms,
            ))
        elif r.result == SMTResult.UNSAT:
            smt_unsat += 1
        else:
            smt_unknown += 1
    summary.smt_verify_time_s = time.time() - t0
    summary.smt_verified_sat = smt_sat
    summary.smt_verified_unsat = smt_unsat
    summary.smt_verified_unknown = smt_unknown
    summary.smt_verified_total = smt_sat + smt_unsat + smt_unknown
    print(f"    -> SAT={smt_sat} UNSAT={smt_unsat} UNKNOWN={smt_unknown} "
          f"({summary.smt_verify_time_s:.2f}s)", flush=True)

    # ----- Baselines -----
    print("  [+] Baselines (TF-IDF, keyword) ...", flush=True)
    summary.tfidf = _stage("tfidf", _tfidf_pairs(cpm_rules), gt_pairs)
    summary.keyword = _stage("keyword", _keyword_pairs(cpm_rules), gt_pairs)
    print(f"    TF-IDF F1={summary.tfidf.f1:.3f}  Keyword F1={summary.keyword.f1:.3f}",
          flush=True)

    # ----- Threshold sweep -----
    print("  [+] Threshold sweep ...", flush=True)
    sweep_screener = SemanticScreener(threshold=0.0)
    all_cands = sweep_screener.generate_candidates(cpm_rules)
    for th in [0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]:
        kept = [c for c in all_cands if c.similarity >= th]
        kept_pairs = _to_idx_pairs(kept, id_to_idx)
        m = _stage(f"th={th}", kept_pairs, gt_pairs)
        summary.threshold_sweep.append({
            "threshold": th, "precision": m.precision, "recall": m.recall,
            "f1": m.f1, "candidates": m.candidates,
        })

    summary.total_time_s = time.time() - t_total
    print(f"  total: {summary.total_time_s:.2f}s", flush=True)
    return summary


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def save_outputs(all_summaries: List[DatasetSummary], out_dir: str):
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "summary.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "dataset", "rules", "permit", "deny", "total_pairs",
            "gt_conflicts", "gt_sat", "gt_unsat", "gt_unknown", "gt_time_s",
            "sim_cands", "sim_P", "sim_R", "sim_F1",
            "ent_cands", "ent_P", "ent_R", "ent_F1",
            "sparql_cands", "sparql_P", "sparql_R", "sparql_F1",
            "tfidf_P", "tfidf_R", "tfidf_F1",
            "keyword_P", "keyword_R", "keyword_F1",
            "smt_sat", "smt_unsat", "smt_unknown", "smt_total",
            "embed_time_s", "filter_time_s", "smt_time_s", "total_time_s",
        ])
        for s in all_summaries:
            def m(stage):
                return (stage.candidates, stage.precision, stage.recall, stage.f1) if stage else (0,0,0,0)
            sim = m(s.sim); ent = m(s.sim_entity); spq = m(s.sim_entity_sparql)
            tfi = m(s.tfidf); kw = m(s.keyword)
            w.writerow([
                s.name, s.total_rules, s.permit, s.deny, s.total_pairs,
                s.gt_conflicts, s.gt_sat, s.gt_unsat, s.gt_unknown, f"{s.gt_time_s:.2f}",
                sim[0], f"{sim[1]:.4f}", f"{sim[2]:.4f}", f"{sim[3]:.4f}",
                ent[0], f"{ent[1]:.4f}", f"{ent[2]:.4f}", f"{ent[3]:.4f}",
                spq[0], f"{spq[1]:.4f}", f"{spq[2]:.4f}", f"{spq[3]:.4f}",
                f"{tfi[1]:.4f}", f"{tfi[2]:.4f}", f"{tfi[3]:.4f}",
                f"{kw[1]:.4f}", f"{kw[2]:.4f}", f"{kw[3]:.4f}",
                s.smt_verified_sat, s.smt_verified_unsat, s.smt_verified_unknown,
                s.smt_verified_total,
                f"{s.embedding_time_s:.2f}", f"{s.filtering_time_s:.2f}",
                f"{s.smt_verify_time_s:.2f}", f"{s.total_time_s:.2f}",
            ])

    with open(os.path.join(out_dir, "conflicts.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["dataset", "rule_i", "rule_j", "effect_i", "effect_j",
                    "similarity", "smt_result",
                    "witness_subject", "witness_action", "witness_resource",
                    "solve_time_ms"])
        for s in all_summaries:
            for r in s.witnesses:
                w.writerow([r.dataset, r.rule_i, r.rule_j, r.effect_i, r.effect_j,
                            f"{r.similarity:.4f}", r.smt_result,
                            r.witness_subject, r.witness_action, r.witness_resource,
                            f"{r.solve_time_ms:.2f}"])

    with open(os.path.join(out_dir, "threshold_sweep.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["dataset", "threshold", "precision", "recall", "f1", "candidates"])
        for s in all_summaries:
            for row in s.threshold_sweep:
                w.writerow([s.name, f"{row['threshold']:.2f}",
                            f"{row['precision']:.4f}", f"{row['recall']:.4f}",
                            f"{row['f1']:.4f}", row["candidates"]])

    raw = []
    for s in all_summaries:
        d = {k: v for k, v in asdict(s).items()
             if k not in {"sim", "sim_entity", "sim_entity_sparql",
                          "tfidf", "keyword", "witnesses"}}
        for stage_name in ["sim", "sim_entity", "sim_entity_sparql",
                           "tfidf", "keyword"]:
            stage = getattr(s, stage_name)
            d[stage_name] = (
                {"candidates": stage.candidates, "tp": stage.tp, "fp": stage.fp,
                 "fn": stage.fn, "precision": stage.precision,
                 "recall": stage.recall, "f1": stage.f1}
                if stage else None
            )
        d["witnesses"] = [asdict(r) for r in s.witnesses[:50]]
        raw.append(d)
    with open(os.path.join(out_dir, "raw.json"), "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, default=str)

    print(f"\nResults saved to: {out_dir}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main():
    print("=" * 80)
    print("PROVE_PAPER_V2  -  hierarchy-aware parser, no any_* wildcards, no 1000-cap")
    print(f"Timestamp: {datetime.now().isoformat()}  Seed: {RANDOM_SEED}")
    print("=" * 80)

    datasets_dir = os.path.join(ROOT, "datasets")
    targets = [
        ("GEYSERS", "GEYSERS.xml"),
        ("KMarket", "KMarket.xml"),
        ("Continue-A", "continue-a-xacml3.xml"),
        ("Synthetic360", "synthetic360.xml"),
    ]

    summaries = []
    for name, fname in targets:
        fp = os.path.join(datasets_dir, fname)
        if not os.path.exists(fp):
            print(f"  [SKIP] {name}: not found at {fp}", flush=True)
            continue
        s = evaluate_dataset(fp, name)
        summaries.append(s)

    out_dir = os.path.join(ROOT, "results_v2")
    save_outputs(summaries, out_dir)

    print("\n" + "=" * 80)
    print("MACRO SUMMARY (final pipeline = sim + entity + SPARQL)")
    print("=" * 80)
    finals = [s for s in summaries if s.sim_entity_sparql]
    if finals:
        macro_p = sum(s.sim_entity_sparql.precision for s in finals) / len(finals)
        macro_r = sum(s.sim_entity_sparql.recall    for s in finals) / len(finals)
        macro_f1 = sum(s.sim_entity_sparql.f1       for s in finals) / len(finals)
        print(f"  macro Precision = {macro_p:.4f}")
        print(f"  macro Recall    = {macro_r:.4f}")
        print(f"  macro F1        = {macro_f1:.4f}")
    total_smt = sum(s.smt_verified_total for s in summaries)
    total_unknown = sum(s.smt_verified_unknown for s in summaries)
    cov = (total_smt - total_unknown) / total_smt * 100 if total_smt else 0.0
    print(f"  SMT-on-detection-candidates: {total_smt} calls, coverage = {cov:.2f}%")


if __name__ == "__main__":
    main()
