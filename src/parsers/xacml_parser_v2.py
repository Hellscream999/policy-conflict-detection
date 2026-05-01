"""
xacml_parser_v2.py
==================
Hierarchy-aware XACML 3.0 parser.

The original parser (xacml_parser.py) only read each <Rule>'s own <Target>.
In Continue-A every rule has an empty <Target/>, so all 298 rules collapsed
to identical CPM scope (subject='user', action='access', resource='resource').
That produced a meaningless dataset where every Permit-Deny pair looked
like a conflict.

This v2 parser walks the PolicySet -> Policy -> Rule hierarchy and
inherits every parent <Target>'s constraints down to each rule. Each rule
ends up with the union of all <Match> constraints that apply to it.

Each match is captured as a tuple:
    (category, attribute_id, operator, value, datatype)

`category` is normalized to one of:  subject | action | resource | environment.
`operator` is one of:                 eq | leq | geq | lt | gt | regex | other.

Two rules conflict iff there exists a concrete request that satisfies all
constraints of both. The v2 SMT encoder uses these tuples directly.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Constraint:
    """A single Match constraint extracted from a Target."""
    category: str          # subject | action | resource | environment
    attribute_id: str      # raw AttributeId (for Z3 variable naming)
    operator: str          # eq | leq | geq | lt | gt | regex | other
    value: str             # literal value
    datatype: str          # XSD datatype hint: string | double | int | boolean | other

    def __repr__(self) -> str:
        return f"{self.category}:{self.attribute_id}{self.operator}{self.value!r}"


AllOfBranch = List[Constraint]   # AND of constraints
AnyOfGroup  = List[AllOfBranch]  # OR over AllOf branches


@dataclass
class HRule:
    """
    A rule with hierarchically-inherited scope.

    XACML target semantics (preserved here):
      Target  = AND  over AnyOf groups
      AnyOf   = OR   over AllOf branches
      AllOf   = AND  over Match constraints

    `anyof_groups` collects every AnyOf group from every level
    (PolicySet, Policy, Rule own Target). Inheritance is "every
    parent's targets must also hold," so concatenation gives an AND.
    Conditions (from <Condition>) are extra AND-clauses with each
    being a single AllOf branch in its own AnyOf group.
    """
    rule_id: str
    effect: str  # 'Permit' or 'Deny'
    policy_id: str
    anyof_groups: List[AnyOfGroup] = field(default_factory=list)
    description: str = ""

    @property
    def constraints(self) -> List[Constraint]:
        """Flat view (only used for summaries / similarity input)."""
        out: List[Constraint] = []
        for grp in self.anyof_groups:
            for branch in grp:
                out.extend(branch)
        return out

    def constraints_by_category(self, category: str) -> List[Constraint]:
        return [c for c in self.constraints if c.category == category]

    def to_summary(self) -> str:
        """Plain-text rendering for embedding-based similarity."""
        parts = [f"{self.effect}"]
        for cat in ("subject", "action", "resource", "environment"):
            cs = self.constraints_by_category(cat)
            if cs:
                parts.append(cat + " " + " ".join(str(c) for c in cs))
        if self.description:
            parts.append(self.description)
        return " | ".join(parts)


# ---------------------------------------------------------------------------
# XACML helpers
# ---------------------------------------------------------------------------


_OP_MAP = {
    "string-equal": "eq",
    "anyURI-equal": "eq",
    "boolean-equal": "eq",
    "integer-equal": "eq",
    "double-equal": "eq",
    "string-less-than-or-equal": "leq",
    "string-greater-than-or-equal": "geq",
    "integer-less-than-or-equal": "leq",
    "integer-greater-than-or-equal": "geq",
    "double-less-than-or-equal": "leq",
    "double-greater-than-or-equal": "geq",
    "string-less-than": "lt",
    "string-greater-than": "gt",
    "integer-less-than": "lt",
    "integer-greater-than": "gt",
    "double-less-than": "lt",
    "double-greater-than": "gt",
    "string-regexp-match": "regex",
}


def _normalize_op(match_id: str) -> str:
    if not match_id:
        return "other"
    last = match_id.rsplit(":", 1)[-1]
    return _OP_MAP.get(last, "other")


def _normalize_datatype(dt: Optional[str]) -> str:
    if not dt:
        return "string"
    last = dt.rsplit("#", 1)[-1].lower()
    if last in ("double", "float", "decimal"):
        return "double"
    if last in ("integer", "int", "long", "short"):
        return "int"
    if last == "boolean":
        return "boolean"
    if last in ("string", "anyuri", "datetime", "date", "time"):
        return "string"
    return "other"


def _normalize_category(category_uri: str, attribute_id: str) -> str:
    """
    Map XACML category URI + attribute id to one of:
    subject | action | resource | environment.
    """
    cat = (category_uri or "").lower()
    aid = (attribute_id or "").lower()

    if "subject-category" in cat or "subject" in cat:
        return "subject"
    if ":action" in cat or cat.endswith("action") or cat.endswith(":action:"):
        return "action"
    if "resource" in cat:
        return "resource"
    if "environment" in cat:
        return "environment"

    # Fallback: examine attribute id
    if "action" in aid:
        return "action"
    if "resource" in aid:
        return "resource"
    if "environment" in aid:
        return "environment"
    if "subject" in aid or "role" in aid or "user" in aid:
        return "subject"

    # Truly unknown -- bucket as environment so it still constrains
    # without being lumped into subject/action/resource.
    return "environment"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class XACMLHierarchyParser:
    """Walks PolicySet -> Policy -> Rule and builds rules with inherited scope."""

    def __init__(self) -> None:
        self.rules: List[HRule] = []

    @staticmethod
    def _strip_ns(root: ET.Element) -> None:
        for elem in root.iter():
            if "}" in elem.tag:
                elem.tag = elem.tag.split("}", 1)[1]

    def parse_file(self, filepath: str) -> List[HRule]:
        self.rules = []
        tree = ET.parse(filepath)
        root = tree.getroot()
        self._strip_ns(root)

        if root.tag == "PolicySet":
            self._walk_policy_set(root, [])
        elif root.tag == "Policy":
            self._walk_policy(root, [])
        return self.rules

    # ------------------------------------------------------------------
    # Hierarchy walkers
    # ------------------------------------------------------------------

    def _walk_policy_set(self, ps: ET.Element, inherited_groups: List[AnyOfGroup]) -> None:
        own = self._extract_target_groups(ps.find("Target"))
        scope = inherited_groups + own
        for child in ps:
            tag = child.tag
            if tag == "PolicySet":
                self._walk_policy_set(child, scope)
            elif tag == "Policy":
                self._walk_policy(child, scope)

    def _walk_policy(self, policy: ET.Element, inherited_groups: List[AnyOfGroup]) -> None:
        own = self._extract_target_groups(policy.find("Target"))
        scope = inherited_groups + own
        policy_id = policy.get("PolicyId", "")

        for child in policy:
            if child.tag == "Rule":
                self._extract_rule(child, scope, policy_id)

    def _extract_rule(self, rule_elem: ET.Element, inherited_groups: List[AnyOfGroup],
                      policy_id: str) -> None:
        rid = rule_elem.get("RuleId", "rule")
        effect = rule_elem.get("Effect", "Deny")
        own = self._extract_target_groups(rule_elem.find("Target"))
        cond = self._extract_condition_groups(rule_elem.find("Condition"))
        description = ""
        d = rule_elem.find("Description")
        if d is not None and d.text:
            description = d.text.strip()
        rule = HRule(
            rule_id=rid,
            effect=effect,
            policy_id=policy_id,
            anyof_groups=inherited_groups + own + cond,
            description=description,
        )
        self.rules.append(rule)

    # ------------------------------------------------------------------
    # Target / Condition extractors
    # ------------------------------------------------------------------

    def _extract_target_groups(self, target: Optional[ET.Element]) -> List[AnyOfGroup]:
        """
        Each <AnyOf> becomes an AnyOfGroup (list of AllOf branches).
        Each <AllOf> branch is the AND of its <Match> constraints.
        """
        if target is None:
            return []
        groups: List[AnyOfGroup] = []
        for any_of in target.findall("AnyOf"):
            branches: AnyOfGroup = []
            for all_of in any_of.findall("AllOf"):
                branch: List[Constraint] = []
                for match in all_of.findall("Match"):
                    c = self._extract_match(match)
                    if c is not None:
                        branch.append(c)
                if branch:
                    branches.append(branch)
            if branches:
                groups.append(branches)
        return groups

    def _extract_condition_groups(
        self, condition: Optional[ET.Element]
    ) -> List[AnyOfGroup]:
        """A Condition is a single AND-block; encode as one AnyOf with one branch."""
        if condition is None:
            return []
        branch: List[Constraint] = []
        for apply_elem in condition.findall(".//Apply"):
            func = apply_elem.get("FunctionId", "")
            op = _normalize_op(func)
            attr_designator = apply_elem.find(".//AttributeDesignator")
            attr_value = apply_elem.find(".//AttributeValue")
            if attr_designator is None or attr_value is None or not attr_value.text:
                continue
            attr_id = attr_designator.get("AttributeId", "")
            cat_uri = attr_designator.get("Category", "")
            dt = attr_designator.get("DataType", "")
            branch.append(Constraint(
                category=_normalize_category(cat_uri, attr_id),
                attribute_id=attr_id,
                operator=op,
                value=attr_value.text.strip(),
                datatype=_normalize_datatype(dt),
            ))
        if not branch:
            return []
        return [[branch]]

    @staticmethod
    def _extract_match(match: ET.Element) -> Optional[Constraint]:
        match_id = match.get("MatchId", "")
        attr_value_elem = match.find("AttributeValue")
        attr_des_elem = match.find("AttributeDesignator")
        if attr_value_elem is None or attr_value_elem.text is None or attr_des_elem is None:
            return None
        return Constraint(
            category=_normalize_category(
                attr_des_elem.get("Category", ""),
                attr_des_elem.get("AttributeId", ""),
            ),
            attribute_id=attr_des_elem.get("AttributeId", ""),
            operator=_normalize_op(match_id),
            value=attr_value_elem.text.strip(),
            datatype=_normalize_datatype(attr_des_elem.get("DataType", "")),
        )


# ---------------------------------------------------------------------------
# Compatibility shim: produce CPMRule too
# ---------------------------------------------------------------------------


def _to_cpm_rule(h: HRule, framework: str):
    """
    Build a CPMRule (legacy structure) so the SemanticScreener / EntityValidator /
    SPARQLValidator written against CPMRule continue to work. The richer
    constraint info is stored alongside via the rule_id index in the caller.
    """
    from models.cpm import CPMRule, Subject, Resource, Environment, Effect

    subj_eqs = [c.value for c in h.constraints if c.category == "subject" and c.operator == "eq"]
    act_eqs  = [c.value for c in h.constraints if c.category == "action"  and c.operator == "eq"]
    res_eqs  = [c.value for c in h.constraints if c.category == "resource" and c.operator == "eq"]
    env_eqs  = {c.attribute_id: c.value
                for c in h.constraints if c.category == "environment"}

    subject = Subject(
        type=subj_eqs[0] if subj_eqs else "user",
        roles=subj_eqs,
        attributes={},
    )
    resource = Resource(
        type=res_eqs[0] if res_eqs else "resource",
        identifiers=res_eqs,
        attributes={},
    )
    environment = Environment(conditions=env_eqs)

    return CPMRule(
        rule_id=h.rule_id,
        subject=subject,
        action=act_eqs[0] if act_eqs else "access",
        resource=resource,
        environment=environment,
        effect=Effect.PERMIT if h.effect == "Permit" else Effect.DENY,
        framework_origin=framework,
        priority=50,
        obligations=[],
    )


def parse_xacml_v2(filepath: str, framework: str = "XACML"):
    """
    Returns (hrules, cpm_rules, by_id).
    by_id maps rule_id -> HRule (for the v2 SMT encoder).
    """
    parser = XACMLHierarchyParser()
    hrules = parser.parse_file(filepath)
    cpm = [_to_cpm_rule(h, framework) for h in hrules]
    by_id = {h.rule_id: h for h in hrules}
    return hrules, cpm, by_id


if __name__ == "__main__":
    import sys
    fp = sys.argv[1] if len(sys.argv) > 1 else "datasets/continue-a-xacml3.xml"
    hrules, cpm, by_id = parse_xacml_v2(fp)
    print(f"Parsed {len(hrules)} rules from {fp}")
    for h in hrules[:6]:
        print(f"  {h.rule_id} [{h.effect}]")
        for c in h.constraints:
            print(f"     {c}")
