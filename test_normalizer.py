import os
import sys
import argparse
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from src.nlp.normalizer import normalize_text

TEST_CASES = [
    ("TC-01", "3D dimension self-correction with sorry", "Self-Correction", "infiltrative mass measuring 2.0 x 3.0 x 1.0 cm sorry 2.5 x 3.5 x 1.5 cm", "infiltrative mass measuring 2.5 x 3.5 x 1.5 cm"),
    ("TC-02", "Dimension followed by weight is 450 grams", "Weight Preservation", "10 x 5 x 2 cm, weight is 450 grams", "10 x 5 x 2 cm, weight is 450 grams"),
    ("TC-03", "Dimension followed by weight of 450 grams", "Weight Preservation", "10 x 5 x 2 cm, weight of 450 grams", "10 x 5 x 2 cm, weight of 450 grams"),
    ("TC-04", "Dimension followed by weight: 450 g", "Weight Preservation", "10 x 5 x 2 cm, weight: 450 g", "10 x 5 x 2 cm, weight: 450 g"),
    ("TC-05", "Dimension followed by weight 0.45 kg", "Weight Preservation", "10 x 5 x 2 cm, weight 0.45 kg", "10 x 5 x 2 cm, weight 0.45 kg"),
    ("TC-06", "Dimension followed by written weight", "Weight Preservation", "specimen measuring 10 x 5 x 2 cm, weight 450 grams", "specimen measuring 10 x 5 x 2 cm, weight 450 grams"),
    ("TC-07", "Actually after dimension without replacement", "False Positive Resistance", "10 x 5 x 2 cm. actually the skin ellipse measures 5 x 2 cm", "10 x 5 x 2 cm. actually the skin ellipse measures 5 x 2 cm"),
    ("TC-08", "Dimension followed by weight margin is 3.0 cm", "Weight Margin Disambiguation", "5.3 x 2.4 x 2.9 cm weight margin is 3.0 cm", "5.3 x 2.4 x 2.9 cm weight margin is 3.0 cm"),
    ("TC-09", "1D dimension followed by no 3 lymph nodes", "Lymph Node Disambiguation", "margin 2 mm no 3 lymph nodes", "margin 2 mm no 3 lymph nodes"),
    ("TC-10", "1D dimension self-correction with units on both sides", "1D Self-Correction", "mass measuring 2 cm no 3 cm", "mass measuring 3 cm"),
    ("TC-11", "Whisper wait transcribed as weight followed by new dimension", "Wait/Weight Disambiguation", "mass measuring 2.0 x 3.0 x 1.0 cm weight 2.5 x 3.5 x 1.5 cm", "mass measuring 2.5 x 3.5 x 1.5 cm"),
    ("TC-12", "Isolated specimen weight without dimension", "Weight Preservation", "specimen weight 450 grams", "specimen weight 450 grams"),
    ("TC-13", "Clinical negation no residual mass preserved", "Negation Preservation", "no residual mass identified in the specimen", "no residual mass identified in the specimen"),
    ("TC-14", "Clinical negation no discrete mass preserved", "Negation Preservation", "no discrete mass identified", "no discrete mass identified"),
    ("TC-15", "Sentence with actually preserving clinical statement", "False Positive Resistance", "actually there is no mass in the upper outer quadrant", "actually there is no mass in the upper outer quadrant"),
    ("TC-16", "Thai self-correction with kae pen", "Thai Self-Correction", "mass measuring 2 x 2 cm แก้เป็น 3 x 3 cm", "mass measuring 3 x 3 cm")
]

def run_tests(csv_out_path=None):
    results = []
    all_pass = True

    print("=" * 75)
    print("NORMALIZER UNIT TEST SUITE (16 CLINICAL EDGE CASES)")
    print("=" * 75)
    print(f"{'Test ID':<8} | {'Type':<26} | {'Status':<6} | {'Input Text (Truncated)':<30}")
    print("-" * 75)

    for tid, desc, ttype, inp, expected in TEST_CASES:
        out = normalize_text(inp).strip()
        out_clean = " ".join(out.split())
        exp_clean = " ".join(expected.lower().split())
        status = "PASS" if out_clean == exp_clean else "FAIL"
        if status == "FAIL":
            all_pass = False

        inp_trunc = inp[:28] + ".." if len(inp) > 30 else inp
        print(f"{tid:<8} | {ttype:<26} | {status:<6} | {inp_trunc:<30}")

        results.append({
            "Test_ID": tid,
            "Description": desc,
            "Type": ttype,
            "Input": inp,
            "Normalized_Output": out_clean,
            "Expected_Output": exp_clean,
            "Status": status
        })

    print("-" * 75)
    print(f"OVERALL RESULT: {len(TEST_CASES)}/{len(TEST_CASES)} {'ALL PASS (100.0%)' if all_pass else 'SOME TESTS FAILED'}")
    print("=" * 75)

    if csv_out_path:
        out_file = Path(csv_out_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(results)
        df.to_csv(out_file, index=False, encoding="utf-8-sig")
        print(f"Saved {len(results)} rows to {out_file}")

    # Also automatically save to benchmarks/thesis_eval_outputs/unit_test_results.csv
    default_out = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "unit_test_results.csv"
    default_out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(default_out, index=False, encoding="utf-8-sig")
    print(f"Updated {default_out}")

    return all_pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run 16 normalizer clinical unit tests.")
    parser.add_argument("--csv", type=str, default="unit_test_results.csv", help="Path to output CSV file")
    args = parser.parse_args()

    success = run_tests(args.csv)
    sys.exit(0 if success else 1)
