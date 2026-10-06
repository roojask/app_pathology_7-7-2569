import os
import sys
import json
import re
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).parent.parent
GT_PATH = BASE_DIR / "data" / "dataset_1000" / "ground_truth_1000_pure.json"
OUT_CSV = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "gt_audit_results.csv"

def audit_ground_truth():
    print("=" * 75)
    print("GROUND TRUTH AUDIT (gt_audit.py)")
    print(f"Target: {GT_PATH}")
    print("=" * 75)

    if not GT_PATH.exists():
        print(f"ERROR: Ground truth file not found at {GT_PATH}")
        sys.exit(1)

    with open(GT_PATH, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    total_cases = len(gt_data)
    print(f"Total Cases to Audit: {total_cases}\n")

    results = []

    for case_id, case in gt_data.items():
        raw = case.get("raw_text", "").lower()
        raw_nospace = re.sub(r"\s+", "", raw)
        cat = case.get("cat_idx", 0)

        # 1. s0_surgical_no
        s0 = case.get("s0_surgical_no")
        s0_ok = (s0 is not None and s0.lower() in raw)

        # 2. s1_side
        s1 = case.get("s1_side")
        if cat == 3:
            # Self-correction: speaker said 'right... sorry left' -> true side is 'left'
            s1_ok = (s1 == "left" and "sorry left" in raw)
        else:
            s1_ok = (s1 is not None and s1.lower() in raw)

        # 3. s2_proc
        s2 = case.get("s2_proc")
        if cat == 10:
            s2_ok = (s2 is None and "mastectomy" in raw and not any(p in raw for p in ["modified", "simple"]))
        else:
            s2_ok = (s2 is not None and s2.lower() in raw)

        # 4. s3_dims
        s3 = case.get("s3_dims")
        if s3 and len(s3) == 3:
            dim_str = f"{s3[0]}x{s3[1]}x{s3[2]}"
            s3_ok = (dim_str in raw_nospace)
        else:
            s3_ok = (s3 is None)

        # 5. s4_skin
        s4 = case.get("s4_skin")
        if s4 is True:
            s4_ok = ("skin" in raw)
        else:
            s4_ok = ("skin" not in raw)

        # 6. s5_dims
        s5 = case.get("s5_dims")
        if s5 and len(s5) == 2:
            dim_str = f"{s5[0]}x{s5[1]}"
            s5_ok = (dim_str in raw_nospace)
        else:
            s5_ok = (s5 is None)

        # 7-10. Negative controls s6-s9
        s6 = case.get("s6_nipple")
        s7 = case.get("s7_biopsy_scar")
        s8 = case.get("s8_cavity")
        s9 = case.get("s9_residual_mass")
        neg_ok = (s6 is None and s7 is None and s8 is None and s9 is None)

        # 11. s10_infiltrative
        s10_inf = case.get("s10_infiltrative")
        if cat in [5, 6]:
            s10_inf_ok = (s10_inf is False)
        else:
            s10_inf_ok = (s10_inf is True and any(w in raw for w in ["mass", "infiltrative", "lesion"]))

        # 12. s10_inf_dims
        s10_dims = case.get("s10_inf_dims")
        if s10_dims and len(s10_dims) == 3:
            dim_str = f"{s10_dims[0]}x{s10_dims[1]}x{s10_dims[2]}"
            s10_dims_ok = (dim_str in raw_nospace)
        else:
            s10_dims_ok = (s10_dims is None)

        # 13. s10_5_quadrant
        quad = case.get("s10_5_quadrant")
        if quad:
            quad_parts = quad.lower().split()
            quad_ok = all(qp in raw for qp in quad_parts)
        else:
            quad_ok = (quad is None and "quadrant" not in raw)

        # 14. s11_deep_margin
        dm = case.get("s11_deep_margin")
        if dm:
            dm_ok = ("deep margin" in raw and str(dm) in raw_nospace)
        else:
            dm_ok = (dm is None and "deep margin" not in raw)

        # 15. s14_check (lymph nodes)
        ln = case.get("s14_check")
        if ln is True:
            ln_ok = ("lymph node" in raw or "node" in raw)
        else:
            ln_ok = ("lymph node" not in raw and "node" not in raw)

        results.append({
            "case_id": case_id,
            "cat_idx": cat,
            "s0_surgical_no": s0_ok,
            "s1_side": s1_ok,
            "s2_proc": s2_ok,
            "s3_dims": s3_ok,
            "s4_skin": s4_ok,
            "s5_dims": s5_ok,
            "negative_controls_none": neg_ok,
            "s10_infiltrative": s10_inf_ok,
            "s10_inf_dims": s10_dims_ok,
            "s10_5_quadrant": quad_ok,
            "s11_deep_margin": dm_ok,
            "s14_check": ln_ok,
        })

    df = pd.DataFrame(results)
    fields = [
        "s0_surgical_no", "s1_side", "s2_proc", "s3_dims", "s4_skin", "s5_dims",
        "negative_controls_none", "s10_infiltrative", "s10_inf_dims", "s10_5_quadrant",
        "s11_deep_margin", "s14_check"
    ]

    print(f"{'Field':<25} | {'Match Count':<12} | {'Mismatch':<10} | {'Audit Pass %':<12}")
    print("-" * 65)

    summary_rows = []
    for fld in fields:
        matched = int(df[fld].sum())
        mismatch = total_cases - matched
        pct = (matched / total_cases) * 100
        print(f"{fld:<25} | {matched:>5}/{total_cases:<5} | {mismatch:>8} | {pct:>10.2f}%")
        summary_rows.append({
            "Field": fld,
            "Match_Count": matched,
            "Total_Cases": total_cases,
            "Mismatch_Count": mismatch,
            "Pass_Rate_Pct": round(pct, 2)
        })

    print("-" * 65)
    overall_all_pass = all(df[fld].all() for fld in fields)
    print(f"OVERALL AUDIT INTEGRITY: {'100% PERFECT MATCH' if overall_all_pass else 'SOME MISMATCHES FOUND'}")
    print("=" * 75)

    df_sum = pd.DataFrame(summary_rows)
    df_sum.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\nSaved detailed audit summary to: {OUT_CSV}")

    # If any mismatch, print details
    if not overall_all_pass:
        print("\nMISMATCH DETAILS:")
        for fld in fields:
            bad_cases = df[~df[fld]][["case_id", "cat_idx"]].to_dict(orient="records")
            if bad_cases:
                print(f"  Field {fld} ({len(bad_cases)} mismatches): {bad_cases[:5]}")

if __name__ == "__main__":
    audit_ground_truth()
