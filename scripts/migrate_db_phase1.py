"""
Phase 1 Database Architecture Migration Script
PathoWhisper Assistant

Performs rock-solid, transactional migration:
1. Adds `is_deleted` and `deleted_at` to `form_history` with index.
2. Creates PostgreSQL GIN index on `(form_data::jsonb)` for high-speed medical record queries.
3. Creates normalized `specimen_photo` table with foreign key cascading delete and index.
4. Safely migrates existing Base64 specimen photos (including Case #66) into `specimen_photo`.
5. Synchronizes SQLite shadow mirror schema and data to match PostgreSQL exactly.
"""

import sys
import json
import sqlite3
import psycopg2
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from configs.config import Config

SQLITE_PATH = BASE_DIR / "data" / "instance" / "local_pathology.db"
PG_URI = Config.SQLALCHEMY_DATABASE_URI

def migrate_postgres():
    print("=" * 70)
    print("[PostgreSQL Migration] Connecting to primary database...")
    print("=" * 70)

    pg_conn = psycopg2.connect(PG_URI)
    pg_conn.autocommit = False
    pg_cur = pg_conn.cursor()

    try:
        # 1. Add soft delete columns
        print("1. Adding soft delete columns (is_deleted, deleted_at) to form_history...")
        pg_cur.execute("""
            ALTER TABLE form_history 
            ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE;
        """)
        pg_cur.execute("""
            ALTER TABLE form_history 
            ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITHOUT TIME ZONE NULL;
        """)
        pg_cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_form_history_is_deleted 
            ON form_history(is_deleted);
        """)
        pg_cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_form_history_surgical_number 
            ON form_history(surgical_number);
        """)
        print("   ✓ Soft delete columns and B-Tree indexes created.")

        # 2. Add JSONB GIN index
        print("2. Creating JSONB GIN index on form_history((form_data::jsonb))...")
        pg_cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_form_history_form_data_gin 
            ON form_history USING gin ((form_data::jsonb));
        """)
        print("   ✓ PostgreSQL JSONB GIN index created.")

        # 3. Create specimen_photo table
        print("3. Creating normalized specimen_photo table...")
        pg_cur.execute("""
            CREATE TABLE IF NOT EXISTS specimen_photo (
                id SERIAL PRIMARY KEY,
                history_id INTEGER NOT NULL REFERENCES form_history(id) ON DELETE CASCADE,
                photo_data TEXT NOT NULL,
                photo_index INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC' + INTERVAL '7 HOURS')
            );
        """)
        pg_cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_specimen_photo_history_id 
            ON specimen_photo(history_id);
        """)
        pg_cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_specimen_photo_lookup 
            ON specimen_photo(history_id, photo_index);
        """)
        print("   ✓ specimen_photo table and indexes created.")

        # 4. Data Migration: Extract existing photos and insert into specimen_photo
        print("4. Migrating existing photos to specimen_photo...")
        pg_cur.execute("SELECT id, surgical_number, form_data, photo_data FROM form_history ORDER BY id;")
        rows = pg_cur.fetchall()
        
        migrated_photos_count = 0
        migrated_cases = []

        for r in rows:
            case_id, surg_no, form_data_str, direct_photo = r
            photos = []
            
            # Check form_data JSON for "photos" array
            if form_data_str:
                try:
                    d = json.loads(form_data_str)
                    if isinstance(d.get("photos"), list):
                        for p in d["photos"]:
                            if p and len(str(p).strip()) > 20:
                                photos.append(str(p).strip())
                except Exception:
                    pass

            # Fallback to direct photo_data column if no JSON photos
            if not photos and direct_photo and len(direct_photo.strip()) > 20:
                photos.append(direct_photo.strip())

            if photos:
                for idx, photo_str in enumerate(photos):
                    # Check if already migrated
                    pg_cur.execute(
                        "SELECT id FROM specimen_photo WHERE history_id = %s AND photo_index = %s;",
                        (case_id, idx)
                    )
                    existing = pg_cur.fetchone()
                    if not existing:
                        pg_cur.execute("""
                            INSERT INTO specimen_photo (history_id, photo_data, photo_index)
                            VALUES (%s, %s, %s);
                        """, (case_id, photo_str, idx))
                        migrated_photos_count += 1
                migrated_cases.append((case_id, surg_no, len(photos)))

        # Commit PostgreSQL transaction
        pg_conn.commit()
        print(f"   ✓ Successfully migrated {migrated_photos_count} photo(s) across {len(migrated_cases)} case(s).")
        for c in migrated_cases:
            print(f"     - Case #{c[0]} ({c[1]}): {c[2]} photo(s) stored in specimen_photo")

        # Verify counts
        pg_cur.execute("SELECT COUNT(*) FROM form_history;")
        total_cases = pg_cur.fetchone()[0]
        pg_cur.execute("SELECT COUNT(*) FROM specimen_photo;")
        total_photos = pg_cur.fetchone()[0]
        print(f"   ✓ PostgreSQL Verification: {total_cases} cases | {total_photos} specimen photos")

    except Exception as e:
        pg_conn.rollback()
        print(f"❌ [PostgreSQL Migration Error]: {e}")
        raise e
    finally:
        pg_cur.close()
        pg_conn.close()

def migrate_sqlite():
    print("\n" + "=" * 70)
    print("📁 [SQLite Migration] Synchronizing shadow mirror...")
    print("=" * 70)

    if not SQLITE_PATH.exists():
        print("SQLite shadow database does not exist. Skipping SQLite migration.")
        return

    sq_conn = sqlite3.connect(SQLITE_PATH)
    sq_cur = sq_conn.cursor()

    try:
        # 1. Add columns to form_history
        sq_cur.execute("PRAGMA table_info(form_history);")
        cols = [c[1] for c in sq_cur.fetchall()]

        if "is_deleted" not in cols:
            print("1. Adding is_deleted column to SQLite form_history...")
            sq_cur.execute("ALTER TABLE form_history ADD COLUMN is_deleted BOOLEAN DEFAULT 0;")
        if "deleted_at" not in cols:
            print("2. Adding deleted_at column to SQLite form_history...")
            sq_cur.execute("ALTER TABLE form_history ADD COLUMN deleted_at DATETIME NULL;")

        # 2. Synchronize row count: Remove IDs not present in PostgreSQL (e.g. 69, 70, 72)
        print("3. Pruning stale test rows from SQLite to align with PostgreSQL (66 cases)...")
        pg_conn = psycopg2.connect(PG_URI)
        pg_cur = pg_conn.cursor()
        pg_cur.execute("SELECT id FROM form_history;")
        pg_ids = [r[0] for r in pg_cur.fetchall()]

        sq_cur.execute("SELECT id FROM form_history;")
        sq_ids = [r[0] for r in sq_cur.fetchall()]

        stale_ids = [x for x in sq_ids if x not in pg_ids]
        if stale_ids:
            for sid in stale_ids:
                sq_cur.execute("DELETE FROM form_history WHERE id = ?;", (sid,))
            print(f"   ✓ Pruned {len(stale_ids)} stale records from SQLite: {stale_ids}")
        else:
            print("   ✓ SQLite IDs already match PostgreSQL.")

        # 3. Create specimen_photo in SQLite
        print("4. Creating specimen_photo in SQLite...")
        sq_cur.execute("""
            CREATE TABLE IF NOT EXISTS specimen_photo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                history_id INTEGER NOT NULL REFERENCES form_history(id) ON DELETE CASCADE,
                photo_data TEXT NOT NULL,
                photo_index INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        sq_cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_sq_specimen_photo_history_id 
            ON specimen_photo(history_id);
        """)

        # 4. Sync photos from PostgreSQL to SQLite
        pg_cur.execute("SELECT id, history_id, photo_data, photo_index, created_at FROM specimen_photo ORDER BY id;")
        pg_photos = pg_cur.fetchall()
        pg_conn.close()

        sq_cur.execute("DELETE FROM specimen_photo;")
        for p in pg_photos:
            sq_cur.execute("""
                INSERT INTO specimen_photo (id, history_id, photo_data, photo_index, created_at)
                VALUES (?, ?, ?, ?, ?);
            """, (p[0], p[1], p[2], p[3], str(p[4])))

        sq_conn.commit()

        sq_cur.execute("SELECT COUNT(*) FROM form_history;")
        sq_cases = sq_cur.fetchone()[0]
        sq_cur.execute("SELECT COUNT(*) FROM specimen_photo;")
        sq_p_count = sq_cur.fetchone()[0]
        print(f"   ✓ SQLite Verification: {sq_cases} cases | {sq_p_count} specimen photos")

    except Exception as e:
        sq_conn.rollback()
        print(f"[SQLite Migration Error]: {e}")
        raise e
    finally:
        sq_conn.close()

if __name__ == "__main__":
    print("\n[START] Starting Phase 1 Architecture Migration...")
    migrate_postgres()
    migrate_sqlite()
    print("\n[DONE] Phase 1 Database Migration Completed Successfully!")
