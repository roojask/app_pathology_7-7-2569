"""
benchmarks/scripts/text_norm_utils.py
================================================================================
Standardized Text Normalization Utilities for PathoWhisper Benchmarks
Strictly implements:
  - Criterion A (norm_a): Standard lowercasing and punctuation removal.
  - Criterion B (norm_b): Dimension & unit formatting + punctuation removal,
    matching the thesis definition in eval_clinical_core_metrics.py.
================================================================================
"""

import re

def norm_a(text: str) -> str:
    """Criterion A: Standard lowercasing and punctuation removal."""
    if not text:
        return ""
    t = str(text).lower()
    t = re.sub(r'[.,;:!?\-]', ' ', t)
    return " ".join(t.split())

def norm_b(text: str) -> str:
    """Criterion B: Dimension formatting, unit spacing, and punctuation removal."""
    if not text:
        return ""
    t = str(text).lower()
    for _ in range(2):
        t = re.sub(r"(\d)\s*(?:x|by)\s*(?=\d)", r"\1 x ", t)
    t = re.sub(r"(\d)(cm|mm|g|kg)\b", r"\1 \2", t)
    t = re.sub(r"[.,;:!?\-]", " ", t)
    return " ".join(t.split())

if __name__ == "__main__":
    test_1 = "Tumor 2.5x1.8x1.0cm, 5mm from margin."
    out_a = norm_a(test_1)
    out_b = norm_b(test_1)
    print("Test input:", test_1)
    print("norm_a    :", out_a)
    print("norm_b    :", out_b)
    
    assert out_a == "tumor 2 5x1 8x1 0cm 5mm from margin"
    assert out_b == "tumor 2 5 x 1 8 x 1 0 cm 5 mm from margin"
    
    test_2 = "3 by 4 by 5 cm"
    assert norm_b(test_2) == "3 x 4 x 5 cm"
    
    print("All unit assertions passed successfully!")
