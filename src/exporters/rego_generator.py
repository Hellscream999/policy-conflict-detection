"""
Rego Policy Generator
======================
Converts CPM rules to OPA Rego policy format.
"""

from typing import List, Dict, Any, Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.cpm import CPMRule, Effect


class RegoGenerator:
    """
    Converts Common Policy Model (CPM) rules to OPA Rego policies.
    
    Rego is the policy language used by Open Policy Agent (OPA).
    This generator creates Rego code that mirrors the CPM semantics.
    """
    
    def __init__(self, package_name: str = "policy"):
        self.package_name = package_name
    
    def generate_package(self, rules: List[CPMRule], 
                         include_helpers: bool = True) -> str:
        """
        Generate a complete Rego package from CPM rules.
        
        Args:
            rules: List of CPM rules to convert
            include_helpers: Whether to include helper functions
            
        Returns:
            Complete Rego policy as string
        """
        lines = []
        
        # Package declaration
        lines.append(f"package {self.package_name}")
        lines.append("")
        
        # Imports
        lines.append("import rego.v1")
        lines.append("")
        
        # Default decision
        lines.append("# Default deny - explicit allow required")
        lines.append("default allow := false")
        lines.append("default deny := false")
        lines.append("")
        
        # Helper functions
        if include_helpers:
            lines.extend(self._generate_helpers())
            lines.append("")
        
        # Group rules by effect
        permit_rules = [r for r in rules if r.effect == Effect.PERMIT]
        deny_rules = [r for r in rules if r.effect == Effect.DENY]
        
        # Generate allow rules
        if permit_rules:
            lines.append("# ===========================================")
            lines.append("# PERMIT RULES")
            lines.append("# ===========================================")
            lines.append("")
            
            for rule in permit_rules:
                lines.extend(self._generate_permit_rule(rule))
                lines.append("")
        
        # Generate deny rules
        if deny_rules:
            lines.append("# ===========================================")
            lines.append("# DENY RULES")
            lines.append("# ===========================================")
            lines.append("")
            
            for rule in deny_rules:
                lines.extend(self._generate_deny_rule(rule))
                lines.append("")
        
        # Final decision logic
        lines.extend(self._generate_decision_logic())
        
        return "\n".join(lines)
    
    def _generate_helpers(self) -> List[str]:
        """Generate helper functions for policy evaluation"""
        return [
            "# Helper: Check if user has required role",
            "has_role(required) if {",
            "    some role in input.subject.roles",
            "    role == required",
            "}",
            "",
            "# Helper: Check if resource matches type",
            "resource_type_matches(required) if {",
            "    input.resource.type == required",
            "}",
            "",
            "# Helper: Check if action matches",
            "action_matches(required) if {",
            "    input.action == required",
            "}",
            "",
            "# Helper: Check environment condition",
            "env_condition(key, value) if {",
            "    input.environment[key] == value",
            "}",
        ]
    
    def _generate_permit_rule(self, rule: CPMRule) -> List[str]:
        """Generate Rego allow rule from CPM permit rule"""
        lines = []
        
        # Rule comment
        rule_id_safe = self._safe_id(rule.rule_id)
        lines.append(f"# Rule: {rule.rule_id}")
        lines.append(f"# Summary: {rule.to_summary()}")
        lines.append(f"allow if {{")
        
        # Subject conditions
        lines.append(f"    # Subject: {rule.subject.type}")
        lines.append(f'    input.subject.type == "{rule.subject.type}"')
        
        # Role check if roles exist
        if rule.subject.roles:
            for role in rule.subject.roles:
                lines.append(f'    has_role("{role}")')
        
        # Action
        lines.append(f"    # Action: {rule.action}")
        lines.append(f'    action_matches("{rule.action}")')
        
        # Resource
        lines.append(f"    # Resource: {rule.resource.type}")
        lines.append(f'    resource_type_matches("{rule.resource.type}")')
        
        # Resource identifiers
        if rule.resource.identifiers:
            for identifier in rule.resource.identifiers:
                lines.append(f'    input.resource.id == "{identifier}"')
        
        # Environment conditions
        if rule.environment.conditions:
            lines.append(f"    # Environment conditions")
            for key, value in rule.environment.conditions.items():
                if isinstance(value, dict) and 'operator' in value:
                    # Complex condition
                    op = value.get('operator', '==')
                    val = value.get('value')
                    lines.append(f'    input.environment.{key} {op} {self._format_value(val)}')
                else:
                    # Simple condition
                    lines.append(f'    env_condition("{key}", {self._format_value(value)})')
        
        lines.append("}")
        
        return lines
    
    def _generate_deny_rule(self, rule: CPMRule) -> List[str]:
        """Generate Rego deny rule from CPM deny rule"""
        lines = []
        
        # Rule comment
        lines.append(f"# Rule: {rule.rule_id}")
        lines.append(f"# Summary: {rule.to_summary()}")
        lines.append(f"deny if {{")
        
        # Subject conditions
        lines.append(f"    # Subject: {rule.subject.type}")
        lines.append(f'    input.subject.type == "{rule.subject.type}"')
        
        # Role check if roles exist
        if rule.subject.roles:
            for role in rule.subject.roles:
                lines.append(f'    has_role("{role}")')
        
        # Action
        lines.append(f"    # Action: {rule.action}")
        lines.append(f'    action_matches("{rule.action}")')
        
        # Resource
        lines.append(f"    # Resource: {rule.resource.type}")
        lines.append(f'    resource_type_matches("{rule.resource.type}")')
        
        # Resource identifiers
        if rule.resource.identifiers:
            for identifier in rule.resource.identifiers:
                lines.append(f'    input.resource.id == "{identifier}"')
        
        # Environment conditions
        if rule.environment.conditions:
            lines.append(f"    # Environment conditions")
            for key, value in rule.environment.conditions.items():
                if isinstance(value, dict) and 'operator' in value:
                    op = value.get('operator', '==')
                    val = value.get('value')
                    lines.append(f'    input.environment.{key} {op} {self._format_value(val)}')
                else:
                    lines.append(f'    env_condition("{key}", {self._format_value(value)})')
        
        lines.append("}")
        
        return lines
    
    def _generate_decision_logic(self) -> List[str]:
        """Generate final decision logic"""
        return [
            "# ===========================================",
            "# FINAL DECISION",
            "# ===========================================",
            "",
            "# Combined decision: deny takes precedence over allow",
            "decision := \"deny\" if {",
            "    deny",
            "}",
            "",
            "decision := \"allow\" if {",
            "    allow",
            "    not deny",
            "}",
            "",
            "decision := \"not_applicable\" if {",
            "    not allow",
            "    not deny",
            "}",
            "",
            "# Conflict detection",
            "has_conflict if {",
            "    allow",
            "    deny",
            "}",
        ]
    
    def _safe_id(self, rule_id: str) -> str:
        """Convert rule ID to safe Rego identifier"""
        return rule_id.replace("-", "_").replace(".", "_").replace(":", "_").lower()
    
    def _format_value(self, value: Any) -> str:
        """Format Python value as Rego literal"""
        if isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, str):
            return f'"{value}"'
        elif isinstance(value, (int, float)):
            return str(value)
        else:
            return f'"{value}"'
    
    def generate_test_input(self, rule: CPMRule) -> Dict[str, Any]:
        """Generate a test input that would match a rule"""
        return {
            "subject": {
                "type": rule.subject.type,
                "roles": rule.subject.roles or ["user"],
                "attributes": rule.subject.attributes
            },
            "action": rule.action,
            "resource": {
                "type": rule.resource.type,
                "id": rule.resource.identifiers[0] if rule.resource.identifiers else "default",
                "attributes": rule.resource.attributes
            },
            "environment": {k: v.get('value', v) if isinstance(v, dict) else v 
                          for k, v in rule.environment.conditions.items()}
        }
    
    def generate_test_suite(self, rules: List[CPMRule]) -> str:
        """Generate Rego test suite for the policy"""
        lines = []
        
        lines.append(f"package {self.package_name}_test")
        lines.append("")
        lines.append(f"import data.{self.package_name}")
        lines.append("import rego.v1")
        lines.append("")
        
        for i, rule in enumerate(rules):
            test_input = self.generate_test_input(rule)
            expected = "allow" if rule.effect == Effect.PERMIT else "deny"
            
            lines.append(f"# Test for {rule.rule_id}")
            lines.append(f"test_{self._safe_id(rule.rule_id)} if {{")
            lines.append(f"    {self.package_name}.{expected} with input as {self._dict_to_rego(test_input)}")
            lines.append("}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _dict_to_rego(self, d: Dict, indent: int = 0) -> str:
        """Convert Python dict to Rego object literal"""
        spaces = "    " * indent
        inner_spaces = "    " * (indent + 1)
        
        pairs = []
        for k, v in d.items():
            if isinstance(v, dict):
                pairs.append(f'{inner_spaces}"{k}": {self._dict_to_rego(v, indent + 1)}')
            elif isinstance(v, list):
                items = [self._format_value(item) for item in v]
                pairs.append(f'{inner_spaces}"{k}": [{", ".join(items)}]')
            else:
                pairs.append(f'{inner_spaces}"{k}": {self._format_value(v)}')
        
        return "{\n" + ",\n".join(pairs) + f"\n{spaces}}}"


def export_rules_to_rego(rules: List[CPMRule], 
                         package_name: str = "policy",
                         output_file: Optional[str] = None) -> str:
    """
    Export CPM rules to Rego policy file.
    
    Args:
        rules: List of CPM rules
        package_name: Rego package name
        output_file: Optional file path to write
        
    Returns:
        Generated Rego code
    """
    generator = RegoGenerator(package_name)
    rego_code = generator.generate_package(rules)
    
    if output_file:
        with open(output_file, 'w') as f:
            f.write(rego_code)
        print(f"Exported {len(rules)} rules to {output_file}")
    
    return rego_code


# ============================================================
# DEMONSTRATION
# ============================================================

if __name__ == "__main__":
    from models.cpm import CPMNormalizer
    
    print("=" * 60)
    print("REGO EXPORTER DEMONSTRATION")
    print("=" * 60)
    
    normalizer = CPMNormalizer()
    
    sample_rules = [
        {
            "rule_id": "PERMIT_ADMIN_READ",
            "subject": {"type": "admin", "roles": ["administrator"]},
            "action": "read",
            "resource": {"type": "database", "identifiers": ["prod_db"]},
            "environment": {"business_hours": True},
            "effect": "Permit",
        },
        {
            "rule_id": "DENY_GUEST_WRITE",
            "subject": {"type": "guest", "roles": ["visitor"]},
            "action": "write",
            "resource": {"type": "database", "identifiers": ["prod_db"]},
            "effect": "Deny",
        },
    ]
    
    cpm_rules = normalizer.normalize_batch(sample_rules, "Test")
    
    generator = RegoGenerator("example_policy")
    rego_code = generator.generate_package(cpm_rules)
    
    print("\nGenerated Rego Policy:")
    print("-" * 60)
    print(rego_code)
    
    print("\n" + "-" * 60)
    print("Test Suite:")
    print("-" * 60)
    print(generator.generate_test_suite(cpm_rules))
