import os
import sys
import re
import json
import random
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.generate_1000_cases import generate_case_text_and_gt
from src.nlp.extractor import extract_data_15_sections

def are_dims_equal(list_a, list_b):
    if not isinstance(list_a, list) or not isinstance(list_b, list):
        return False
    if len(list_a) != len(list_b):
        return False
    try:
        return all(abs(float(a) - float(b)) < 0.05 for a, b in zip(list_a, list_b))
    except (ValueError, TypeError):
        return [str(a).strip().lower() for a in list_a] == [str(b).strip().lower() for b in list_b]

def are_numbers_equal(num_a, num_b):
    try:
        return abs(float(num_a) - float(num_b)) < 0.05
    except (ValueError, TypeError):
        return str(num_a).strip().lower() == str(num_b).strip().lower()

def are_strings_equal(str_a, str_b):
    s_a = re.sub(r"[\s\-_]+", "", str(str_a).lower())
    s_b = re.sub(r"[\s\-_]+", "", str(str_b).lower())
    return s_a == s_b

def build_pure_gt():
    # Load original dataset to verify text identity
    orig_gt_path = BASE_DIR / "data" / "dataset_1000" / "ground_truth_1000.json"
    with open(orig_gt_path, "r", encoding="utf-8") as f:
        orig_gt_data = json.load(f)

    gt_cases = {}
    mismatches = 0

    for cid in range(1, 1001):
        cat_idx = ((cid - 1) % 10) + 1
        random.seed(cid)
        surg_no = f"S-24-{1000 + cid:04d}"
        
        # Side: In Category 3 (Self-correction), speaker says 'right... sorry left' -> True side is 'left'
        side_rand = random.choice(["right", "left"])
        side = "left" if cat_idx == 3 else side_rand
        
        proc_raw = random.choice(["modified radical mastectomy", "simple mastectomy"])
        # Procedure: In Category 10, speaker only says 'mastectomy' without modifier
        proc_val = None if cat_idx == 10 else ("modified" if "modified" in proc_raw else "simple")
        
        d1, d2, d3 = round(random.uniform(5, 30), 1), round(random.uniform(5, 25), 1), round(random.uniform(2, 15), 1)
        sd1, sd2 = round(random.uniform(5, 20), 1), round(random.uniform(2, 10), 1)
        md1, md2, md3 = round(random.uniform(1, 8), 1), round(random.uniform(1, 6), 1), round(random.uniform(1, 5), 1)
        node_count = random.randint(3, 20)
        n_min = round(random.uniform(0.1, 0.8), 1)
        n_max = round(random.uniform(1.0, 3.5), 1)
        quad = random.choice(["upper inner", "upper outer", "lower inner", "lower outer", "central"])
        
        if cat_idx == 1:
            deep_m = str(round(random.uniform(0.2, 3.0), 1))
        elif cat_idx in [2, 7, 9]:
            deep_m = "1.5"
        elif cat_idx in [4, 8]:
            deep_m = "1.0"
        elif cat_idx == 10:
            deep_m = "1.2"
        else:
            deep_m = None
            
        skin_dims = [str(sd1), str(sd2)] if cat_idx in [1, 2, 4, 7] else None
        mass_dims = [str(md1), str(md2), str(md3)] if cat_idx in [1, 2, 3, 4, 7, 8, 9] else None
        quad_val = quad if cat_idx in [1, 2, 4, 7, 9] else None
        has_skin = True if cat_idx in [1, 2, 3, 4, 7] else False
        
        # Mass: Cat 5 has axillary content only (NO mass), Cat 6 is fibrocystic (NO mass)
        has_inf = True if cat_idx not in [5, 6] else False
        
        # Lymph nodes: Cats 1, 2, 3, 5, 7, and 9 (Cat 9 has '4 lymph nodes identified')
        has_nodes = True if cat_idx in [1, 2, 3, 5, 7, 9] else False
        
        # Generate raw text deterministically
        text, _ = generate_case_text_and_gt(cid, cat_idx)
        
        cid_str = f"case_{cid:04d}"
        if text != orig_gt_data[cid_str]["raw_text"]:
            mismatches += 1
            
        gt_cases[cid_str] = {
            "cat_idx": cat_idx,
            "raw_text": text,
            "s0_surgical_no": surg_no,
            "s1_side": side,
            "s2_proc": proc_val,
            "s3_dims": [str(d1), str(d2), str(d3)],
            "s4_skin": has_skin,
            "s5_dims": skin_dims,
            "s6_nipple": None,
            "s7_biopsy_scar": None,
            "s8_cavity": None,
            "s9_residual_mass": None,
            "s10_infiltrative": has_inf,
            "s10_inf_dims": mass_dims,
            "s10_5_quadrant": quad_val,
            "s11_deep_margin": deep_m,
            "s14_check": has_nodes
        }

    assert mismatches == 0, f"Critical: Expected 0 raw_text mismatches, got {mismatches}"
    print(f"VERIFIED: 1,000/1,000 cases matched raw_text exactly (Mismatch = {mismatches})")
    return gt_cases

def run_evaluation():
    gt_cases = build_pure_gt()
    
    # Save pure ground truth JSON
    pure_gt_path = BASE_DIR / "data" / "dataset_1000" / "ground_truth_1000_pure.json"
    with open(pure_gt_path, "w", encoding="utf-8") as f:
        json.dump(gt_cases, f, indent=2, ensure_ascii=False)
    print(f"Saved pure ground truth to {pure_gt_path}")
    
    # Load 1000 overnight benchmark results
    csv_path = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "benchmark_1000_cases_overnight.csv"
    df = pd.read_csv(csv_path)
    
    field_keys = [
        "s0_surgical_no", "s1_side", "s2_proc", "s3_dims", "s4_skin",
        "s5_dims", "s6_nipple", "s7_biopsy_scar", "s8_cavity", "s9_residual_mass",
        "s10_infiltrative", "s10_inf_dims", "s10_5_quadrant", "s11_deep_margin", "s14_check"
    ]
    
    descriptions = {
        "s0_surgical_no": "เลขที่สิ่งส่งตรวจ (Surgical Number)",
        "s1_side": "ข้างเต้านม (Laterality/Side)",
        "s2_proc": "ชนิดหัตถการ (Procedure)",
        "s3_dims": "ขนาดสิ่งส่งตรวจ 3 มิติ (Specimen 3D)",
        "s4_skin": "การมีชิ้นผิวหนังติดมา (Skin Presence)",
        "s5_dims": "ขนาดชิ้นผิวหนัง 2 มิติ (Skin 2D)",
        "s6_nipple": "สภาพหัวนมและลานนม (Nipple/Areola)",
        "s7_biopsy_scar": "รอยแผลเป็นเจาะตรวจเดิม (Biopsy Scar)",
        "s8_cavity": "โพรงผ่าตัดเดิม (Previous Cavity)",
        "s9_residual_mass": "ก้อนเนื้องอกตกค้าง (Residual Mass)",
        "s10_infiltrative": "การพบก้อนมะเร็งลุกลาม (Infiltrative Mass)",
        "s10_inf_dims": "ขนาดก้อนมะเร็ง 3 มิติ (Mass 3D)",
        "s10_5_quadrant": "ตำแหน่งจตุภาคของก้อน (Quadrant)",
        "s11_deep_margin": "ระยะห่างขอบตัดด้านลึก (Deep Margin)",
        "s14_check": "การตรวจต่อมน้ำเหลืองรักแร้ (Lymph Nodes)"
    }
    
    def eval_system(sys_keyword):
        sub = df[df["system"].str.contains(sys_keyword, case=False, na=False)]
        stats = {k: {"TP": 0, "FP": 0, "FN": 0, "TN": 0} for k in field_keys}
        category_errors = {k: {c: 0 for c in range(1, 11)} for k in field_keys}
        
        for _, row in sub.iterrows():
            cid = row["case_id"]
            gt = gt_cases[cid]
            cat = gt["cat_idx"]
            text_to_extract = str(row["hyp_text"])
            pred = extract_data_15_sections(text_to_extract)
            
            p_quad = None
            if pred.get("s10_5_quadrant_vals"):
                p_quad = " ".join(pred["s10_5_quadrant_vals"])
            elif pred.get("s10_5_central"):
                p_quad = "central"
                
            # Evaluated strictly from extractor outputs
            pred_mapped = {
                "s0_surgical_no": pred.get("s0_surgical_no"),
                "s1_side": pred.get("s1_side"),
                "s2_proc": pred.get("s2_proc"),
                "s3_dims": pred.get("s3_dims"),
                "s4_skin": bool(pred.get("s5_appears_normal") or pred.get("s5_dims")),
                "s5_dims": pred.get("s5_dims"),
                "s6_nipple": pred.get("s9_val"),
                "s7_biopsy_scar": pred.get("s6_check"),
                "s8_cavity": pred.get("s10_prev1") or pred.get("s10_prev2"),
                "s9_residual_mass": pred.get("s10_prev2_mass_dims"),
                "s10_infiltrative": pred.get("s10_infiltrative"),
                "s10_inf_dims": pred.get("s10_inf_dims"),
                "s10_5_quadrant": p_quad,
                "s11_deep_margin": pred.get("s11_deep"),
                "s14_check": pred.get("s14_check")
            }
            
            for k in field_keys:
                gv = gt[k]
                pv = pred_mapped[k]
                
                g_has = (gv is not None and gv != "" and gv != [] and gv is not False)
                p_has = (pv is not None and pv != "" and pv != [] and pv is not False)
                
                if not g_has and not p_has:
                    stats[k]["TN"] += 1
                elif g_has and not p_has:
                    stats[k]["FN"] += 1
                    category_errors[k][cat] += 1
                elif not g_has and p_has:
                    stats[k]["FP"] += 1
                    category_errors[k][cat] += 1
                else:
                    # Both present -> Strict Exact Match
                    match = False
                    if k in ["s3_dims", "s5_dims", "s10_inf_dims"]:
                        match = are_dims_equal(gv, pv)
                    elif k in ["s11_deep_margin"]:
                        match = are_numbers_equal(gv, pv)
                    elif isinstance(gv, bool):
                        match = (pv == gv)
                    else:
                        match = are_strings_equal(gv, pv)
                        
                    if match:
                        stats[k]["TP"] += 1
                    else:
                        stats[k]["FP"] += 1
                        stats[k]["FN"] += 1
                        category_errors[k][cat] += 1
                        
        return stats, category_errors

    base_stats, base_cat_err = eval_system("Baseline")
    pw_stats, pw_cat_err = eval_system("PathoWhisper")
    
    rows = []
    for k in field_keys:
        pos = sum(1 for cid in gt_cases.values() if cid[k] is not None and cid[k] != "" and cid[k] != [] and cid[k] is not False)
        bs = base_stats[k]
        ps = pw_stats[k]
        
        bp = (bs["TP"] / max(1, bs["TP"] + bs["FP"])) * 100
        br = (bs["TP"] / max(1, bs["TP"] + bs["FN"])) * 100
        bf = (2*bp*br / max(1e-9, bp+br)) if bp+br > 0 else 0
        
        pp = (ps["TP"] / max(1, ps["TP"] + ps["FP"])) * 100
        pr = (ps["TP"] / max(1, ps["TP"] + ps["FN"])) * 100
        pf = (2*pp*pr / max(1e-9, pp+pr)) if pp+pr > 0 else 0
        
        role = "Negative Control (Spec 100%)" if pos == 0 else ("Core Field" if pos in [900, 1000] else f"Spoken in {pos} cases")
        
        rows.append({
            "Field_ID": k,
            "Description": descriptions[k],
            "Positive_Cases": pos,
            "Baseline_Prec": f"{bp:.1f}%" if pos > 0 else "-",
            "Baseline_Rec": f"{br:.1f}%" if pos > 0 else "-",
            "Baseline_F1": f"{bf:.1f}%" if pos > 0 else "-",
            "PW_Prec": f"{pp:.1f}%" if pos > 0 else "-",
            "PW_Rec": f"{pr:.1f}%" if pos > 0 else "-",
            "PW_F1": f"{pf:.1f}%" if pos > 0 else "-",
            "Field_Role": role,
            "Baseline_TP": bs["TP"],
            "Baseline_FP": bs["FP"],
            "Baseline_FN": bs["FN"],
            "Baseline_TN": bs["TN"],
            "PW_TP": ps["TP"],
            "PW_FP": ps["FP"],
            "PW_FN": ps["FN"],
            "PW_TN": ps["TN"]
        })
        
    out_df = pd.DataFrame(rows)
    out_csv = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "field_metrics_15_pure_gt.csv"
    out_df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"Saved evaluation results to {out_csv}")
    
    # Save Category Error Breakdown
    cat_err_rows = []
    for k in field_keys:
        err_dict = pw_cat_err[k]
        row_dict = {"Field_ID": k}
        for c in range(1, 11):
            row_dict[f"Cat_{c}"] = err_dict[c]
        row_dict["Total_Errors"] = sum(err_dict.values())
        cat_err_rows.append(row_dict)
    cat_df = pd.DataFrame(cat_err_rows)
    cat_csv = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "category_errors_15_fields.csv"
    cat_df.to_csv(cat_csv, index=False, encoding="utf-8-sig")
    print(f"Saved category error breakdown to {cat_csv}")

if __name__ == "__main__":
    run_evaluation()
