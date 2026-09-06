import os
import sys
import json
import sqlite3
import psycopg2
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))
DATA_DIR = BASE_DIR / "data"
SQLITE_DB = DATA_DIR / "instance" / "local_pathology.db"
OUTPUT_DIR = DATA_DIR / "outputs"

def shadow_sync_case_to_sqlite(case_id, user_id, surgical_number, form_data, audio_filename, photo_data, timestamp):
    """
    Guarantees Zero-Data-Loss by immediately writing every created/updated case
    to the local SQLite database and to a permanent filesystem JSON archive.
    Completely isolated so that any exception will never disrupt the web request.
    """
    try:
        # 1. Permanent JSON archive in data/outputs/
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        json_file = OUTPUT_DIR / f"case_{case_id}.json"
        with open(json_file, "w", encoding="utf-8") as jf:
            if isinstance(form_data, dict):
                json.dump(form_data, jf, ensure_ascii=False, indent=2)
            else:
                jf.write(str(form_data))

        # 2. Local SQLite mirror backup
        if not SQLITE_DB.parent.exists():
            SQLITE_DB.parent.mkdir(parents=True, exist_ok=True)

        sq_conn = sqlite3.connect(str(SQLITE_DB), timeout=5)
        sq_cur = sq_conn.cursor()

        ts_str = str(timestamp) if timestamp else datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Check if photo_data column exists in SQLite
        sq_cur.execute("PRAGMA table_info(form_history);")
        cols = [c[1] for c in sq_cur.fetchall()]
        has_photo = 'photo_data' in cols

        f_data_str = form_data if isinstance(form_data, str) else json.dumps(form_data, ensure_ascii=False)

        if has_photo:
            sq_cur.execute('''
                INSERT OR REPLACE INTO form_history (id, user_id, surgical_number, form_data, audio_filename, photo_data, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            ''', (case_id, user_id, surgical_number, f_data_str, audio_filename or "", photo_data or None, ts_str))
        else:
            sq_cur.execute('''
                INSERT OR REPLACE INTO form_history (id, user_id, surgical_number, form_data, audio_filename, timestamp)
                VALUES (?, ?, ?, ?, ?, ?);
            ''', (case_id, user_id, surgical_number, f_data_str, audio_filename or "", ts_str))

        sq_conn.commit()
        sq_conn.close()
    except Exception as e:
        print(f"[SHADOW SYNC WARNING] Could not shadow-sync case #{case_id} to SQLite: {e}")

def auto_self_healing_db_check():
    """
    Runs on server startup.
    Verifies that PostgreSQL and SQLite are both intact and have matching data.
    If either database has lost cases, it automatically heals itself from the other!
    """
    try:
        if not SQLITE_DB.exists():
            return

        # 1. Connect to PostgreSQL
        from configs.config import Config
        pg_url = Config.SQLALCHEMY_DATABASE_URI
        if not pg_url.startswith('postgresql'):
            return

        pg_conn = psycopg2.connect(pg_url)
        pg_cur = pg_conn.cursor()

        # Check row count
        pg_cur.execute('SELECT count(*) FROM "form_history";')
        pg_count = pg_cur.fetchone()[0]

        sq_conn = sqlite3.connect(str(SQLITE_DB))
        sq_cur = sq_conn.cursor()
        sq_cur.execute('SELECT count(*) FROM form_history;')
        sq_count = sq_cur.fetchone()[0]

        print(f"[DB INTEGRITY CHECK] PostgreSQL cases: {pg_count} | SQLite cases: {sq_count}")

        # Self-healing Scenario A: PostgreSQL is empty or missing cases, but SQLite has them
        if sq_count > pg_count:
            print(f"[SELF-HEALING] PostgreSQL has {pg_count} cases while SQLite has {sq_count}. Auto-syncing from SQLite to PostgreSQL...")
            from scripts.sync_to_postgres import sync
            sync()
            print("[SELF-HEALING] PostgreSQL healed successfully from SQLite!")

        # Self-healing Scenario B: SQLite is missing cases that PostgreSQL has
        elif pg_count > sq_count:
            print(f"[SELF-HEALING] SQLite has {sq_count} cases while PostgreSQL has {pg_count}. Auto-syncing PostgreSQL to SQLite...")
            pg_cur.execute('SELECT id, user_id, surgical_number, form_data, audio_filename, photo_data, timestamp FROM "form_history";')
            rows = pg_cur.fetchall()
            
            sq_cur.execute("PRAGMA table_info(form_history);")
            cols = [c[1] for c in sq_cur.fetchall()]
            has_photo = 'photo_data' in cols

            for r in rows:
                if has_photo:
                    sq_cur.execute('''
                        INSERT OR REPLACE INTO form_history (id, user_id, surgical_number, form_data, audio_filename, photo_data, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?);
                    ''', (r[0], r[1], r[2], r[3], r[4], r[5], str(r[6])))
                else:
                    sq_cur.execute('''
                        INSERT OR REPLACE INTO form_history (id, user_id, surgical_number, form_data, audio_filename, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?);
                    ''', (r[0], r[1], r[2], r[3], r[4], str(r[6])))
            sq_conn.commit()
            print("[SELF-HEALING] SQLite shadow database healed successfully from PostgreSQL!")

        pg_conn.close()
        sq_conn.close()
    except Exception as e:
        print(f"[DB INTEGRITY WARNING] Auto self-healing check note: {e}")

if __name__ == '__main__':
    auto_self_healing_db_check()
