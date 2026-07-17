import os
import time
import json
import argparse
import jiwer
import warnings
import sys

# ปรับ Path เพื่อให้ import app.py ได้
sys.path.append(os.getcwd())

from app import extract_data_15_sections
from benchmarks_and_tools.evaluate_mapping import compare_data

# ปิด Warning ที่ไม่จำเป็น
warnings.filterwarnings("ignore")

# ==========================================
# 1. ฟังก์ชันคำนวณ WER และ CER
# ==========================================
def calculate_error_rates(reference_text, predicted_text):
    ref = " ".join(reference_text.lower().split())
    pred = " ".join(predicted_text.lower().split())
    
    if not ref: return 0.0, 0.0
    
    try:
        wer = jiwer.wer(ref, pred)
        cer = jiwer.cer(ref, pred)
        return wer * 100, cer * 100
    except Exception:
        return 100.0, 100.0

# ==========================================
# 2. โหลดไฟล์เฉลย (Ground Truth)
# ==========================================
def load_test_cases():
    try:
        with open("benchmarks_and_tools/ground_truth.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ ไม่พบไฟล์ ground_truth.json กรุณารัน prepare_benchmark_data.py ก่อนครับ")
        sys.exit(1)

# ==========================================
# 3. ฟังก์ชันหลักสำหรับรัน Benchmark
# ==========================================
def run_benchmark(model_name):
    print(f"\n🚀 Running Comprehensive Benchmark for: {model_name}")
    
    # ----------------------------------------
    # โหลดโมเดล
    # ----------------------------------------
    start_load = time.time()
    model = None
    stt_type = "openai"

    try:
        if model_name.startswith("openai-"):
            import whisper
            size = model_name.split("-")[1] 
            model = whisper.load_model(size)
            stt_type = "openai"
        elif model_name.startswith("faster-"):
            from faster_whisper import WhisperModel
            size = model_name.split("-")[1]
            # ใช้ cpu และ int8 เพื่อความเร็วในการทดสอบ (ปรับเป็น cuda ได้ถ้ามี GPU)
            model = WhisperModel(size, device="cpu", compute_type="int8")
            stt_type = "faster"
        elif "vosk" in model_name:
            stt_type = "vosk"
            print("⚠️ Vosk implementation is a placeholder in this script.")
        else:
            print(f"❌ Unsupported model: {model_name}")
            return None
    except Exception as e:
        print(f"❌ Error loading model {model_name}: {e}")
        return None
    
    load_time = time.time() - start_load
    print(f"✅ Model loaded in {load_time:.2f}s")

    test_cases = load_test_cases()
    total_wer, total_cer, total_map, total_time = 0, 0, 0, 0
    num_cases = len(test_cases)
    
    results_log = []

    # ----------------------------------------
    # วนลูปทดสอบ
    # ----------------------------------------
    for i, case in enumerate(test_cases, 1):
        audio_path = case["audio_path"]
        ref_text = case["reference_text"]
        truth_json = case["expected_json"]
        
        start_time = time.time()
        
        # 1. STT: แปลงเสียงเป็นข้อความ
        predicted_text = ""
        try:
            if stt_type == "openai":
                initial_prompt = "Surgical number, mastectomy, infiltrative mass, lymph nodes" if "prompt" in model_name else None
                result = model.transcribe(audio_path, initial_prompt=initial_prompt)
                predicted_text = result["text"]
            elif stt_type == "faster":
                segments, _ = model.transcribe(audio_path, beam_size=5)
                predicted_text = " ".join([seg.text for seg in segments])
            elif stt_type == "vosk":
                predicted_text = "mock text for vosk" 
        except Exception as e:
            print(f" Error in STT ({case['case_id']}): {e}")
            predicted_text = ""

        # 2. NLP: ดึงข้อมูลจากข้อความที่ได้
        extracted_json = extract_data_15_sections(predicted_text)

        process_time = time.time() - start_time
        
        # 3. วัดผลคะแนน
        wer, cer = calculate_error_rates(ref_text, predicted_text)
        
        # ใช้ compare_data จาก evaluate_mapping.py เพื่อความแม่นยำ
        total_keys, matched_keys, _, _, _ = compare_data(truth_json, extracted_json)
        map_acc = (matched_keys / total_keys * 100) if total_keys > 0 else 100.0
        
        total_wer += wer
        total_cer += cer
        total_map += map_acc
        total_time += process_time
        
        print(f"[{i}/{num_cases}] {case['case_id']:<35} | WER: {wer:>5.2f}% | Map: {map_acc:>6.2f}% | {process_time:.2f}s")
        
        results_log.append({
            "case": case['case_id'], "wer": wer, "cer": cer, "map": map_acc, "time": process_time, "text": predicted_text
        })

    # ----------------------------------------
    # สรุปผลภาพรวม
    # ----------------------------------------
    avg_wer = total_wer / num_cases
    avg_cer = total_cer / num_cases
    avg_map = total_map / num_cases
    avg_speed = total_time / num_cases
    
    print(f"\n📊 {model_name} SUMMARY:")
    print(f"   Avg WER  : {avg_wer:.2f}%")
    print(f"   Avg CER  : {avg_cer:.2f}%")
    print(f"   Avg Map  : {avg_map:.2f}%")
    print(f"   Avg Speed: {avg_speed:.2f}s/sample\n")
    
    return {
        "model": model_name, 
        "avg_wer": avg_wer, 
        "avg_cer": avg_cer, 
        "avg_map": avg_map, 
        "avg_speed": avg_speed, 
        "load_time": load_time,
        "details": results_log
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Patho Voice Comprehensive STT & NLP Benchmark")
    parser.add_argument("--models", type=str, required=True, help="Comma-separated models: openai-tiny, faster-tiny, vosk")
    args = parser.parse_args()
    
    models_to_test = [m.strip() for m in args.models.split(",")]
    all_results = {}
    
    for m in models_to_test:
        res = run_benchmark(m)
        if res:
            all_results[m] = res
        
    # บันทึกผลลัพธ์
    output_path = "benchmarks_and_tools/comprehensive_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=4, ensure_ascii=False)
        
    print(f"✅ All results saved to {output_path}")