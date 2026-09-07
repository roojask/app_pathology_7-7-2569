import os
import sys
import json
import shutil
from pathlib import Path

# Add project root
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from configs.config import Config
from src.database.models import db, AudioTrainingPair
from src.flywheel.collector import (
    standardize_audio_to_16k_wav,
    deidentify_text,
    construct_verified_narrative,
    calculate_wer_simple,
    capture_audio_training_pair,
    get_flywheel_stats
)
from src.flywheel.exporter import export_clinical_dataset
from app import app

def run_tests():
    print("==================================================")
    print("🧪 Running Clinical Audio Data Flywheel Tests")
    print("==================================================")
    
    # 1. Test De-identification
    print("[Test 1/5] Testing PII De-identification...")
    pii_sample = "ผู้ป่วย นางสาวสมศรี ใจดี HN: 987654321 เลขบัตร 1234567890123 โทร 081-234-5678 พบก้อน infiltrative ductal carcinoma"
    clean_text = deidentify_text(pii_sample)
    assert "987654321" not in clean_text, "HN was not masked!"
    assert "1234567890123" not in clean_text, "Citizen ID was not masked!"
    assert "081-234-5678" not in clean_text, "Phone was not masked!"
    assert "infiltrative ductal carcinoma" in clean_text, "Medical terms must be preserved!"
    print(f"  ✅ De-identification Output: {clean_text}")

    # 2. Test Narrative Construction
    print("\n[Test 2/5] Testing Narrative Construction from 15 Sections...")
    sample_form = {
        "s0_surgical_no": "S-26-9999",
        "s1_side": "right",
        "s2_proc": "modified",
        "s3_dims": ["10.5", "12.0", "5.5"],
        "s4_dims": ["14.0", "6.0"],
        "s10_infiltrative": True,
        "s10_inf_dims": ["2.5", "1.8", "1.2"],
        "s10_5_quadrant_vals": ["upper outer"],
        "s11_deep": "1.2",
        "s14_num": "12",
        "s14_min": "0.5",
        "s14_max": "2.0"
    }
    narrative = construct_verified_narrative(sample_form)
    assert "Surgical number S-26-9999." in narrative
    assert "modified radical mastectomy" in narrative
    assert "10.5 x 12.0 x 5.5 cm" in narrative
    assert "infiltrative firm yellow white mass" in narrative
    assert "Deep margin is 1.2 cm." in narrative
    assert "12 lymph nodes" in narrative
    print(f"  ✅ Synthesized Narrative: {narrative[:90]}...")

    # 3. Test Audio Standardization
    print("\n[Test 3/5] Testing 16kHz WAV Audio Standardization...")
    # Find a sample mp3 in dataset
    sample_mp3 = BASE_DIR / "data" / "dataset_1000" / "audio" / "case_0001.mp3"
    if not sample_mp3.exists():
        sample_mp3 = list(Path(Config.CLINICAL_DATASET_DIR / "audio").glob("*.mp3"))[0]
        
    test_dst_wav = Config.CLINICAL_AUDIO_DIR / "test_standardize.wav"
    duration = standardize_audio_to_16k_wav(sample_mp3, test_dst_wav)
    assert test_dst_wav.exists() and test_dst_wav.stat().st_size > 0
    assert duration > 0.0
    print(f"  ✅ Audio successfully converted to 16kHz WAV (Duration: {duration}s, Size: {test_dst_wav.stat().st_size} bytes)")
    if test_dst_wav.exists():
        test_dst_wav.unlink()

    # 4. Test End-to-End Flywheel Capture & DB Storage
    print("\n[Test 4/5] Testing Asynchronous Flywheel Capture & Database Storage...")
    with app.app_context():
        db.create_all()
        
        # Copy a sample file into UPLOAD_DIR for test
        test_upload_fn = "test_flywheel_mic.mp3"
        upload_dst = Config.UPLOAD_DIR / test_upload_fn
        shutil.copy(sample_mp3, upload_dst)
        
        audio_clips = [{"filename": test_upload_fn, "url": f"/uploads/{test_upload_fn}", "label": "Clip 1"}]
        initial_stt = "surgical number s-26-9999 right modified mastectomy mass 2.5 cm"
        
        from src.database.models import FormHistory
        real_history = FormHistory.query.first()
        test_hid = real_history.id if real_history else None
        
        # Trigger capture
        capture_audio_training_pair(
            app=app,
            history_id=test_hid,
            surgical_number="S-26-9999",
            audio_clips=audio_clips,
            form_data=sample_form,
            initial_stt_text=initial_stt
        )

        
        # Give worker a moment to process
        import time
        time.sleep(2.0)
        
        # Query DB
        record = AudioTrainingPair.query.filter_by(surgical_number="S-26-9999").order_by(AudioTrainingPair.id.desc()).first()
        assert record is not None, "AudioTrainingPair record was not created in DB!"
        assert record.duration_seconds > 0, "Duration was not set!"
        assert Path(record.standardized_wav_path).exists(), "Standardized WAV file was not created on disk!"
        print(f"  ✅ DB Record verified: #{record.id} | File: {record.audio_filename} | Duration: {record.duration_seconds}s | WER: {record.initial_wer}%")

    # 5. Test Statistics & Exporting
    print("\n[Test 5/5] Testing Flywheel Stats & Dataset Exporter...")
    stats = get_flywheel_stats()
    assert stats["total_clips"] > 0, "Total clips must be > 0"
    print(f"  ✅ Live Stats: {stats['total_clips']} clips, {stats['total_seconds']} seconds ({stats['total_hours']} hours), Progress: {stats['progress_percent']}%")
    
    export_res = export_clinical_dataset(output_format="jsonl")
    assert export_res["success"] is True, f"Export failed: {export_res}"
    print(f"  ✅ Dataset Exported: {export_res['count']} items -> {export_res['path']}")

    print("\n🎉 ALL 5 FLYWHEEL TESTS PASSED WITH 100% SUCCESS!")

if __name__ == "__main__":
    run_tests()
