import sys
import json
import sqlite3
import datetime
from pathlib import Path

# Ensure UTF-8 encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DATA_DIR = BASE_DIR / "data"
SQLITE_DB_PATH = DATA_DIR / "instance" / "local_pathology.db"
ENV_PATH = BASE_DIR / ".env"

def setup_postgres(password="postgres"):
    print("==================================================")
    print("[POSTGRES SETUP] Initializing PostgreSQL for Pathology App")
    print("==================================================")

    # 1. Connect to PostgreSQL server
    try:
        conn = psycopg2.connect(
            dbname="postgres",
            user="postgres",
            password=password,
            host="localhost",
            port=5432
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        print(f"✅ Successfully connected to PostgreSQL Server on port 5432 with password '{password}'!")
    except Exception as e:
        print(f"❌ Connection failed with password '{password}': {e}")
        return False

    # 2. Create 'pathology_db' database if not exists
    cursor.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = 'pathology_db';")
    exists = cursor.fetchone()
    if not exists:
        cursor.execute("CREATE DATABASE pathology_db;")
        print("✅ Database 'pathology_db' created successfully!")
    else:
        print("ℹ️ Database 'pathology_db' already exists.")

    cursor.close()
    conn.close()

    # 3. Connect to pathology_db and create tables via Flask SQLAlchemy
    postgres_url = f"postgresql://postgres:{password}@localhost:5432/pathology_db"
    
    # Update .env file with DATABASE_URL
    try:
        env_content = ""
        if ENV_PATH.exists():
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
            new_lines = []
            updated = False
            for line in lines:
                if line.startswith("DATABASE_URL="):
                    new_lines.append(f"DATABASE_URL={postgres_url}\n")
                    updated = True
                else:
                    new_lines.append(line)
            if not updated:
                new_lines.append(f"DATABASE_URL={postgres_url}\n")
            env_content = "".join(new_lines)
        else:
            env_content = f"DATABASE_URL={postgres_url}\nUSE_HTTPS=True\nSECRET_KEY=pathology-secret\n"

        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write(env_content)
        print("✅ Updated .env file with PostgreSQL DATABASE_URL!")
    except Exception as e:
        print(f"⚠️ Failed to update .env: {e}")

    # Initialize tables using Flask App Context
    from app import app
    from src.database.models import db, User, FormHistory
    
    app.config["SQLALCHEMY_DATABASE_URI"] = postgres_url
    with app.app_context():
        db.create_all()
        print("✅ Tables ('user', 'form_history') initialized on PostgreSQL!")

        # 4. Migrate data from SQLite to PostgreSQL if SQLite exists
        if SQLITE_DB_PATH.exists():
            print("\n[MIGRATION] Transferring existing data from SQLite to PostgreSQL...")
            try:
                sq_conn = sqlite3.connect(str(SQLITE_DB_PATH))
                sq_cur = sq_conn.cursor()

                # Migrate Users
                sq_cur.execute("SELECT id, username, email, password_hash, name FROM user;")
                sqlite_users = sq_cur.fetchall()
                for u in sqlite_users:
                    existing_u = User.query.filter_by(username=u[1]).first()
                    if not existing_u:
                        new_u = User(
                            id=u[0],
                            username=u[1],
                            email=u[2],
                            password_hash=u[3],
                            name=u[4]
                        )
                        db.session.add(new_u)
                db.session.commit()
                print(f"  • Migrated {len(sqlite_users)} user accounts to PostgreSQL.")

                # Migrate Form History
                sq_cur.execute("SELECT id, user_id, surgical_number, form_data, audio_filename, timestamp FROM form_history;")
                sqlite_histories = sq_cur.fetchall()
                for h in sqlite_histories:
                    existing_h = FormHistory.query.filter_by(id=h[0]).first()
                    if not existing_h:
                        ts = datetime.datetime.strptime(h[5], "%Y-%m-%d %H:%M:%S.%f") if isinstance(h[5], str) and "." in h[5] else datetime.datetime.utcnow()
                        new_h = FormHistory(
                            id=h[0],
                            user_id=h[1],
                            surgical_number=h[2],
                            form_data=h[3],
                            audio_filename=h[4],
                            timestamp=ts
                        )
                        db.session.add(new_h)
                db.session.commit()
                print(f"  • Migrated {len(sqlite_histories)} pathology case reports to PostgreSQL.")
                sq_conn.close()

                # Reset PostgreSQL ID Sequences so future inserts don't hit UniqueViolation
                try:
                    db.session.execute(db.text("SELECT setval('form_history_id_seq', (SELECT COALESCE(MAX(id), 1) FROM form_history));"))
                    db.session.execute(db.text("SELECT setval('user_id_seq', (SELECT COALESCE(MAX(id), 1) FROM \"user\"));"))
                    db.session.commit()
                    print("  • Updated PostgreSQL primary key sequences to match latest IDs.")
                except Exception as seq_err:
                    print(f"  • Sequence sync note: {seq_err}")

            except Exception as me:
                print(f"⚠️ Migration note: {me}")

    print("\n==================================================")
    print("🎉 PostgreSQL Setup & Migration Completed Successfully!")
    print("==================================================")
    return True

if __name__ == "__main__":
    pwd = sys.argv[1] if len(sys.argv) > 1 else "postgres"
    setup_postgres(pwd)
