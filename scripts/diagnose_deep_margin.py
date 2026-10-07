import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import zipfile
import json
import pandas as pd
from src.nlp.extractor import extract_data_15_sections

with zipfile.ZipFile(r'benchmarks\thesis_eval_outputs\pathowhisper_evaluation_data.zip') as z:
    with z.open('ground_truth_1000_pure.json') as f:
        gt = json.load(f)

df = pd.read_csv('benchmarks/thesis_eval_outputs/benchmark_1000_cases_overnight.csv')
pw_df = df[df['system'].str.contains('PathoWhisper')].sort_values('case_id').reset_index(drop=True)
bs_df = df[df['system'].str.contains('Baseline')].sort_values('case_id').reset_index(drop=True)

pw_errors, bs_errors = [], []
pw_worse = []

for i in range(1000):
    cid = bs_df.loc[i, 'case_id']
    gt_val = gt[cid].get('s11_deep_margin')
    
    pw_ext_dict = extract_data_15_sections(pw_df.loc[i, 'hyp_text'])
    bs_ext_dict = extract_data_15_sections(bs_df.loc[i, 'hyp_text'])
    
    pw_ext = pw_ext_dict.get('s11_deep')
    bs_ext = bs_ext_dict.get('s11_deep')
    
    pw_ok = (pw_ext == gt_val)
    bs_ok = (bs_ext == gt_val)
    
    if not pw_ok: pw_errors.append((cid, gt_val, pw_ext))
    if not bs_ok: bs_errors.append((cid, gt_val, bs_ext))
    if bs_ok and not pw_ok:
        pw_worse.append((cid, gt_val, pw_ext, bs_ext, pw_df.loc[i, 'hyp_text'], bs_df.loc[i, 'hyp_text'], bs_df.loc[i, 'ref_text']))

print("Total Deep Margin Cases in GT:", sum(1 for v in gt.values() if v.get("s11_deep_margin") is not None))
print(f"PW Errors: {len(pw_errors)}, BS Errors: {len(bs_errors)}")
print(f"Cases where BS was correct but PW failed: {len(pw_worse)}")

for item in pw_worse[:10]:
    print("=" * 60)
    print("Case ID:", item[0])
    print("GT     :", item[1])
    print("PW Ext :", item[2])
    print("BS Ext :", item[3])
    print("Ref    :", item[6])
    print("PW Hyp :", item[4])
    print("BS Hyp :", item[5])
