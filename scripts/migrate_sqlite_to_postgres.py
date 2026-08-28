import sqlite3
import psycopg2
from pathlib import Path

def migrate():
    # 1. Connect to PostgreSQL
    pg_conn = psycopg2.connect(
        dbname='pathology_db',
        user='postgres',
        password='rooj282026',
        host='localhost',
        port='5432'
    )
    pg_cur = pg_conn.cursor()

    # Create tables
    pg_cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(100) UNIQUE NOT NULL,
        email VARCHAR(120) UNIQUE NOT NULL,
        password_hash VARCHAR(200) NOT NULL,
        name VARCHAR(150),
        is_admin BOOLEAN DEFAULT FALSE
    );
    CREATE TABLE IF NOT EXISTS form_histories (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        surgical_number VARCHAR(100),
        form_data TEXT NOT NULL,
        audio_filename VARCHAR(200),
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS audio_tasks (
        id VARCHAR(36) PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        file_path VARCHAR(255) NOT NULL,
        status VARCHAR(20) DEFAULT 'pending',
        result_text TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ''')
    pg_conn.commit()

    # 2. Check SQLite databases and migrate data
    candidate_paths = [Path('pathology.db'), Path('data/instance/local_pathology.db'), Path('instance/pathology.db')]
    for sqlite_path in candidate_paths:
        if not sqlite_path.exists(): continue
        print(f"Checking SQLite database at: {sqlite_path}")
        sq_conn = sqlite3.connect(sqlite_path)
        sq_cur = sq_conn.cursor()
        
        # Migrate users
        try:
            sq_cur.execute('PRAGMA table_info(user);')
            cols = [c[1] for c in sq_cur.fetchall()]
            has_admin = 'is_admin' in cols
            
            if has_admin:
                sq_cur.execute('SELECT id, username, email, password_hash, name, is_admin FROM user')
                users = sq_cur.fetchall()
            else:
                sq_cur.execute('SELECT id, username, email, password_hash, name FROM user')
                users = [(u[0], u[1], u[2], u[3], u[4], False) for u in sq_cur.fetchall()]
                
            for u in users:
                pg_cur.execute('''
                    INSERT INTO users (id, username, email, password_hash, name, is_admin)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        username = EXCLUDED.username,
                        email = EXCLUDED.email,
                        password_hash = EXCLUDED.password_hash,
                        name = EXCLUDED.name,
                        is_admin = EXCLUDED.is_admin;
                ''', u)
            pg_conn.commit()
            print(f'Migrated {len(users)} users from {sqlite_path} to PostgreSQL!')
        except Exception as e:
            pg_conn.rollback()
            print(f'User migration note for {sqlite_path}:', e)

        # Migrate form histories
        try:
            sq_cur.execute('SELECT id, user_id, surgical_number, form_data, audio_filename, timestamp FROM form_history')
            histories = sq_cur.fetchall()
            for h in histories:
                pg_cur.execute('''
                    INSERT INTO form_histories (id, user_id, surgical_number, form_data, audio_filename, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        surgical_number = EXCLUDED.surgical_number,
                        form_data = EXCLUDED.form_data,
                        audio_filename = EXCLUDED.audio_filename,
                        timestamp = EXCLUDED.timestamp;
                ''', h)
            print(f'Migrated {len(histories)} form history cases from {sqlite_path} to PostgreSQL!')
        except Exception as e:
            print(f'History migration note for {sqlite_path}:', e)
            
        sq_conn.close()

    pg_cur.execute("SELECT setval('users_id_seq', (SELECT COALESCE(MAX(id), 1) FROM users));")
    pg_cur.execute("SELECT setval('form_histories_id_seq', (SELECT COALESCE(MAX(id), 1) FROM form_histories));")

    pg_conn.commit()
    pg_conn.close()
    print('All data migrated to PostgreSQL successfully!')

if __name__ == '__main__':
    migrate()
