"""
Dataset Evaluation Script
==========================
Tests the conflict detection pipeline on public XACML datasets.
"""

import os
import sys
import json
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass, asdict

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from parsers.xacml_parser import parse_xacml_file, XACML3Parser
from models.cpm import CPMRule, Effect
from detection.semantic_screener import SemanticScreener
from detection.entity_validator import EntityValidator
from detection.sparql_validator import SPARQLValidator
from verification.smt_verifier import SMTVerifier, SMTResult


@dataclass
class DatasetMetrics:
    """Metrics for a single dataset evaluation"""
    dataset_name: str
    file_path: str
    
    # Parsing
    total_rules: int = 0
    permit_rules: int = 0
    deny_rules: int = 0
    
    # Detection
    rule_pairs: int = 0
    semantic_candidates: int = 0
    entity_validated: int = 0
    sparql_validated: int = 0
    
    # Verification
    smt_sat: int = 0
    smt_unsat: int = 0
    smt_unknown: int = 0
    total_conflicts: int = 0
    
    # Timing
    parse_time_ms: float = 0.0
    detection_time_ms: float = 0.0
    verification_time_ms: float = 0.0
    total_time_ms: float = 0.0


def evaluate_dataset(filepath: str, dataset_name: str, 
                     similarity_threshold: float = 0.50,
                     entity_threshold: float = 0.30) -> DatasetMetrics:
    """
    Evaluate a single dataset through the conflict detection pipeline.
    """
    import time
    
    metrics = DatasetMetrics(dataset_name=dataset_name, file_path=filepath)
    start_total = time.time()
    
    # ========================================
    # STAGE 1: Parse XACML
    # ========================================
    start_parse = time.time()
    
    xacml_rules, cpm_rules = parse_xacml_file(filepath, dataset_name)
    
    metrics.total_rules = len(cpm_rules)
    metrics.permit_rules = sum(1 for r in cpm_rules if r.effect == Effect.PERMIT)
    metrics.deny_rules = sum(1 for r in cpm_rules if r.effect == Effect.DENY)
    metrics.parse_time_ms = (time.time() - start_parse) * 1000
    
    if metrics.total_rules < 2:
        print(f"  Warning: Only {metrics.total_rules} rules found, skipping detection")
        return metrics
    
    # Total possible pairs
    n = metrics.total_rules
    metrics.rule_pairs = n * (n - 1) // 2
    
    # ========================================
    # STAGE 2: Detection Pipeline
    # ========================================
    start_detection = time.time()
    
    # Phase 1: Semantic screening
    screener = SemanticScreener(threshold=similarity_threshold)
    semantic_candidates = screener.generate_candidates(cpm_rules)
    metrics.semantic_candidates = len(semantic_candidates)
    
    # Phase 2: Entity validation
    entity_validator = EntityValidator(threshold=entity_threshold)
    entity_validated = entity_validator.validate_candidates(semantic_candidates)
    metrics.entity_validated = len(entity_validated)
    
    # Phase 3: SPARQL validation
    sparql_validator = SPARQLValidator()
    sparql_validated = sparql_validator.validate_structure(entity_validated)
    metrics.sparql_validated = len(sparql_validated)
    
    metrics.detection_time_ms = (time.time() - start_detection) * 1000
    
    # ========================================
    # STAGE 3: SMT Verification
    # ========================================
    start_verification = time.time()
    
    verifier = SMTVerifier(timeout_ms=10000)
    
    for candidate in sparql_validated:
        result = verifier.verify_conflict(candidate.rule_i, candidate.rule_j)
        
        if result.result == SMTResult.SAT:
            metrics.smt_sat += 1
        elif result.result == SMTResult.UNSAT:
            metrics.smt_unsat += 1
        else:
            metrics.smt_unknown += 1
    
    metrics.total_conflicts = metrics.smt_sat
    metrics.verification_time_ms = (time.time() - start_verification) * 1000
    
    metrics.total_time_ms = (time.time() - start_total) * 1000
    
    return metrics


def format_metrics_table(all_metrics: List[DatasetMetrics]) -> str:
    """Format metrics as a table"""
    lines = []
    lines.append("=" * 100)
    lines.append(f"{'Dataset':<15} {'Rules':>8} {'P/D':>8} {'Pairs':>8} {'Sem':>8} {'Ent':>8} {'SPARQL':>8} {'Conflicts':>10} {'Time(ms)':>10}")
    lines.append("=" * 100)
    
    for m in all_metrics:
        pd_ratio = f"{m.permit_rules}/{m.deny_rules}"
        lines.append(
            f"{m.dataset_name:<15} {m.total_rules:>8} {pd_ratio:>8} {m.rule_pairs:>8} "
            f"{m.semantic_candidates:>8} {m.entity_validated:>8} {m.sparql_validated:>8} "
            f"{m.total_conflicts:>10} {m.total_time_ms:>10.1f}"
        )
    
    lines.append("=" * 100)
    
    # Totals
    total_rules = sum(m.total_rules for m in all_metrics)
    total_conflicts = sum(m.total_conflicts for m in all_metrics)
    total_time = sum(m.total_time_ms for m in all_metrics)
    
    lines.append(f"{'TOTAL':<15} {total_rules:>8} {'':<8} {'':<8} "
                 f"{'':<8} {'':<8} {'':<8} {total_conflicts:>10} {total_time:>10.1f}")
    
    return "\n".join(lines)


def run_evaluation():
    """Run evaluation on all XACML datasets"""
    print("=" * 80)
    print("XACML DATASET EVALUATION")
    print("Testing Conflict Detection Pipeline on Public Datasets")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Dataset paths - relative to magnetic-planck folder
    base_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "magnetic-planck", "test-data", "XACs-DyPol-master", "data"
    )
    
    datasets = [
        ("GEYSERS", "GEYSERS.xml"),
        ("Continue-A", "continue-a-xacml3.xml"),
        ("KMarket", "KMarket.xml"),
        ("Synthetic360", "synthetic360.xml"),
    ]
    
    # Check which datasets exist
    available_datasets = []
    print("\nDataset Discovery:")
    print("-" * 50)
    
    for name, filename in datasets:
        filepath = os.path.join(base_path, filename)
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            print(f"  [OK] {name}: {filepath} ({size:,} bytes)")
            available_datasets.append((name, filepath))
        else:
            print(f"  [NOT FOUND] {name}: {filepath}")
    
    if not available_datasets:
        print("\nNo datasets found! Please check the base path:")
        print(f"  {base_path}")
        return None
    
    # Evaluate each dataset
    print("\n" + "=" * 80)
    print("RUNNING EVALUATION")
    print("=" * 80)
    
    all_metrics = []
    
    for name, filepath in available_datasets:
        print(f"\n[{name}]")
        print("-" * 40)
        
        try:
            metrics = evaluate_dataset(filepath, name)
            all_metrics.append(metrics)
            
            print(f"  Rules: {metrics.total_rules} (Permit: {metrics.permit_rules}, Deny: {metrics.deny_rules})")
            print(f"  Pairs analyzed: {metrics.rule_pairs}")
            print(f"  Semantic candidates: {metrics.semantic_candidates}")
            print(f"  Entity validated: {metrics.entity_validated}")
            print(f"  SPARQL validated: {metrics.sparql_validated}")
            print(f"  SMT Results: SAT={metrics.smt_sat}, UNSAT={metrics.smt_unsat}")
            print(f"  Conflicts detected: {metrics.total_conflicts}")
            print(f"  Time: {metrics.total_time_ms:.1f} ms")
            
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary table
    print("\n" + "=" * 80)
    print("EVALUATION SUMMARY")
    print("=" * 80)
    print(format_metrics_table(all_metrics))
    
    # Detailed statistics
    print("\n" + "=" * 80)
    print("DETECTION STATISTICS")
    print("=" * 80)
    
    total_rules = sum(m.total_rules for m in all_metrics)
    total_pairs = sum(m.rule_pairs for m in all_metrics)
    total_semantic = sum(m.semantic_candidates for m in all_metrics)
    total_entity = sum(m.entity_validated for m in all_metrics)
    total_sparql = sum(m.sparql_validated for m in all_metrics)
    total_conflicts = sum(m.total_conflicts for m in all_metrics)
    
    print(f"\n  Total Rules Analyzed: {total_rules}")
    print(f"  Total Rule Pairs: {total_pairs}")
    print(f"\n  Pipeline Reduction:")
    print(f"    Semantic Screening: {total_pairs} -> {total_semantic} ({(1-total_semantic/max(total_pairs,1))*100:.1f}% reduction)")
    print(f"    Entity Validation: {total_semantic} -> {total_entity} ({(1-total_entity/max(total_semantic,1))*100:.1f}% reduction)")
    print(f"    SPARQL Validation: {total_entity} -> {total_sparql} ({(1-total_sparql/max(total_entity,1))*100:.1f}% reduction)")
    print(f"    SMT Verification: {total_sparql} -> {total_conflicts} conflicts confirmed")
    
    if total_pairs > 0:
        print(f"\n  Overall Reduction: {total_pairs} pairs -> {total_conflicts} conflicts")
        print(f"  Conflict Rate: {total_conflicts/total_pairs*100:.2f}%")
    
    # Save results
    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
    os.makedirs(results_dir, exist_ok=True)
    
    results_file = os.path.join(results_dir, f'evaluation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "datasets": [asdict(m) for m in all_metrics],
        "summary": {
            "total_rules": total_rules,
            "total_pairs": total_pairs,
            "total_conflicts": total_conflicts,
            "conflict_rate": total_conflicts/max(total_pairs,1),
        }
    }
    
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n  Results saved to: {results_file}")
    
    return all_metrics


if __name__ == "__main__":
    run_evaluation()
