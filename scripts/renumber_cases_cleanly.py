import os
import sys
import json
import re
import shutil
import datetime
from pathlib import Path

# Add project root
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import psycopg2
import sqlite3
from scripts.backup_db import backup_database

OUT_DIR = BASE_DIR / "data" / "outputs"
SQLITE_PATH = BASE_DIR / "data" / "instance" / "local_pathology.db"

def renumber_cases():
    print("==================================================")
    print("      RE-SEQUENCING CASES CHRONOLOGICALLY 1..N    ")
    print("==================================================")

    # 1. Safety Backup First
    print("[*] Creating safety backup before renumbering...")
    backup_database()

    # 2. Connect to PostgreSQL
    pg_conn = psycopg2.connect('postgresql://postgres:rooj282026@localhost:5432/pathology_db')
    pg_cur = pg_conn.cursor()

    # Read all cases ordered chronologically by timestamp
    pg_cur.execute('''
        SELECT id, user_id, surgical_number, form_data, audio_filename, photo_data, timestamp
        FROM "form_history"
        ORDER BY timestamp ASC;
    ''')
    raw_cases = pg_cur.fetchall()
    print(f"[*] Read {len(raw_cases)} cases from PostgreSQL.")

    # Read all revisions
    pg_cur.execute('''
        SELECT id, history_id, user_id, revision_number, action, changes_summary, full_snapshot, comment, timestamp
        FROM "case_revision"
        ORDER BY id ASC;
    ''')
    raw_revisions = pg_cur.fetchall()
    
    # Map old revisions to old history_id
    revisions_by_old_hist = {}
    for r in raw_revisions:
        old_h_id = r[1]
        revisions_by_old_hist.setdefault(old_h_id, []).append(r)

    # Prepare mapping and new cases
    old_to_new_id = {}
    new_cases = []
    
    for new_id, row in enumerate(raw_cases, start=1):
        old_id = row[0]
        old_to_new_id[old_id] = new_id
        new_cases.append({
            'new_id': new_id,
            'old_id': old_id,
            'user_id': row[1],
            'surgical_number': row[2],
            'form_data': row[3],
            'audio_filename': row[4],
            'photo_data': row[5],
            'timestamp': row[6]
        })

    print(f"[*] Generated clean mapping from {len(new_cases)} cases to IDs 1..{len(new_cases)}")

    # 3. Clean and Re-insert into PostgreSQL
    try:
        pg_cur.execute('DELETE FROM "case_revision";')
        pg_cur.execute('DELETE FROM "form_history";')

        rev_id_counter = 1
        for c in new_cases:
            # Insert FormHistory with clean ID
            pg_cur.execute('''
                INSERT INTO "form_history" (id, user_id, surgical_number, form_data, audio_filename, photo_data, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            ''', (c['new_id'], c['user_id'], c['surgical_number'], c['form_data'], c['audio_filename'], c['photo_data'], c['timestamp']))

            # Insert Revisions with new history_id
            old_revs = revisions_by_old_hist.get(c['old_id'], [])
            if old_revs:
                for rev in old_revs:
                    pg_cur.execute('''
                        INSERT INTO "case_revision" (id, history_id, user_id, revision_number, action, changes_summary, full_snapshot, comment, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                    ''', (rev_id_counter, c['new_id'], rev[2], rev[3], rev[4], rev[5], rev[6], rev[7], rev[8]))
                    rev_id_counter += 1
            else:
                # Baseline revision
                pg_cur.execute('''
                    INSERT INTO "case_revision" (id, history_id, user_id, revision_number, action, changes_summary, full_snapshot, comment, timestamp)
                    VALUES (%s, %s, %s, 1, 'create', '[]', %s, 'เอกสารเคสเดิม', %s);
                ''', (rev_id_counter, c['new_id'], c['user_id'], c['form_data'], c['timestamp']))
                rev_id_counter += 1

        # Reset sequences
        total_cases = len(new_cases)
        pg_cur.execute(f"SELECT setval('form_history_id_seq', {total_cases});")
        pg_cur.execute(f"SELECT setval('case_revision_id_seq', {rev_id_counter - 1});")

        pg_conn.commit()
        print(f"[+] PostgreSQL updated successfully: {total_cases} cases (IDs 1..{total_cases}).")
    except Exception as e:
        pg_conn.rollback()
        print(f"[-] PostgreSQL Error during renumbering: {e}")
        pg_conn.close()
        return False

    pg_conn.close()

    # 4. Clean and Re-insert into SQLite
    try:
        sq_conn = sqlite3.connect(str(SQLITE_PATH))
        sq_cur = sq_conn.cursor()
        sq_cur.execute("DELETE FROM form_history;")

        sq_cur.execute("PRAGMA table_info(form_history);")
        cols = [col[1] for col in sq_cur.fetchall()]
        has_photo = 'photo_data' in cols

        for c in new_cases:
            ts_str = str(c['timestamp'])
            if has_photo:
                sq_cur.execute('''
                    INSERT INTO form_history (id, user_id, surgical_number, form_data, audio_filename, photo_data, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                ''', (c['new_id'], c['user_id'], c['surgical_number'], c['form_data'], c['audio_filename'], c['photo_data'], ts_str))
            else:
                sq_cur.execute('''
                    INSERT INTO form_history (id, user_id, surgical_number, form_data, audio_filename, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?);
                ''', (c['new_id'], c['user_id'], c['surgical_number'], c['form_data'], c['audio_filename'], ts_str))

        sq_conn.commit()
        sq_conn.close()
        print(f"[+] SQLite updated successfully: {total_cases} cases (IDs 1..{total_cases}).")
    except Exception as e:
        print(f"[-] SQLite Error during renumbering: {e}")

    # 5. Remap and update files in data/outputs/
    print("[*] Remapping output files in data/outputs/ to new IDs 1..58...")
    for c in new_cases:
        old_id = c['old_id']
        new_id = c['new_id']

        # Update JSON archive
        json_target = OUT_DIR / f"case_{new_id}.json"
        with open(json_target, "w", encoding="utf-8") as jf:
            jf.write(c['form_data'])

        # Docx
        old_docx = OUT_DIR / f"case_{old_id}.docx"
        new_docx = OUT_DIR / f"case_{new_id}.docx"
        if old_docx.exists() and old_id != new_id and not new_docx.exists():
            shutil.copy2(old_docx, new_docx)

        # PDF
        old_pdf = OUT_DIR / f"case_{old_id}.pdf"
        new_pdf = OUT_DIR / f"case_{new_id}.pdf"
        if old_pdf.exists() and old_id != new_id and not new_pdf.exists():
            shutil.copy2(old_pdf, new_pdf)

    # Clean up old case files above total_cases
    for old_file in OUT_DIR.glob("case_*.json"):
        m = re.match(r'^case_(\d+)\.json$', old_file.name)
        if m and int(m.group(1)) > total_cases:
            try: old_file.unlink()
            except: pass

    for old_file in OUT_DIR.glob("case_*.docx"):
        m = re.match(r'^case_(\d+)\.docx$', old_file.name)
        if m and int(m.group(1)) > total_cases:
            try: old_file.unlink()
            except: pass

    for old_file in OUT_DIR.glob("case_*.pdf"):
        m = re.match(r'^case_(\d+)\.pdf$', old_file.name)
        if m and int(m.group(1)) > total_cases:
            try: old_file.unlink()
            except: pass

    print("\n==================================================")
    print(f"🎉 RENUMBERING COMPLETED! All cases are now clean: 1 to {total_cases}")
    print(f"🎉 Next case will automatically be ID #{total_cases + 1}")
    print("==================================================")
    return True

if __name__ == '__main__':
    renumber_cases()
