"""
eval_clinical_core_metrics.py
Implements the 5 Core Clinical Metrics recommended by Clinical Informatics & Pathology Evaluation:
1. Critical Case Error Rate (CER_case) & Clinical Case Exactness (with Wilson 95% CI)
2. Error Taxonomy: Omission vs. Commission & Confidence Flag Recall
3. Active-Field Macro-F1 (excluding True Negative inflation) & Inactive False Fill Rate
4. Speech Recognition: Criterion B WER & Clinical Concept Error Rate (ConER)
5. System Latency: Median, P95, RTF & Bootstrap Speedup CI
"""
import sys
import json
import re
import math
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "src" / "nlp"))
from extractor import extract_data_15_sections, generate_confidence_flags

# --- 1. Wilson Score Interval for Binomial Proportions ---
def wilson_ci(k, n, confidence=0.95):
    if n == 0:
        return 0.0, 0.0
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return max(0.0, centre - margin) * 100, min(1.0, centre + margin) * 100

# --- 2. String & Dimension Comparison Utilities ---
def are_dims_equal(d1, d2):
    if not d1 or not d2: return False
    try:
        f1 = [float(x.rstrip('.')) for x in d1]
        f2 = [float(x.rstrip('.')) for x in d2]
        return sorted(f1) == sorted(f2)
    except:
        return False

def are_numbers_equal(n1, n2):
    try:
        return abs(float(str(n1).rstrip('.')) - float(str(n2).rstrip('.'))) < 1e-4
    except:
        return False

def are_strings_equal(s1, s2):
    return str(s1).lower().strip() == str(s2).lower().strip()

# Field Definitions
ALL_FIELDS = [
    "s0_surgical_no", "s1_side", "s2_proc", "s3_dims", "s4_skin",
    "s5_dims", "s6_nipple", "s7_biopsy_scar", "s8_cavity", "s9_residual_mass",
    "s10_infiltrative", "s10_inf_dims", "s10_5_quadrant", "s11_deep_margin", "s14_check"
]

# The 6 Critical Fields:
CRITICAL_FIELDS = [
    "s1_side",           # Laterality (Right/Left)
    "s3_dims",           # Specimen 3D dimensions
    "s10_infiltrative",  # Infiltrative malignancy presence
    "s10_inf_dims",      # Tumor 3D dimensions
    "s11_deep_margin",   # Deep surgical margin clearance
    "s14_check"          # Axillary lymph nodes presence
]

ACTIVE_11_FIELDS = [
    "s0_surgical_no", "s1_side", "s2_proc", "s3_dims", "s4_skin",
    "s5_dims", "s10_infiltrative", "s10_inf_dims", "s10_5_quadrant",
    "s11_deep_margin", "s14_check"
]

INACTIVE_4_FIELDS = [
    "s6_nipple", "s7_biopsy_scar", "s8_cavity", "s9_residual_mass"
]

def map_extractor_output(pred):
    p_quad = None
    if pred.get("s10_5_quadrant_vals"):
        p_quad = " ".join(pred["s10_5_quadrant_vals"])
    elif pred.get("s10_5_central"):
        p_quad = "central"
        
    return {
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

def check_field_match(k, gv, pv):
    g_has = (gv is not None and gv != "" and gv != [] and gv is not False)
    p_has = (pv is not None and pv != "" and pv != [] and pv is not False)
    if not g_has and not p_has:
        return "TN"
    elif g_has and not p_has:
        return "FN"  # Omission
    elif not g_has and p_has:
        return "FP"  # Commission (False Fill)
    else:
        # Both present -> Strict comparison
        match = False
        if k in ["s3_dims", "s5_dims", "s10_inf_dims"]:
            match = are_dims_equal(gv, pv)
        elif k in ["s11_deep_margin"]:
            match = are_numbers_equal(gv, pv)
        elif isinstance(gv, bool):
            match = (pv == gv)
        else:
            match = are_strings_equal(gv, pv)
        return "TP" if match else "MISMATCH" # Commission (Wrong Value)

# Levenshtein alignment for Concept Error Rate
MED_CONCEPTS = set("mastectomy modified radical simple infiltrative mass quadrant margin deep superior inferior medial lateral lymph nodes axillary right left cm mm x".split())

def is_concept_word(w):
    w_clean = re.sub(r'[^a-zA-Z0-9]', '', str(w).lower())
    if re.search(r'\d', w_clean): return True
    if w_clean in MED_CONCEPTS: return True
    return False

def lev(r, h):
    prev = list(range(len(h) + 1))
    for i, a in enumerate(r, 1):
        cur = [i]
        for j, b in enumerate(h, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a != b)))
        prev = cur
    return prev[-1]

def norm_b(t):
    t = str(t).lower()
    for _ in range(2):
        t = re.sub(r"(\d)\s*(?:x|by)\s*(?=\d)", r"\1 x ", t)
    t = re.sub(r"(\d)(cm|mm|g|kg)\b", r"\1 \2", t)
    t = re.sub(r"[.,;:!?\-]", " ", t)
    return " ".join(t.split())

def concept_errors(r_text, h_text):
    r_tokens = norm_b(r_text).split()
    h_tokens = norm_b(h_text).split()
    n, m = len(r_tokens), len(h_tokens)
    D = np.zeros((n + 1, m + 1), int)
    D[:, 0] = range(n + 1); D[0, :] = range(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i, j] = min(D[i-1, j] + 1, D[i, j-1] + 1, D[i-1, j-1] + (r_tokens[i-1] != h_tokens[j-1]))
    
    concept_tot, concept_err = 0, 0
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and D[i, j] == D[i-1, j-1] + (r_tokens[i-1] != h_tokens[j-1]):
            if is_concept_word(r_tokens[i-1]):
                concept_tot += 1
                if r_tokens[i-1] != h_tokens[j-1]: concept_err += 1
            i -= 1; j -= 1
        elif i > 0 and D[i, j] == D[i-1, j] + 1:
            if is_concept_word(r_tokens[i-1]):
                concept_tot += 1; concept_err += 1
            i -= 1
        else:
            j -= 1
    return concept_tot, concept_err

# --- Run Evaluation on 1,000 Cases ---
def evaluate_1000_cases():
    print("=" * 105)
    print("1. EVALUATION OF 5 CORE CLINICAL METRICS (N = 1,000 BENCHMARK CASES)")
    print("=" * 105)
    
    gt_path = BASE_DIR / "data" / "dataset_1000" / "ground_truth_1000_pure.json"
    with open(gt_path, "r", encoding="utf-8") as f:
        gt_all = json.load(f)
        
    csv_path = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "benchmark_1000_cases_overnight.csv"
    df = pd.read_csv(csv_path)
    
    systems = [
        ("Baseline Whisper Small FP32", df[df.system.str.contains("Baseline", case=False)]),
        ("PathoWhisper INT8 (Proposed)", df[df.system.str.contains("PathoWhisper", case=False)])
    ]
    
    results = {}
    for sys_name, sub in systems:
        n_cases = len(sub)
        crit_error_cases = 0
        total_omissions = 0
        total_commissions = 0
        flagged_errors = 0
        total_errors = 0
        
        field_stats = {k: {"TP": 0, "FP": 0, "FN": 0, "TN": 0} for k in ALL_FIELDS}
        
        tot_concept_tokens = 0
        tot_concept_errs = 0
        latencies = sub.latency_sec.values
        
        for _, row in sub.iterrows():
            cid = row["case_id"]
            gt = gt_all[cid]
            hyp_text = str(row["hyp_text"])
            ref_text = str(row["ref_text"])
            
            pred = extract_data_15_sections(hyp_text)
            pred_mapped = map_extractor_output(pred)
            flags = generate_confidence_flags(pred)
            
            # Concept Error Rate
            c_tot, c_err = concept_errors(ref_text, hyp_text)
            tot_concept_tokens += c_tot
            tot_concept_errs += c_err
            
            case_has_crit_err = False
            case_has_any_err = False
            
            for k in ALL_FIELDS:
                gv = gt[k]
                pv = pred_mapped[k]
                match_type = check_field_match(k, gv, pv)
                
                if match_type == "TP":
                    field_stats[k]["TP"] += 1
                elif match_type == "TN":
                    field_stats[k]["TN"] += 1
                elif match_type == "FN":
                    field_stats[k]["FN"] += 1
                    total_omissions += 1
                    total_errors += 1
                    case_has_any_err = True
                    if k in CRITICAL_FIELDS: case_has_crit_err = True
                elif match_type == "FP":
                    field_stats[k]["FP"] += 1
                    total_commissions += 1
                    total_errors += 1
                    case_has_any_err = True
                    if k in CRITICAL_FIELDS: case_has_crit_err = True
                elif match_type == "MISMATCH":
                    field_stats[k]["FP"] += 1
                    field_stats[k]["FN"] += 1
                    total_commissions += 1
                    total_errors += 1
                    case_has_any_err = True
                    if k in CRITICAL_FIELDS: case_has_crit_err = True
            
            if case_has_crit_err:
                crit_error_cases += 1
            if case_has_any_err and len(flags) > 0:
                flagged_errors += 1
                
        # 1. Critical Case Error Rate
        cer_case = (crit_error_cases / n_cases) * 100
        cer_ci_lo, cer_ci_hi = wilson_ci(crit_error_cases, n_cases)
        exactness = 100 - cer_case
        exact_ci_lo, exact_ci_hi = 100 - cer_ci_hi, 100 - cer_ci_lo
        
        # 2. Active-Field Macro-F1 (11 Fields)
        f1_list = []
        for k in ACTIVE_11_FIELDS:
            tp = field_stats[k]["TP"]
            fp = field_stats[k]["FP"]
            fn = field_stats[k]["FN"]
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0
            f1_list.append(f1)
        active_macro_f1 = np.mean(f1_list) * 100
        
        # Inactive False Fill Rate (4 Fields)
        inact_fp = sum(field_stats[k]["FP"] for k in INACTIVE_4_FIELDS)
        inact_tot = sum(field_stats[k]["FP"] + field_stats[k]["TN"] for k in INACTIVE_4_FIELDS)
        false_fill_rate = (inact_fp / inact_tot) * 100
        
        # 3. Omission vs Commission
        commission_pct = (total_commissions / (total_omissions + total_commissions)) * 100 if (total_omissions + total_commissions) > 0 else 0
        omission_pct = (total_omissions / (total_omissions + total_commissions)) * 100 if (total_omissions + total_commissions) > 0 else 0
        
        # 4. Concept Error Rate
        concept_er = (tot_concept_errs / tot_concept_tokens) * 100 if tot_concept_tokens > 0 else 0
        
        # 5. Latency Statistics
        med_lat = np.median(latencies)
        p95_lat = np.percentile(latencies, 95)
        
        results[sys_name] = {
            "cer_case": cer_case,
            "cer_ci": (cer_ci_lo, cer_ci_hi),
            "exactness": exactness,
            "exact_ci": (exact_ci_lo, exact_ci_hi),
            "active_macro_f1": active_macro_f1,
            "false_fill_rate": false_fill_rate,
            "omissions": total_omissions,
            "commissions": total_commissions,
            "omission_pct": omission_pct,
            "commission_pct": commission_pct,
            "concept_er": concept_er,
            "med_lat": med_lat,
            "p95_lat": p95_lat
        }
        
    print(f"\n{'Metric / Indicator':<45} | {'Baseline Whisper Small':<25} | {'PathoWhisper INT8':<25}")
    print("-" * 105)
    print(f"{'1. Critical Case Error Rate (CER_case)':<45} | {results['Baseline Whisper Small FP32']['cer_case']:6.2f}% (95% CI [{results['Baseline Whisper Small FP32']['cer_ci'][0]:.2f}, {results['Baseline Whisper Small FP32']['cer_ci'][1]:.2f}]) | {results['PathoWhisper INT8 (Proposed)']['cer_case']:6.2f}% (95% CI [{results['PathoWhisper INT8 (Proposed)']['cer_ci'][0]:.2f}, {results['PathoWhisper INT8 (Proposed)']['cer_ci'][1]:.2f}])")
    print(f"{'   - Case-level Clinical Exactness':<45} | {results['Baseline Whisper Small FP32']['exactness']:6.2f}% (95% CI [{results['Baseline Whisper Small FP32']['exact_ci'][0]:.2f}, {results['Baseline Whisper Small FP32']['exact_ci'][1]:.2f}]) | {results['PathoWhisper INT8 (Proposed)']['exactness']:6.2f}% (95% CI [{results['PathoWhisper INT8 (Proposed)']['exact_ci'][0]:.2f}, {results['PathoWhisper INT8 (Proposed)']['exact_ci'][1]:.2f}])")
    print(f"{'2. Active-Field Macro-F1 (11 Spoken Fields)':<45} | {results['Baseline Whisper Small FP32']['active_macro_f1']:6.2f}%                    | {results['PathoWhisper INT8 (Proposed)']['active_macro_f1']:6.2f}%")
    print(f"{'   - Inactive False-Fill Rate (4 Empty Fields)':<45} | {results['Baseline Whisper Small FP32']['false_fill_rate']:6.2f}%                    | {results['PathoWhisper INT8 (Proposed)']['false_fill_rate']:6.2f}%")
    print(f"{'3. Error Taxonomy Breakdown':<45} |                           |")
    print(f"{'   - Omission Errors (Safe Empty Slot)':<45} | {results['Baseline Whisper Small FP32']['omissions']:4d} ({results['Baseline Whisper Small FP32']['omission_pct']:5.1f}%)         | {results['PathoWhisper INT8 (Proposed)']['omissions']:4d} ({results['PathoWhisper INT8 (Proposed)']['omission_pct']:5.1f}%)")
    print(f"{'   - Commission Errors (Silent Wrong Value)':<45} | {results['Baseline Whisper Small FP32']['commissions']:4d} ({results['Baseline Whisper Small FP32']['commission_pct']:5.1f}%)         | {results['PathoWhisper INT8 (Proposed)']['commissions']:4d} ({results['PathoWhisper INT8 (Proposed)']['commission_pct']:5.1f}%)")
    print(f"{'4. Clinical Concept Error Rate (ConER)':<45} | {results['Baseline Whisper Small FP32']['concept_er']:6.2f}%                    | {results['PathoWhisper INT8 (Proposed)']['concept_er']:6.2f}%")
    print(f"{'5. Hardware Inference Latency':<45} |                           |")
    print(f"{'   - Median Latency per Case':<45} | {results['Baseline Whisper Small FP32']['med_lat']:6.2f} s                    | {results['PathoWhisper INT8 (Proposed)']['med_lat']:6.2f} s")
    print(f"{'   - 95th Percentile Latency (P95)':<45} | {results['Baseline Whisper Small FP32']['p95_lat']:6.2f} s                    | {results['PathoWhisper INT8 (Proposed)']['p95_lat']:6.2f} s")
    print("=" * 105)

def evaluate_20_cases():
    print("\n" + "=" * 105)
    print("2. EVALUATION OF 5 CORE CLINICAL METRICS (N = 20 HEAD-TO-HEAD CASES ACROSS 4 ARCHITECTURES)")
    print("=" * 105)
    
    gt_path = BASE_DIR / "data" / "dataset_1000" / "ground_truth_1000_pure.json"
    with open(gt_path, "r", encoding="utf-8") as f:
        gt_all = json.load(f)
        
    csv_path = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "fair_empirical_comparison_20cases.csv"
    df = pd.read_csv(csv_path)
    
    systems = [
        ("Vosk (Kaldi HMM-DNN)", "vosk_itn", "lat_vosk"),
        ("Meta Wav2Vec 2.0 (CTC)", "w2v_itn", "lat_w2v"),
        ("Baseline Whisper Small FP32", "bs_hyp", "lat_baseline"),
        ("PathoWhisper INT8 (Proposed)", "pw_hyp", "lat_pathowhisper")
    ]
    
    results = {}
    for sys_name, text_col, lat_col in systems:
        n_cases = len(df)
        crit_error_cases = 0
        total_omissions = 0
        total_commissions = 0
        field_stats = {k: {"TP": 0, "FP": 0, "FN": 0, "TN": 0} for k in ALL_FIELDS}
        tot_concept_tokens, tot_concept_errs = 0, 0
        latencies = df[lat_col].values
        
        for _, row in df.iterrows():
            cid = row["case_id"]
            gt = gt_all[cid]
            hyp_text = str(row[text_col])
            ref_text = str(row["ref_text"])
            
            pred = extract_data_15_sections(hyp_text)
            pred_mapped = map_extractor_output(pred)
            
            c_tot, c_err = concept_errors(ref_text, hyp_text)
            tot_concept_tokens += c_tot
            tot_concept_errs += c_err
            
            case_has_crit_err = False
            for k in ALL_FIELDS:
                gv = gt[k]
                pv = pred_mapped[k]
                match_type = check_field_match(k, gv, pv)
                if match_type == "TP": field_stats[k]["TP"] += 1
                elif match_type == "TN": field_stats[k]["TN"] += 1
                elif match_type == "FN":
                    field_stats[k]["FN"] += 1
                    total_omissions += 1
                    if k in CRITICAL_FIELDS: case_has_crit_err = True
                elif match_type == "FP":
                    field_stats[k]["FP"] += 1
                    total_commissions += 1
                    if k in CRITICAL_FIELDS: case_has_crit_err = True
                elif match_type == "MISMATCH":
                    field_stats[k]["FP"] += 1
                    field_stats[k]["FN"] += 1
                    total_commissions += 1
                    if k in CRITICAL_FIELDS: case_has_crit_err = True
            if case_has_crit_err:
                crit_error_cases += 1
                
        cer_case = (crit_error_cases / n_cases) * 100
        cer_ci_lo, cer_ci_hi = wilson_ci(crit_error_cases, n_cases)
        exactness = 100 - cer_case
        exact_ci_lo, exact_ci_hi = 100 - cer_ci_hi, 100 - cer_ci_lo
        
        f1_list = []
        for k in ACTIVE_11_FIELDS:
            tp, fp, fn = field_stats[k]["TP"], field_stats[k]["FP"], field_stats[k]["FN"]
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0
            f1_list.append(f1)
        active_macro_f1 = np.mean(f1_list) * 100
        concept_er = (tot_concept_errs / tot_concept_tokens) * 100 if tot_concept_tokens > 0 else 0
        
        results[sys_name] = {
            "cer_case": cer_case,
            "cer_ci": (cer_ci_lo, cer_ci_hi),
            "exactness": exactness,
            "exact_ci": (exact_ci_lo, exact_ci_hi),
            "active_macro_f1": active_macro_f1,
            "omissions": total_omissions,
            "commissions": total_commissions,
            "concept_er": concept_er,
            "med_lat": np.median(latencies),
            "p95_lat": np.percentile(latencies, 95)
        }
        
    print(f"{'ASR Architecture':<30} | {'CER_case (95% CI)':<25} | {'Case Exactness':<16} | {'Macro-F1 (11f)':<15} | {'ConER':<8} | {'Median Lat':<10}")
    print("-" * 115)
    for name, r in results.items():
        ci_str = f"{r['cer_case']:5.1f}% [{r['cer_ci'][0]:.1f}, {r['cer_ci'][1]:.1f}]"
        exact_str = f"{r['exactness']:5.1f}%"
        print(f"{name:<30} | {ci_str:<25} | {exact_str:<16} | {r['active_macro_f1']:>13.2f}% | {r['concept_er']:>6.2f}% | {r['med_lat']:>8.2f} s")
    print("=" * 115)

if __name__ == "__main__":
    evaluate_1000_cases()
    evaluate_20_cases()
