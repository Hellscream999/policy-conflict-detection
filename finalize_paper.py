"""
finalize_paper.py
=================
Once prove_paper_v2.py has produced results_v2/, this script:
  1. Generates the 6 figures into results_v2/figures/
  2. Builds the IEEE Software .docx into paper/

Run after: python prove_paper_v2.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

from figures_v2 import main as build_figures
from build_paper_v2 import build_docx, PAPER_DIR


if __name__ == "__main__":
    print("[1/2] Generating figures ...")
    build_figures()
    print("[2/2] Building IEEE Software .docx ...")
    build_docx(PAPER_DIR)
    print("\nDone.")
