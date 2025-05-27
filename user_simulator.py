import os
import psycopg2
from psycopg2 import sql, extras
import random
from datetime import datetime

# Database connection details from environment variables
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "fashion_db")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")

USER_IDS = [f"user{i:03d}" for i in range(1, 16)] # user001 to user015

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
        return conn
    except psycopg2.OperationalError as e:
        print(f"Error connecting to the database: {e}")
        return None

def create_tables_if_not_exist(conn):
    """Creates tables from schema.sql if they don't exist."""
    try:
        with open("schema.sql", "r") as f:
            schema_sql = f.read()
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
        print("Tables from schema.sql checked/created successfully.")
    except (FileNotFoundError, psycopg2.Error) as e:
        print(f"Error creating tables: {e}")
        conn.rollback()
        return False
    return True

def fetch_all_image_ids(conn):
    """Fetches all image_ids from the image_metadata table."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT image_id FROM image_metadata;")
            records = cur.fetchall()
            if not records:
                print("No image_ids found in image_metadata. Run ETL script first.")
                return []
            return [record[0] for record in records]
    except psycopg2.Error as e:
        print(f"Error fetching all image_ids: {e}")
        return []

def fetch_navigation_paths(conn):
    """Fetches navigation paths and stores them in a dictionary."""
    paths = {}
    try:
        with conn.cursor(cursor_factory=extras.DictCursor) as cur:
            cur.execute("SELECT source_image_id, next_possible_images FROM image_navigation_paths WHERE next_possible_images IS NOT NULL AND array_length(next_possible_images, 1) > 0;")
            records = cur.fetchall()
            if not records:
                print("No navigation paths found. Run semantic_enrichment.py first.")
                return {}
            for record in records:
                paths[record['source_image_id']] = record['next_possible_images']
            return paths
    except psycopg2.Error as e:
        print(f"Error fetching navigation paths: {e}")
        return {}

def insert_user_interaction(conn, user_id, image_id, clicked):
    """Inserts a single user interaction record."""
    insert_query = sql.SQL("""
        INSERT INTO user_interactions (user_id, image_id, clicked, timestamp)
        VALUES (%s, %s, %s, %s);
    """)
    try:
        with conn.cursor() as cur:
            cur.execute(insert_query, (user_id, image_id, clicked, datetime.now()))
        return True
    except psycopg2.Error as e:
        print(f"Error inserting interaction for user {user_id}, image {image_id}: {e}")
        return False

def simulate_user_sessions(conn, all_image_ids, nav_paths):
    """Simulates user sessions and records interactions."""
    if not all_image_ids:
        print("Cannot simulate sessions: No image IDs available.")
        return

    total_interactions_recorded = 0
    print("Starting user simulation...")

    for user_id in USER_IDS:
        print(f"Simulating session for {user_id}...")
        session_length = random.randint(3, 7)
        
        # Entry point: Select a random image
        current_image_id = random.choice(all_image_ids)
        if insert_user_interaction(conn, user_id, current_image_id, True): # First interaction is always a "click"
            total_interactions_recorded += 1
        else:
            conn.rollback() # Rollback this user's transaction if first insert fails
            continue # Skip to next user if initial interaction fails

        for _ in range(1, session_length): # Remaining interactions in the session
            action_choice = random.random() # 0.0 to 1.0

            if action_choice < 0.85 and current_image_id in nav_paths: # 85% chance to follow path
                next_images = nav_paths[current_image_id]
                if next_images:
                    viewed_image_id = random.choice(next_images)
                    clicked = random.random() < 0.70 # 70% chance to click
                    
                    if insert_user_interaction(conn, user_id, viewed_image_id, clicked):
                        total_interactions_recorded += 1
                    else:
                        conn.rollback() # Rollback this user's transaction
                        break # End session for this user on error

                    if clicked:
                        current_image_id = viewed_image_id
                    else:
                        # User didn't click, they might "bounce" or continue from same image.
                        # For simplicity, let's say they might pick a random image next (fall through to Random Skip)
                        # or try to follow path from the *same* current_image_id again.
                        # To make it more likely to move, let's make them fall to Random Skip.
                        current_image_id = random.choice(all_image_ids) # Simulates a "bounce" to a new random image
                else: # No path available from current image
                    current_image_id = random.choice(all_image_ids)
                    if insert_user_interaction(conn, user_id, current_image_id, random.random() < 0.50):
                         total_interactions_recorded +=1
                    else:
                        conn.rollback(); break
            else: # 15% chance for Random Skip or if path following ended/failed
                current_image_id = random.choice(all_image_ids)
                clicked = random.random() < 0.50 # 50% chance to click on a random skip
                if insert_user_interaction(conn, user_id, current_image_id, clicked):
                    total_interactions_recorded += 1
                else:
                    conn.rollback() # Rollback this user's transaction
                    break # End session for this user on error
        
        conn.commit() # Commit all interactions for this user
        print(f"Session for {user_id} completed.")

    print(f"\nUser simulation completed. Total interactions recorded: {total_interactions_recorded}.")

def main():
    """Main function to run the user interaction simulator."""
    try:
        import psycopg2
        from psycopg2 import extras
    except ImportError:
        print("psycopg2 or its extras module is not installed. Please install it: pip install psycopg2-binary")
        return

    conn = get_db_connection()
    if not conn:
        return

    if not create_tables_if_not_exist(conn): # This will also create user_interactions table
        conn.close()
        return

    all_image_ids = fetch_all_image_ids(conn)
    if not all_image_ids:
        print("Exiting: No image metadata found. Run ETL first.")
        conn.close()
        return
        
    nav_paths = fetch_navigation_paths(conn)
    if not nav_paths:
        print("Warning: No navigation paths found. Simulation will rely more on random skips. Run semantic_enrichment.py.")
        # Continue simulation, but it will be mostly random.

    simulate_user_sessions(conn, all_image_ids, nav_paths)

    conn.close()
    print("User simulation process finished.")

if __name__ == "__main__":
    main()
