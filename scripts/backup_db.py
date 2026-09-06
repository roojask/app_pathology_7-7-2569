import os
import sys
import json
import shutil
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

DATA_DIR = BASE_DIR / "data"
DB_FILE = DATA_DIR / "instance" / "local_pathology.db"
BACKUP_DIR = DATA_DIR / "backups"

def backup_database():
    """
    Creates an automated snapshot backup of BOTH the SQLite database
    and the PostgreSQL database to prevent any accidental data loss.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. Backup SQLite Database File
    try:
        if DB_FILE.exists():
            backup_filename = f"db_backup_{timestamp}.db"
            backup_filepath = BACKUP_DIR / backup_filename
            shutil.copy2(DB_FILE, backup_filepath)
            print(f"[BACKUP SUCCESS] SQLite DB backed up to: {backup_filepath.name}")
        else:
            print("[BACKUP] No SQLite file found yet.")
    except Exception as e:
        print(f"[BACKUP WARNING] Failed to backup SQLite: {e}")

    # 2. Backup PostgreSQL Database Tables (Users, FormHistory, CaseRevision)
    try:
        from configs.config import Config
        pg_url = Config.SQLALCHEMY_DATABASE_URI
        if pg_url and pg_url.startswith("postgresql"):
            import psycopg2
            pg_conn = psycopg2.connect(pg_url)
            pg_cur = pg_conn.cursor()

            pg_dump = {"timestamp": timestamp, "tables": {}}
            for tbl in ["user", "form_history", "case_revision"]:
                try:
                    pg_cur.execute(f'SELECT * FROM "{tbl}";')
                    cols = [desc[0] for desc in pg_cur.description]
                    rows = pg_cur.fetchall()
                    table_rows = []
                    for r in rows:
                        row_dict = {}
                        for idx, col in enumerate(cols):
                            val = r[idx]
                            if isinstance(val, (datetime.datetime, datetime.date)):
                                val = str(val)
                            row_dict[col] = val
                        table_rows.append(row_dict)
                    pg_dump["tables"][tbl] = table_rows
                except Exception as te:
                    print(f"[BACKUP NOTE] Table {tbl} backup note: {te}")
                    pg_conn.rollback()

            pg_backup_file = BACKUP_DIR / f"pg_backup_{timestamp}.json"
            with open(pg_backup_file, "w", encoding="utf-8") as pf:
                json.dump(pg_dump, pf, ensure_ascii=False, indent=2)

            counts_summary = ", ".join([f"{t}: {len(r)}" for t, r in pg_dump["tables"].items()])
            print(f"[BACKUP SUCCESS] PostgreSQL backed up to: {pg_backup_file.name} ({counts_summary})")
            pg_conn.close()
    except Exception as e:
        print(f"[BACKUP NOTE] PostgreSQL backup note: {e}")

    # 3. Keep the last 20 backups to save disk space
    try:
        all_backups = sorted(list(BACKUP_DIR.glob("db_backup_*.db")) + list(BACKUP_DIR.glob("pg_backup_*.json")), key=os.path.getmtime)
        if len(all_backups) > 30:
            for old_b in all_backups[:-30]:
                try:
                    os.remove(old_b)
                except Exception:
                    pass
    except Exception:
        pass

def restore_latest_backup():
    """
    Restores the database from the latest backup file if needed.
    """
    try:
        backups = sorted(list(BACKUP_DIR.glob("db_backup_*.db")), key=os.path.getmtime)
        if not backups:
            print("[RESTORE ERROR] No backup files found in data/backups/")
            return False

        latest_backup = backups[-1]
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(latest_backup, DB_FILE)
        print(f"[RESTORE SUCCESS] SQLite Database restored from: {latest_backup.name}")
        return True
    except Exception as e:
        print(f"[RESTORE ERROR] Failed to restore database: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "restore":
        restore_latest_backup()
    else:
        backup_database()
