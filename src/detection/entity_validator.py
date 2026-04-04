"""
Entity Validation - Figure 3 (Phase 2)
=======================================
CRF-based entity extraction and overlap validation.
"""

import re
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.cpm import CPMRule
from detection.semantic_screener import CandidatePair


@dataclass
class SecurityEntity:
    """Extracted security-domain entity"""
    text: str
    entity_type: str  # Enforcer, Asset, Action, Condition, Consequence
    start: int = 0
    end: int = 0
    
    def __hash__(self):
        return hash((self.text.lower(), self.entity_type))
    
    def __eq__(self, other):
        if not isinstance(other, SecurityEntity):
            return False
        return self.text.lower() == other.text.lower() and self.entity_type == other.entity_type


@dataclass  
class ValidatedPair:
    """A candidate pair that passed entity validation"""
    rule_i: CPMRule
    rule_j: CPMRule
    similarity: float
    entity_overlap: float
    entities_i: List[SecurityEntity] = field(default_factory=list)
    entities_j: List[SecurityEntity] = field(default_factory=list)


class SecurityEntityExtractor:
    """
    Extracts security-domain entities from policy summaries.
    
    Entity Types (from paper Section III-C):
    - Enforcer: Subject/role that enforces the rule
    - Asset: Resource being protected
    - Action: Operation being performed
    - Condition: Environmental constraints
    - Consequence: Effect or obligation
    
    This is a rule-based implementation for demonstration.
    Production would use trained CRF model.
    """
    
    # Pattern definitions for entity extraction
    PATTERNS = {
        "Enforcer": [
            r"\b(administrator|admin|user|customer|operator|auditor|processor|provider)\b",
            r"\b(privileged_user|superuser|root|account_holder|end_user)\b",
            r"\b(system_operator|compliance_officer|incident_responder)\b",
            r"\b(third_party|tpp|data_subject)\b",
        ],
        "Asset": [
            r"\b(transaction|payment|transfer|data|record|config|configuration)\b",
            r"\b(api|endpoint|service|system|logs|file|database)\b",
            r"\b(personal_data|pii|customer_data|account|financial)\b",
            r"\b(firewall|security|audit|settings)\b",
        ],
        "Action": [
            r"\b(read|write|create|delete|execute|update|modify|access)\b",
            r"\b(initiate|export|view|retrieve|remove|invoke)\b",
            r"\b(permitted|denied|allowed|blocked)\b",
        ],
        "Condition": [
            r"\b(when|if|requires|during|within|under|only)\b",
            r"\b(mfa|sca|verified|authenticated|authorized)\b",
            r"\b(internal|external|business_hours|emergency)\b",
            r"\b(consent|valid|active|enabled)\b",
            r"\b(max_amount|threshold|limit)\b",
        ],
        "Consequence": [
            r"\b(permit|deny|allow|block|reject|grant)\b",
            r"\b(audit|log|notify|alert|require)\b",
            r"\b(obligation|must|shall|should)\b",
        ],
    }
    
    def __init__(self):
        # Compile patterns for efficiency
        self.compiled_patterns = {}
        for entity_type, patterns in self.PATTERNS.items():
            combined = "|".join(patterns)
            self.compiled_patterns[entity_type] = re.compile(combined, re.IGNORECASE)
    
    def extract(self, text: str) -> List[SecurityEntity]:
        """
        Extract security entities from text.
        
        Args:
            text: Policy summary text
            
        Returns:
            List of extracted entities
        """
        entities = []
        seen = set()
        
        for entity_type, pattern in self.compiled_patterns.items():
            for match in pattern.finditer(text):
                entity_text = match.group().lower()
                key = (entity_text, entity_type)
                
                if key not in seen:
                    seen.add(key)
                    entities.append(SecurityEntity(
                        text=entity_text,
                        entity_type=entity_type,
                        start=match.start(),
                        end=match.end()
                    ))
        
        return entities
    
    def extract_from_rule(self, rule: CPMRule) -> List[SecurityEntity]:
        """Extract entities from a CPM rule"""
        summary = rule.to_summary()
        entities = self.extract(summary)
        
        # Also extract from structured fields
        # Subject
        entities.append(SecurityEntity(
            text=rule.subject.type,
            entity_type="Enforcer"
        ))
        for role in rule.subject.roles:
            entities.append(SecurityEntity(
                text=role,
                entity_type="Enforcer"
            ))
        
        # Action
        entities.append(SecurityEntity(
            text=rule.action,
            entity_type="Action"
        ))
        
        # Resource
        entities.append(SecurityEntity(
            text=rule.resource.type,
            entity_type="Asset"
        ))
        for identifier in rule.resource.identifiers:
            entities.append(SecurityEntity(
                text=identifier,
                entity_type="Asset"
            ))
        
        # Effect
        entities.append(SecurityEntity(
            text=rule.effect.value,
            entity_type="Consequence"
        ))
        
        # Deduplicate
        unique_entities = list(set(entities))
        return unique_entities


class EntityValidator:
    """
    Validates candidate pairs based on entity overlap.
    Implementation of Figure 3, Phase 2.
    """
    
    DEFAULT_THRESHOLD = 0.40  # From paper Section III-C
    
    def __init__(self, threshold: float = None):
        self.threshold = threshold or self.DEFAULT_THRESHOLD
        self.extractor = SecurityEntityExtractor()
    
    def compute_overlap(self, entities_i: List[SecurityEntity], 
                       entities_j: List[SecurityEntity]) -> float:
        """
        Compute Jaccard similarity between entity sets.
        
        overlap = |intersection| / |union|
        """
        set_i = set(entities_i)
        set_j = set(entities_j)
        
        intersection = len(set_i & set_j)
        union = len(set_i | set_j)
        
        if union == 0:
            return 0.0
        
        return intersection / union
    
    def compute_type_overlap(self, entities_i: List[SecurityEntity],
                            entities_j: List[SecurityEntity]) -> Dict[str, float]:
        """Compute overlap per entity type"""
        overlaps = {}
        
        for entity_type in ["Enforcer", "Asset", "Action", "Condition", "Consequence"]:
            type_i = {e for e in entities_i if e.entity_type == entity_type}
            type_j = {e for e in entities_j if e.entity_type == entity_type}
            
            intersection = len(type_i & type_j)
            union = len(type_i | type_j)
            
            overlaps[entity_type] = intersection / union if union > 0 else 0.0
        
        return overlaps
    
    def validate_candidates(self, candidates: List[CandidatePair]) -> List[ValidatedPair]:
        """
        Filter candidates based on entity overlap threshold.
        
        Args:
            candidates: Candidate pairs from semantic screening
            
        Returns:
            Validated pairs with overlap >= threshold
        """
        validated = []
        
        for cand in candidates:
            # Extract entities
            entities_i = self.extractor.extract_from_rule(cand.rule_i)
            entities_j = self.extractor.extract_from_rule(cand.rule_j)
            
            # Compute overlap
            overlap = self.compute_overlap(entities_i, entities_j)
            
            if overlap >= self.threshold:
                validated.append(ValidatedPair(
                    rule_i=cand.rule_i,
                    rule_j=cand.rule_j,
                    similarity=cand.similarity,
                    entity_overlap=overlap,
                    entities_i=entities_i,
                    entities_j=entities_j
                ))
        
        return validated


# ============================================================
# DEMONSTRATION: Figure 3 (Phase 2) - Entity Validation
# ============================================================

def demonstrate_entity_validation():
    """
    Demonstrates entity extraction and validation.
    """
    from models.cpm import CPMNormalizer
    from detection.semantic_screener import SemanticScreener
    
    print("=" * 70)
    print("FIGURE 3 (Phase 2): Entity Validation Demonstration")
    print("=" * 70)
    
    # Create sample rules
    normalizer = CPMNormalizer()
    sample_rules = [
        {
            "rule_id": "RULE_001",
            "subject": {"type": "administrator", "roles": ["admin", "superuser"]},
            "action": "modify",
            "resource": {"type": "system_config", "identifiers": ["firewall_api"]},
            "environment": {"mfa_verified": True, "location": "internal"},
            "effect": "Permit",
        },
        {
            "rule_id": "RULE_002",
            "subject": {"type": "privileged_user", "roles": ["admin"]},
            "action": "update",
            "resource": {"type": "configuration", "identifiers": ["settings_api"]},
            "environment": {"authenticated": True},
            "effect": "Deny",
        },
        {
            "rule_id": "RULE_003",
            "subject": {"type": "customer", "roles": ["user"]},
            "action": "view",
            "resource": {"type": "account_data", "identifiers": ["account_api"]},
            "environment": {},
            "effect": "Permit",
        },
    ]
    
    cpm_rules = normalizer.normalize_batch(sample_rules, "TEST")
    
    # Extract entities
    extractor = SecurityEntityExtractor()
    
    print("\n1. Entity Extraction Results:")
    print("-" * 50)
    
    for rule in cpm_rules:
        print(f"\n  {rule.rule_id}: {rule.to_summary()}")
        entities = extractor.extract_from_rule(rule)
        
        by_type = defaultdict(list)
        for e in entities:
            by_type[e.entity_type].append(e.text)
        
        for etype in ["Enforcer", "Asset", "Action", "Condition", "Consequence"]:
            if by_type[etype]:
                print(f"    {etype}: {', '.join(set(by_type[etype]))}")
    
    # Generate candidates and validate
    print("\n2. Semantic Candidates:")
    print("-" * 50)
    
    screener = SemanticScreener(threshold=0.4)  # Lower threshold for demo
    candidates = screener.generate_candidates(cpm_rules)
    
    for cand in candidates:
        print(f"  {cand.rule_i.rule_id} <-> {cand.rule_j.rule_id}: similarity={cand.similarity:.3f}")
    
    # Validate with entity overlap
    print(f"\n3. Entity Validation (threshold={EntityValidator.DEFAULT_THRESHOLD}):")
    print("-" * 50)
    
    validator = EntityValidator()
    validated = validator.validate_candidates(candidates)
    
    for vpair in validated:
        type_overlap = validator.compute_type_overlap(vpair.entities_i, vpair.entities_j)
        
        print(f"\n  {vpair.rule_i.rule_id} <-> {vpair.rule_j.rule_id}")
        print(f"    Semantic similarity: {vpair.similarity:.3f}")
        print(f"    Entity overlap: {vpair.entity_overlap:.3f}")
        print(f"    Per-type overlap:")
        for etype, overlap in type_overlap.items():
            if overlap > 0:
                print(f"      {etype}: {overlap:.2f}")
        
        # Check for potential conflict
        if vpair.rule_i.effect != vpair.rule_j.effect:
            print(f"    ⚠️  POTENTIAL CONFLICT: {vpair.rule_i.effect.value} vs {vpair.rule_j.effect.value}")
    
    # Threshold sensitivity
    print("\n4. Threshold Sensitivity:")
    print("-" * 50)
    
    for threshold in [0.2, 0.3, 0.4, 0.5, 0.6]:
        validator.threshold = threshold
        validated = validator.validate_candidates(candidates)
        conflicts = [v for v in validated if v.rule_i.effect != v.rule_j.effect]
        print(f"  Threshold {threshold:.2f}: {len(validated)} validated, {len(conflicts)} potential conflicts")
    
    return validated


if __name__ == "__main__":
    demonstrate_entity_validation()
