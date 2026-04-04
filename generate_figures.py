"""
Visualization Scripts for Paper Figures
=========================================
Generates figures to prove the paper's methodology.
"""

import os
import sys
import json
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

# Try importing visualization libraries
try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not available. Install with: pip install matplotlib")


def create_dataset_comparison_figure(results_file: str = None):
    """
    Creates Figure: Dataset Comparison Bar Chart
    Shows rules, conflicts, and detection rates per dataset.
    """
    if not MATPLOTLIB_AVAILABLE:
        print("matplotlib required for visualization")
        return
    
    # Data from evaluation results
    datasets = ['GEYSERS', 'Continue-A', 'KMarket', 'Synthetic360']
    rules = [15, 298, 5, 360]
    conflicts = [0, 14280, 1, 32399]
    permit = [15, 238, 1, 179]
    deny = [0, 60, 4, 181]
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    # Plot 1: Rules per dataset
    ax1 = axes[0]
    x = range(len(datasets))
    width = 0.35
    bars1 = ax1.bar([i - width/2 for i in x], permit, width, label='Permit', color='#2ecc71')
    bars2 = ax1.bar([i + width/2 for i in x], deny, width, label='Deny', color='#e74c3c')
    ax1.set_xlabel('Dataset')
    ax1.set_ylabel('Number of Rules')
    ax1.set_title('(a) Rule Distribution by Effect')
    ax1.set_xticks(x)
    ax1.set_xticklabels(datasets, rotation=15)
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3)
    
    # Plot 2: Conflicts detected
    ax2 = axes[1]
    colors = ['#3498db', '#e74c3c', '#2ecc71', '#9b59b6']
    bars = ax2.bar(datasets, conflicts, color=colors)
    ax2.set_xlabel('Dataset')
    ax2.set_ylabel('Conflicts Detected')
    ax2.set_title('(b) Conflicts Detected by SMT Verification')
    ax2.set_xticklabels(datasets, rotation=15)
    ax2.grid(axis='y', alpha=0.3)
    
    # Add value labels
    for bar, val in zip(bars, conflicts):
        if val > 0:
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 500, 
                    f'{val:,}', ha='center', va='bottom', fontsize=9)
    
    # Plot 3: Conflict rate
    ax3 = axes[2]
    pairs = [105, 44253, 10, 64620]
    conflict_rates = [c/p*100 if p > 0 else 0 for c, p in zip(conflicts, pairs)]
    bars = ax3.bar(datasets, conflict_rates, color=colors)
    ax3.set_xlabel('Dataset')
    ax3.set_ylabel('Conflict Rate (%)')
    ax3.set_title('(c) Conflict Rate per Dataset')
    ax3.set_xticklabels(datasets, rotation=15)
    ax3.grid(axis='y', alpha=0.3)
    ax3.set_ylim(0, 100)
    
    # Add percentage labels
    for bar, val in zip(bars, conflict_rates):
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2, 
                f'{val:.1f}%', ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    
    # Save figure
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'figures')
    os.makedirs(output_dir, exist_ok=True)
    
    filepath = os.path.join(output_dir, 'dataset_comparison.png')
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    print(f"Saved: {filepath}")
    
    plt.close()
    return filepath


def create_pipeline_reduction_figure():
    """
    Creates Figure: Pipeline Reduction Funnel
    Shows how each stage reduces candidate pairs.
    """
    if not MATPLOTLIB_AVAILABLE:
        print("matplotlib required for visualization")
        return
    
    # Data from evaluation
    stages = ['Rule Pairs\n(108,988)', 
              'Semantic\nScreening\n(108,940)', 
              'Entity\nValidation\n(108,939)',
              'SPARQL\nValidation\n(46,680)',
              'SMT Verified\nConflicts\n(46,680)']
    values = [108988, 108940, 108939, 46680, 46680]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Create funnel-like horizontal bar chart
    colors = ['#3498db', '#2ecc71', '#f39c12', '#e74c3c', '#9b59b6']
    y_pos = range(len(stages))
    
    # Calculate relative widths for funnel effect
    max_val = max(values)
    widths = [v/max_val for v in values]
    
    for i, (stage, val, width, color) in enumerate(zip(stages, values, widths, colors)):
        # Center the bars
        left = (1 - width) / 2
        ax.barh(i, width, left=left, height=0.6, color=color, alpha=0.8)
        ax.text(0.5, i, f'{val:,}', ha='center', va='center', 
                fontsize=12, fontweight='bold', color='white')
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(stages)
    ax.set_xlim(0, 1)
    ax.set_xlabel('Relative Scale')
    ax.set_title('Pipeline Reduction: From Rule Pairs to Verified Conflicts', fontsize=14)
    ax.invert_yaxis()
    ax.set_xticks([])
    
    # Add reduction percentages
    reductions = ['', '0.04%', '0.00%', '57.2%', '0%']
    for i, red in enumerate(reductions):
        if red:
            ax.text(1.02, i, f'-{red}', va='center', fontsize=10, color='gray')
    
    ax.text(1.02, -0.5, 'Reduction', va='center', fontsize=10, fontweight='bold', color='gray')
    
    plt.tight_layout()
    
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'figures')
    os.makedirs(output_dir, exist_ok=True)
    
    filepath = os.path.join(output_dir, 'pipeline_reduction.png')
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    print(f"Saved: {filepath}")
    
    plt.close()
    return filepath


def create_similarity_matrix_figure():
    """
    Creates Figure: Semantic Similarity Matrix Heatmap
    Shows BERT embedding similarities between sample rules.
    """
    if not MATPLOTLIB_AVAILABLE:
        print("matplotlib required for visualization")
        return
    
    from models.cpm import CPMNormalizer
    from detection.semantic_screener import SemanticScreener
    
    # Sample rules for visualization
    normalizer = CPMNormalizer()
    sample_rules = [
        {"rule_id": "PSD2_001", "subject": {"type": "customer", "roles": ["user"]},
         "action": "read", "resource": {"type": "account_data", "identifiers": ["api"]},
         "environment": {}, "effect": "Permit"},
        {"rule_id": "PSD2_002", "subject": {"type": "customer", "roles": ["user"]},
         "action": "initiate", "resource": {"type": "transaction", "identifiers": ["pay"]},
         "environment": {}, "effect": "Permit"},
        {"rule_id": "NIST_001", "subject": {"type": "admin", "roles": ["admin"]},
         "action": "modify", "resource": {"type": "config", "identifiers": ["fw"]},
         "environment": {}, "effect": "Permit"},
        {"rule_id": "NIST_002", "subject": {"type": "admin", "roles": ["admin"]},
         "action": "read", "resource": {"type": "logs", "identifiers": ["audit"]},
         "environment": {}, "effect": "Permit"},
        {"rule_id": "INT_001", "subject": {"type": "user", "roles": ["customer"]},
         "action": "view", "resource": {"type": "account_data", "identifiers": ["api"]},
         "environment": {}, "effect": "Deny"},
    ]
    
    cpm_rules = normalizer.normalize_batch(sample_rules, "MIXED")
    
    # Generate similarity matrix
    screener = SemanticScreener(threshold=0.5)
    matrix = screener.compute_similarity_matrix(cpm_rules)
    
    # Plot
    fig, ax = plt.subplots(figsize=(8, 6))
    
    import numpy as np
    labels = [r.rule_id for r in cpm_rules]
    
    im = ax.imshow(matrix, cmap='RdYlGn', aspect='auto', vmin=0, vmax=1)
    
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha='right')
    ax.set_yticklabels(labels)
    
    # Add colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('Cosine Similarity')
    
    # Add values in cells
    for i in range(len(labels)):
        for j in range(len(labels)):
            text = ax.text(j, i, f'{matrix[i][j]:.2f}',
                          ha='center', va='center', color='black', fontsize=9)
    
    ax.set_title('Semantic Similarity Matrix (BERT Embeddings)', fontsize=12)
    ax.set_xlabel('Rule ID')
    ax.set_ylabel('Rule ID')
    
    # Mark threshold
    ax.axhline(y=-0.5, color='red', linestyle='--', alpha=0)  # placeholder
    
    plt.tight_layout()
    
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'figures')
    os.makedirs(output_dir, exist_ok=True)
    
    filepath = os.path.join(output_dir, 'similarity_matrix.png')
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    print(f"Saved: {filepath}")
    
    plt.close()
    return filepath


def create_smt_coverage_figure():
    """
    Creates Figure: SMT Verification Coverage
    Pie chart showing SAT/UNSAT/UNKNOWN distribution.
    """
    if not MATPLOTLIB_AVAILABLE:
        print("matplotlib required for visualization")
        return
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # Overall SMT results
    ax1 = axes[0]
    labels = ['SAT (Conflicts)', 'UNSAT (Compatible)']
    sizes = [46680, 0]  # From evaluation
    colors = ['#e74c3c', '#2ecc71']
    explode = (0.05, 0)
    
    ax1.pie(sizes if sum(sizes) > 0 else [1, 0], explode=explode, labels=labels, colors=colors,
            autopct=lambda p: f'{p:.1f}%' if p > 0 else '', startangle=90)
    ax1.set_title('SMT Verification Results\n(All Datasets)')
    
    # Per-dataset breakdown
    ax2 = axes[1]
    datasets = ['GEYSERS', 'Continue-A', 'KMarket', 'Synthetic360']
    sat = [0, 14280, 1, 32399]
    unsat = [0, 0, 0, 0]
    
    x = range(len(datasets))
    width = 0.35
    
    bars1 = ax2.bar([i - width/2 for i in x], sat, width, label='SAT (Conflicts)', color='#e74c3c')
    bars2 = ax2.bar([i + width/2 for i in x], unsat, width, label='UNSAT (Compatible)', color='#2ecc71')
    
    ax2.set_xlabel('Dataset')
    ax2.set_ylabel('Count')
    ax2.set_title('SMT Results by Dataset')
    ax2.set_xticks(x)
    ax2.set_xticklabels(datasets, rotation=15)
    ax2.legend()
    ax2.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'figures')
    os.makedirs(output_dir, exist_ok=True)
    
    filepath = os.path.join(output_dir, 'smt_coverage.png')
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    print(f"Saved: {filepath}")
    
    plt.close()
    return filepath


def create_timing_performance_figure():
    """
    Creates Figure: Timing Performance
    Shows processing time per dataset.
    """
    if not MATPLOTLIB_AVAILABLE:
        print("matplotlib required for visualization")
        return
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # Processing time per dataset
    ax1 = axes[0]
    datasets = ['GEYSERS', 'Continue-A', 'KMarket', 'Synthetic360']
    times_sec = [4.7, 6.7, 3.9, 8.0]
    rules = [15, 298, 5, 360]
    
    colors = ['#3498db', '#e74c3c', '#2ecc71', '#9b59b6']
    bars = ax1.bar(datasets, times_sec, color=colors)
    
    ax1.set_xlabel('Dataset')
    ax1.set_ylabel('Processing Time (seconds)')
    ax1.set_title('(a) Total Processing Time per Dataset')
    ax1.set_xticklabels(datasets, rotation=15)
    ax1.grid(axis='y', alpha=0.3)
    
    # Time per rule pair
    ax2 = axes[1]
    pairs = [105, 44253, 10, 64620]
    time_per_pair = [t*1000/p for t, p in zip(times_sec, pairs)]  # ms per pair
    
    bars = ax2.bar(datasets, time_per_pair, color=colors)
    ax2.set_xlabel('Dataset')
    ax2.set_ylabel('Time per Rule Pair (ms)')
    ax2.set_title('(b) Processing Efficiency')
    ax2.set_xticklabels(datasets, rotation=15)
    ax2.grid(axis='y', alpha=0.3)
    
    # Add value labels
    for bar, val in zip(bars, time_per_pair):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01, 
                f'{val:.2f}', ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'figures')
    os.makedirs(output_dir, exist_ok=True)
    
    filepath = os.path.join(output_dir, 'timing_performance.png')
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    print(f"Saved: {filepath}")
    
    plt.close()
    return filepath


def generate_all_figures():
    """Generate all visualization figures for the paper."""
    print("=" * 70)
    print("GENERATING PAPER FIGURES")
    print("=" * 70)
    
    if not MATPLOTLIB_AVAILABLE:
        print("\nERROR: matplotlib is required!")
        print("Install with: pip install matplotlib")
        return []
    
    figures = []
    
    print("\n1. Dataset Comparison (Rule distribution & conflicts)...")
    fig1 = create_dataset_comparison_figure()
    if fig1: figures.append(fig1)
    
    print("\n2. Pipeline Reduction Funnel...")
    fig2 = create_pipeline_reduction_figure()
    if fig2: figures.append(fig2)
    
    print("\n3. Similarity Matrix Heatmap...")
    fig3 = create_similarity_matrix_figure()
    if fig3: figures.append(fig3)
    
    print("\n4. SMT Coverage Chart...")
    fig4 = create_smt_coverage_figure()
    if fig4: figures.append(fig4)
    
    print("\n5. Timing Performance Chart...")
    fig5 = create_timing_performance_figure()
    if fig5: figures.append(fig5)
    
    print("\n" + "=" * 70)
    print("FIGURES GENERATED")
    print("=" * 70)
    print(f"\nLocation: {os.path.join(os.path.dirname(os.path.abspath(__file__)), 'figures')}")
    print(f"Total figures: {len(figures)}")
    
    for fig in figures:
        print(f"  - {os.path.basename(fig)}")
    
    return figures


if __name__ == "__main__":
    generate_all_figures()
