import sys
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app import app, db
from src.database.models import User, FormHistory
from src.nlp.extractor import extract_data_15_sections
from src.nlp.normalizer import normalize_text

def run_system_audit():
    print("==================================================")
    print("🔍 [SYSTEM AUDIT & SECURITY SUITE] Running Unvarnished Audit...")
    print("==================================================")
    
    findings = []

    # 1. Audit Security: Direct Object Reference (IDOR) & Route Protections
    with app.test_client() as client:
        # Check /download without login
        res_dl = client.get('/download/test.pdf')
        if res_dl.status_code != 401 and res_dl.status_code != 302:
            findings.append({
                "severity": "HIGH",
                "category": "Security & Privacy (PDPA/HIPAA)",
                "issue": "/download/<filename> route lacks @login_required decorator",
                "impact": "Unauthenticated users can download PDF/DOCX reports if filename is guessed",
                "recommendation": "Add @login_required decorator to /download/<filename>"
            })
            
        # Check /uploads without login
        res_up = client.get('/uploads/test.wav')
        if res_up.status_code != 401 and res_up.status_code != 302:
            findings.append({
                "severity": "HIGH",
                "category": "Security & Privacy (PDPA/HIPAA)",
                "issue": "/uploads/<filename> route allows unauthenticated file access",
                "impact": "Unauthenticated users can listen to patient audio recordings if filename is known",
                "recommendation": "Enforce @login_required and check ownership of audio files"
            })
            
        # Check /history without login
        res_hist = client.get('/history')
        if res_hist.status_code == 200:
            findings.append({
                "severity": "HIGH",
                "category": "Security",
                "issue": "/history route accessible without login",
                "impact": "Guest users can view patient history",
                "recommendation": "Ensure @login_required redirects to login"
            })

    # 2. Audit NLP Extractor: Empty & Malformed Input Handling
    try:
        empty_res = extract_data_15_sections("")
        if not isinstance(empty_res, dict):
            findings.append({
                "severity": "MEDIUM",
                "category": "NLP Extractor Robustness",
                "issue": "extract_data_15_sections('') did not return valid dictionary",
                "impact": "Empty transcription causes server internal error",
                "recommendation": "Add input validation for empty/None strings"
            })
    except Exception as e:
        findings.append({
            "severity": "HIGH",
            "category": "NLP Extractor Robustness",
            "issue": f"extract_data_15_sections('') crashed with exception: {e}",
            "impact": "Server crash on empty audio/transcription",
            "recommendation": "Wrap extraction in try-except block returning empty dict"
        })

    # 3. Audit Database & Primary Key Sequence Health
    with app.app_context():
        try:
            users = User.query.all()
            histories = FormHistory.query.all()
            print(f"  • Active Users in DB: {len(users)}")
            print(f"  • Active Form Histories in DB: {len(histories)}")
        except Exception as e:
            findings.append({
                "severity": "CRITICAL",
                "category": "Database Connectivity",
                "issue": f"Database query failed: {e}",
                "impact": "Database query error during app execution",
                "recommendation": "Verify PostgreSQL 18 service and connection parameters"
            })

    print("\n" + "="*85)
    print("📋 UNVARNISHED SYSTEM AUDIT FINDINGS")
    print("="*85)
    for idx, f in enumerate(findings, 1):
        print(f"[{f['severity']}] Finding #{idx}: {f['issue']}")
        print(f"  • Category: {f['category']}")
        print(f"  • Impact: {f['impact']}")
        print(f"  • Recommendation: {f['recommendation']}\n")
        
    return findings

if __name__ == "__main__":
    run_system_audit()
