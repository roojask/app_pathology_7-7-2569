import os
import sys
import json
import re
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.nlp.extractor import extract_data_15_sections
from src.nlp.normalizer import normalize_text

with open(BASE_DIR / 'data' / 'dataset_1000' / 'ground_truth_1000_pure.json', 'r', encoding='utf-8') as f:
    gt_data = json.load(f)

csv_path = BASE_DIR / 'benchmarks' / 'thesis_eval_outputs' / 'benchmark_1000_cases_overnight.csv'
df = pd.read_csv(csv_path)

pw_df = df[df['system'].str.contains('PathoWhisper', case=False, na=False)].copy()
bs_df = df[df['system'].str.contains('Baseline', case=False, na=False)].copy()

def are_num_equal(a, b):
    if a is None or b is None: return False
    try:
        return abs(float(a) - float(b)) < 0.05
    except:
        return str(a).strip().lower() == str(b).strip().lower()

def are_dims_equal(list_a, list_b):
    if not isinstance(list_a, list) or not isinstance(list_b, list):
        return False
    if len(list_a) != len(list_b): return False
    try:
        return all(abs(float(a) - float(b)) < 0.05 for a, b in zip(list_a, list_b))
    except:
        return list_a == list_b

def are_strings_equal(a, b):
    s_a = re.sub(r"[\s\-_]+", "", str(a).lower())
    s_b = re.sub(r"[\s\-_]+", "", str(b).lower())
    return s_a == s_b

print("=" * 80)
print("CLINICAL ERROR CASE DIAGNOSIS & EXTRACTION TRACE")
print("=" * 80)

# =========================================================================
# Part 1: s11_deep_margin in Categories 1, 7, 8
# =========================================================================
print("\n" + "=" * 50)
print("1. s11_deep_margin ERROR CASES (Cat 1, 7, 8)")
print("=" * 50)

for target_cat in [1, 7, 8]:
    sub = pw_df[pw_df['category_id'] == target_cat]
    err_cases = []
    for _, row in sub.iterrows():
        cid = row['case_id']
        gt_val = gt_data[cid].get('s11_deep_margin')
        hyp = str(row['hyp_text'])
        norm = normalize_text(hyp)
        ext = extract_data_15_sections(hyp)
        pred_val = ext.get('s11_deep')
        
        match = False
        if gt_val is None and pred_val is None:
            match = True
        elif gt_val is not None and pred_val is not None:
            match = are_num_equal(gt_val, pred_val)
            
        if not match:
            err_cases.append({
                'case_id': cid,
                'cat': target_cat,
                'ref': row['ref_text'],
                'gt': gt_val,
                'pred': pred_val,
                'hyp': hyp,
                'norm': norm
            })
            
    print(f"\n--- Category {target_cat} (Errors: {len(err_cases)} / {len(sub)}) ---")
    for i, e in enumerate(err_cases[:3], 1):
        print(f"[{target_cat}.{i}] {e['case_id']}:")
        print(f"  Ground Truth : {e['gt']}")
        print(f"  Extractor Val: {e['pred']}")
        print(f"  Ref Text     : {e['ref']}")
        print(f"  Hyp Text     : {e['hyp']}")
        print(f"  Norm Text    : {e['norm']}")

# =========================================================================
# Part 2: s0_surgical_no (across all categories)
# =========================================================================
print("\n" + "=" * 50)
print("2. s0_surgical_no ERROR CASES (PathoWhisper vs Baseline)")
print("=" * 50)

sno_errs = []
for _, row in pw_df.iterrows():
    cid = row['case_id']
    gt_val = gt_data[cid].get('s0_surgical_no')
    hyp = str(row['hyp_text'])
    norm = normalize_text(hyp)
    ext = extract_data_15_sections(hyp)
    pred_val = ext.get('s0_surgical_no')
    
    match = are_strings_equal(gt_val, pred_val) if (gt_val and pred_val) else False
    if not match:
        # Check baseline
        b_row = bs_df[bs_df['case_id'] == cid].iloc[0]
        b_ext = extract_data_15_sections(str(b_row['hyp_text']))
        b_pred = b_ext.get('s0_surgical_no')
        b_match = are_strings_equal(gt_val, b_pred) if (gt_val and b_pred) else False
        
        sno_errs.append({
            'case_id': cid,
            'cat': row['category_id'],
            'gt': gt_val,
            'pw_pred': pred_val,
            'pw_hyp': hyp,
            'pw_norm': norm,
            'bs_pred': b_pred,
            'bs_hyp': b_row['hyp_text'],
            'bs_match': b_match
        })

print(f"Total s0_surgical_no Errors in PathoWhisper: {len(sno_errs)} / 1000")
print(f"  Of which Baseline got CORRECT: {sum(1 for e in sno_errs if e['bs_match'])}")
print("Sample 3 cases:")
for i, e in enumerate(sno_errs[:3], 1):
    print(f"\n[SNO.{i}] {e['case_id']} (Cat {e['cat']}):")
    print(f"  Ground Truth   : {e['gt']}")
    print(f"  PW Extracted   : {e['pw_pred']}")
    print(f"  PW Hyp Text    : {e['pw_hyp']}")
    print(f"  PW Norm Text   : {e['pw_norm']}")
    print(f"  BS Extracted   : {e['bs_pred']} (Match: {e['bs_match']})")
    print(f"  BS Hyp Text    : {e['bs_hyp']}")

# =========================================================================
# Part 3: s10_inf_dims in Categories 3 and 7
# =========================================================================
print("\n" + "=" * 50)
print("3. s10_inf_dims ERROR CASES (Cat 3 and 7)")
print("=" * 50)

for target_cat in [3, 7]:
    sub = pw_df[pw_df['category_id'] == target_cat]
    err_cases = []
    for _, row in sub.iterrows():
        cid = row['case_id']
        gt_val = gt_data[cid].get('s10_inf_dims')
        hyp = str(row['hyp_text'])
        norm = normalize_text(hyp)
        ext = extract_data_15_sections(hyp)
        pred_val = ext.get('s10_inf_dims')
        
        match = False
        if gt_val is None and pred_val is None:
            match = True
        elif gt_val is not None and pred_val is not None:
            match = are_dims_equal(gt_val, pred_val)
            
        if not match:
            err_cases.append({
                'case_id': cid,
                'cat': target_cat,
                'gt': gt_val,
                'pred': pred_val,
                'hyp': hyp,
                'norm': norm
            })
            
    print(f"\n--- Category {target_cat} (Errors: {len(err_cases)} / {len(sub)}) ---")
    for i, e in enumerate(err_cases[:3], 1):
        print(f"[{target_cat}.{i}] {e['case_id']}:")
        print(f"  Ground Truth : {e['gt']}")
        print(f"  Extractor Val: {e['pred']}")
        print(f"  Hyp Text     : {e['hyp']}")
        print(f"  Norm Text    : {e['norm']}")
