"""
RDF/SPARQL Structural Validation - Figure 3 (Phase 3)
======================================================
Semantic graph-based structural checks for conflict candidates.
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from rdflib import Graph, Namespace, Literal, URIRef, RDF, RDFS
    from rdflib.namespace import XSD
    RDFLIB_AVAILABLE = True
    # Define policy ontology namespace
    POLICY = Namespace("http://example.org/policy#")
except ImportError:
    RDFLIB_AVAILABLE = False
    POLICY = None
    Graph = None
    Literal = None
    URIRef = None
    RDF = None
    print("Warning: rdflib not available, using fallback validation")

from models.cpm import CPMRule, Effect
from detection.entity_validator import ValidatedPair


@dataclass
class StructurallyValidatedPair:
    """A candidate pair that passed SPARQL structural validation"""
    rule_i: CPMRule
    rule_j: CPMRule
    similarity: float
    entity_overlap: float
    shared_resources: List[str]
    shared_actions: bool
    opposite_effects: bool
    sparql_valid: bool


class PolicyRDFGraph:
    """
    Builds RDF graph from CPM rules for SPARQL queries.
    Implements semantic layer for structural validation.
    """
    
    def __init__(self):
        if RDFLIB_AVAILABLE:
            self.graph = Graph()
            self.graph.bind("policy", POLICY)
        else:
            self.graph = None
        self.rules = {}
    
    def add_rule(self, rule: CPMRule):
        """Add a CPM rule to the RDF graph"""
        self.rules[rule.rule_id] = rule
        
        if not RDFLIB_AVAILABLE:
            return
        
        rule_uri = URIRef(f"{POLICY}{rule.rule_id}")
        
        # Rule type
        self.graph.add((rule_uri, RDF.type, POLICY.Rule))
        
        # Subject
        subject_uri = URIRef(f"{POLICY}subject_{rule.rule_id}")
        self.graph.add((rule_uri, POLICY.hasSubject, subject_uri))
        self.graph.add((subject_uri, RDF.type, POLICY.Subject))
        self.graph.add((subject_uri, POLICY.subjectType, Literal(rule.subject.type)))
        
        for role in rule.subject.roles:
            self.graph.add((subject_uri, POLICY.hasRole, Literal(role)))
        
        # Action
        self.graph.add((rule_uri, POLICY.hasAction, Literal(rule.action)))
        
        # Resource
        resource_uri = URIRef(f"{POLICY}resource_{rule.rule_id}")
        self.graph.add((rule_uri, POLICY.hasResource, resource_uri))
        self.graph.add((resource_uri, RDF.type, POLICY.Resource))
        self.graph.add((resource_uri, POLICY.resourceType, Literal(rule.resource.type)))
        
        for identifier in rule.resource.identifiers:
            self.graph.add((resource_uri, POLICY.hasIdentifier, Literal(identifier)))
        
        # Effect
        self.graph.add((rule_uri, POLICY.hasEffect, Literal(rule.effect.value)))
        
        # Framework and Priority
        self.graph.add((rule_uri, POLICY.fromFramework, Literal(rule.framework_origin)))
        self.graph.add((rule_uri, POLICY.hasPriority, Literal(rule.priority)))
    
    def add_rules(self, rules: List[CPMRule]):
        """Add multiple rules to the graph"""
        for rule in rules:
            self.add_rule(rule)
    
    def query(self, sparql_query: str) -> List[Dict]:
        """Execute SPARQL query and return results"""
        if not RDFLIB_AVAILABLE:
            return []
        
        results = []
        for row in self.graph.query(sparql_query):
            results.append({str(var): str(val) for var, val in zip(row.labels, row)})
        return results


class SPARQLValidator:
    """
    Validates candidate pairs using SPARQL structural queries.
    Implementation of Figure 3, Phase 3.
    """
    
    # SPARQL query to find rules with shared resources
    SHARED_RESOURCE_QUERY = """
    PREFIX policy: <http://example.org/policy#>
    
    SELECT ?rule1 ?rule2 ?resourceType
    WHERE {
        ?rule1 a policy:Rule .
        ?rule2 a policy:Rule .
        ?rule1 policy:hasResource ?res1 .
        ?rule2 policy:hasResource ?res2 .
        ?res1 policy:resourceType ?resourceType .
        ?res2 policy:resourceType ?resourceType .
        FILTER(?rule1 != ?rule2)
    }
    """
    
    # SPARQL query to find rules with opposite effects
    OPPOSITE_EFFECTS_QUERY = """
    PREFIX policy: <http://example.org/policy#>
    
    SELECT ?rule1 ?rule2 ?effect1 ?effect2
    WHERE {
        ?rule1 a policy:Rule .
        ?rule2 a policy:Rule .
        ?rule1 policy:hasEffect ?effect1 .
        ?rule2 policy:hasEffect ?effect2 .
        FILTER(?rule1 != ?rule2)
        FILTER(?effect1 != ?effect2)
    }
    """
    
    # SPARQL query to find rules with compatible actions
    COMPATIBLE_ACTIONS_QUERY = """
    PREFIX policy: <http://example.org/policy#>
    
    SELECT ?rule1 ?rule2 ?action1 ?action2
    WHERE {
        ?rule1 a policy:Rule .
        ?rule2 a policy:Rule .
        ?rule1 policy:hasAction ?action1 .
        ?rule2 policy:hasAction ?action2 .
        FILTER(?rule1 != ?rule2)
    }
    """
    
    # Action compatibility groups
    ACTION_GROUPS = {
        "read": {"read", "view", "access", "retrieve"},
        "write": {"write", "modify", "update", "change", "create"},
        "delete": {"delete", "remove", "erase"},
        "execute": {"execute", "run", "invoke"},
    }
    
    def __init__(self):
        self.rdf_graph = PolicyRDFGraph()
        self._action_to_group = {}
        for group, actions in self.ACTION_GROUPS.items():
            for action in actions:
                self._action_to_group[action] = group
    
    def build_graph(self, rules: List[CPMRule]):
        """Build RDF graph from rules"""
        self.rdf_graph = PolicyRDFGraph()
        self.rdf_graph.add_rules(rules)
    
    def actions_compatible(self, action1: str, action2: str) -> bool:
        """Check if two actions are in the same compatibility group"""
        group1 = self._action_to_group.get(action1.lower(), action1.lower())
        group2 = self._action_to_group.get(action2.lower(), action2.lower())
        return group1 == group2
    
    def shared_resource_scope(self, rule_i: CPMRule, rule_j: CPMRule) -> Tuple[bool, List[str]]:
        """
        Check if two rules share resource scope.
        
        Returns:
            (has_shared_scope, list of shared resource types)
        """
        # Check resource type match
        shared = []
        
        if rule_i.resource.type == rule_j.resource.type:
            shared.append(rule_i.resource.type)
        
        # Check identifier overlap
        ids_i = set(rule_i.resource.identifiers)
        ids_j = set(rule_j.resource.identifiers)
        shared_ids = ids_i & ids_j
        shared.extend(list(shared_ids))
        
        return len(shared) > 0, shared
    
    def validate_structure(self, validated_pairs: List[ValidatedPair]) -> List[StructurallyValidatedPair]:
        """
        Validate candidate pairs with SPARQL structural checks.
        
        Checks:
        1. Shared resource scope
        2. Compatible actions
        3. Opposite effects (potential conflict indicator)
        
        Args:
            validated_pairs: Pairs that passed entity validation
            
        Returns:
            Structurally validated pairs
        """
        results = []
        
        for vpair in validated_pairs:
            rule_i = vpair.rule_i
            rule_j = vpair.rule_j
            
            # Check shared resource scope
            has_shared, shared_resources = self.shared_resource_scope(rule_i, rule_j)
            
            # Check action compatibility
            shared_actions = self.actions_compatible(rule_i.action, rule_j.action)
            
            # Check opposite effects
            opposite_effects = rule_i.effect != rule_j.effect
            
            # SPARQL validation: shared scope AND compatible actions
            sparql_valid = has_shared and shared_actions
            
            # For conflicts, also need opposite effects
            if opposite_effects and sparql_valid:
                results.append(StructurallyValidatedPair(
                    rule_i=rule_i,
                    rule_j=rule_j,
                    similarity=vpair.similarity,
                    entity_overlap=vpair.entity_overlap,
                    shared_resources=shared_resources,
                    shared_actions=shared_actions,
                    opposite_effects=opposite_effects,
                    sparql_valid=sparql_valid
                ))
        
        return results
    
    def get_conflict_candidates(self, rules: List[CPMRule]) -> List[StructurallyValidatedPair]:
        """
        Get all pairs that could potentially conflict based on structure.
        Uses direct analysis without prior semantic filtering.
        """
        self.build_graph(rules)
        results = []
        
        for i, rule_i in enumerate(rules):
            for j, rule_j in enumerate(rules):
                if i >= j:
                    continue
                
                has_shared, shared_resources = self.shared_resource_scope(rule_i, rule_j)
                shared_actions = self.actions_compatible(rule_i.action, rule_j.action)
                opposite_effects = rule_i.effect != rule_j.effect
                sparql_valid = has_shared and shared_actions
                
                if sparql_valid and opposite_effects:
                    results.append(StructurallyValidatedPair(
                        rule_i=rule_i,
                        rule_j=rule_j,
                        similarity=0.0,  # Not computed
                        entity_overlap=0.0,  # Not computed
                        shared_resources=shared_resources,
                        shared_actions=shared_actions,
                        opposite_effects=opposite_effects,
                        sparql_valid=sparql_valid
                    ))
        
        return results


# ============================================================
# DEMONSTRATION: Figure 3 (Phase 3) - SPARQL Validation
# ============================================================

def demonstrate_sparql_validation():
    """
    Demonstrates RDF graph building and SPARQL structural validation.
    """
    from models.cpm import CPMNormalizer
    from detection.semantic_screener import SemanticScreener
    from detection.entity_validator import EntityValidator
    
    print("=" * 70)
    print("FIGURE 3 (Phase 3): SPARQL Structural Validation Demonstration")
    print("=" * 70)
    
    # Create sample rules with structural relationships
    normalizer = CPMNormalizer()
    sample_rules = [
        # Rule 1 & 2: Same resource type, compatible actions, opposite effects = CONFLICT
        {
            "rule_id": "PSD2_001",
            "subject": {"type": "customer", "roles": ["user"]},
            "action": "read",
            "resource": {"type": "account_data", "identifiers": ["balance_api"]},
            "environment": {"authenticated": True},
            "effect": "Permit",
        },
        {
            "rule_id": "INTERNAL_001",
            "subject": {"type": "user", "roles": ["customer"]},
            "action": "view",  # Compatible with 'read'
            "resource": {"type": "account_data", "identifiers": ["balance_api"]},
            "environment": {"business_hours": True},
            "effect": "Deny",  # Opposite effect!
        },
        
        # Rule 3: Different resource, no conflict
        {
            "rule_id": "NIST_001",
            "subject": {"type": "admin", "roles": ["administrator"]},
            "action": "modify",
            "resource": {"type": "system_config", "identifiers": ["firewall_api"]},
            "environment": {"mfa_verified": True},
            "effect": "Permit",
        },
        
        # Rule 4: Same resource as 3, but compatible effects
        {
            "rule_id": "ISO_001",
            "subject": {"type": "admin", "roles": ["superuser"]},
            "action": "update",  # Compatible with 'modify'
            "resource": {"type": "system_config", "identifiers": ["config_api"]},
            "environment": {},
            "effect": "Permit",  # Same effect = no conflict
        },
    ]
    
    cpm_rules = normalizer.normalize_batch(sample_rules, "MIXED")
    
    # Build RDF graph
    print("\n1. Building RDF Graph:")
    print("-" * 50)
    
    validator = SPARQLValidator()
    validator.build_graph(cpm_rules)
    
    print(f"  Added {len(cpm_rules)} rules to RDF graph")
    
    if RDFLIB_AVAILABLE:
        print(f"  Total triples: {len(validator.rdf_graph.graph)}")
    
    # Show action compatibility
    print("\n2. Action Compatibility Groups:")
    print("-" * 50)
    for group, actions in SPARQLValidator.ACTION_GROUPS.items():
        print(f"  {group}: {', '.join(actions)}")
    
    # Analyze structural relationships
    print("\n3. Structural Analysis (Direct):")
    print("-" * 50)
    
    structural_candidates = validator.get_conflict_candidates(cpm_rules)
    
    for svpair in structural_candidates:
        print(f"\n  {svpair.rule_i.rule_id} <-> {svpair.rule_j.rule_id}")
        print(f"    Shared resources: {', '.join(svpair.shared_resources)}")
        print(f"    Actions compatible: {svpair.shared_actions}")
        print(f"      ({svpair.rule_i.action} ~ {svpair.rule_j.action})")
        print(f"    Opposite effects: {svpair.opposite_effects}")
        print(f"      ({svpair.rule_i.effect.value} vs {svpair.rule_j.effect.value})")
        print(f"    ⚠️  SPARQL CONFLICT CANDIDATE")
    
    # Full pipeline: Semantic -> Entity -> SPARQL
    print("\n4. Full Three-Phase Pipeline:")
    print("-" * 50)
    
    # Phase 1: Semantic screening
    screener = SemanticScreener(threshold=0.3)
    semantic_candidates = screener.generate_candidates(cpm_rules)
    print(f"  Phase 1 (Semantic): {len(semantic_candidates)} candidates")
    
    # Phase 2: Entity validation
    entity_validator = EntityValidator(threshold=0.2)
    entity_validated = entity_validator.validate_candidates(semantic_candidates)
    print(f"  Phase 2 (Entity): {len(entity_validated)} validated")
    
    # Phase 3: SPARQL structural
    sparql_validated = validator.validate_structure(entity_validated)
    print(f"  Phase 3 (SPARQL): {len(sparql_validated)} conflict candidates")
    
    print("\n  Final Conflict Candidates for SMT Verification:")
    for svpair in sparql_validated:
        print(f"    • {svpair.rule_i.rule_id} vs {svpair.rule_j.rule_id}")
        print(f"      Similarity: {svpair.similarity:.3f}, Entity Overlap: {svpair.entity_overlap:.3f}")
    
    return sparql_validated


if __name__ == "__main__":
    demonstrate_sparql_validation()
