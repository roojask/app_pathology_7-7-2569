import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from app import app
from src.database.models import db, User, FormHistory, CaseRevision, AudioTask
import psycopg2
import sqlite3

def test_databases():
    print("=================================================================")
    print("           COMPREHENSIVE DATABASE VERIFICATION REPORT           ")
    print("=================================================================")

    # 1. PostgreSQL Direct Inspection
    print("\n--- 1. PostgreSQL (Primary DB: pathology_db) ---")
    try:
        pg_conn = psycopg2.connect('postgresql://postgres:rooj282026@localhost:5432/pathology_db')
        pg_cur = pg_conn.cursor()

        # Check public tables
        pg_cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;")
        tables = [t[0] for t in pg_cur.fetchall()]
        print(f"[+] Connected to PostgreSQL successfully. Public tables: {tables}")

        for t in tables:
            pg_cur.execute(f'SELECT count(*) FROM "{t}";')
            cnt = pg_cur.fetchone()[0]
            print(f"    - Table \"{t}\": {cnt} records")

        # Check Users
        print("\n  [User Records in PostgreSQL]:")
        pg_cur.execute('SELECT id, username, email, name, is_admin FROM "user" ORDER BY id;')
        for u in pg_cur.fetchall():
            print(f"    * ID: {u[0]}, Username: '{u[1]}', Email: '{u[2]}', Name: '{u[3]}', Admin: {u[4]}")

        # Check Sequences
        print("\n  [Sequences]:")
        pg_cur.execute("SELECT sequence_name, last_value FROM information_schema.sequences s JOIN pg_sequences ps ON s.sequence_name = ps.sequencename;")
        for s in pg_cur.fetchall():
            print(f"    * Sequence: {s[0]}, Last Value: {s[1]}")

        # Check Form History Sample
        print("\n  [Form History Sample]:")
        pg_cur.execute('SELECT id, user_id, surgical_number, timestamp FROM form_history ORDER BY id DESC LIMIT 5;')
        for h in pg_cur.fetchall():
            print(f"    * Case #{h[0]} (User {h[1]}): Surgical No = {h[2]}, Timestamp = {h[3]}")

        # Check Case Revisions Sample
        print("\n  [Case Revisions Sample]:")
        pg_cur.execute('SELECT id, history_id, revision_number, action, timestamp FROM case_revision ORDER BY id DESC LIMIT 5;')
        for r in pg_cur.fetchall():
            print(f"    * Revision #{r[0]}: History #{r[1]}, Rev {r[2]}, Action: {r[3]}, Timestamp: {r[4]}")

        pg_conn.close()
    except Exception as e:
        print(f"[-] PostgreSQL Error: {e}")

    # 2. SQLite (Local / Fallback DB: data/instance/local_pathology.db)
    print("\n--- 2. SQLite Local Fallback DB (data/instance/local_pathology.db) ---")
    sq_path = Path('data/instance/local_pathology.db')
    if sq_path.exists():
        sq_conn = sqlite3.connect(sq_path)
        sq_cur = sq_conn.cursor()
        sq_cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        sq_tables = [t[0] for t in sq_cur.fetchall()]
        print(f"[+] SQLite Tables: {sq_tables}")
        for t in sq_tables:
            sq_cur.execute(f'SELECT count(*) FROM "{t}";')
            cnt = sq_cur.fetchone()[0]
            print(f"    - Table \"{t}\": {cnt} records")
        
        sq_cur.execute("PRAGMA table_info(user);")
        u_cols = [c[1] for c in sq_cur.fetchall()]
        print(f"    - User table columns: {u_cols}")
        sq_conn.close()
    else:
        print("[-] SQLite local file not found.")

    # 3. SQLAlchemy Model & ORM Level Check via Flask App Context
    print("\n--- 3. Flask SQLAlchemy ORM Integration Test ---")
    with app.app_context():
        print(f"[+] Active SQLALCHEMY_DATABASE_URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
        users = User.query.all()
        print(f"[+] ORM User.query.all(): {len(users)} users found")
        for u in users:
            print(f"    * ORM User: id={u.id}, username='{u.username}', check_is_admin={u.check_is_admin}")
            print(f"      - Can authenticate with 'rooj282026': {u.check_password('rooj282026')}")
            print(f"      - History cases count: {len(u.histories)}")

        cases = FormHistory.query.all()
        print(f"[+] ORM FormHistory.query.all(): {len(cases)} cases found")
        for c in cases[:3]:
            print(f"    * ORM Case #{c.id}: SurgNo='{c.surgical_number}', Author='{c.author.username if c.author else None}', Revisions={len(c.revisions)}")

    # 4. HTTP / Session Login Simulation Test via Flask Test Client
    print("\n--- 4. HTTP Client Authentication Simulation Test ---")
    with app.test_client() as client:
        # Test 1: GET / (with unauthenticated session)
        res_index = client.get('/')
        print(f"[+] GET / -> Status: {res_index.status_code}")

        # Test 2: POST /login with invalid password
        res_login_bad = client.post('/login', data={'username': 'roojask', 'password': 'wrongpassword'}, follow_redirects=True)
        print(f"[+] POST /login (wrong password) -> Status: {res_login_bad.status_code}, 'Invalid username or password' present: {'Invalid username or password' in res_login_bad.get_data(as_text=True)}")

        # Test 3: POST /login with correct password for 'roojask'
        res_login_ok = client.post('/login', data={'username': 'roojask', 'password': 'rooj282026'}, follow_redirects=False)
        print(f"[+] POST /login (correct password 'roojask') -> Status: {res_login_ok.status_code}, Location: {res_login_ok.headers.get('Location')}")

        # Test 4: Follow redirect to /dashboard with authenticated cookie session
        res_dash = client.get('/dashboard')
        print(f"[+] GET /dashboard (with session) -> Status: {res_dash.status_code}, User greeting present: {'roojask' in res_dash.get_data(as_text=True)}")

        # Test 5: POST /login with user 'test1'
        client.get('/logout')
        res_test1 = client.post('/login', data={'username': 'test1', 'password': 'rooj282026'}, follow_redirects=False)
        print(f"[+] POST /login (correct password 'test1') -> Status: {res_test1.status_code}, Location: {res_test1.headers.get('Location')}")

    print("\n=================================================================")
    print("              DATABASE VERIFICATION COMPLETED                    ")
    print("=================================================================")

if __name__ == '__main__':
    test_databases()
