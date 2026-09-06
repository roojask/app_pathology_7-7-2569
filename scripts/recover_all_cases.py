import os
import sys
import re
import json
import shutil
import datetime
from pathlib import Path

# Add project root
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import docx
import psycopg2
import sqlite3
from src.nlp.extractor import extract_data_15_sections

OUT_DIR = BASE_DIR / "data" / "outputs"
UPLOADS_DIR = BASE_DIR / "data" / "uploads"
SQLITE_PATH = BASE_DIR / "data" / "instance" / "local_pathology.db"

def recover_all_cases():
    print("==================================================")
    print("      PATHOLOGY CASE ZERO-LOSS AUTO-RECOVERY      ")
    print("==================================================")

    # 1. Connect to PostgreSQL
    pg_conn = psycopg2.connect('postgresql://postgres:rooj282026@localhost:5432/pathology_db')
    pg_cur = pg_conn.cursor()

    # Get existing cases in PostgreSQL
    pg_cur.execute('SELECT id, surgical_number, timestamp FROM "form_history" ORDER BY id;')
    existing_pg_rows = pg_cur.fetchall()
    existing_pg_ids = {r[0] for r in existing_pg_rows}
    print(f"[*] Existing cases in PostgreSQL: {len(existing_pg_ids)} (IDs: {sorted(list(existing_pg_ids))})")

    # Connect to SQLite
    sq_conn = sqlite3.connect(str(SQLITE_PATH))
    sq_cur = sq_conn.cursor()
    sq_cur.execute('SELECT id, surgical_number, timestamp FROM form_history ORDER BY id;')
    existing_sq_ids = {r[0] for r in sq_cur.fetchall()}
    print(f"[*] Existing cases in SQLite: {len(existing_sq_ids)} (IDs: {sorted(list(existing_sq_ids))})")

    # Audio files for matching
    audio_files = sorted(list(UPLOADS_DIR.glob("*")), key=lambda x: x.stat().st_mtime)

    def find_best_audio(surg_no, file_mtime):
        clean_sno = surg_no.replace("S-", "").replace("24-", "").lower() if surg_no else ""
        best = None
        min_diff = 1800 # 30 mins
        for a in audio_files:
            a_mtime = a.stat().st_mtime
            diff = abs(a_mtime - file_mtime)
            if clean_sno and len(clean_sno) >= 3 and clean_sno in a.name.lower():
                return a.name
            if diff < min_diff:
                min_diff = diff
                best = a.name
        return best

    # Find all docx files
    all_docx = sorted(list(OUT_DIR.glob("*.docx")), key=lambda x: x.stat().st_mtime)
    print(f"[*] Found {len(all_docx)} Word docx files in data/outputs/")

    # Separate explicit case files (e.g. case_40.docx) from final_*.docx
    explicit_cases = {}
    general_cases = []

    for f in all_docx:
        m_explicit = re.match(r'^case_(\d+)\.docx$', f.name)
        if m_explicit:
            c_id = int(m_explicit.group(1))
            explicit_cases[c_id] = f
        elif f.name != 'test_filled.docx':
            general_cases.append(f)

    print(f"[*] Explicit case files found: {len(explicit_cases)} (IDs: {sorted(list(explicit_cases.keys()))})")
    print(f"[*] General case reports (final_*.docx): {len(general_cases)}")

    # Step A: Restore explicit case files that are missing from DB
    new_cases_to_insert = []
    
    for c_id, f in sorted(explicit_cases.items()):
        if c_id in existing_pg_ids:
            continue
        try:
            doc = docx.Document(f)
            full_text = "\n".join([p.text.strip() for p in doc.paragraphs if p.text.strip()])
            sno = "Unknown"
            m = re.search(r'Surgical Number\s*S[\s\.]*([0-9A-Za-z\-_]+)', full_text)
            if m and m.group(1).strip() and not m.group(1).strip().startswith('.'):
                sno = f"S-{m.group(1).strip()}" if not m.group(1).startswith('S-') else m.group(1).strip()
            else:
                m2 = re.search(r'S-(\d{2}-\d{3,})', full_text)
                if m2: sno = m2.group(0)

            form_dict = extract_data_15_sections(full_text)
            if sno != "Unknown": form_dict["s0_surgical_no"] = sno

            mtime_ts = f.stat().st_mtime
            mtime_dt = datetime.datetime.fromtimestamp(mtime_ts)
            audio_match = find_best_audio(sno, mtime_ts)

            new_cases_to_insert.append({
                'id': c_id,
                'user_id': 3, # default to roojask (admin)
                'surgical_number': sno,
                'form_data': json.dumps(form_dict, ensure_ascii=False),
                'audio_filename': audio_match or "",
                'timestamp': mtime_dt,
                'source_docx': f,
                'explicit_id': True
            })
        except Exception as e:
            print(f"[-] Error reading {f.name}: {e}")

    # Step B: Restore from final_*.docx for any reports not already in DB
    # We track existing timestamps and surgical numbers to avoid duplicates
    existing_signatures = set()
    for r in existing_pg_rows:
        ts_val = r[2]
        ts_int = int(ts_val.timestamp() // 120) if isinstance(ts_val, datetime.datetime) else 0
        existing_signatures.add((r[1], ts_int))

    for item in new_cases_to_insert:
        ts_int = int(item['timestamp'].timestamp() // 120)
        existing_signatures.add((item['surgical_number'], ts_int))

    # Determine starting ID for new auto-increment cases
    max_explicit_id = max(list(explicit_cases.keys()) + list(existing_pg_ids) + [0])
    next_id = max_explicit_id + 1

    for f in general_cases:
        mtime_ts = f.stat().st_mtime
        mtime_dt = datetime.datetime.fromtimestamp(mtime_ts)
        try:
            doc = docx.Document(f)
            full_text = "\n".join([p.text.strip() for p in doc.paragraphs if p.text.strip()])
            sno = "Unknown"
            m = re.search(r'Surgical Number\s*S[\s\.]*([0-9A-Za-z\-_]+)', full_text)
            if m and m.group(1).strip() and not m.group(1).strip().startswith('.'):
                sno = f"S-{m.group(1).strip()}" if not m.group(1).startswith('S-') else m.group(1).strip()
            else:
                m2 = re.search(r'S-(\d{2}-\d{3,})', full_text)
                if m2: sno = m2.group(0)

            # Check if this exact case is already recorded within 2 minutes
            ts_int = int(mtime_ts // 120)
            sig = (sno, ts_int)
            if sig in existing_signatures:
                continue
            existing_signatures.add(sig)

            form_dict = extract_data_15_sections(full_text)
            if sno != "Unknown": form_dict["s0_surgical_no"] = sno

            audio_match = find_best_audio(sno, mtime_ts)

            # Also find corresponding PDF
            pdf_equiv = f.with_suffix('.pdf')

            new_cases_to_insert.append({
                'id': next_id,
                'user_id': 3,
                'surgical_number': sno,
                'form_data': json.dumps(form_dict, ensure_ascii=False),
                'audio_filename': audio_match or "",
                'timestamp': mtime_dt,
                'source_docx': f,
                'source_pdf': pdf_equiv if pdf_equiv.exists() else None,
                'explicit_id': False
            })
            next_id += 1
        except Exception as e:
            print(f"[-] Error reading {f.name}: {e}")

    print(f"\n[+] Total new cases to restore into DB: {len(new_cases_to_insert)}")

    # Step C: Insert into PostgreSQL and SQLite
    for c in new_cases_to_insert:
        c_id = c['id']
        u_id = c['user_id']
        sno = c['surgical_number']
        fdata = c['form_data']
        audio_fn = c['audio_filename']
        ts = c['timestamp']

        # PostgreSQL insert
        pg_cur.execute('''
            INSERT INTO "form_history" (id, user_id, surgical_number, form_data, audio_filename, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                surgical_number = EXCLUDED.surgical_number,
                form_data = EXCLUDED.form_data,
                audio_filename = EXCLUDED.audio_filename,
                timestamp = EXCLUDED.timestamp;
        ''', (c_id, u_id, sno, fdata, audio_fn, ts))

        # Baseline Revision
        pg_cur.execute('''
            INSERT INTO case_revision (history_id, user_id, revision_number, action, full_snapshot, comment, timestamp)
            VALUES (%s, %s, 1, 'create', %s, 'กู้คืนจากเอกสารรายงานเดิม (Recovered)', %s)
            ON CONFLICT DO NOTHING;
        ''', (c_id, u_id, fdata, ts))

        # SQLite insert
        sq_cur.execute('''
            INSERT OR REPLACE INTO form_history (id, user_id, surgical_number, form_data, audio_filename, timestamp)
            VALUES (?, ?, ?, ?, ?, ?);
        ''', (c_id, u_id, sno, fdata, audio_fn, str(ts)))

        # Also ensure case_<id>.docx and case_<id>.pdf exist in data/outputs
        case_docx_target = OUT_DIR / f"case_{c_id}.docx"
        case_pdf_target = OUT_DIR / f"case_{c_id}.pdf"
        case_json_target = OUT_DIR / f"case_{c_id}.json"

        # Save JSON snapshot permanently in outputs
        with open(case_json_target, "w", encoding="utf-8") as jf:
            jf.write(fdata)

        if 'source_docx' in c and c['source_docx'] and not case_docx_target.exists():
            shutil.copy2(c['source_docx'], case_docx_target)

        if 'source_pdf' in c and c['source_pdf'] and not case_pdf_target.exists():
            shutil.copy2(c['source_pdf'], case_pdf_target)

    pg_conn.commit()
    sq_conn.commit()

    # Update PostgreSQL Sequences
    pg_cur.execute('SELECT setval(\'form_history_id_seq\', (SELECT COALESCE(MAX(id), 1) FROM "form_history"));')
    pg_cur.execute('SELECT setval(\'case_revision_id_seq\', (SELECT COALESCE(MAX(id), 1) FROM case_revision));')
    pg_conn.commit()

    pg_cur.execute('SELECT count(*) FROM "form_history";')
    total_pg = pg_cur.fetchone()[0]

    sq_cur.execute('SELECT count(*) FROM form_history;')
    total_sq = sq_cur.fetchone()[0]

    print("\n==================================================")
    print(f"🎉 SUCCESS! Total cases in PostgreSQL: {total_pg}")
    print(f"🎉 SUCCESS! Total cases in SQLite:     {total_sq}")
    print("==================================================")

    pg_conn.close()
    sq_conn.close()
    return total_pg

if __name__ == '__main__':
    recover_all_cases()
