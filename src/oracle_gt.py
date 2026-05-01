"""
SMT-derived ground truth.

The original `compute_ground_truth` in prove_paper.py used a permissive
heuristic: opposite effects PLUS scope-overlap-on-any-of (resource type,
action, identifier). On Continue-A (where every rule shares the same
resource type) this collapsed to "every Permit x Deny pair" =
238 x 60 = 14,280 conflicts -- meaningless ground truth.

Per the paper's Section III.D, ground truth is supposed to come from the
SMT encoding itself: a pair is a conflict iff Phi_conf(r_i, r_j) is SAT.
This module implements that definition.

For datasets with N rules we run at most N*(N-1)/2 SMT calls. Same-effect
pairs short-circuit to UNSAT inside the encoder, so the real cost is
~(permits x denies) Z3 calls.
"""

from typing import List, Set, Tuple, Dict
import time

from models.cpm import CPMRule, Effect
from verification.smt_verifier import SMTVerifier, SMTResult


def compute_oracle_ground_truth(
    rules: List[CPMRule],
    timeout_ms: int = 5000,
    progress_every: int = 5000,
) -> Tuple[Set[Tuple[int, int]], Dict[str, int]]:
    """
    Run Z3 SMT on every rule pair to produce ground truth.

    Returns
    -------
    conflicts : set of (i, j) index tuples with i < j, where SMT returned SAT.
    stats : counters for sat / unsat / unknown / same_effect / total.
    """
    verifier = SMTVerifier(timeout_ms=timeout_ms)
    conflicts: Set[Tuple[int, int]] = set()
    stats = {"sat": 0, "unsat": 0, "unknown": 0, "same_effect": 0, "total": 0}

    n = len(rules)
    pair_idx = 0
    t0 = time.time()

    for i in range(n):
        for j in range(i + 1, n):
            stats["total"] += 1
            pair_idx += 1

            if rules[i].effect == rules[j].effect:
                stats["same_effect"] += 1
                stats["unsat"] += 1
                continue

            r = verifier.verify_conflict(rules[i], rules[j])
            if r.result == SMTResult.SAT:
                conflicts.add((i, j))
                stats["sat"] += 1
            elif r.result == SMTResult.UNSAT:
                stats["unsat"] += 1
            else:
                stats["unknown"] += 1

            if pair_idx % progress_every == 0:
                rate = pair_idx / max(time.time() - t0, 1e-6)
                print(
                    f"    [oracle GT] {pair_idx}/{n*(n-1)//2} pairs "
                    f"({rate:.0f}/s)  sat={stats['sat']} unsat={stats['unsat']} "
                    f"unknown={stats['unknown']}"
                )

    elapsed = time.time() - t0
    print(
        f"    [oracle GT] done: {stats['total']} pairs in {elapsed:.1f}s "
        f"-> sat={stats['sat']} unsat={stats['unsat']} "
        f"unknown={stats['unknown']} same_effect_skipped={stats['same_effect']}"
    )

    return conflicts, stats
