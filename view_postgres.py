import psycopg2

def view_pg_data():
    conn_str = "postgresql://pathology_user:secure_password@localhost:5432/pathology_db"
    try:
        conn = psycopg2.connect(conn_str)
        cur = conn.cursor()
        
        # 1. Query Users
        print("\n" + "=" * 50)
        print("PostgreSQL - USER TABLE")
        print("=" * 50)
        cur.execute('SELECT id, username, email, name FROM "user" ORDER BY id;')
        users = cur.fetchall()
        for u in users:
            print(f"ID: {u[0]} | Username: {u[1]} | Email: {u[2]} | Name: {u[3]}")
        if not users:
            print("(No records found)")
        
        # 2. Query Histories
        print("\n" + "=" * 50)
        print("PostgreSQL - FORM_HISTORY TABLE")
        print("=" * 50)
        cur.execute('SELECT id, user_id, surgical_number, timestamp FROM form_history ORDER BY id;')
        histories = cur.fetchall()
        for h in histories:
            print(f"ID: {h[0]} | User ID: {h[1]} | Surgical No: {h[2]} | Timestamp: {h[3]}")
        if not histories:
            print("(No records found)")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {e}")

if __name__ == "__main__":
    view_pg_data()
