"""
smt_verifier_v2.py
==================
Z3-based conflict verification using HRule constraints from xacml_parser_v2.

The v1 encoder always added an "any_subject" / "any_action" / "any_resource"
wildcard disjunct. That made every applicability formula trivially satisfiable
(Z3 just sets q = ("any_*",)) so every opposite-effect pair returned SAT.
The v1 encoder was the real source of the bogus 14,280 / 32,399 GT counts.

v2 fixes this. Each rule's applicability is a conjunction of the rule's own
constraints; there is no wildcard escape hatch. Two rules conflict iff there
exists a concrete request q that satisfies all constraints of both rules.

Supported XACML operators:
    eq, leq, geq, lt, gt   on numeric datatypes (int / double)
    eq                     on string / boolean datatypes
Unsupported (regex, other) are dropped (over-approximates scope, never under).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

from z3 import (
    Solver, String, Real, Bool, And, Or, Not, sat, unsat, unknown,
    StringVal, RealVal, BoolVal, set_param,
)

from parsers.xacml_parser_v2 import HRule, Constraint


class SMTResult(Enum):
    SAT = "sat"
    UNSAT = "unsat"
    UNKNOWN = "unknown"


@dataclass
class Witness:
    bindings: Dict[str, str]   # attribute_id -> concrete value chosen by Z3
    rule_i: str
    rule_j: str
    effect_i: str
    effect_j: str

    def short(self) -> str:
        kv = ", ".join(f"{k}={v}" for k, v in list(self.bindings.items())[:6])
        return f"({kv}) -> {self.effect_i} vs {self.effect_j}"


@dataclass
class VerifyResult:
    rule_i: str
    rule_j: str
    result: SMTResult
    witness: Optional[Witness] = None
    solve_time_ms: float = 0.0


def _is_numeric(dt: str) -> bool:
    return dt in ("int", "double")


def _try_float(v: str) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class SMTEncoderV2:
    """Encode constraints as Z3 formulas; no wildcards."""

    def __init__(self, timeout_ms: int = 5000) -> None:
        self.timeout_ms = timeout_ms

    @staticmethod
    def _suffix_num(value: str):
        """Strip non-numeric prefix (e.g. 'r-3' -> 3.0) to keep ordering meaningful."""
        n = _try_float(value)
        if n is not None:
            return n
        if "-" in value:
            return _try_float(value.split("-")[-1])
        return None

    def _attr_kind(self, c: Constraint) -> str:
        """
        Decide whether to model an attribute as numeric (Real) or string (String).
        We commit to one choice per attribute_id across the whole conflict check
        so eq / leq / geq / lt / gt all share the same Z3 variable.

        - If the datatype is numeric, model as Real.
        - If the operator is comparative (leq/geq/lt/gt) and the value is parseable
          as a number (possibly after stripping a 'r-' prefix), model as Real.
        - Otherwise model as String.
        """
        if _is_numeric(c.datatype):
            return "num"
        if c.operator in ("leq", "geq", "lt", "gt") and self._suffix_num(c.value) is not None:
            return "num"
        return "str"

    def _var_for(self, env: Dict[str, object], attr_id: str, kind: str) -> object:
        if attr_id in env:
            return env[attr_id]
        name = f"q_{attr_id}".replace(":", "_").replace("/", "_").replace(".", "_")
        v = Real(name + "_n") if kind == "num" else String(name + "_s")
        env[attr_id] = v
        # Track the kind so later constraints on the same attribute use the same kind.
        env[("__kind__", attr_id)] = kind
        return v

    def _encode_constraint(self, c: Constraint, env: Dict[str, object]):
        """Return a Z3 formula or None if the constraint is unsupported."""
        kind = env.get(("__kind__", c.attribute_id), self._attr_kind(c))
        v = self._var_for(env, c.attribute_id, kind)

        if kind == "num":
            num = self._suffix_num(c.value)
            if num is None:
                return None
            lit = RealVal(num)
            if c.operator == "eq":  return v == lit
            if c.operator == "leq": return v <= lit
            if c.operator == "geq": return v >= lit
            if c.operator == "lt":  return v <  lit
            if c.operator == "gt":  return v >  lit
            return None

        # string variable: only equality is reliably supported
        if c.operator == "eq":
            return v == StringVal(c.value)
        return None

    def encode_rule(self, rule: HRule, env: Dict[str, object]):
        """
        Return a single Z3 formula representing rule applicability:
            AND_{group in rule.anyof_groups} OR_{branch in group} AND_{c in branch} encode(c)
        Returns None if the rule has no encodable scope at all.
        """
        per_group_disjuncts = []
        for group in rule.anyof_groups:
            branch_formulas = []
            for branch in group:
                clauses = []
                for c in branch:
                    f = self._encode_constraint(c, env)
                    if f is not None:
                        clauses.append(f)
                if clauses:
                    branch_formulas.append(And(*clauses) if len(clauses) > 1 else clauses[0])
            if branch_formulas:
                per_group_disjuncts.append(
                    Or(*branch_formulas) if len(branch_formulas) > 1 else branch_formulas[0]
                )
        if not per_group_disjuncts:
            return None
        if len(per_group_disjuncts) == 1:
            return per_group_disjuncts[0]
        return And(*per_group_disjuncts)

    def verify(self, ri: HRule, rj: HRule) -> VerifyResult:
        # Same-effect pairs cannot be effect-conflicts in this analysis.
        if ri.effect == rj.effect:
            return VerifyResult(ri.rule_id, rj.rule_id, SMTResult.UNSAT, None, 0.0)

        env: Dict[str, object] = {}
        f_i = self.encode_rule(ri, env)
        f_j = self.encode_rule(rj, env)

        # If a rule has no encodable constraints, it has no scope -> nothing applies.
        # Treat as UNSAT (no concrete request can satisfy "no constraint").
        # This is conservative: it avoids declaring a no-scope rule a conflict.
        if f_i is None or f_j is None:
            return VerifyResult(ri.rule_id, rj.rule_id, SMTResult.UNSAT, None, 0.0)

        s = Solver()
        s.set("timeout", self.timeout_ms)
        s.add(f_i)
        s.add(f_j)

        t0 = time.time()
        r = s.check()
        elapsed = (time.time() - t0) * 1000.0

        if r == sat:
            m = s.model()
            bindings: Dict[str, str] = {}
            for d in m.decls():
                try:
                    bindings[d.name()] = str(m[d]).strip('"')
                except Exception:
                    bindings[d.name()] = "?"
            w = Witness(
                bindings=bindings, rule_i=ri.rule_id, rule_j=rj.rule_id,
                effect_i=ri.effect, effect_j=rj.effect,
            )
            return VerifyResult(ri.rule_id, rj.rule_id, SMTResult.SAT, w, elapsed)
        elif r == unsat:
            return VerifyResult(ri.rule_id, rj.rule_id, SMTResult.UNSAT, None, elapsed)
        else:
            return VerifyResult(ri.rule_id, rj.rule_id, SMTResult.UNKNOWN, None, elapsed)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def _smoke():
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from parsers.xacml_parser_v2 import parse_xacml_v2
    enc = SMTEncoderV2(timeout_ms=2000)
    for name, fname in [("KMarket", "KMarket.xml"),
                        ("Continue-A", "continue-a-xacml3.xml")]:
        path = os.path.join("datasets", fname)
        hrules, _, _ = parse_xacml_v2(path, name)
        n = len(hrules)
        sat_n = unsat_n = same = 0
        t0 = time.time()
        for i in range(n):
            for j in range(i + 1, n):
                r = enc.verify(hrules[i], hrules[j])
                if r.result == SMTResult.SAT: sat_n += 1
                elif r.result == SMTResult.UNSAT and hrules[i].effect == hrules[j].effect: same += 1
                else: unsat_n += 1
        print(f"{name}: pairs={n*(n-1)//2}  SAT={sat_n}  UNSAT={unsat_n}  same_effect={same}  in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    _smoke()
