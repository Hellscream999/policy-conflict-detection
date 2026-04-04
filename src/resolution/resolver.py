"""
Conflict Resolution Module
===========================
Provides strategies to resolve detected policy conflicts and re-verify fixes.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from enum import Enum
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.cpm import CPMRule, Effect, Subject, Resource
from verification.smt_verifier import SMTVerifier, SMTResult


class ResolutionStrategy(Enum):
    """Available conflict resolution strategies"""
    ADD_CONDITION = "add_condition"
    SET_PRECEDENCE = "set_precedence"
    REFINE_SUBJECT = "refine_subject"
    REFINE_ACTION = "refine_action"
    REFINE_RESOURCE = "refine_resource"
    DISABLE_RULE = "disable_rule"
    OBLIGATION_HARMONIZATION = "obligation_harmonization"  # Added to match existing if needed


@dataclass
class Resolution:
    """A resolution applied to a conflict"""
    strategy: ResolutionStrategy
    target_rule_id: str
    parameters: Dict[str, Any]
    verified: bool = False
    verification_result: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            'strategy': self.strategy.value,
            'target_rule_id': self.target_rule_id,
            'parameters': self.parameters,
            'verified': self.verified,
            'verification_result': self.verification_result
        }


class ConflictResolver:
    """
    Applies resolution strategies to CPM rules and verifies the fix.
    """
    
    def __init__(self):
        self.verifier = SMTVerifier(timeout_ms=30000)
    
    def apply_resolution(self, rule: CPMRule, resolution: Resolution) -> CPMRule:
        """
        Apply a resolution strategy to a CPM rule.
        
        Args:
            rule: The original rule to modify
            resolution: The resolution strategy and parameters
            
        Returns:
            Modified CPMRule with resolution applied
        """
        # Create a copy of the rule to modify (conceptually, CPMRule is mutable-ish or we create new)
        # We'll create a new instance to be safe/functional
        
        if resolution.strategy == ResolutionStrategy.ADD_CONDITION:
            return self._add_condition(rule, resolution.parameters)
        
        elif resolution.strategy == ResolutionStrategy.SET_PRECEDENCE:
            return self._set_precedence(rule, resolution.parameters)
        
        elif resolution.strategy == ResolutionStrategy.REFINE_SUBJECT:
            return self._refine_subject(rule, resolution.parameters)
        
        elif resolution.strategy == ResolutionStrategy.REFINE_ACTION:
            return self._refine_action(rule, resolution.parameters)
        
        elif resolution.strategy == ResolutionStrategy.REFINE_RESOURCE:
            return self._refine_resource(rule, resolution.parameters)
        
        elif resolution.strategy == ResolutionStrategy.DISABLE_RULE:
            return self._disable_rule(rule)
        
        else:
            raise ValueError(f"Unknown resolution strategy: {resolution.strategy}")
    
    def _add_condition(self, rule: CPMRule, params: dict) -> CPMRule:
        """Add environment condition to narrow rule scope"""
        condition_key = params.get('condition_key')
        condition_value = params.get('condition_value')
        operator = params.get('operator', '==')  # ==, <, >, <=, >=, !=
        
        new_rule = self._copy_rule(rule)
        
        # Add condition
        new_rule.environment.conditions[condition_key] = {
            'operator': operator,
            'value': condition_value
        }
        
        return new_rule
    
    def _set_precedence(self, rule: CPMRule, params: dict) -> CPMRule:
        """Set priority to resolve conflict via precedence"""
        new_priority = params.get('priority', 100)
        
        new_rule = self._copy_rule(rule)
        new_rule.priority = new_priority
        
        return new_rule
    
    def _refine_subject(self, rule: CPMRule, params: dict) -> CPMRule:
        """Make subject more specific"""
        new_type = params.get('type', rule.subject.type)
        new_roles = params.get('roles', rule.subject.roles)
        # Handle comma-separated string if passed from UI
        if isinstance(new_roles, str):
            new_roles = [r.strip() for r in new_roles.split(',')]
            
        new_attributes = params.get('attributes', rule.subject.attributes)
        
        new_rule = self._copy_rule(rule)
        new_rule.subject = Subject(
            type=new_type,
            roles=new_roles if isinstance(new_roles, list) else [new_roles] if new_roles else [],
            attributes=new_attributes or {}
        )
        
        return new_rule
    
    def _refine_action(self, rule: CPMRule, params: dict) -> CPMRule:
        """Make action more specific"""
        new_action = params.get('action', rule.action)
        
        new_rule = self._copy_rule(rule)
        new_rule.action = new_action
        
        return new_rule
    
    def _refine_resource(self, rule: CPMRule, params: dict) -> CPMRule:
        """Make resource more specific"""
        new_type = params.get('type', rule.resource.type)
        new_identifiers = params.get('identifiers', rule.resource.identifiers)
        new_attributes = params.get('attributes', rule.resource.attributes)
        
        new_rule = self._copy_rule(rule)
        new_rule.resource = Resource(
            type=new_type,
            identifiers=new_identifiers if isinstance(new_identifiers, list) else [new_identifiers] if new_identifiers else [],
            attributes=new_attributes or {}
        )
        
        return new_rule
    
    def _disable_rule(self, rule: CPMRule) -> CPMRule:
        """Disable a rule by setting impossible condition"""
        new_rule = self._copy_rule(rule)
        new_rule.rule_id = rule.rule_id + "_DISABLED"
        new_rule.priority = 0
        
        # Add impossible condition
        new_rule.environment.conditions['__disabled__'] = {
            'operator': '==',
            'value': False
        }
        
        return new_rule
    
    def _copy_rule(self, rule: CPMRule) -> CPMRule:
        """Create a deep copy of a CPMRule"""
        # Since CPMRule creates new objects for components in init, 
        # we can just init with current values. 
        # Objects like environment need deep copy if we modify them.
        
        import copy
        return CPMRule(
            rule_id=rule.rule_id,
            subject=copy.deepcopy(rule.subject),
            action=rule.action,
            resource=copy.deepcopy(rule.resource),
            environment=copy.deepcopy(rule.environment),
            effect=rule.effect,
            framework_origin=rule.framework_origin,
            priority=rule.priority,
            obligations=copy.deepcopy(rule.obligations)
        )
    
    def verify_resolution(self, rule_i: CPMRule, rule_j: CPMRule) -> Dict[str, Any]:
        """
        Verify if two rules still conflict after resolution.
        
        Args:
            rule_i: First rule (potentially modified)
            rule_j: Second rule (potentially modified)
            
        Returns:
            Dict with verification result
        """
        result = self.verifier.verify_conflict(rule_i, rule_j)
        
        # If UNSAT, conflict is resolved. If SAT, still conflicts.
        resolved = (result.result == SMTResult.UNSAT)
        
        return {
            "resolved": resolved,
            "smt_result": result.result.value,
            "message": "Conflict eliminated" if resolved else "Conflict still exists"
        }
    
    def suggest_resolutions(self, rule_i: CPMRule, rule_j: CPMRule) -> List[Dict[str, Any]]:
        """
        Suggest possible resolutions for a conflict.
        
        Args:
            rule_i: First conflicting rule
            rule_j: Second conflicting rule
            
        Returns:
            List of suggests
        """
        suggestions = []
        
        # Suggestion 1: Add time-based condition
        suggestions.append({
            'strategy': ResolutionStrategy.ADD_CONDITION.value,
            'target_rule_id': rule_i.rule_id,
            'description': f'Add time constraint to {rule_i.rule_id}',
            'parameters': {
                'condition_key': 'time_of_day',
                'operator': '<',
                'condition_value': '18:00'
            }
        })
        
        # Suggestion 2: Set precedence
        # Deny usually wins
        target_rule = rule_i if rule_i.effect == Effect.DENY else rule_j
        suggestions.append({
            'strategy': ResolutionStrategy.SET_PRECEDENCE.value,
            'target_rule_id': target_rule.rule_id,
            'description': f'Give {target_rule.rule_id} (Deny) higher priority',
            'parameters': {
                'priority': 100
            }
        })
        
        return suggestions
