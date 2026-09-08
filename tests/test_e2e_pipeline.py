"""
Comprehensive End-to-End (E2E) System Test Suite for PathoWhisper Assistant
Validates the complete 6-stage clinical pipeline from raw audio to final medical reports.
"""

import sys
import os
import time
import json
import base64
import unittest
from pathlib import Path
from io import BytesIO

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from configs.config import Config
from app import app, db
from src.database.models import User, FormHistory, CaseRevision
from src.stt.whisper_model import denoise_audio, transcribe_audio
from src.nlp.normalizer import normalize_text
from src.nlp.extractor import extract_data_15_sections, generate_confidence_flags
from src.pdf.generator import process_pdf_15_sections
from src.export.docx_exporter import generate_docx_document

import fitz
import docx

# 1x1 Red Pixel PNG in Base64 for Mock Specimen Macro Photo
MOCK_BASE64_PHOTO = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

class TestPathoWhisperE2EPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("\n" + "=" * 80)
        print("🧪 [E2E TEST SUITE] Starting Complete End-to-End Pipeline Verification")
        print("=" * 80)
        
        cls.app = app
        cls.client = app.test_client()
        cls.sample_audio = BASE_DIR / "data" / "audio_cases" / "case_01_perfect_standard_right.mp3"
        if not cls.sample_audio.exists():
            cls.sample_audio = BASE_DIR / "data" / "dataset_1000" / "audio" / "case_0001.mp3"

        cls.test_outputs = []
        cls.test_db_records = []

    @classmethod
    def tearDownClass(cls):
        print("\n" + "-" * 80)
        print("🧹 Cleaning up temporary test artifacts...")
        for p in cls.test_outputs:
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

        with app.app_context():
            for hist_id in cls.test_db_records:
                try:
                    h = FormHistory.query.get(hist_id)
                    if h:
                        CaseRevision.query.filter_by(history_id=hist_id).delete()
                        db.session.delete(h)
                    db.session.commit()
                except Exception:
                    db.session.rollback()

            # Resynchronize sequence counter to real MAX(id) so tests don't leave gaps
            try:
                from sqlalchemy import text
                max_id = db.session.execute(text("SELECT COALESCE(MAX(id), 0) FROM form_history;")).scalar()
                db.session.execute(text(f"SELECT setval('public.form_history_id_seq', {max_id}, true);"))
                db.session.commit()
            except Exception as seq_err:
                print(f"[TEARDOWN POSTGRES SEQ NOTE] {seq_err}")

        # Airtight cleanup: also prune test records from SQLite shadow mirror
        try:
            import sqlite3
            sq_path = BASE_DIR / "data" / "instance" / "local_pathology.db"
            if sq_path.exists():
                sq_c = sqlite3.connect(sq_path)
                sq_cur = sq_c.cursor()
                for hist_id in cls.test_db_records:
                    sq_cur.execute("DELETE FROM form_history WHERE id = ?;", (hist_id,))
                    sq_cur.execute("DELETE FROM specimen_photo WHERE history_id = ?;", (hist_id,))
                sq_cur.execute("UPDATE sqlite_sequence SET seq = (SELECT COALESCE(MAX(id), 0) FROM form_history) WHERE name = 'form_history';")
                sq_c.commit()
                sq_c.close()
        except Exception as sq_e:
            print(f"[TEARDOWN SQLITE NOTE] {sq_e}")

        print("✅ Cleanup complete and database sequences resynchronized.")
        print("=" * 80)

    def test_01_audio_spectral_denoising(self):
        """STAGE 1: Audio Signal Ingestion & Spectral Denoising (afftdn)"""
        print("\n[Stage 1/6] Testing Audio Signal Ingestion & Spectral Denoising...")
        self.assertTrue(self.sample_audio.exists(), f"Sample audio missing: {self.sample_audio}")
        
        t0 = time.time()
        denoised_audio = denoise_audio(self.sample_audio)
        latency = time.time() - t0
        
        self.assertTrue(denoised_audio.exists(), "Denoised audio file was not generated.")
        self.assertGreater(denoised_audio.stat().st_size, 1000, "Denoised audio file is too small.")
        print(f"  ✓ Spectral Denoise completed in {latency*1000:.1f} ms")
        print(f"  ✓ Processed Audio Path: {denoised_audio.name} ({denoised_audio.stat().st_size:,} bytes)")

    def test_02_speech_to_text_whisper(self):
        """STAGE 2: ASR Speech-to-Text Transcription (Whisper Engine)"""
        print("\n[Stage 2/6] Testing Speech-to-Text Transcription (Whisper Engine)...")
        t0 = time.time()
        transcript = transcribe_audio(self.sample_audio)
        latency = time.time() - t0
        
        self.assertIsInstance(transcript, str)
        self.assertNotIn("Error during transcription", transcript)
        self.assertGreater(len(transcript), 20, "Transcript is too short.")
        
        t_lower = transcript.lower()
        has_medical_term = any(k in t_lower for k in ["mastectomy", "specimen", "mass", "breast", "cm", "infiltrative"])
        self.assertTrue(has_medical_term, f"Transcript did not contain expected pathology keywords: {transcript}")
        
        print(f"  ✓ Whisper Transcription completed in {latency:.2f} s")
        print(f"  ✓ Transcribed Raw Text ({len(transcript)} chars): '{transcript[:75]}...'")
        self.__class__.raw_transcript = transcript

    def test_03_clinical_nlp_extraction(self):
        """STAGE 3: Clinical Text Normalization & 15-Section NLP Extraction"""
        print("\n[Stage 3/6] Testing Clinical Text Normalization & 15-Section NLP Extraction...")
        transcript = getattr(self.__class__, "raw_transcript", (
            "Surgical number S-26-1001. Received in formalin is a right modified radical mastectomy "
            "specimen measuring 15 by 12 by 4.5 cm. Skin ellipse measures 10 by 5 cm. "
            "Infiltrative firm yellow-white mass measuring 2.5 by 2.0 by 1.5 cm at upper outer quadrant. "
            "Deep margin is 1.2 cm from mass. 12 lymph nodes identified."
        ))
        
        t0 = time.time()
        norm_text = normalize_text(transcript)
        extracted = extract_data_15_sections(norm_text)
        flags = generate_confidence_flags(extracted)
        latency = time.time() - t0
        
        self.assertIsInstance(extracted, dict)
        self.assertIn("s1_side", extracted)
        self.assertIn("s2_proc", extracted)
        self.assertIn("s3_dims", extracted)
        
        print(f"  ✓ NLP Extraction completed in {latency*1000:.2f} ms")
        print(f"  ✓ Surgical Number   : {extracted.get('s0_surgical_no')}")
        print(f"  ✓ Specimen Side     : {extracted.get('s1_side')}")
        print(f"  ✓ Procedure Type    : {extracted.get('s2_proc')}")
        print(f"  ✓ Specimen 3D Dims  : {extracted.get('s3_dims')}")
        print(f"  ✓ Mass 3D Dims      : {extracted.get('s10_inf_dims')}")
        self.__class__.extracted_data = extracted

    def test_04_postgresql_database_persistence(self):
        """STAGE 4: PostgreSQL In-Database Direct Storage & Audit Trail (with Base64 Photo)"""
        print("\n[Stage 4/6] Testing PostgreSQL Database Direct Storage & Audit Trail...")
        data = getattr(self.__class__, "extracted_data", {})
        
        with app.app_context():
            user = User.query.first()
            if not user:
                user = User(username="e2e_tester", email="e2e@test.local", name="E2E Pipeline Tester")
                user.set_password("E2ePass123!")
                db.session.add(user)
                db.session.commit()
            
            t0 = time.time()
            record = FormHistory(
                user_id=user.id,
                surgical_number=data.get("s0_surgical_no", "S-26-E2E-TEST"),
                form_data=json.dumps(data),
                photo_data=MOCK_BASE64_PHOTO,
                audio_filename="case_01_perfect_standard_right.mp3"
            )
            db.session.add(record)
            db.session.commit()
            
            rev = CaseRevision(
                history_id=record.id,
                revision_number=1,
                user_id=user.id,
                action="create",
                full_snapshot=json.dumps(data),
                changes_summary="Initial automated E2E test ingestion"
            )
            db.session.add(rev)
            db.session.commit()
            
            latency = time.time() - t0
            self.__class__.test_db_records.append(record.id)
            
            queried = FormHistory.query.get(record.id)
            self.assertIsNotNone(queried, "Failed to query back stored case from database.")
            self.assertEqual(queried.surgical_number, record.surgical_number)
            self.assertEqual(queried.photo_data, MOCK_BASE64_PHOTO, "Base64 photo was corrupted or modified in database.")
            
            parsed_data = json.loads(queried.form_data)
            self.assertIsInstance(parsed_data, dict)
            self.assertEqual(parsed_data.get("s1_side"), data.get("s1_side"))
            
            print(f"  ✓ Database Commit & Integrity Verification completed in {latency*1000:.2f} ms")
            print(f"  ✓ Record ID #{record.id} stored in PostgreSQL successfully.")
            print(f"  ✓ Verified In-Database Base64 Photo Storage ({len(queried.photo_data)} bytes).")

    def test_05_document_generation_pdf_and_docx(self):
        """STAGE 5: Multi-Format Medical Document Generation Engine (PDF & DOCX)"""
        print("\n[Stage 5/6] Testing Document Generation Engine (CAP PDF & Hospital DOCX)...")
        data = getattr(self.__class__, "extracted_data", {
            "s0_surgical_no": "S-26-E2E-TEST",
            "s1_side": "right",
            "s2_proc": "modified",
            "s3_dims": ["15.0", "12.0", "4.5"],
            "s10_infiltrative": True,
            "s10_inf_dims": ["2.5", "2.0", "1.5"],
            "s11_deep": "1.2",
            "s14_check": True
        })
        
        pdf_out = Config.OUTPUT_DIR / f"e2e_test_cap_{int(time.time())}.pdf"
        self.__class__.test_outputs.append(pdf_out)
        
        t0 = time.time()
        process_pdf_15_sections(Config.PDF_TEMPLATE_PATH, pdf_out, data)
        pdf_time = time.time() - t0
        
        self.assertTrue(pdf_out.exists(), "Output PDF file was not created.")
        self.assertGreater(pdf_out.stat().st_size, 50000, "Output PDF file is unexpectedly small.")
        
        doc = fitz.open(pdf_out)
        self.assertGreaterEqual(len(doc), 1, "PDF has 0 pages.")
        doc.close()
        print(f"  ✓ CAP Protocol PDF generated in {pdf_time*1000:.1f} ms ({pdf_out.stat().st_size:,} bytes)")
        
        docx_out = Config.OUTPUT_DIR / f"e2e_test_hospital_{int(time.time())}.docx"
        self.__class__.test_outputs.append(docx_out)
        
        t0 = time.time()
        docx_buf = generate_docx_document(data)
        with open(docx_out, "wb") as f:
            f.write(docx_buf.getvalue())
        docx_time = time.time() - t0
        
        self.assertTrue(docx_out.exists(), "Output DOCX file was not created.")
        self.assertGreater(docx_out.stat().st_size, 10000, "Output DOCX file is unexpectedly small.")
        
        w_doc = docx.Document(docx_out)
        self.assertGreater(len(w_doc.paragraphs), 5, "DOCX has insufficient paragraphs.")
        print(f"  ✓ Hospital Word DOCX generated in {docx_time*1000:.1f} ms ({docx_out.stat().st_size:,} bytes)")

    def test_06_web_api_end_to_end_flow(self):
        """STAGE 6: Web Application Endpoints & Full Session Integration"""
        print("\n[Stage 6/6] Testing Web Application API Endpoints & Session Integration...")
        
        res_index = self.client.get("/")
        self.assertEqual(res_index.status_code, 200, "Landing page did not return HTTP 200.")
        self.assertTrue(
            b"Patho Voice Assistant" in res_index.data or b"Gross reporting" in res_index.data or b"Patho" in res_index.data,
            "Page header did not match expected application branding."
        )
        print("  ✓ Landing Page GET / -> HTTP 200 OK")
        
        res_extract = self.client.post("/api/extract", json={
            "text": "Surgical number S-26-9999 right simple mastectomy measuring 18 x 10 x 3 cm."
        })
        self.assertEqual(res_extract.status_code, 200)
        res_json = res_extract.get_json()
        self.assertTrue(res_json.get("success"))
        self.assertEqual(res_json.get("data", {}).get("s1_side"), "right")
        self.assertEqual(res_json.get("data", {}).get("s2_proc"), "simple")
        print("  ✓ NLP Extraction API POST /api/extract -> HTTP 200 OK")
        
        post_data = {
            "s0_surgical_no": "S-26-E2E-API",
            "s1_side": "right",
            "s2_proc": "modified",
            "s3_dims_0": "15", "s3_dims_1": "10", "s3_dims_2": "4",
            "s10_infiltrative": "on",
            "s10_inf_dims_0": "3", "s10_inf_dims_1": "2", "s10_inf_dims_2": "2",
            "s11_deep": "1.0",
            "photo_data": MOCK_BASE64_PHOTO
        }
        res_gen = self.client.post("/generate", data=post_data)
        self.assertEqual(res_gen.status_code, 200)
        self.assertIn(b"pdf", res_gen.data.lower())
        
        # Track generated test case for cleanup
        with app.app_context():
            created_case = FormHistory.query.filter_by(surgical_number="S-26-E2E-API").first()
            if created_case:
                self.__class__.test_db_records.append(created_case.id)
                
        print("  ✓ Medical Form Save & Document Export POST /generate -> HTTP 200 OK")

if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPathoWhisperE2EPipeline)
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    
    print("\n" + "=" * 80)
    print(f"📊 [E2E TEST SUMMARY]: {'ALL PASS (6/6 STAGES SUCCESSFUL)' if result.wasSuccessful() else 'FAILED'}")
    print(f"   • Total Tests Run : {result.testsRun}")
    print(f"   • Failures         : {len(result.failures)}")
    print(f"   • Errors           : {len(result.errors)}")
    print("=" * 80)
    
    sys.exit(0 if result.wasSuccessful() else 1)
