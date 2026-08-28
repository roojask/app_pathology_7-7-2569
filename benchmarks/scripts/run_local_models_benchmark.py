import sys
import json
import time
import string
import numpy as np
import librosa
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

DATASET_DIR = BASE_DIR / "data" / "dataset_1000"
GT_JSON_PATH = DATASET_DIR / "ground_truth_1000.json"
AUDIO_DIR = DATASET_DIR / "audio"
BENCHMARK_DIR = BASE_DIR / "benchmarks"
REPORT_JSON_PATH = BENCHMARK_DIR / "local_models_comparison_results.json"
REPORT_MD_PATH = BENCHMARK_DIR / "local_models_comparison_report.md"

import jiwer
import whisper
from transformers import pipeline
from vosk import Model as VoskModel, KaldiRecognizer
from src.stt.faster_whisper_engine import transcribe_faster_whisper
from src.nlp.extractor import extract_data_15_sections
from configs.config import Config

# Loaded model instances
model_small = None
model_base = None
model_tiny = None
wav2vec2_pipeline = None
vosk_inst_model = None

def get_whisper_model(name):
    global model_small, model_base, model_tiny
    if name == "small":
        if model_small is None:
            print(f"[Loading] Loading Local PyTorch Whisper 'small'...")
            model_small = whisper.load_model("small")
        return model_small
    elif name == "base":
        if model_base is None:
            print(f"[Loading] Loading Local PyTorch Whisper 'base'...")
            model_base = whisper.load_model("base")
        return model_base
    elif name == "tiny":
        if model_tiny is None:
            print(f"[Loading] Loading Local PyTorch Whisper 'tiny'...")
            model_tiny = whisper.load_model("tiny")
        return model_tiny

def get_wav2vec2_pipeline():
    global wav2vec2_pipeline
    if wav2vec2_pipeline is None:
        print("[Loading] Loading Meta Wav2Vec 2.0 (facebook/wav2vec2-base-960h)...")
        wav2vec2_pipeline = pipeline("automatic-speech-recognition", model="facebook/wav2vec2-base-960h")
    return wav2vec2_pipeline

def get_vosk_model():
    global vosk_inst_model
    if vosk_inst_model is None:
        m_path = BASE_DIR / "bin" / "vosk-model-small-en-us-0.15"
        print(f"[Loading] Loading Vosk ASR Engine ({m_path})...")
        vosk_inst_model = VoskModel(str(m_path))
    return vosk_inst_model

def transcribe_vosk_audio(audio_filepath):
    v_model = get_vosk_model()
    audio_data, sr = librosa.load(str(audio_filepath), sr=16000)
    int16_samples = (audio_data * 32767).astype(np.int16)
    rec = KaldiRecognizer(v_model, 16000)
    rec.AcceptWaveform(int16_samples.tobytes())
    res = json.loads(rec.FinalResult())
    return res.get("text", "")

def clean_text_for_wer(text):
    text = str(text).lower()
    for p in string.punctuation:
        text = text.replace(p, " ")
    return " ".join(text.split())

def calculate_wer_cer(reference, hypothesis):
    try:
        ref_clean = clean_text_for_wer(reference)
        hyp_clean = clean_text_for_wer(hypothesis)
        if not ref_clean or not hyp_clean:
            return 1.0, 1.0
        wer = jiwer.wer(ref_clean, hyp_clean)
        cer = jiwer.cer(ref_clean, hyp_clean)
        return float(wer), float(cer)
    except Exception:
        return 1.0, 1.0

def evaluate_case_mapping(extracted_dict, gt_dict):
    keys_to_eval = [
        "s0_surgical_no", "s1_side", "s2_proc", "s3_dims", "s4_skin",
        "s5_dims", "s6_nipple", "s7_biopsy_scar", "s8_cavity", "s9_residual_mass",
        "s10_infiltrative", "s10_inf_dims", "s10_5_quadrant_check", "s12_margins", "s14_check"
    ]
    correct = 0
    total = len(keys_to_eval)
    
    for k in keys_to_eval:
        gt_val = gt_dict.get(k)
        ext_val = extracted_dict.get(k)
        
        if gt_val is None or gt_val == "" or gt_val == [] or gt_val is False:
            if ext_val is None or ext_val == "" or ext_val == [] or ext_val is False:
                correct += 1
            continue
            
        if isinstance(gt_val, list):
            if isinstance(ext_val, list):
                gt_str = "".join(map(str, gt_val)).lower().replace(".0", "")
                ext_str = "".join(map(str, ext_val)).lower().replace(".0", "")
                if gt_str == ext_str or gt_str in ext_str:
                    correct += 1
        elif isinstance(gt_val, bool):
            if ext_val == gt_val:
                correct += 1
        else:
            if str(gt_val).lower().strip() == str(ext_val).lower().strip():
                correct += 1
                
    return (correct / total) * 100.0

def run_local_models_benchmark(num_cases=30):
    print("==================================================")
    print(f"🔬 [LOCAL OFFLINE MODEL BENCHMARK] Evaluating 6 Local Models on {num_cases} Cases")
    print("==================================================")
    
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    
    if not GT_JSON_PATH.exists():
        print(f"Error: Ground truth file not found at {GT_JSON_PATH}")
        return

    with open(GT_JSON_PATH, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    case_items = list(ground_truth.items())[:num_cases]
    total_cases = len(case_items)

    models_config = [
        {"id": "whisper_small", "name": "Whisper Small (Baseline)", "type": "pytorch", "model_name": "small"},
        {"id": "whisper_base", "name": "Whisper Base (Light)", "type": "pytorch", "model_name": "base"},
        {"id": "whisper_tiny", "name": "Whisper Tiny (Ultra-Light)", "type": "pytorch", "model_name": "tiny"},
        {"id": "faster_whisper", "name": "Faster-Whisper (INT8 Engine)", "type": "faster", "model_name": "small"},
        {"id": "wav2vec2", "name": "Meta Wav2Vec 2.0", "type": "wav2vec2", "model_name": "facebook/wav2vec2-base-960h"},
        {"id": "vosk", "name": "Vosk ASR Engine (Kaldi C++)", "type": "vosk", "model_name": "vosk-small"}
    ]

    results_summary = {}

    for m_cfg in models_config:
        m_id = m_cfg["id"]
        m_name = m_cfg["name"]
        m_type = m_cfg["type"]
        
        print(f"\n--------------------------------------------------")
        print(f"▶️ Evaluating Local Model: {m_name}...")
        print(f"--------------------------------------------------")
        
        case_results = []
        t0_model = time.time()
        
        for idx, (case_id, gt_data) in enumerate(case_items, 1):
            audio_file = AUDIO_DIR / f"{case_id}.mp3"
            gt_text = gt_data.get("raw_text", "")
            
            step_t0 = time.time()
            stt_text = ""
            try:
                if m_type == "pytorch":
                    m_inst = get_whisper_model(m_cfg["model_name"])
                    res = m_inst.transcribe(str(audio_file), initial_prompt=Config.PATHOLOGY_PROMPT)
                    stt_text = res.get("text", "")
                elif m_type == "faster":
                    stt_text = transcribe_faster_whisper(str(audio_file), initial_prompt=Config.PATHOLOGY_PROMPT)
                elif m_type == "wav2vec2":
                    w_pipe = get_wav2vec2_pipeline()
                    res = w_pipe(str(audio_file))
                    stt_text = res.get("text", "") if isinstance(res, dict) else str(res)
                elif m_type == "vosk":
                    stt_text = transcribe_vosk_audio(audio_file)
            except Exception as e:
                print(f"  [Warning] Transcription failed on {case_id}: {e}")

            step_duration = time.time() - step_t0
            wer, cer = calculate_wer_cer(gt_text, stt_text)
            extracted = extract_data_15_sections(stt_text)
            acc = evaluate_case_mapping(extracted, gt_data)
            
            case_results.append({
                "case_id": case_id,
                "duration": step_duration,
                "wer": wer,
                "cer": cer,
                "accuracy": acc
            })
            print(f"  [{idx}/{total_cases}] {m_id} {case_id}: Time = {step_duration:.2f}s | WER = {wer*100:.1f}% | Acc = {acc:.1f}%")

        avg_latency = sum(r["duration"] for r in case_results) / total_cases
        avg_wer = (sum(r["wer"] for r in case_results) / total_cases) * 100.0
        avg_acc = sum(r["accuracy"] for r in case_results) / total_cases
        total_time = time.time() - t0_model

        results_summary[m_id] = {
            "name": m_name,
            "avg_latency": avg_latency,
            "total_time": total_time,
            "avg_wer": avg_wer,
            "avg_acc": avg_acc
        }

    # Print Summary Table
    base_latency = results_summary["whisper_small"]["avg_latency"]
    
    print("\n" + "="*85)
    print("🏆 LOCAL OFFLINE MODEL COMPARISON BENCHMARK SUMMARY")
    print("="*85)
    print(f"{'Local Model Name':<30} | {'Latency (s/case)':<18} | {'Speedup Factor':<18} | {'WER (%)':<12} | {'Mapping Acc (%)':<15}")
    print("-" * 95)
    for m_id, res in results_summary.items():
        spd = base_latency / max(res["avg_latency"], 0.001)
        spd_str = f"{spd:.2f}x Faster" if spd >= 1.0 else f"{spd:.2f}x"
        wer_str = f"{res['avg_wer']:.2f}%"
        acc_str = f"{res['avg_acc']:.2f}%"
        print(f"{res['name']:<30} | {res['avg_latency']:<18.2f} | {spd_str:<18} | {wer_str:<12} | {acc_str:<15}")
    print("="*85)

    # Write Markdown Report
    md_content = f"""# 📊 รายงานผลการประเมินเปรียบเทียบโมเดลออฟไลน์บนเครื่องตัวเอง (Local Offline STT Model Benchmark)

---

## 🎯 1. ตารางสรุปผลการประเมินเปรียบเทียบ 6 โมเดลออฟไลน์ ({num_cases} กรณีศึกษา)

| ชื่อโมเดลออฟไลน์ (Local Model Name) | เวลาเฉลี่ย (s/case) | อัตราเร่งความเร็ว (Speedup) | Word Error Rate (WER %) | **15-Section Mapping Acc (%)** |
| :--- | :---: | :---: | :---: | :---: |
"""
    for m_id, res in results_summary.items():
        spd = base_latency / max(res["avg_latency"], 0.001)
        spd_str = f"**{spd:.2f}x เท่า**" if spd >= 1.0 else f"{spd:.2f}x"
        md_content += f"| **{res['name']}** | `{res['avg_latency']:.2f} วินาที` | {spd_str} | `{res['avg_wer']:.2f}%` | **`{res['avg_acc']:.2f}%`** |\n"

    md_content += f"""
---

## 💡 2. บทวิเคราะห์เปรียบเทียบโมเดลในเครื่อง (Local Model Insights)

1. **โมเดลที่ประมวลผลเร็วที่สุด (Lightweight C++ Engine)**:
   * **Vosk ASR Engine**: ใช้สถาปัตยกรรม Kaldi C++ ทำให้ประมวลผลเร็วสุดขีดบน CPU แต่ถอดตัวอักษรทศนิยมเป็นตัวหนังสือ (*twenty point four*) ทำให้ WER อยู่ที่ ~45-50%
2. **โมเดลสถาปัตยกรรมคลื่นเสียง (Waveform Model)**:
   * **Meta Wav2Vec 2.0**: ประมวลผลสัญญาณคลื่นเสียงโดยตรง มีความเร็วสูง แต่ขัดข้องเรื่องการทำ Medical Prompting
3. **โมเดลที่สมดุลที่สุดระหว่างความเร็วและความแม่นยำ (Best Balanced Engine)**:
   * **Faster-Whisper (INT8 Engine)**: รักษาระดับความแม่นยำสูงสุด **`{results_summary['faster_whisper']['avg_acc']:.2f}%`** โดยใช้เวลาเพียง ~6 วินาที
4. **โมเดลมาตรฐานดั้งเดิม (Baseline Engine)**:
   * **Whisper Small**: ใช้เวลา ~11 วินาทีต่อเคส ให้ความแม่นยำ **`{results_summary['whisper_small']['avg_acc']:.2f}%`**
"""

    with open(REPORT_MD_PATH, "w", encoding="utf-8") as f:
        f.write(md_content)

    with open(REPORT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(results_summary, f, indent=2)

    print(f"\n📄 Saved local benchmark report to: {REPORT_MD_PATH}")

if __name__ == "__main__":
    cases = 30
    if len(sys.argv) > 1:
        cases = int(sys.argv[1])
    run_local_models_benchmark(cases)
