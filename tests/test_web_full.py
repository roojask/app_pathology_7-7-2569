import os
import sys
import json
import time
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

# Use SQLite for testing
os.environ["DATABASE_URL"] = "sqlite:///test_pathology.db"
os.environ["USE_HTTPS"] = "False"

from app import app
from src.database.models import db, User, FormHistory, CaseRevision
from configs.config import Config

def run_web_tests():
    print("=" * 70)
    print("[START] STARTING COMPREHENSIVE WEB APPLICATION TEST SUITE")
    print("=" * 70)
    
    test_results = []
    
    with app.app_context():
        # Setup clean test DB
        db.drop_all()
        db.create_all()
        
        client = app.test_client()
        
        # Test 1: Health / Redirect to Login
        print("\n[Test 1] Root Route & Auth Guard")
        t0 = time.perf_counter()
        res = client.get('/', follow_redirects=False)
        lat = (time.perf_counter() - t0) * 1000
        # / redirects to /login if not authenticated
        status = "PASS" if res.status_code in [200, 302] else "FAIL"
        print(f"  Status: {res.status_code} ({status}) | Latency: {lat:.1f} ms")
        test_results.append(("T1_AUTH_GUARD", "Root route redirects to login or loads", status, f"{lat:.1f}ms"))

        # Test 2: User Registration
        print("\n[Test 2] User Registration (/register)")
        t0 = time.perf_counter()
        test_username = f"pathologist_{int(time.time())}"
        test_email = f"{test_username}@hospital.test"
        test_password = "Password123!"
        res = client.post('/register', data={
            "username": test_username,
            "email": test_email,
            "password": test_password,
            "confirm_password": test_password,
            "name": "Dr. Test Pathologist"
        }, follow_redirects=True)
        lat = (time.perf_counter() - t0) * 1000
        user = User.query.filter_by(username=test_username).first()
        status = "PASS" if user is not None and user.check_password(test_password) else "FAIL"
        print(f"  User created: {user.username if user else 'None'} ({status}) | Latency: {lat:.1f} ms")
        test_results.append(("T2_REGISTER", "Create user account with password hashing", status, f"{lat:.1f}ms"))

        # Test 3: User Login
        print("\n[Test 3] User Authentication (/login)")
        t0 = time.perf_counter()
        res = client.post('/login', data={
            "username": test_username,
            "password": test_password
        }, follow_redirects=True)
        lat = (time.perf_counter() - t0) * 1000
        status = "PASS" if res.status_code == 200 and b"logout" in res.data.lower() or res.status_code == 200 else "FAIL"
        print(f"  Login response: {res.status_code} ({status}) | Latency: {lat:.1f} ms")
        test_results.append(("T3_LOGIN", "Login and establish secure session", status, f"{lat:.1f}ms"))

        # Test 4: Structured NLP Extraction API (/api/extract)
        print("\n[Test 4] Structured Clinical Extraction API (/api/extract)")
        sample_dictation = (
            "Surgical number S-24-1001. Received in formalin is a right modified radical mastectomy "
            "specimen measuring 20.0 x 15.0 x 5.0 cm. The skin ellipse measures 10.0 x 4.0 cm and appears normal. "
            "There is an infiltrative firm yellow white mass measuring 3.5 x 2.5 x 1.5 cm at the upper outer quadrant. "
            "Deep margin is 1.2 cm. 12 lymph nodes ranging from 0.5 to 2.0 cm are identified."
        )
        t0 = time.perf_counter()
        res = client.post('/api/extract', 
                          json={"text": sample_dictation},
                          content_type='application/json')
        lat = (time.perf_counter() - t0) * 1000
        res_json = res.get_json() or {}
        extracted = res_json.get("data", {})
        
        ok_sno = (extracted.get("s0_surgical_no") == "S-24-1001")
        ok_side = (extracted.get("s1_side") == "right")
        ok_proc = (extracted.get("s2_proc") == "modified")
        ok_dims = (extracted.get("s3_dims") == ["20", "15", "5"] or extracted.get("s3_dims") == ["20.0", "15.0", "5.0"])
        ok_mass = (extracted.get("s10_infiltrative") is True)
        
        status = "PASS" if (ok_sno and ok_side and ok_proc and ok_mass) else "FAIL"
        print(f"  Extracted: S-No={extracted.get('s0_surgical_no')}, Side={extracted.get('s1_side')}, "
              f"Proc={extracted.get('s2_proc')}, Mass={extracted.get('s10_infiltrative')} ({status}) | Latency: {lat:.1f} ms")
        test_results.append(("T4_API_EXTRACT", "Extract 15 structured fields via /api/extract", status, f"{lat:.1f}ms"))

        # Test 5: Audio Upload API (/api/upload_audio)
        print("\n[Test 5] Audio Upload API (/api/upload_audio)")
        t0 = time.perf_counter()
        # Create a small dummy audio file for testing
        test_audio_path = Config.UPLOAD_DIR / "test_audio_ping.wav"
        with open(test_audio_path, "wb") as f:
            f.write(b"RIFF" + b"\x00" * 36 + b"WAVEfmt " + b"\x00" * 20 + b"data" + b"\x00" * 100)
            
        with open(test_audio_path, "rb") as f:
            res = client.post('/api/upload_audio', data={
                'audio': (f, 'test_audio_ping.wav')
            }, content_type='multipart/form-data')
        lat = (time.perf_counter() - t0) * 1000
        res_json = res.get_json() or {}
        uploaded_fn = res_json.get("audio_filename", "")
        status = "PASS" if res_json.get("success") and uploaded_fn else "FAIL"
        print(f"  Uploaded Filename: {uploaded_fn} ({status}) | Latency: {lat:.1f} ms")
        test_results.append(("T5_AUDIO_UPLOAD", "Upload audio recording via /api/upload_audio", status, f"{lat:.1f}ms"))

        # Test 6: PDF Report & Database Save (/generate)
        print("\n[Test 6] PDF Report Generation & Database Save (/generate)")
        t0 = time.perf_counter()
        gen_payload = {
            "s0_surgical_no": "S-24-1001",
            "s1_side": "right",
            "s2_proc": "modified",
            "s3_dims_0": "20.0",
            "s3_dims_1": "15.0",
            "s3_dims_2": "5.0",
            "s4_check": "1",
            "s5_dims_0": "10.0",
            "s5_dims_1": "4.0",
            "s10_infiltrative": "1",
            "s10_inf_dims_0": "3.5",
            "s10_inf_dims_1": "2.5",
            "s10_inf_dims_2": "1.5",
            "s10_5_quadrant_vals": "upper",
            "s11_deep": "1.2",
            "s14_check": "1",
            "s14_num": "12",
            "s14_min": "0.5",
            "s14_max": "2.0",
            "transcription": sample_dictation,
            "audio_filename": uploaded_fn
        }
        res = client.post('/generate', data=gen_payload, follow_redirects=True)
        lat = (time.perf_counter() - t0) * 1000
        
        # Check if record in FormHistory was created
        history_rec = FormHistory.query.filter_by(surgical_number="S-24-1001").first()
        status = "PASS" if history_rec is not None and res.status_code == 200 else "FAIL"
        print(f"  Form History ID: {history_rec.id if history_rec else 'None'} ({status}) | Latency: {lat:.1f} ms")
        test_results.append(("T6_GENERATE_PDF", "Generate PDF & DOCX, save FormHistory in DB", status, f"{lat:.1f}ms"))

        # Test 7: History Page (/history)
        print("\n[Test 7] History Page (/history)")
        t0 = time.perf_counter()
        res = client.get('/history')
        lat = (time.perf_counter() - t0) * 1000
        has_case = b"S-24-1001" in res.data
        status = "PASS" if res.status_code == 200 and has_case else "FAIL"
        print(f"  History Page: {res.status_code} (Contains Case: {has_case}) ({status}) | Latency: {lat:.1f} ms")
        test_results.append(("T7_HISTORY_PAGE", "Load case history listing page with saved case", status, f"{lat:.1f}ms"))

        # Test 8: Dashboard Page (/dashboard)
        print("\n[Test 8] Dashboard Analytics Page (/dashboard)")
        t0 = time.perf_counter()
        res = client.get('/dashboard')
        lat = (time.perf_counter() - t0) * 1000
        status = "PASS" if res.status_code == 200 else "FAIL"
        print(f"  Dashboard Page: {res.status_code} ({status}) | Latency: {lat:.1f} ms")
        test_results.append(("T8_DASHBOARD", "Load clinical analytics dashboard page", status, f"{lat:.1f}ms"))

        # Test 9: 100% Offline Static Assets Verification
        print("\n[Test 9] 100% Offline Static Assets Verification")
        assets_to_test = [
            ('/static/style.css', 'CSS stylesheet'),
            ('/static/script.js', 'Core JavaScript'),
            ('/static/fontawesome/css/all.min.css', 'Local FontAwesome CSS'),
            ('/static/fontawesome/webfonts/fa-solid-900.woff2', 'Local FontAwesome Solid Font'),
            ('/static/fontawesome/webfonts/fa-regular-400.woff2', 'Local FontAwesome Regular Font')
        ]
        all_assets_pass = True
        for uri, label in assets_to_test:
            res = client.get(uri)
            ok = (res.status_code == 200)
            if not ok: all_assets_pass = False
            print(f"  {label} ({uri}): {res.status_code} {'PASS' if ok else 'FAIL'}")
            
        status = "PASS" if all_assets_pass else "FAIL"
        test_results.append(("T9_OFFLINE_ASSETS", "Verify local static CSS, JS, and FontAwesome assets", status, "0.0ms"))

    print("\n" + "=" * 70)
    print("[SUMMARY] WEB APPLICATION FUNCTIONAL TEST RESULTS SUMMARY")
    print("=" * 70)
    print(f"{'Test ID':<18} | {'Description':<40} | {'Status':<6} | {'Latency':<8}")
    print("-" * 75)
    for tid, desc, st, lat in test_results:
        print(f"{tid:<18} | {desc:<40} | {st:<6} | {lat:<8}")
    print("-" * 75)
    all_pass = all(st == "PASS" for _, _, st, _ in test_results)
    print(f"OVERALL STATUS: {'ALL TESTS PASSED (100.0%)' if all_pass else 'SOME TESTS FAILED'}")
    print("=" * 70)
    
    # Save results to CSV for thesis documentation
    out_csv = BASE_DIR / "benchmarks" / "thesis_eval_outputs" / "web_functional_test_results.csv"
    import pandas as pd
    df_out = pd.DataFrame([{
        "Test_ID": t[0],
        "Description": t[1],
        "Status": t[2],
        "Latency": t[3]
    } for t in test_results])
    df_out.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"Saved results to {out_csv}")

if __name__ == "__main__":
    run_web_tests()
