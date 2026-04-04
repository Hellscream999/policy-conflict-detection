"""
Common Policy Model (CPM) - Figure 2
=====================================
Demonstrates the normalization of heterogeneous policies into a unified representation.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from enum import Enum
import json


class Effect(Enum):
    """Policy effect: Permit or Deny"""
    PERMIT = "Permit"
    DENY = "Deny"


class ConflictType(Enum):
    """Types of policy conflicts as defined in Section III-C"""
    EXACT_CONTRADICTION = "Exact Contradiction"
    ATTRIBUTE_CONFLICT = "Attribute Conflict"
    SCOPE_CONFLICT = "Scope Conflict"
    PRIORITY_CONFLICT = "Priority Conflict"


@dataclass
class Subject:
    """Subject/Role attributes in CPM"""
    type: str
    roles: List[str] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "roles": self.roles,
            "attributes": self.attributes
        }


@dataclass
class Resource:
    """Resource attributes in CPM"""
    type: str
    identifiers: List[str] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "identifiers": self.identifiers,
            "attributes": self.attributes
        }


@dataclass
class Environment:
    """Environment conditions in CPM"""
    conditions: Dict[str, any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {"conditions": self.conditions}


@dataclass
class CPMRule:
    """
    Common Policy Model Rule - Figure 2
    
    Fields:
    - rule_id: Unique identifier
    - subject: Subject/role attributes
    - action: Standardized action verb
    - resource: Resource type and identifiers
    - environment: Environment constraints
    - effect: Permit or Deny
    - framework_origin: Source framework tag
    - priority: Precedence score
    - obligations: Optional post-conditions
    """
    rule_id: str
    subject: Subject
    action: str
    resource: Resource
    environment: Environment
    effect: Effect
    framework_origin: str
    priority: int = 0
    obligations: List[str] = field(default_factory=list)
    
    def to_summary(self) -> str:
        """Generate textual summary for BERT embedding"""
        subject_str = f"{self.subject.type}"
        if self.subject.roles:
            subject_str += f" with roles {', '.join(self.subject.roles)}"
        
        resource_str = f"{self.resource.type}"
        if self.resource.identifiers:
            resource_str += f" ({', '.join(self.resource.identifiers[:2])})"
        
        env_str = ""
        if self.environment.conditions:
            conditions = [f"{k}={v}" for k, v in list(self.environment.conditions.items())[:2]]
            env_str = f" when {', '.join(conditions)}"
        
        effect_verb = "permitted" if self.effect == Effect.PERMIT else "denied"
        
        return f"{subject_str} is {effect_verb} to {self.action} {resource_str}{env_str}"
    
    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "subject": self.subject.to_dict(),
            "action": self.action,
            "resource": self.resource.to_dict(),
            "environment": self.environment.to_dict(),
            "effect": self.effect.value,
            "framework_origin": self.framework_origin,
            "priority": self.priority,
            "obligations": self.obligations
        }
    
    def __repr__(self):
        return f"CPMRule(id={self.rule_id}, effect={self.effect.value}, action={self.action})"


class SynonymMapper:
    """
    Vocabulary normalization for cross-framework consistency.
    Maps framework-specific terms to standardized vocabulary.
    """
    
    def __init__(self):
        # Role synonyms
        self.role_mapping = {
            "administrator": "admin",
            "root": "admin",
            "superuser": "admin",
            "privileged_user": "admin",
            "end_user": "user",
            "customer": "user",
            "client": "user",
            "account_holder": "user",
            "auditor": "auditor",
            "compliance_officer": "auditor",
            "operator": "operator",
            "system_operator": "operator",
        }
        
        # Action synonyms
        self.action_mapping = {
            "view": "read",
            "access": "read",
            "retrieve": "read",
            "fetch": "read",
            "modify": "write",
            "update": "write",
            "change": "write",
            "edit": "write",
            "remove": "delete",
            "erase": "delete",
            "destroy": "delete",
            "create": "create",
            "add": "create",
            "insert": "create",
            "run": "execute",
            "invoke": "execute",
            "call": "execute",
        }
        
        # Resource type synonyms
        self.resource_mapping = {
            "payment_transaction": "transaction",
            "financial_record": "transaction",
            "transfer": "transaction",
            "customer_data": "personal_data",
            "pii": "personal_data",
            "user_information": "personal_data",
            "api": "api_endpoint",
            "service": "api_endpoint",
            "endpoint": "api_endpoint",
        }
    
    def map_role(self, role: str) -> str:
        return self.role_mapping.get(role.lower(), role.lower())
    
    def map_action(self, action: str) -> str:
        return self.action_mapping.get(action.lower(), action.lower())
    
    def map_resource(self, resource: str) -> str:
        return self.resource_mapping.get(resource.lower(), resource.lower())


class FrameworkPrecedence:
    """
    Framework precedence ordering for priority-based resolution.
    Higher score = higher priority.
    """
    
    DEFAULT_PRECEDENCE = {
        # Regulatory frameworks (highest priority)
        "GDPR": 100,
        "PSD2": 95,
        "DORA": 90,
        "SOX": 85,
        
        # Industry standards
        "ISO27001": 75,
        "NIST_CSF": 70,
        "PCI_DSS": 70,
        
        # Organizational policies
        "INTERNAL_SECURITY": 50,
        "INTERNAL_OPERATIONAL": 40,
        
        # Emergency overrides (context-dependent)
        "BREAK_GLASS": 110,  # Highest when activated
        
        # Default
        "DEFAULT": 0,
    }
    
    @classmethod
    def get_priority(cls, framework: str) -> int:
        return cls.DEFAULT_PRECEDENCE.get(framework.upper(), 0)


class CPMNormalizer:
    """
    Normalizes heterogeneous policies into Common Policy Model.
    Implements Stage 1 of the pipeline (Figure 1).
    """
    
    def __init__(self):
        self.synonym_mapper = SynonymMapper()
        self.rule_counter = 0
    
    def normalize_xacml_rule(self, xacml_rule: dict, framework: str = "XACML") -> CPMRule:
        """Convert XACML-style rule dict to CPM"""
        self.rule_counter += 1
        
        # Extract subject
        subject_data = xacml_rule.get("subject", {})
        subject = Subject(
            type=self.synonym_mapper.map_role(subject_data.get("type", "user")),
            roles=[self.synonym_mapper.map_role(r) for r in subject_data.get("roles", [])],
            attributes=subject_data.get("attributes", {})
        )
        
        # Extract action
        action = self.synonym_mapper.map_action(xacml_rule.get("action", "read"))
        
        # Extract resource
        resource_data = xacml_rule.get("resource", {})
        resource = Resource(
            type=self.synonym_mapper.map_resource(resource_data.get("type", "data")),
            identifiers=resource_data.get("identifiers", []),
            attributes=resource_data.get("attributes", {})
        )
        
        # Extract environment
        env_data = xacml_rule.get("environment", {})
        environment = Environment(conditions=env_data)
        
        # Extract effect
        effect_str = xacml_rule.get("effect", "Deny").upper()
        effect = Effect.PERMIT if effect_str == "PERMIT" else Effect.DENY
        
        # Calculate priority
        priority = FrameworkPrecedence.get_priority(framework)
        
        return CPMRule(
            rule_id=xacml_rule.get("rule_id", f"rule_{self.rule_counter}"),
            subject=subject,
            action=action,
            resource=resource,
            environment=environment,
            effect=effect,
            framework_origin=framework,
            priority=priority,
            obligations=xacml_rule.get("obligations", [])
        )
    
    def normalize_batch(self, rules: List[dict], framework: str = "XACML") -> List[CPMRule]:
        """Normalize a batch of rules"""
        return [self.normalize_xacml_rule(r, framework) for r in rules]


# ============================================================
# DEMONSTRATION: Figure 2 - Common Policy Model
# ============================================================

def demonstrate_cpm():
    """
    Demonstrates CPM normalization with sample policies from different frameworks.
    """
    print("=" * 70)
    print("FIGURE 2: Common Policy Model (CPM) Demonstration")
    print("=" * 70)
    
    # Sample policies from different frameworks
    psd2_rules = [
        {
            "rule_id": "PSD2_SCA_001",
            "subject": {"type": "account_holder", "roles": ["customer"]},
            "action": "initiate",
            "resource": {"type": "payment_transaction", "identifiers": ["payment_api"]},
            "environment": {"requires_sca": True, "max_amount": 500},
            "effect": "Permit",
        },
        {
            "rule_id": "PSD2_SCA_002",
            "subject": {"type": "third_party_provider", "roles": ["tpp"]},
            "action": "access",
            "resource": {"type": "account_data", "identifiers": ["account_info_api"]},
            "environment": {"consent_valid": True},
            "effect": "Permit",
        }
    ]
    
    nist_rules = [
        {
            "rule_id": "NIST_AC_001",
            "subject": {"type": "privileged_user", "roles": ["administrator"]},
            "action": "modify",
            "resource": {"type": "system_config", "identifiers": ["firewall_rules"]},
            "environment": {"mfa_verified": True, "location": "internal"},
            "effect": "Permit",
        },
        {
            "rule_id": "NIST_AC_002",
            "subject": {"type": "operator", "roles": ["system_operator"]},
            "action": "view",
            "resource": {"type": "audit_logs", "identifiers": ["security_logs"]},
            "environment": {},
            "effect": "Permit",
        }
    ]
    
    internal_rules = [
        {
            "rule_id": "INT_BG_001",
            "subject": {"type": "operator", "roles": ["incident_responder"]},
            "action": "execute",
            "resource": {"type": "emergency_override", "identifiers": ["break_glass_api"]},
            "environment": {"incident_declared": True},
            "effect": "Permit",
            "obligations": ["require_audit_log", "require_justification"]
        }
    ]
    
    # Normalize all rules
    normalizer = CPMNormalizer()
    
    print("\n1. Normalizing PSD2 Rules:")
    print("-" * 40)
    psd2_cpm = normalizer.normalize_batch(psd2_rules, "PSD2")
    for rule in psd2_cpm:
        print(f"  {rule.rule_id}:")
        print(f"    Summary: {rule.to_summary()}")
        print(f"    Priority: {rule.priority}")
        print()
    
    print("\n2. Normalizing NIST CSF Rules:")
    print("-" * 40)
    nist_cpm = normalizer.normalize_batch(nist_rules, "NIST_CSF")
    for rule in nist_cpm:
        print(f"  {rule.rule_id}:")
        print(f"    Summary: {rule.to_summary()}")
        print(f"    Priority: {rule.priority}")
        print()
    
    print("\n3. Normalizing Internal Policies:")
    print("-" * 40)
    internal_cpm = normalizer.normalize_batch(internal_rules, "BREAK_GLASS")
    for rule in internal_cpm:
        print(f"  {rule.rule_id}:")
        print(f"    Summary: {rule.to_summary()}")
        print(f"    Priority: {rule.priority}")
        print(f"    Obligations: {rule.obligations}")
        print()
    
    # Demonstrate synonym mapping
    print("\n4. Synonym Mapping Examples:")
    print("-" * 40)
    mapper = SynonymMapper()
    print(f"  'administrator' -> '{mapper.map_role('administrator')}'")
    print(f"  'superuser' -> '{mapper.map_role('superuser')}'")
    print(f"  'modify' -> '{mapper.map_action('modify')}'")
    print(f"  'payment_transaction' -> '{mapper.map_resource('payment_transaction')}'")
    
    # Show JSON representation
    print("\n5. CPM JSON Representation:")
    print("-" * 40)
    sample_cpm = psd2_cpm[0]
    print(json.dumps(sample_cpm.to_dict(), indent=2))
    
    return psd2_cpm + nist_cpm + internal_cpm


if __name__ == "__main__":
    demonstrate_cpm()
