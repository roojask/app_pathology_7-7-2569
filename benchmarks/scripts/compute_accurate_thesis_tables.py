import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_PATH = os.path.join(BASE_DIR, "benchmarks", "live_1000_results.json")
GT_PATH = os.path.join(BASE_DIR, "data", "dataset_1000", "ground_truth_1000.json")

def main():
    print("=" * 80)
    print("1,000 CASES EMPIRICAL BENCHMARK ANALYSIS (FROM LIVE_1000_RESULTS.JSON)")
    print("=" * 80)
    
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    kpi = data.get("kpi_summary", {})
    cases = data.get("cases", [])
    
    print("\n[1] Overall KPI Summary from JSON:")
    for k, v in kpi.items():
        print(f"  - {k}: {v:.2f}" if isinstance(v, float) else f"  - {k}: {v}")
        
    # Group by category
    cats = {}
    for c in cases:
        cid = c.get("category_id", 1)
        cname = c.get("category", f"Category {cid}")
        if cid not in cats:
            cats[cid] = {
                "name": cname,
                "wers": [],
                "cers": [],
                "accs": [],
                "lats": []
            }
        cats[cid]["wers"].append(c.get("wer", 0.0))
        cats[cid]["cers"].append(c.get("cer", 0.0))
        cats[cid]["accs"].append(c.get("mapping_acc", 0.0))
        cats[cid]["lats"].append(c.get("latency", 0.0))
        
    print("\n[2] Category Breakdown (N=100 per category):")
    print(f"{'Cat':<4} | {'Category Description':<32} | {'WER (%)':<10} | {'CER (%)':<10} | {'Acc (%)':<10} | {'Latency (s)':<12}")
    print("-" * 88)
    
    cat_macro_wers = []
    cat_macro_cers = []
    cat_macro_accs = []
    cat_macro_lats = []
    
    for cid in sorted(cats.keys()):
        item = cats[cid]
        n = len(item["wers"])
        avg_w = sum(item["wers"]) / n
        avg_c = sum(item["cers"]) / n
        avg_a = sum(item["accs"]) / n
        avg_l = sum(item["lats"]) / n
        
        cat_macro_wers.append(avg_w)
        cat_macro_cers.append(avg_c)
        cat_macro_accs.append(avg_a)
        cat_macro_lats.append(avg_l)
        
        print(f"{cid:<4} | {item['name']:<32} | {avg_w:9.2f}% | {avg_c:9.2f}% | {avg_a:9.2f}% | {avg_l:10.2f}s")
        
    macro_wer = sum(cat_macro_wers) / len(cat_macro_wers)
    macro_cer = sum(cat_macro_cers) / len(cat_macro_cers)
    macro_acc = sum(cat_macro_accs) / len(cat_macro_accs)
    macro_lat = sum(cat_macro_lats) / len(cat_macro_lats)
    
    all_wers = [c.get("wer", 0.0) for c in cases]
    all_cers = [c.get("cer", 0.0) for c in cases]
    all_accs = [c.get("mapping_acc", 0.0) for c in cases]
    all_lats = [c.get("latency", 0.0) for c in cases]
    
    micro_wer = sum(all_wers) / len(all_wers)
    micro_cer = sum(all_cers) / len(all_cers)
    micro_acc = sum(all_accs) / len(all_accs)
    micro_lat = sum(all_lats) / len(all_lats)
    
    print("-" * 88)
    print(f"Macro-Average (10 Cats) : WER = {macro_wer:.2f}% | CER = {macro_cer:.2f}% | Acc = {macro_acc:.2f}% | Lat = {macro_lat:.2f}s")
    print(f"Micro-Average (1,000 Cs): WER = {micro_wer:.2f}% | CER = {micro_cer:.2f}% | Acc = {micro_acc:.2f}% | Lat = {micro_lat:.2f}s")
    print("=" * 88)

if __name__ == "__main__":
    main()
