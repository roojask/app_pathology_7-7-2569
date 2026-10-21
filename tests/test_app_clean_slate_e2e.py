"""
End-to-End Integration Test for PathoWhisper Flask Web Application (`app.py`)
with Clean-Slate S3 Pipeline:
  1. Blind SNR-Gated Adaptive Denoising (`D8_snr_gated`, tau* = 13.55 dB, afftdn nr = 6 dB)
  2. Fine-Tuned Whisper Small LoRA CTranslate2 INT8 Engine (`models/pathowhisper_lora_int8` / `200_int8`)
  3. Phonetic-Contrastive Prompt (`P4`)
  4. 15-Field CAP Breast Cancer Extractor (`extractor.py` v3) + Multi-Signal Clinical Safety Flagging
  5. PDF Report Generation (`process_pdf_15_sections`)
"""
import io
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import app
from src.pdf.generator import process_pdf_15_sections
from configs.config import Config


def run_e2e_tests():
    client = app.test_client()
    print("=" * 72)
    print("PATHOWHISPER FLASK WEB APP END-TO-END INTEGRATION TEST (S3 PIPELINE)")
    print("=" * 72)

    # 1. Test /api/extract with 15-field clinical dictation + self-correction
    sample_text = (
        "Surgical specimen number S-26-08412. Received in formalin is a right modified radical mastectomy "
        "specimen measuring 18.0 x 14.0 x 4.0 cm, sorry wait measuring 19.5 x 15.2 x 4.8 cm. "
        "The skin ellipse measures 12.4 x 6.2 cm and shows a healed biopsy scar. "
        "The nipple is everted. "
        "On serial sectioning, there is an infiltrative firm yellow-white mass measuring 3.2 x 2.5 x 1.8 cm "
        "located in the upper outer quadrant. "
        "Resection margins: deep margin is clear at 1.4 cm, superior margin 2.8 cm, inferior margin 2.1 cm, "
        "medial margin 3.5 cm, lateral margin 2.9 cm. "
        "Axillary contents reveal 14 lymph nodes ranging from 0.4 to 1.6 cm."
    )
    resp = client.post("/api/extract", json={"text": sample_text})
    assert resp.status_code == 200, f"/api/extract failed with {resp.status_code}"
    payload = resp.get_json()
    assert payload["success"] is True
    data = payload["data"]
    flags = payload["flags"]
    print("\n[Test 1: /api/extract (15-Field NLP + Self-Correction)]")
    print(f"  s0_surgical_no : {data.get('s0_surgical_no')} (Expected: S-26-08412)")
    print(f"  s1_side / s2   : {data.get('s1_side')} / {data.get('s2_proc')}")
    print(f"  s3_dims (corr) : {data.get('s3_dims')} (Expected: ['19.5', '15.2', '4.8'])")
    print(f"  s5_dims / scar : {data.get('s5_dims')} / s6_check={data.get('s6_check')}")
    print(f"  s9_val (nipple): {data.get('s9_val')}")
    print(f"  s10_inf_dims   : {data.get('s10_inf_dims')} @ {data.get('s10_5_quadrant_vals')}")
    print(f"  s11_margins    : deep={data.get('s11_deep')}, sup={data.get('s11_superior')}, inf={data.get('s11_inferior')}, med={data.get('s11_medial')}, lat={data.get('s11_lateral')}")
    print(f"  s14_lymph_nodes: check={data.get('s14_check')}, num={data.get('s14_num')}, range={data.get('s14_min')}-{data.get('s14_max')}")
    print(f"  Safety Flags   : {flags} (Expected: {{}})")
    assert data.get("s0_surgical_no") == "S-26-08412"
    assert data.get("s3_dims") == ["19.5", "15.2", "4.8"]
    assert data.get("s10_inf_dims") == ["3.2", "2.5", "1.8"]
    assert data.get("s11_deep") == "1.4"
    assert data.get("s14_num") == "14"
    assert len(flags) == 0

    # 2. Test /api/extract Safety Flagging on Phonetic Ambiguity & Missing Margin
    risky_text = (
        "Surgical number S-26-09911. Write simple mastectomy measuring 16.0 x 12.0 x 3.5 cm. "
        "There is an infiltrative mass measuring 2.2 x 1.8 x 1.5 cm in the lower inner quadrant. "
        "No deep margin reported."
    )
    resp2 = client.post("/api/extract", json={"text": risky_text})
    p2 = resp2.get_json()
    print("\n[Test 2: /api/extract (Multi-Signal Safety Flagging on Risky Input)]")
    print(f"  Triggered Flags: {p2['flags']}")
    assert p2["flags"].get("homophone_write_for_right") is True
    assert p2["flags"].get("mass_missing_deep_margin") is True

    # 3. Test /api/upload_audio with Clean Audio & Noisy (-10 dB) Audio from test_seen
    manifest_path = BASE_DIR / "data" / "dataset_ft" / "test_seen.jsonl"
    cases = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    clean_case = next(c for c in cases if c.get("snr_tag") == "clean" or c.get("snr_db") is None)
    noisy_case = next(c for c in cases if c.get("snr_tag") == "snr_m10dB" or c.get("snr_db") == -10)

    for label, case, expect_denoise in [
        ("CLEAN AUDIO (Blind SNR >= 13.55 dB -> Bypass afftdn)", clean_case, False),
        ("NOISY -10 dB AUDIO (Blind SNR < 13.55 dB -> Apply afftdn nr=6dB)", noisy_case, True),
    ]:
        wav_path = BASE_DIR / "data" / "dataset_ft" / case["audio"]
        with open(wav_path, "rb") as f:
            wav_bytes = f.read()
        resp_audio = client.post(
            "/api/upload_audio?transcribe=true",
            data={"audio": (io.BytesIO(wav_bytes), wav_path.name)},
            content_type="multipart/form-data",
        )
        assert resp_audio.status_code == 200, f"/api/upload_audio failed: {resp_audio.status_code}"
        res_json = resp_audio.get_json()
        assert res_json["success"] is True
        print(f"\n[Test 3: /api/upload_audio — {label}]")
        print(f"  Case ID          : {case['case_id']} (Category {case['category']}, Ground-Truth SNR={case.get('snr_db')})")
        print(f"  Blind SNR (dB)   : {res_json.get('snr_db')} dB | Denoise Applied: {res_json.get('denoised_applied')} (Expected: {expect_denoise})")
        print(f"  Acoustic Conf    : avg_logprob={res_json.get('avg_logprob')}, min_word_prob={res_json.get('min_word_prob')}")
        print(f"  Transcription    : {res_json.get('transcription')[:140]}...")
        print(f"  Extracted Fields : s0={res_json['data'].get('s0_surgical_no')}, s1={res_json['data'].get('s1_side')}, s2={res_json['data'].get('s2_proc')}, s3={res_json['data'].get('s3_dims')}")
        print(f"  Safety Flags     : {res_json.get('flags')}")
        assert res_json.get("denoised_applied") is expect_denoise

    # 4. Test PDF Report Generator (`process_pdf_15_sections`)
    out_pdf = Config.OUTPUT_DIR / "test_clean_slate_e2e_report.pdf"
    process_pdf_15_sections(Config.PDF_TEMPLATE_PATH, out_pdf, data)
    assert out_pdf.exists() and out_pdf.stat().st_size > 1000
    print(f"\n[Test 4: PDF Report Generation (`process_pdf_15_sections`)]")
    print(f"  Generated PDF    : {out_pdf} ({out_pdf.stat().st_size:,} bytes)")
    print("\nALL 4 END-TO-END WEB APPLICATION TESTS PASSED 100%!")


if __name__ == "__main__":
    run_e2e_tests()
