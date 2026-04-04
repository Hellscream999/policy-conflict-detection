"""
Main Pipeline - Figure 1
=========================
Complete three-stage pipeline for policy conflict detection and resolution.
"""

import sys
import os
import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.cpm import CPMRule, CPMNormalizer, Effect, ConflictType
from detection.semantic_screener import SemanticScreener, CandidatePair
from detection.entity_validator import EntityValidator, ValidatedPair
from detection.sparql_validator import SPARQLValidator, StructurallyValidatedPair
from verification.smt_verifier import SMTVerifier, SMTVerificationResult, SMTResult
from resolution.resolver import ConflictResolver
from codegen.generator import RegoGenerator, XACMLGenerator, TestCaseGenerator


@dataclass
class PipelineConfig:
    """Configuration for the conflict detection pipeline"""
    # Stage 1: Normalization
    default_framework: str = "XACML"
    
    # Stage 2: Detection thresholds
    similarity_threshold: float = 0.65
    entity_overlap_threshold: float = 0.40
    
    # Stage 3: Verification
    smt_timeout_ms: int = 30000
    
    # Output
    output_format: str = "rego"  # "rego" or "xacml"


@dataclass
class PipelineMetrics:
    """Metrics from pipeline execution"""
    # Stage 1
    total_rules: int = 0
    normalized_rules: int = 0
    
    # Stage 2
    semantic_candidates: int = 0
    entity_validated: int = 0
    sparql_validated: int = 0
    
    # Stage 3
    smt_sat: int = 0
    smt_unsat: int = 0
    smt_unknown: int = 0
    smt_coverage: float = 0.0
    avg_solve_time_ms: float = 0.0
    
    # Resolution
    conflicts_resolved: int = 0
    resolutions_verified: int = 0
    
    def to_dict(self) -> dict:
        return {
            "stage1_normalization": {
                "total_rules": self.total_rules,
                "normalized_rules": self.normalized_rules,
            },
            "stage2_detection": {
                "semantic_candidates": self.semantic_candidates,
                "entity_validated": self.entity_validated,
                "sparql_validated": self.sparql_validated,
            },
            "stage3_verification": {
                "smt_sat": self.smt_sat,
                "smt_unsat": self.smt_unsat,
                "smt_unknown": self.smt_unknown,
                "smt_coverage": f"{self.smt_coverage:.1%}",
                "avg_solve_time_ms": f"{self.avg_solve_time_ms:.2f}",
            },
            "resolution": {
                "conflicts_resolved": self.conflicts_resolved,
                "resolutions_verified": self.resolutions_verified,
            }
        }


class ConflictDetectionPipeline:
    """
    Main three-stage pipeline for cross-framework conflict detection.
    Implementation of Figure 1.
    
    Stage 1: Normalization
        - Parse heterogeneous policies
        - Convert to Common Policy Model (CPM)
        - Apply synonym mapping
    
    Stage 2: Conflict Detection
        - Semantic screening (BERT embeddings)
        - Entity validation (CRF-based)
        - SPARQL structural checks
    
    Stage 3: Verification & Resolution
        - SMT verification (Z3)
        - Conflict resolution
        - Policy-as-code generation
    """
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.metrics = PipelineMetrics()
        
        # Initialize components
        self.normalizer = CPMNormalizer()
        self.semantic_screener = SemanticScreener(threshold=self.config.similarity_threshold)
        self.entity_validator = EntityValidator(threshold=self.config.entity_overlap_threshold)
        self.sparql_validator = SPARQLValidator()
        self.smt_verifier = SMTVerifier(timeout_ms=self.config.smt_timeout_ms)
        self.resolver = ConflictResolver(self.smt_verifier)
        
        # Code generators
        self.rego_generator = RegoGenerator()
        self.xacml_generator = XACMLGenerator()
        self.test_generator = TestCaseGenerator()
    
    def run(self, raw_policies: List[Dict], 
            frameworks: Optional[Dict[str, str]] = None) -> Dict:
        """
        Execute the complete three-stage pipeline.
        
        Args:
            raw_policies: List of policy dictionaries
            frameworks: Optional mapping of rule_id to framework name
            
        Returns:
            Pipeline results including resolved policies, conflicts, and metrics
        """
        print("=" * 70)
        print("POLICY CONFLICT DETECTION PIPELINE")
        print("=" * 70)
        timestamp = datetime.now().isoformat()
        print(f"Started at: {timestamp}")
        
        # ============================================
        # STAGE 1: NORMALIZATION
        # ============================================
        print("\n" + "=" * 50)
        print("STAGE 1: NORMALIZATION (Figure 2)")
        print("=" * 50)
        
        self.metrics.total_rules = len(raw_policies)
        print(f"Input: {self.metrics.total_rules} raw policies")
        
        cpm_rules = []
        for policy in raw_policies:
            rule_id = policy.get("rule_id", "unknown")
            framework = (frameworks or {}).get(rule_id, self.config.default_framework)
            cpm_rule = self.normalizer.normalize_xacml_rule(policy, framework)
            cpm_rules.append(cpm_rule)
        
        self.metrics.normalized_rules = len(cpm_rules)
        print(f"Output: {self.metrics.normalized_rules} CPM rules")
        
        for rule in cpm_rules:
            print(f"  • {rule.rule_id} [{rule.framework_origin}] P{rule.priority}: {rule.effect.value}")
        
        # ============================================
        # STAGE 2: CONFLICT DETECTION
        # ============================================
        print("\n" + "=" * 50)
        print("STAGE 2: CONFLICT DETECTION (Figure 3)")
        print("=" * 50)
        
        # Phase 1: Semantic screening
        print("\nPhase 2.1: Semantic Screening")
        print(f"  Threshold: {self.config.similarity_threshold}")
        
        semantic_candidates = self.semantic_screener.generate_candidates(cpm_rules)
        self.metrics.semantic_candidates = len(semantic_candidates)
        print(f"  Candidates: {self.metrics.semantic_candidates}")
        
        # Phase 2: Entity validation
        print("\nPhase 2.2: Entity Validation")
        print(f"  Threshold: {self.config.entity_overlap_threshold}")
        
        entity_validated = self.entity_validator.validate_candidates(semantic_candidates)
        self.metrics.entity_validated = len(entity_validated)
        print(f"  Validated: {self.metrics.entity_validated}")
        
        # Phase 3: SPARQL structural checks
        print("\nPhase 2.3: SPARQL Structural Validation")
        
        sparql_validated = self.sparql_validator.validate_structure(entity_validated)
        self.metrics.sparql_validated = len(sparql_validated)
        print(f"  Conflict candidates: {self.metrics.sparql_validated}")
        
        for sv in sparql_validated:
            print(f"  • {sv.rule_i.rule_id} <-> {sv.rule_j.rule_id}")
            print(f"    Shared: {sv.shared_resources}, Opposite: {sv.opposite_effects}")
        
        # ============================================
        # STAGE 3: VERIFICATION & RESOLUTION
        # ============================================
        print("\n" + "=" * 50)
        print("STAGE 3: SMT VERIFICATION & RESOLUTION (Figure 4 & 5)")
        print("=" * 50)
        
        # Verify conflicts with SMT
        print("\nPhase 3.1: SMT Verification")
        
        verification_results = []
        total_solve_time = 0
        
        for sv in sparql_validated:
            result = self.smt_verifier.verify_conflict(sv.rule_i, sv.rule_j)
            verification_results.append(result)
            total_solve_time += result.solve_time_ms
            
            if result.result == SMTResult.SAT:
                self.metrics.smt_sat += 1
                print(f"  SAT: {result.rule_i.rule_id} <-> {result.rule_j.rule_id}")
                if result.witness:
                    print(f"       Witness: {result.witness.action} on {result.witness.resource}")
            elif result.result == SMTResult.UNSAT:
                self.metrics.smt_unsat += 1
                print(f"  UNSAT: {result.rule_i.rule_id} <-> {result.rule_j.rule_id}")
            else:
                self.metrics.smt_unknown += 1
                print(f"  UNKNOWN: {result.rule_i.rule_id} <-> {result.rule_j.rule_id}")
        
        total_verified = self.metrics.smt_sat + self.metrics.smt_unsat
        total_checks = total_verified + self.metrics.smt_unknown
        
        self.metrics.smt_coverage = total_verified / total_checks if total_checks > 0 else 1.0
        self.metrics.avg_solve_time_ms = total_solve_time / total_checks if total_checks > 0 else 0
        
        print(f"\n  SMT Coverage: {self.metrics.smt_coverage:.1%}")
        print(f"  Avg Solve Time: {self.metrics.avg_solve_time_ms:.2f} ms")
        
        # Resolve conflicts
        print("\nPhase 3.2: Conflict Resolution")
        
        resolutions = []
        for result in verification_results:
            if result.is_conflict():
                resolution = self.resolver.resolve(result)
                if resolution:
                    resolutions.append(resolution)
                    self.metrics.conflicts_resolved += 1
                    if resolution["verified"]:
                        self.metrics.resolutions_verified += 1
                    print(f"  Resolved: {result.rule_i.rule_id} vs {result.rule_j.rule_id}")
                    print(f"    Strategy: {resolution['strategy']}")
                    print(f"    Winner: {resolution['winner'].rule_id}")
                    print(f"    Verified: {resolution['verified']}")
        
        # Generate policy-as-code
        print("\nPhase 3.3: Policy-as-Code Generation")
        
        if self.config.output_format == "rego":
            policy_code = self.rego_generator.generate(cpm_rules)
            print(f"  Generated: Rego policy ({len(policy_code)} chars)")
        else:
            policy_code = self.xacml_generator.generate(cpm_rules)
            print(f"  Generated: XACML policy ({len(policy_code)} chars)")
        
        # Generate test cases from witnesses
        witnesses = [r.witness.to_dict() for r in verification_results 
                    if r.is_conflict() and r.witness]
        test_cases = [self.test_generator.generate_json_test_case(w) for w in witnesses]
        print(f"  Generated: {len(test_cases)} test cases from witnesses")
        
        # ============================================
        # SUMMARY
        # ============================================
        print("\n" + "=" * 50)
        print("PIPELINE SUMMARY")
        print("=" * 50)
        
        print(f"\n  Stage 1 (Normalization):")
        print(f"    Rules processed: {self.metrics.normalized_rules}")
        
        print(f"\n  Stage 2 (Detection):")
        print(f"    Semantic candidates: {self.metrics.semantic_candidates}")
        print(f"    Entity validated: {self.metrics.entity_validated}")
        print(f"    SPARQL validated: {self.metrics.sparql_validated}")
        
        print(f"\n  Stage 3 (Verification):")
        print(f"    Conflicts (SAT): {self.metrics.smt_sat}")
        print(f"    No conflict (UNSAT): {self.metrics.smt_unsat}")
        print(f"    SMT Coverage: {self.metrics.smt_coverage:.1%}")
        
        print(f"\n  Resolution:")
        print(f"    Resolved: {self.metrics.conflicts_resolved}")
        print(f"    Verified: {self.metrics.resolutions_verified}")
        
        return {
            "timestamp": timestamp,
            "config": {
                "similarity_threshold": self.config.similarity_threshold,
                "entity_threshold": self.config.entity_overlap_threshold,
                "smt_timeout_ms": self.config.smt_timeout_ms,
            },
            "metrics": self.metrics.to_dict(),
            "cpm_rules": [r.to_dict() for r in cpm_rules],
            "conflicts": [
                {
                    "rule_i": r.rule_i.rule_id,
                    "rule_j": r.rule_j.rule_id,
                    "result": r.result.value,
                    "conflict_type": r.conflict_type.value if r.conflict_type else None,
                    "witness": r.witness.to_dict() if r.witness else None,
                }
                for r in verification_results if r.is_conflict()
            ],
            "resolutions": resolutions,
            "policy_code": policy_code,
            "test_cases": test_cases,
        }


# ============================================================
# DEMONSTRATION: Figure 1 - Complete Pipeline
# ============================================================

def demonstrate_complete_pipeline():
    """
    Demonstrates the complete three-stage pipeline.
    """
    print("\n" + "=" * 70)
    print("FIGURE 1: COMPLETE PIPELINE DEMONSTRATION")
    print("=" * 70)
    
    # Sample heterogeneous policies from different frameworks
    heterogeneous_policies = [
        # PSD2 Rules
        {
            "rule_id": "PSD2_SCA_001",
            "subject": {"type": "customer", "roles": ["account_holder"]},
            "action": "initiate",
            "resource": {"type": "payment_transaction", "identifiers": ["payment_api"]},
            "environment": {"sca_verified": True, "amount_below_30": True},
            "effect": "Permit",
        },
        {
            "rule_id": "PSD2_ACCESS_001",
            "subject": {"type": "tpp", "roles": ["third_party_provider"]},
            "action": "read",
            "resource": {"type": "account_data", "identifiers": ["account_info_api"]},
            "environment": {"consent_valid": True},
            "effect": "Permit",
        },
        
        # NIST CSF Rules
        {
            "rule_id": "NIST_AC_001",
            "subject": {"type": "administrator", "roles": ["admin"]},
            "action": "modify",
            "resource": {"type": "system_config", "identifiers": ["firewall_config"]},
            "environment": {"mfa_verified": True},
            "effect": "Permit",
        },
        
        # Internal Security Rules (may conflict)
        {
            "rule_id": "INT_SEC_001",
            "subject": {"type": "user", "roles": ["customer"]},
            "action": "write",
            "resource": {"type": "transaction", "identifiers": ["payment_api"]},
            "environment": {},
            "effect": "Deny",  # Potential conflict with PSD2_SCA_001
        },
        {
            "rule_id": "INT_SEC_002",
            "subject": {"type": "admin", "roles": ["admin"]},
            "action": "update",
            "resource": {"type": "config", "identifiers": ["firewall_config"]},
            "environment": {"business_hours": True},
            "effect": "Deny",  # Potential conflict with NIST_AC_001
        },
        
        # Break-glass emergency rule
        {
            "rule_id": "BG_001",
            "subject": {"type": "operator", "roles": ["incident_responder"]},
            "action": "execute",
            "resource": {"type": "emergency_action", "identifiers": ["break_glass_api"]},
            "environment": {"incident_declared": True},
            "effect": "Permit",
            "obligations": ["require_audit_log", "require_justification"],
        },
    ]
    
    # Framework mappings
    framework_mappings = {
        "PSD2_SCA_001": "PSD2",
        "PSD2_ACCESS_001": "PSD2",
        "NIST_AC_001": "NIST_CSF",
        "INT_SEC_001": "INTERNAL_SECURITY",
        "INT_SEC_002": "INTERNAL_SECURITY",
        "BG_001": "BREAK_GLASS",
    }
    
    # Create pipeline with custom config
    config = PipelineConfig(
        similarity_threshold=0.50,  # Lower for demo
        entity_overlap_threshold=0.30,  # Lower for demo
        smt_timeout_ms=10000,
        output_format="rego"
    )
    
    pipeline = ConflictDetectionPipeline(config)
    
    # Run pipeline
    results = pipeline.run(heterogeneous_policies, framework_mappings)
    
    # Save results
    print("\n" + "=" * 50)
    print("OUTPUT FILES")
    print("=" * 50)
    
    # Print sample outputs
    print("\nGenerated Rego Policy (first 1000 chars):")
    print("-" * 40)
    print(results["policy_code"][:1000] + "...\n")
    
    if results["test_cases"]:
        print("\nGenerated Test Cases:")
        print("-" * 40)
        for tc in results["test_cases"][:2]:
            print(json.dumps(tc, indent=2))
    
    return results


if __name__ == "__main__":
    demonstrate_complete_pipeline()
