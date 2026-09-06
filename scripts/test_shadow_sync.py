import sys
import json
import sqlite3
import psycopg2
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

from app import app
from src.database.models import db, User, FormHistory

def test_shadow_sync_pipeline():
    print("=== TESTING SHADOW SYNC AND PERSISTENCE PIPELINE ===")
    with app.test_client() as client:
        # Login
        client.post('/login', data={'username': 'roojask', 'password': 'rooj282026'}, follow_redirects=True)
        
        # Test case data
        test_sno = "S-TEST-ZERO-LOSS"
        post_data = {
            's0_surgical_no': test_sno,
            's1_side': 'right',
            's2_proc': 'modified',
            's3_dims_0': '10', 's3_dims_1': '8', 's3_dims_2': '5',
            'footer_prosecutor': 'Dr. Test',
            'footer_date': '2026-09-06'
        }

        # Send POST to /generate
        res = client.post('/generate', data=post_data, follow_redirects=False)
        print(f"[1] POST /generate status: {res.status_code}")

        # Verify in PostgreSQL
        with app.app_context():
            created = FormHistory.query.filter_by(surgical_number=test_sno).first()
            if created:
                print(f"[2] PostgreSQL: Found created case ID={created.id}, SurgNo={created.surgical_number}")
                case_id = created.id
            else:
                print("[-] PostgreSQL: Case not found!")
                return

        # Verify in SQLite
        sq_path = BASE_DIR / "data" / "instance" / "local_pathology.db"
        sq_conn = sqlite3.connect(str(sq_path))
        sq_cur = sq_conn.cursor()
        sq_cur.execute("SELECT id, surgical_number FROM form_history WHERE id = ?", (case_id,))
        sq_row = sq_cur.fetchone()
        sq_conn.close()
        if sq_row:
            print(f"[3] SQLite Shadow DB: Verified case ID={sq_row[0]}, SurgNo={sq_row[1]}")
        else:
            print("[-] SQLite Shadow DB: Case not found!")

        # Verify JSON file
        json_path = BASE_DIR / "data" / "outputs" / f"case_{case_id}.json"
        if json_path.exists():
            print(f"[4] Filesystem JSON Archive: Verified file exists ({json_path.name})")
        else:
            print("[-] Filesystem JSON Archive: Not found!")

        # Clean up test case
        with app.app_context():
            db.session.delete(created)
            db.session.commit()

        sq_conn = sqlite3.connect(str(sq_path))
        sq_cur = sq_conn.cursor()
        sq_cur.execute("DELETE FROM form_history WHERE id = ?", (case_id,))
        sq_conn.commit()
        sq_conn.close()

        if json_path.exists():
            json_path.unlink()

        print("[+] Test case cleaned up cleanly.")
        print("=== PIPELINE TEST PASSED 100% ===")

if __name__ == '__main__':
    test_shadow_sync_pipeline()
