import json
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
csv_path = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "fair_empirical_comparison_20cases.csv"
json_path = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "fair_empirical_comparison_20cases.json"

df = pd.read_csv(csv_path)

# Dump clean JSON
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(json.loads(df.to_json(orient="records")), f, ensure_ascii=False, indent=2)

print("=" * 105)
print("FAIR HEAD-TO-HEAD BENCHMARK SUMMARY (20 CASES ACROSS 10 CLINICAL CATEGORIES)")
print("=" * 105)

summary_data = [
    ("Vosk (Kaldi HMM-DNN)", df['wer_v_raw'].mean(), df['wer_v_itn'].mean(), df['lat_vosk'].mean(), df['slots_vosk'].sum() / (20 * 15) * 100),
    ("Meta Wav2Vec 2.0 (CTC)", df['wer_w_raw'].mean(), df['wer_w_itn'].mean(), df['lat_w2v'].mean(), df['slots_w2v'].sum() / (20 * 15) * 100),
    ("Baseline Whisper Small FP32", df['wer_b_raw'].mean(), df['wer_b_itn'].mean(), df['lat_baseline'].mean(), df['slots_baseline'].sum() / (20 * 15) * 100),
    ("PathoWhisper INT8 (Proposed)", df['wer_p_raw'].mean(), df['wer_p_itn'].mean(), df['lat_pathowhisper'].mean(), df['slots_pathowhisper'].sum() / (20 * 15) * 100),
]

header = f"{'ASR Architecture / Model':<32} | {'Raw WER':<10} | {'Fair ITN WER':<14} | {'Latency':<10} | {'Slot Agreement (15 fld)':<22}"
print(header)
print("-" * 105)
for name, raw_w, itn_w, lat, slot_acc in summary_data:
    print(f"{name:<32} | {raw_w:>8.2f}% | {itn_w:>12.2f}% | {lat:>7.2f} s | {slot_acc:>20.2f}%")
print("=" * 105)

print("\n--- CATEGORY-BY-CATEGORY BREAKDOWN (Fair ITN WER %) ---")
cat_summary = df.groupby(["category_id", "category_name"])[['wer_v_itn', 'wer_w_itn', 'wer_b_itn', 'wer_p_itn']].mean().reset_index()
print(f"{'Cat':<4} | {'Category Name':<30} | {'Vosk ITN':<10} | {'W2V2 ITN':<10} | {'Base Small':<10} | {'PathoWhisper':<12}")
print("-" * 90)
for _, r in cat_summary.iterrows():
    print(f"{int(r['category_id']):<4} | {r['category_name'][:30]:<30} | {r['wer_v_itn']:>8.2f}% | {r['wer_w_itn']:>8.2f}% | {r['wer_b_itn']:>8.2f}% | {r['wer_p_itn']:>10.2f}%")
print("=" * 90)

print("\n--- CASE-BY-CASE DETAILS (20 CASES) ---")
print(f"{'Case ID':<10} | {'Cat':<4} | {'Vosk Raw':<9} | {'Vosk ITN':<9} | {'W2V2 Raw':<9} | {'W2V2 ITN':<9} | {'Base ITN':<9} | {'PW ITN':<9} | {'Vosk Slots':<10} | {'W2V2 Slots':<10} | {'PW Slots':<10}")
print("-" * 120)
for _, r in df.iterrows():
    print(f"{r['case_id']:<10} | {int(r['category_id']):<4} | {r['wer_v_raw']:>7.1f}% | {r['wer_v_itn']:>7.1f}% | {r['wer_w_raw']:>7.1f}% | {r['wer_w_itn']:>7.1f}% | {r['wer_b_itn']:>7.1f}% | {r['wer_p_itn']:>7.1f}% | {int(r['slots_vosk']):>5}/15     | {int(r['slots_w2v']):>5}/15     | {int(r['slots_pathowhisper']):>5}/15")
print("=" * 120)
