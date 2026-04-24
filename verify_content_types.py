import psycopg2
import sys

# Configuration
DB_HOST = "127.0.0.1"
DB_PORT = "5435"
DB_NAME = "socguard_db"
DB_USER = "socguard_user"
DB_PASS = "socguard_password"

def verify_content_types():
    print("---------------------------------------------------")
    print("SOCGUARD CONTENT TYPE VERIFICATION")
    print("---------------------------------------------------")
    
    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        
        # 1. Count Total
        cur.execute("SELECT COUNT(*) FROM alerts;")
        total = cur.fetchone()[0]
        print(f"Total Alerts: {total}")
        
        # 2. Count by Service (Inferred from Reasoning or Threat Category)
        print("\n--- Breakdown by Threat Category ---")
        cur.execute("SELECT threat_category, COUNT(*) FROM alerts GROUP BY threat_category ORDER BY COUNT(*) DESC;")
        rows = cur.fetchall()
        for row in rows:
            print(f"{row[0]}: {row[1]}")
            
        print("\n--- Recent Alerts ---")
        cur.execute("SELECT threat_category, original_url FROM alerts ORDER BY id DESC LIMIT 5;")
        rows = cur.fetchall()
        for row in rows:
            print(f"Type: {row[0]}, URL: {row[1]}")

        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")
        if conn:
            conn.close()

if __name__ == "__main__":
    verify_content_types()
