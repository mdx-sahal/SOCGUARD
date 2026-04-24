import time
import psycopg2
import sys

# Configuration
DB_HOST = "127.0.0.1"
DB_PORT = "5435"
DB_NAME = "socguard_db"
DB_USER = "socguard_user"
DB_PASS = "socguard_password"

def check_pipeline():
    print("---------------------------------------------------")
    print("SOCGUARD PIPEPLINE VERIFICATION")
    print("---------------------------------------------------")
    print(f"Target: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"User: {DB_USER}")
    print(f"Attempting to connect with password: {DB_PASS}...") # Debug line as requested
    
    conn = None
    try:
        max_retries = 5
        for i in range(max_retries):
            try:
                conn = psycopg2.connect(
                    host=DB_HOST,
                    port=DB_PORT,
                    dbname=DB_NAME,
                    user=DB_USER,
                    password=DB_PASS
                )
                print("SUCCESS: Connected to the database!")
                break
            except psycopg2.OperationalError as e:
                if i < max_retries - 1:
                    print(f"Connection failed (attempt {i+1}/{max_retries}): {e}")
                    print("Retrying in 2 seconds...")
                    time.sleep(2)
                else:
                    print(f"\nCRITICAL ERROR: Connection Failed after {max_retries} attempts.\n{e}")
                    print("Did you run 'docker-compose down -v' to clear old password data?")
                    sys.exit(1)
            
        cur = conn.cursor()
        
        print("\nChecking for alerts (waiting 60 seconds for pipeline to warm up)...")
        print("Press Ctrl+C to abort.")
        
        initial_count = -1
        start_time = time.time()
        timeout = 60 # seconds
        
        while (time.time() - start_time) < timeout:
            try:
                cur.execute("SELECT COUNT(*) FROM alerts;")
                count = cur.fetchone()[0]
                
                if initial_count == -1:
                    initial_count = count
                    print(f"Initial Alert Count: {count}")
                elif count > initial_count:
                    print(f"\n[PASS] Pipeline is working! Alert count increased: {initial_count} -> {count}")
                    print("New alerts are being persisted to the database.")
                    
                    # Fetch one usage example
                    cur.execute("SELECT threat_category, reasoning FROM alerts ORDER BY id DESC LIMIT 1;")
                    alert = cur.fetchone()
                    if alert:
                         print(f"Latest Alert: [{alert[0]}] - {alert[1]}")
                    
                    conn.close()
                    sys.exit(0)
                else:
                    sys.stdout.write(".")
                    sys.stdout.flush()
                
                time.sleep(2)
                
            except Exception as e:
                print(f"\nError Querying DB: {e}")
                if conn:
                    conn.rollback()
                
        print("\n\n[FAIL] Timeout reached. No new alerts arrived in the database.")
        print("Troubleshooting:")
        print("1. Check if 'ingestion-service' is running.")
        print("2. Check 'kafka' health.")
        print("3. Check 'alert-persistence-service' logs for errors.")

    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    check_pipeline()
