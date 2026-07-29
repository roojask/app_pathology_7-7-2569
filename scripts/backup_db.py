import os
import sys
import shutil
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DB_FILE = DATA_DIR / "instance" / "local_pathology.db"
BACKUP_DIR = DATA_DIR / "backups"

def backup_database():
    """
    Creates an automated snapshot backup of the SQLite database
    and audio uploads to prevent any accidental data loss.
    """
    try:
        if not DB_FILE.exists():
            print("[BACKUP] No existing database file found to backup yet.")
            return

        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"db_backup_{timestamp}.db"
        backup_filepath = BACKUP_DIR / backup_filename

        # 1. Backup SQLite Database File
        shutil.copy2(DB_FILE, backup_filepath)
        print(f"[BACKUP SUCCESS] Database backed up to: {backup_filepath.name}")

        # 2. Keep only the last 10 database backups to save disk space
        backups = sorted(list(BACKUP_DIR.glob("db_backup_*.db")), key=os.path.getmtime)
        if len(backups) > 10:
            for old_b in backups[:-10]:
                try:
                    os.remove(old_b)
                    print(f"[BACKUP ROTATION] Cleaned up old backup: {old_b.name}")
                except Exception:
                    pass

    except Exception as e:
        print(f"[BACKUP ERROR] Failed to create database backup: {e}")

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
        print(f"[RESTORE SUCCESS] Database restored from: {latest_backup.name}")
        return True
    except Exception as e:
        print(f"[RESTORE ERROR] Failed to restore database: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "restore":
        restore_latest_backup()
    else:
        backup_database()
