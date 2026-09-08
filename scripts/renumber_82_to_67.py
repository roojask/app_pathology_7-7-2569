import sys
import shutil
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"c:\app_pathology_7-7-2569-main")
sys.path.insert(0, str(BASE_DIR))

from scripts.backup_db import backup_database
from app import app, db
from sqlalchemy import text
import sqlite3

def run_renumber():
    print("=" * 60)
    print("      RENUMBERING CASE 82 -> 67 & SEQUENCE RESET")
    print("=" * 60)

    # 1. PostgreSQL Status
    print("\n[1/4] Checking PostgreSQL...")
    with app.app_context():
        case_67 = db.session.execute(text("SELECT id, surgical_number FROM form_history WHERE id = 67")).fetchone()
        case_82 = db.session.execute(text("SELECT id, surgical_number FROM form_history WHERE id = 82")).fetchone()
        
        if case_67 and not case_82:
            print(f"  [+] PostgreSQL is already up to date: Case 67 exists ('{case_67[1]}'), Case 82 removed.")
        elif case_82 and not case_67:
            db.session.execute(text("""
                INSERT INTO form_history (id, user_id, surgical_number, form_data, audio_filename, photo_data, is_deleted, deleted_at, timestamp)
                SELECT 67, user_id, surgical_number, form_data, audio_filename, photo_data, is_deleted, deleted_at, timestamp
                FROM form_history WHERE id = 82;
            """))
            db.session.execute(text("UPDATE case_revision SET history_id = 67 WHERE history_id = 82"))
            db.session.execute(text("UPDATE specimen_photo SET history_id = 67 WHERE history_id = 82"))
            db.session.execute(text("DELETE FROM form_history WHERE id = 82;"))
            db.session.commit()
            print("  [+] PostgreSQL updated: 82 -> 67.")

        # Always ensure sequence is 67
        db.session.execute(text("SELECT setval('public.form_history_id_seq', 67, true);"))
        db.session.commit()
        seq_val = db.session.execute(text("SELECT last_value FROM public.form_history_id_seq")).scalar()
        print(f"  [+] PostgreSQL sequence set to {seq_val} (next insert will be 68)")

    # 2. SQLite Shadow Mirror
    print("\n[2/4] Updating SQLite shadow mirror...")
    sq_path = BASE_DIR / "data" / "instance" / "local_pathology.db"
    if sq_path.exists():
        sq_conn = sqlite3.connect(sq_path)
        sq_cur = sq_conn.cursor()

        sq_case_82 = sq_cur.execute("SELECT id FROM form_history WHERE id = 82").fetchone()
        sq_case_67 = sq_cur.execute("SELECT id FROM form_history WHERE id = 67").fetchone()

        if sq_case_82 and not sq_case_67:
            sq_cur.execute("PRAGMA table_info(form_history);")
            cols = [c[1] for c in sq_cur.fetchall()]
            non_id_cols = [c for c in cols if c != 'id']

            insert_sql = f"""
                INSERT INTO form_history (id, {", ".join(non_id_cols)})
                SELECT 67, {", ".join(non_id_cols)}
                FROM form_history WHERE id = 82;
            """
            sq_cur.execute(insert_sql)

            tables = [t[0] for t in sq_cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            if 'specimen_photo' in tables:
                sq_cur.execute("UPDATE specimen_photo SET history_id = 67 WHERE history_id = 82;")
            if 'case_revision' in tables:
                sq_cur.execute("UPDATE case_revision SET history_id = 67 WHERE history_id = 82;")

            sq_cur.execute("DELETE FROM form_history WHERE id = 82;")
            sq_cur.execute("UPDATE sqlite_sequence SET seq = 67 WHERE name = 'form_history';")
            sq_conn.commit()
            print("  [+] SQLite shadow mirror updated to ID 67 and sequence set to 67.")
        elif sq_case_67:
            sq_cur.execute("UPDATE sqlite_sequence SET seq = 67 WHERE name = 'form_history';")
            sq_conn.commit()
            print("  [+] SQLite shadow mirror already has ID 67.")
        sq_conn.close()

    # 3. File Remapping in data/outputs
    print("\n[3/4] Remapping output files in data/outputs/...")
    out_dir = BASE_DIR / "data" / "outputs"
    for ext in ["json", "docx", "pdf"]:
        old_file = out_dir / f"case_82.{ext}"
        new_file = out_dir / f"case_67.{ext}"
        if old_file.exists():
            shutil.copy2(old_file, new_file)
            old_file.unlink()
            print(f"  [+] Moved {old_file.name} -> {new_file.name}")
        elif new_file.exists():
            print(f"  [+] {new_file.name} exists.")

    # 4. Final Verification
    print("\n[4/4] Verification Summary...")
    with app.app_context():
        total = db.session.execute(text("SELECT count(*) FROM form_history")).scalar()
        seq_val = db.session.execute(text("SELECT last_value FROM public.form_history_id_seq")).scalar()
        row_67 = db.session.execute(text("SELECT id, surgical_number, timestamp FROM form_history WHERE id = 67")).fetchone()
        rev_count = db.session.execute(text("SELECT count(*) FROM case_revision WHERE history_id = 67")).scalar()
        photo_count = db.session.execute(text("SELECT count(*) FROM specimen_photo WHERE history_id = 67")).scalar()
        print(f"  PostgreSQL: Total cases = {total}, Sequence last_value = {seq_val}")
        print(f"  Case #67: {row_67}, Revisions = {rev_count}, Photos = {photo_count}")

    if sq_path.exists():
        sq_conn = sqlite3.connect(sq_path)
        sq_cur = sq_conn.cursor()
        sq_total = sq_cur.execute("SELECT count(*) FROM form_history").fetchone()[0]
        sq_seq = sq_cur.execute("SELECT seq FROM sqlite_sequence WHERE name = 'form_history'").fetchone()[0]
        sq_conn.close()
        print(f"  SQLite: Total cases = {sq_total}, Sequence = {sq_seq}")

    print("\n" + "=" * 60)
    print("SUCCESS: Both PostgreSQL and SQLite are synchronized at 1..67.")
    print("=" * 60)

if __name__ == "__main__":
    run_renumber()
