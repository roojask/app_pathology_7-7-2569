import psycopg2

def clean():
    conn = psycopg2.connect(dbname='pathology_db', user='postgres', password='rooj282026', host='localhost', port='5432')
    cur = conn.cursor()

    # Drop the duplicate plural tables
    cur.execute('DROP TABLE IF EXISTS audio_tasks CASCADE;')
    cur.execute('DROP TABLE IF EXISTS form_histories CASCADE;')
    cur.execute('DROP TABLE IF EXISTS users CASCADE;')
    conn.commit()

    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
    remaining = [t[0] for t in cur.fetchall()]
    print('Remaining clean tables in PostgreSQL:', remaining)
    
    for t in remaining:
        cur.execute(f'SELECT count(*) FROM "{t}"')
        print(f' - {t}: {cur.fetchone()[0]} rows')
        
    conn.close()

if __name__ == '__main__':
    clean()
