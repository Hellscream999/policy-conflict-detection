"""
Semantic Screening - Figure 3 (Phase 1)
========================================
BERT-based semantic similarity for candidate generation.
"""

import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from sentence_transformers import SentenceTransformer
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    print("Warning: sentence-transformers not available, using fallback")

from models.cpm import CPMRule, Effect


@dataclass
class CandidatePair:
    """A candidate conflict pair with similarity score"""
    rule_i: CPMRule
    rule_j: CPMRule
    similarity: float
    
    def __repr__(self):
        return f"CandidatePair({self.rule_i.rule_id} <-> {self.rule_j.rule_id}, sim={self.similarity:.3f})"


class SemanticScreener:
    """
    Phase 1 of conflict detection pipeline (Figure 3).
    Uses BERT embeddings to identify semantically similar rule pairs.
    """
    
    DEFAULT_THRESHOLD = 0.65  # As specified in paper Section III-C
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", threshold: float = None):
        """
        Initialize with sentence transformer model.
        
        Args:
            model_name: Sentence transformer model name
            threshold: Similarity threshold (default: 0.65 from paper)
        """
        self.threshold = threshold or self.DEFAULT_THRESHOLD
        
        if TRANSFORMERS_AVAILABLE:
            self.model = SentenceTransformer(model_name)
            self.use_transformers = True
        else:
            self.model = None
            self.use_transformers = False
    
    def _compute_embeddings(self, summaries: List[str]) -> np.ndarray:
        """Compute BERT embeddings for rule summaries"""
        if self.use_transformers:
            return self.model.encode(summaries, convert_to_numpy=True)
        else:
            # Fallback: TF-IDF-like word overlap (for demo without transformers)
            return self._fallback_embeddings(summaries)
    
    def _fallback_embeddings(self, summaries: List[str]) -> np.ndarray:
        """Simple word-overlap based similarity for fallback"""
        # Build vocabulary
        vocab = set()
        for s in summaries:
            vocab.update(s.lower().split())
        vocab = sorted(vocab)
        word_to_idx = {w: i for i, w in enumerate(vocab)}
        
        # Create TF vectors
        embeddings = np.zeros((len(summaries), len(vocab)))
        for i, s in enumerate(summaries):
            words = s.lower().split()
            for w in words:
                embeddings[i, word_to_idx[w]] += 1
            # Normalize
            norm = np.linalg.norm(embeddings[i])
            if norm > 0:
                embeddings[i] /= norm
        
        return embeddings
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors"""
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
    
    def generate_candidates(self, rules: List[CPMRule]) -> List[CandidatePair]:
        """
        Generate candidate conflict pairs using semantic similarity.
        
        Algorithm (from paper Section III-C):
        1. Generate textual summary for each rule
        2. Compute BERT embeddings
        3. Calculate pairwise cosine similarity
        4. Return pairs above threshold WITH OPPOSITE EFFECTS (actual conflicts)
        
        Args:
            rules: List of CPM rules
            
        Returns:
            List of candidate pairs with similarity >= threshold and opposite effects
        """
        if len(rules) < 2:
            return []
        
        # Step 1: Generate summaries
        summaries = [rule.to_summary() for rule in rules]
        
        # Step 2: Compute embeddings
        embeddings = self._compute_embeddings(summaries)
        
        # Step 3 & 4: Pairwise similarity and filtering
        # Only consider pairs with OPPOSITE EFFECTS (Permit vs Deny)
        candidates = []
        for i in range(len(rules)):
            for j in range(i + 1, len(rules)):
                # CRITICAL: Only consider actual conflict pairs (Permit vs Deny)
                if rules[i].effect == rules[j].effect:
                    continue  # Skip same-effect pairs - they cannot conflict
                
                sim = self._cosine_similarity(embeddings[i], embeddings[j])
                
                if sim >= self.threshold:
                    candidates.append(CandidatePair(
                        rule_i=rules[i],
                        rule_j=rules[j],
                        similarity=sim
                    ))
        
        # Sort by similarity (descending)
        candidates.sort(key=lambda x: x.similarity, reverse=True)
        
        return candidates

    
    def compute_similarity_matrix(self, rules: List[CPMRule]) -> np.ndarray:
        """Compute full similarity matrix for visualization"""
        summaries = [rule.to_summary() for rule in rules]
        embeddings = self._compute_embeddings(summaries)
        
        n = len(rules)
        matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                matrix[i, j] = self._cosine_similarity(embeddings[i], embeddings[j])
        
        return matrix


# ============================================================
# DEMONSTRATION: Figure 3 - Semantic Screening
# ============================================================

def demonstrate_semantic_screening():
    """
    Demonstrates semantic similarity-based candidate generation.
    """
    from models.cpm import CPMNormalizer, Subject, Resource, Environment, Effect
    
    print("=" * 70)
    print("FIGURE 3 (Phase 1): Semantic Screening Demonstration")
    print("=" * 70)
    
    # Create sample rules with varying similarity
    normalizer = CPMNormalizer()
    
    sample_rules = [
        # Group 1: Payment-related rules (should be similar)
        {
            "rule_id": "PSD2_PAY_001",
            "subject": {"type": "customer", "roles": ["account_holder"]},
            "action": "initiate",
            "resource": {"type": "payment_transaction", "identifiers": ["payments_api"]},
            "environment": {"requires_sca": True},
            "effect": "Permit",
        },
        {
            "rule_id": "INTERNAL_PAY_001",
            "subject": {"type": "user", "roles": ["customer"]},
            "action": "create",
            "resource": {"type": "financial_transfer", "identifiers": ["transfer_api"]},
            "environment": {"max_amount": 1000},
            "effect": "Deny",  # Potential conflict!
        },
        
        # Group 2: Admin access rules (should be similar)
        {
            "rule_id": "NIST_ADMIN_001",
            "subject": {"type": "administrator", "roles": ["admin"]},
            "action": "modify",
            "resource": {"type": "system_config", "identifiers": ["config_api"]},
            "environment": {"mfa_verified": True},
            "effect": "Permit",
        },
        {
            "rule_id": "ISO_ADMIN_001",
            "subject": {"type": "privileged_user", "roles": ["superuser"]},
            "action": "update",
            "resource": {"type": "configuration", "identifiers": ["settings_api"]},
            "environment": {"location": "internal"},
            "effect": "Deny",  # Potential conflict!
        },
        
        # Group 3: Unrelated rule
        {
            "rule_id": "GDPR_DATA_001",
            "subject": {"type": "data_processor", "roles": ["processor"]},
            "action": "export",
            "resource": {"type": "personal_data", "identifiers": ["export_api"]},
            "environment": {"consent_valid": True},
            "effect": "Permit",
        },
    ]
    
    # Normalize rules
    cpm_rules = normalizer.normalize_batch(sample_rules, "MIXED")
    
    print("\n1. Input Rules and Summaries:")
    print("-" * 50)
    for rule in cpm_rules:
        print(f"  {rule.rule_id}: {rule.to_summary()}")
    
    # Create screener with different thresholds
    print("\n2. Semantic Similarity Matrix:")
    print("-" * 50)
    
    screener = SemanticScreener(threshold=0.65)
    sim_matrix = screener.compute_similarity_matrix(cpm_rules)
    
    # Print matrix
    rule_ids = [r.rule_id for r in cpm_rules]
    print(f"{'':>20}", end="")
    for rid in rule_ids:
        print(f"{rid[:15]:>16}", end="")
    print()
    
    for i, rid in enumerate(rule_ids):
        print(f"{rid[:20]:>20}", end="")
        for j in range(len(rule_ids)):
            val = sim_matrix[i, j]
            marker = "*" if val >= 0.65 and i != j else " "
            print(f"{val:>15.3f}{marker}", end="")
        print()
    
    print("\n  * = Above threshold (0.65)")
    
    # Generate candidates
    print(f"\n3. Generated Candidates (threshold={screener.threshold}):")
    print("-" * 50)
    
    candidates = screener.generate_candidates(cpm_rules)
    
    if candidates:
        for i, cand in enumerate(candidates, 1):
            effect_match = "⚠️ CONFLICT" if cand.rule_i.effect != cand.rule_j.effect else "✓ Same effect"
            print(f"  {i}. {cand.rule_i.rule_id} <-> {cand.rule_j.rule_id}")
            print(f"     Similarity: {cand.similarity:.3f}")
            print(f"     Effects: {cand.rule_i.effect.value} vs {cand.rule_j.effect.value} {effect_match}")
            print()
    else:
        print("  No candidates above threshold")
    
    # Show threshold sensitivity
    print("\n4. Threshold Sensitivity Analysis:")
    print("-" * 50)
    
    for threshold in [0.5, 0.55, 0.6, 0.65, 0.7, 0.75]:
        screener.threshold = threshold
        candidates = screener.generate_candidates(cpm_rules)
        conflict_candidates = [c for c in candidates if c.rule_i.effect != c.rule_j.effect]
        print(f"  Threshold {threshold:.2f}: {len(candidates)} candidates, {len(conflict_candidates)} with opposite effects")
    
    return candidates


if __name__ == "__main__":
    demonstrate_semantic_screening()
