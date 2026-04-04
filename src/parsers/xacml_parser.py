"""
XACML 3.0 Parser
=================
Parses XACML 3.0 policy files and converts to CPM rules.
"""

import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import re
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.cpm import CPMRule, Subject, Resource, Environment, Effect


# XACML 3.0 namespace
XACML_NS = "{urn:oasis:names:tc:xacml:3.0:core:schema:wd-17}"


def strip_namespace(tag: str) -> str:
    """Remove namespace prefix from tag"""
    return tag.split('}')[-1] if '}' in tag else tag


@dataclass
class XACMLRule:
    """Parsed XACML rule"""
    rule_id: str
    effect: str  # "Permit" or "Deny"
    policy_id: str = ""
    description: str = ""
    resource_type: str = ""
    resource_id: str = ""
    action_id: str = ""
    subject_type: str = ""
    subject_role: str = ""
    conditions: Dict = None
    
    def __post_init__(self):
        if self.conditions is None:
            self.conditions = {}


class XACML3Parser:
    """
    Parser for XACML 3.0 policy files.
    Extracts rules and converts to CPM format.
    """
    
    def __init__(self):
        self.policies = []
        self.rules = []
    
    def parse_file(self, filepath: str) -> List[XACMLRule]:
        """Parse XACML file and extract rules"""
        self.rules = []
        
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
            
            # Remove namespace for easier parsing
            self._strip_namespaces(root)
            
            # Parse PolicySet or Policy
            if root.tag == 'PolicySet' or strip_namespace(root.tag) == 'PolicySet':
                self._parse_policy_set(root)
            elif root.tag == 'Policy' or strip_namespace(root.tag) == 'Policy':
                self._parse_policy(root)
            
        except ET.ParseError as e:
            print(f"XML Parse Error: {e}")
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
        
        return self.rules
    
    def _strip_namespaces(self, root):
        """Remove namespaces from all elements"""
        for elem in root.iter():
            if '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]
    
    def _parse_policy_set(self, policy_set):
        """Parse PolicySet element"""
        policy_set_id = policy_set.get('PolicySetId', 'unknown')
        
        for child in policy_set:
            tag = strip_namespace(child.tag)
            if tag == 'Policy':
                self._parse_policy(child, policy_set_id)
            elif tag == 'PolicySet':
                self._parse_policy_set(child)
    
    def _parse_policy(self, policy, parent_id: str = ""):
        """Parse Policy element"""
        policy_id = policy.get('PolicyId', parent_id)
        
        for child in policy:
            tag = strip_namespace(child.tag)
            if tag == 'Rule':
                self._parse_rule(child, policy_id)
    
    def _parse_rule(self, rule_elem, policy_id: str):
        """Parse Rule element"""
        rule_id = rule_elem.get('RuleId', 'unknown')
        effect = rule_elem.get('Effect', 'Deny')
        
        rule = XACMLRule(
            rule_id=self._extract_simple_id(rule_id),
            effect=effect,
            policy_id=policy_id
        )
        
        # Parse rule components
        for child in rule_elem:
            tag = strip_namespace(child.tag)
            
            if tag == 'Description':
                rule.description = child.text or ""
            
            elif tag == 'Target':
                self._parse_target(child, rule)
            
            elif tag == 'Condition':
                self._parse_condition(child, rule)
        
        self.rules.append(rule)
    
    def _extract_simple_id(self, full_id: str) -> str:
        """Extract simple ID from URL-like identifiers"""
        if '/' in full_id:
            return full_id.split('/')[-1]
        return full_id
    
    def _parse_target(self, target, rule: XACMLRule):
        """Parse Target element to extract subject, action, resource"""
        for any_of in target.findall('.//AnyOf'):
            for all_of in any_of.findall('.//AllOf'):
                for match in all_of.findall('.//Match'):
                    self._parse_match(match, rule)
    
    def _parse_match(self, match, rule: XACMLRule):
        """Parse Match element"""
        attr_value = None
        attr_id = None
        
        for child in match:
            tag = strip_namespace(child.tag)
            
            if tag == 'AttributeValue':
                attr_value = child.text
            
            elif tag == 'AttributeDesignator':
                attr_id = child.get('AttributeId', '')
        
        if attr_value and attr_id:
            self._classify_attribute(attr_id, attr_value, rule)
    
    def _classify_attribute(self, attr_id: str, value: str, rule: XACMLRule):
        """Classify attribute into subject/action/resource"""
        attr_lower = attr_id.lower()
        
        # Action patterns
        if 'action' in attr_lower or 'action-id' in attr_lower:
            rule.action_id = self._extract_simple_id(value)
        
        # Resource patterns
        elif 'resource' in attr_lower:
            if 'type' in attr_lower:
                rule.resource_type = self._extract_simple_id(value)
            else:
                rule.resource_id = value
        
        # Subject patterns
        elif 'subject' in attr_lower or 'role' in attr_lower:
            if 'role' in attr_lower:
                rule.subject_role = value
            else:
                rule.subject_type = value
    
    def _parse_condition(self, condition, rule: XACMLRule):
        """Parse Condition element for additional constraints"""
        # Extract any threshold/limit conditions
        for apply_elem in condition.findall('.//Apply'):
            func_id = apply_elem.get('FunctionId', '')
            
            for attr_val in apply_elem.findall('.//AttributeValue'):
                if attr_val.text and attr_val.text.isdigit():
                    if 'greater' in func_id or 'less' in func_id:
                        rule.conditions['threshold'] = int(attr_val.text)
    
    def to_cpm_rules(self, framework: str = "XACML") -> List[CPMRule]:
        """Convert parsed XACML rules to CPM format"""
        cpm_rules = []
        
        for xacml_rule in self.rules:
            # Build subject
            subject = Subject(
                type=xacml_rule.subject_role or xacml_rule.subject_type or "user",
                roles=[xacml_rule.subject_role] if xacml_rule.subject_role else [],
                attributes={}
            )
            
            # Build resource
            resource = Resource(
                type=xacml_rule.resource_type or xacml_rule.resource_id or "resource",
                identifiers=[xacml_rule.resource_id] if xacml_rule.resource_id else [],
                attributes={}
            )
            
            # Build environment
            environment = Environment(conditions=xacml_rule.conditions)
            
            # Build CPM rule
            cpm_rule = CPMRule(
                rule_id=xacml_rule.rule_id,
                subject=subject,
                action=xacml_rule.action_id or "access",
                resource=resource,
                environment=environment,
                effect=Effect.PERMIT if xacml_rule.effect == "Permit" else Effect.DENY,
                framework_origin=framework,
                priority=50,  # Default, can be overridden
                obligations=[]
            )
            
            cpm_rules.append(cpm_rule)
        
        return cpm_rules


def parse_xacml_file(filepath: str, framework: str = None) -> Tuple[List[XACMLRule], List[CPMRule]]:
    """
    Parse XACML file and return both raw rules and CPM rules.
    """
    parser = XACML3Parser()
    xacml_rules = parser.parse_file(filepath)
    
    # Infer framework from filename
    if framework is None:
        filename = os.path.basename(filepath).lower()
        if 'geysers' in filename:
            framework = "GEYSERS"
        elif 'kmarket' in filename:
            framework = "KMarket"
        elif 'continue' in filename:
            framework = "Continue-A"
        elif 'synthetic' in filename:
            framework = "Synthetic"
        else:
            framework = "XACML"
    
    cpm_rules = parser.to_cpm_rules(framework)
    
    return xacml_rules, cpm_rules


# ============================================================
# DEMONSTRATION
# ============================================================

def demonstrate_xacml_parser():
    """Demo the XACML parser"""
    print("=" * 70)
    print("XACML 3.0 Parser Demonstration")
    print("=" * 70)
    
    # Test with sample XML
    sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <PolicySet xmlns="urn:oasis:names:tc:xacml:3.0:core:schema:wd-17"
               PolicySetId="TestPolicySet" Version="1.0"
               PolicyCombiningAlgId="urn:oasis:names:tc:xacml:1.0:policy-combining-algorithm:first-applicable">
        <Policy PolicyId="TestPolicy" Version="1.0"
                RuleCombiningAlgId="urn:oasis:names:tc:xacml:3.0:rule-combining-algorithm:deny-overrides">
            <Target/>
            <Rule RuleId="TestRule1" Effect="Permit">
                <Target>
                    <AnyOf>
                        <AllOf>
                            <Match MatchId="urn:oasis:names:tc:xacml:1.0:function:string-equal">
                                <AttributeValue DataType="http://www.w3.org/2001/XMLSchema#string">admin</AttributeValue>
                                <AttributeDesignator AttributeId="role" Category="subject" DataType="string"/>
                            </Match>
                        </AllOf>
                    </AnyOf>
                    <AnyOf>
                        <AllOf>
                            <Match MatchId="urn:oasis:names:tc:xacml:1.0:function:string-equal">
                                <AttributeValue DataType="http://www.w3.org/2001/XMLSchema#string">read</AttributeValue>
                                <AttributeDesignator AttributeId="action-id" Category="action" DataType="string"/>
                            </Match>
                        </AllOf>
                    </AnyOf>
                </Target>
            </Rule>
            <Rule RuleId="TestRule2" Effect="Deny">
                <Description>Deny access for guests</Description>
                <Target>
                    <AnyOf>
                        <AllOf>
                            <Match MatchId="urn:oasis:names:tc:xacml:1.0:function:string-equal">
                                <AttributeValue DataType="http://www.w3.org/2001/XMLSchema#string">guest</AttributeValue>
                                <AttributeDesignator AttributeId="role" Category="subject" DataType="string"/>
                            </Match>
                        </AllOf>
                    </AnyOf>
                </Target>
            </Rule>
        </Policy>
    </PolicySet>
    """
    
    # Parse from string
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
        f.write(sample_xml)
        temp_path = f.name
    
    try:
        xacml_rules, cpm_rules = parse_xacml_file(temp_path, "TEST")
        
        print(f"\nParsed {len(xacml_rules)} XACML rules -> {len(cpm_rules)} CPM rules")
        
        for xacml, cpm in zip(xacml_rules, cpm_rules):
            print(f"\n  {xacml.rule_id}:")
            print(f"    Effect: {xacml.effect}")
            print(f"    Subject: {xacml.subject_role or xacml.subject_type}")
            print(f"    Action: {xacml.action_id}")
            print(f"    CPM Summary: {cpm.to_summary()}")
    
    finally:
        os.unlink(temp_path)
    
    return cpm_rules


if __name__ == "__main__":
    demonstrate_xacml_parser()
