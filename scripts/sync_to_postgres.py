import sqlite3
import psycopg2
from pathlib import Path

def sync():
    sqlite_path = Path('data/instance/local_pathology.db')
    if not sqlite_path.exists():
        print(f"Error: {sqlite_path} does not exist!")
        return

    # 1. Update SQLite schema if needed (add is_admin to user if missing)
    sq_conn = sqlite3.connect(sqlite_path)
    sq_cur = sq_conn.cursor()
    sq_cur.execute("PRAGMA table_info(user)")
    cols = [c[1] for c in sq_cur.fetchall()]
    if 'is_admin' not in cols:
        print("[SQLite] Adding is_admin column to user table...")
        sq_cur.execute("ALTER TABLE user ADD COLUMN is_admin BOOLEAN DEFAULT 0;")
        sq_cur.execute("UPDATE user SET is_admin = 1 WHERE username IN ('roojask', 'test1');")
        sq_conn.commit()
        print("[SQLite] is_admin added and admin users updated.")
    else:
        print("[SQLite] is_admin column already exists.")

    sq_cur.execute("SELECT id, username, email, password_hash, name, is_admin FROM user")
    users = sq_cur.fetchall()
    print(f"[SQLite] Found {len(users)} users.")

    sq_cur.execute("PRAGMA table_info(form_history)")
    hist_cols = [c[1] for c in sq_cur.fetchall()]
    has_photo = 'photo_data' in hist_cols

    if has_photo:
        sq_cur.execute("SELECT id, user_id, surgical_number, form_data, audio_filename, photo_data, timestamp FROM form_history")
    else:
        sq_cur.execute("SELECT id, user_id, surgical_number, form_data, audio_filename, timestamp FROM form_history")
    histories = sq_cur.fetchall()
    print(f"[SQLite] Found {len(histories)} form_history records.")

    # 2. Connect to PostgreSQL
    pg_conn = psycopg2.connect(
        dbname='pathology_db',
        user='postgres',
        password='rooj282026',
        host='localhost',
        port='5432'
    )
    pg_cur = pg_conn.cursor()

    # 3. Insert users into PostgreSQL "user" table
    for u in users:
        u_id, username, email, password_hash, name, is_admin = u
        is_admin_bool = bool(is_admin) or (username in ['roojask', 'test1'])
        pg_cur.execute('''
            INSERT INTO "user" (id, username, email, password_hash, name, is_admin)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                username = EXCLUDED.username,
                email = EXCLUDED.email,
                password_hash = EXCLUDED.password_hash,
                name = EXCLUDED.name,
                is_admin = EXCLUDED.is_admin;
        ''', (u_id, username, email, password_hash, name, is_admin_bool))
    pg_conn.commit()
    print(f"[PostgreSQL] Successfully synced {len(users)} users into \"user\" table.")

    # Update user sequence
    pg_cur.execute('SELECT setval(\'user_id_seq\', (SELECT COALESCE(MAX(id), 1) FROM "user"));')
    pg_conn.commit()

    # 4. Insert form_history into PostgreSQL "form_history" table
    for h in histories:
        if has_photo:
            h_id, user_id, surg_no, form_data, audio_fn, photo_data, timestamp = h
        else:
            h_id, user_id, surg_no, form_data, audio_fn, timestamp = h
            photo_data = None

        pg_cur.execute('''
            INSERT INTO "form_history" (id, user_id, surgical_number, form_data, audio_filename, photo_data, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                surgical_number = EXCLUDED.surgical_number,
                form_data = EXCLUDED.form_data,
                audio_filename = EXCLUDED.audio_filename,
                photo_data = EXCLUDED.photo_data,
                timestamp = EXCLUDED.timestamp;
        ''', (h_id, user_id, surg_no, form_data, audio_fn, photo_data, timestamp))
    pg_conn.commit()
    print(f"[PostgreSQL] Successfully synced {len(histories)} form_history records into \"form_history\" table.")

    # Update form_history sequence
    pg_cur.execute('SELECT setval(\'form_history_id_seq\', (SELECT COALESCE(MAX(id), 1) FROM "form_history"));')
    pg_conn.commit()

    # 5. Populate initial case revisions for histories if not already present
    pg_cur.execute('SELECT count(*) FROM case_revision;')
    rev_count = pg_cur.fetchone()[0]
    if rev_count == 0:
        print("[PostgreSQL] Creating baseline revisions for form_history cases...")
        for h in histories:
            h_id = h[0]
            u_id = h[1]
            f_data = h[3]
            t_stamp = h[-1]
            pg_cur.execute('''
                INSERT INTO case_revision (history_id, user_id, revision_number, action, full_snapshot, timestamp)
                VALUES (%s, %s, 1, 'create', %s, %s);
            ''', (h_id, u_id, f_data, t_stamp))
        pg_conn.commit()
        print(f"[PostgreSQL] Created {len(histories)} baseline case revisions.")

    pg_cur.execute('SELECT setval(\'case_revision_id_seq\', (SELECT COALESCE(MAX(id), 1) FROM case_revision));')
    pg_conn.commit()

    pg_conn.close()
    sq_conn.close()
    print("=== SYNC COMPLETED SUCCESSFULLY ===")

if __name__ == '__main__':
    sync()
