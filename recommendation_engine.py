import os
import psycopg2
from psycopg2 import sql, extras
import random
from collections import Counter

# Database connection details from environment variables
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "fashion_db")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")

# Predefined user_ids for whom to generate recommendations
# These are example users; in a real system, this would be dynamic.
TARGET_USER_IDS = ["user001", "user005", "user010"]

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

def get_last_clicked_image_for_users(conn, user_ids):
    """
    Fetches the last clicked image_id for a list of user_ids.
    Returns a dictionary {user_id: image_id or None}.
    """
    if not user_ids:
        return {}
    
    query = sql.SQL("""
        SELECT DISTINCT ON (user_id) user_id, image_id
        FROM user_interactions
        WHERE user_id IN %s AND clicked = TRUE
        ORDER BY user_id, timestamp DESC;
    """)
    
    user_last_clicked = {}
    try:
        with conn.cursor(cursor_factory=extras.DictCursor) as cur:
            cur.execute(query, (tuple(user_ids),))
            records = cur.fetchall()
            for record in records:
                user_last_clicked[record['user_id']] = record['image_id']
        
        # For users who might not have clicked anything, assign None (or a random image later)
        for user_id in user_ids:
            if user_id not in user_last_clicked:
                user_last_clicked[user_id] = None # Will be handled by fetching a random image
        return user_last_clicked
    except psycopg2.Error as e:
        print(f"Error fetching last clicked images: {e}")
        return {user_id: None for user_id in user_ids} # Default to None on error

def get_random_image(conn):
    """Fetches a single random image_id from image_metadata."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT image_id FROM image_metadata ORDER BY RANDOM() LIMIT 1;")
            record = cur.fetchone()
            return record[0] if record else None
    except psycopg2.Error as e:
        print(f"Error fetching random image: {e}")
        return None

def get_user_clicked_history(conn, user_id):
    """Fetches all image_ids clicked by a user."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT image_id FROM user_interactions WHERE user_id = %s AND clicked = TRUE;", (user_id,))
            return [row[0] for row in cur.fetchall()]
    except psycopg2.Error as e:
        print(f"Error fetching user history for {user_id}: {e}")
        return []

def get_image_metadata_batch(conn, image_ids):
    """Fetches metadata for a list of image_ids."""
    if not image_ids: return {}
    try:
        with conn.cursor(cursor_factory=extras.DictCursor) as cur:
            cur.execute("SELECT image_id, style_tags, dominant_colors, garment_type FROM image_metadata WHERE image_id IN %s;", (tuple(image_ids),))
            return {row['image_id']: dict(row) for row in cur.fetchall()}
    except psycopg2.Error as e:
        print(f"Error fetching image metadata batch: {e}")
        return {}

def get_navigation_path_for_source(conn, source_image_id):
    """Fetches next_possible_images and path_scores for a source_image_id."""
    try:
        with conn.cursor(cursor_factory=extras.DictCursor) as cur:
            cur.execute("SELECT next_possible_images, path_scores FROM image_navigation_paths WHERE source_image_id = %s;", (source_image_id,))
            record = cur.fetchone()
            if record and record['next_possible_images'] and record['path_scores']:
                return record['next_possible_images'], record['path_scores']
            return [], []
    except psycopg2.Error as e:
        print(f"Error fetching navigation path for {source_image_id}: {e}")
        return [], []

def generate_recommendations_for_pair(conn, user_id, source_image_id, all_metadata_cache):
    """Generates recommendations for a single user and source image."""
    user_clicked_history = get_user_clicked_history(conn, user_id)
    
    # Fetch metadata for source image if not in cache
    if source_image_id not in all_metadata_cache:
        meta = get_image_metadata_batch(conn, [source_image_id])
        if meta: all_metadata_cache.update(meta)

    source_image_meta = all_metadata_cache.get(source_image_id)
    if not source_image_meta:
        print(f"Skipping recommendations for user {user_id}: Source image {source_image_id} metadata not found.")
        return [], []

    # Fetch user liked items' metadata
    liked_items_metadata_list = []
    if user_clicked_history:
        # Ensure metadata for liked items is in cache
        missing_liked_meta_ids = [img_id for img_id in user_clicked_history if img_id not in all_metadata_cache]
        if missing_liked_meta_ids:
             all_metadata_cache.update(get_image_metadata_batch(conn, missing_liked_meta_ids))
        liked_items_metadata_list = [all_metadata_cache[img_id] for img_id in user_clicked_history if img_id in all_metadata_cache]

    # 1. Initial Candidates from navigation paths
    nav_candidates, nav_scores = get_navigation_path_for_source(conn, source_image_id)
    
    candidate_scores = {}
    for img_id, score in zip(nav_candidates, nav_scores):
        candidate_scores[img_id] = {"score": score, "reasons": ["This item complements your current selection."]}

    # 2. Filter Out
    filtered_candidates = {}
    for img_id, data in candidate_scores.items():
        if img_id == source_image_id:
            continue
        if img_id in user_clicked_history:
            continue
        filtered_candidates[img_id] = data
    
    # Ensure metadata for candidates is cached
    missing_candidate_meta_ids = [img_id for img_id in filtered_candidates if img_id not in all_metadata_cache]
    if missing_candidate_meta_ids:
        all_metadata_cache.update(get_image_metadata_batch(conn, missing_candidate_meta_ids))

    # 3. Scoring & Boosting based on user history
    if liked_items_metadata_list:
        common_style_tags = Counter(tag for item_meta in liked_items_metadata_list for tag in item_meta.get('style_tags', []))
        common_colors = Counter(color for item_meta in liked_items_metadata_list for color in item_meta.get('dominant_colors', []))
        common_garment_types = Counter(item_meta.get('garment_type') for item_meta in liked_items_metadata_list if item_meta.get('garment_type'))

        for img_id, data in filtered_candidates.items():
            candidate_meta = all_metadata_cache.get(img_id)
            if not candidate_meta: continue

            boost_reasons = []
            # Boost for matching style tags
            for tag in candidate_meta.get('style_tags', []):
                if tag in common_style_tags:
                    data['score'] += 0.1 * common_style_tags[tag] # More liked, more boost
                    boost_reasons.append(f"You previously liked items with similar '{tag}' style.")
            # Boost for matching dominant colors
            for color in candidate_meta.get('dominant_colors', []):
                if color in common_colors:
                    data['score'] += 0.05 * common_colors[color]
                    boost_reasons.append(f"You previously liked items with similar '{color}' color.")
            # Boost for matching garment type (if different from source image's garment type, to encourage variety unless it's a strong match)
            cand_garment = candidate_meta.get('garment_type')
            if cand_garment and cand_garment in common_garment_types and cand_garment != source_image_meta.get('garment_type'):
                data['score'] += 0.2 
                boost_reasons.append(f"You previously liked '{cand_garment}' type items.")
            
            if boost_reasons:
                 # Prioritize new reasons if they are specific
                if "This item complements your current selection." in data['reasons'] and len(boost_reasons) > 0:
                    data['reasons'] = boost_reasons
                else:
                    data['reasons'].extend(boost_reasons)
                # Remove duplicates
                data['reasons'] = sorted(list(set(data['reasons'])))


    # 4. Ranking & Selection
    # Sort by score
    sorted_candidates = sorted(filtered_candidates.items(), key=lambda item: item[1]['score'], reverse=True)
    
    top_3_recommendations = []
    top_3_reasons = []
    for img_id, data in sorted_candidates[:3]:
        top_3_recommendations.append(img_id)
        top_3_reasons.append(". ".join(data['reasons']))
        
    return top_3_recommendations, top_3_reasons


def insert_recommendations(conn, user_id, source_image_id, recommended_ids, reasons_text):
    """Inserts generated recommendations into the recommendations table."""
    if not recommended_ids:
        print(f"No recommendations to insert for user {user_id}, source {source_image_id}.")
        return False
        
    insert_query = sql.SQL("""
        INSERT INTO recommendations (user_id, source_image_id, recommended_images, reasoning, generated_at)
        VALUES (%s, %s, %s, %s, %s);
    """)
    try:
        with conn.cursor() as cur:
            cur.execute(insert_query, (user_id, source_image_id, recommended_ids, reasons_text, datetime.now()))
        conn.commit()
        return True
    except psycopg2.Error as e:
        print(f"Error inserting recommendations for user {user_id}, source {source_image_id}: {e}")
        conn.rollback()
        return False

def main():
    """Main function to run the recommendation engine for target users."""
    try:
        import psycopg2
        from psycopg2 import extras
    except ImportError:
        print("psycopg2 or its extras module is not installed. Please install it: pip install psycopg2-binary")
        return

    conn = get_db_connection()
    if not conn:
        return

    if not create_tables_if_not_exist(conn): # Ensures 'recommendations' table is created
        conn.close()
        return

    # Get (user_id, source_image_id) pairs
    user_source_images = get_last_clicked_image_for_users(conn, TARGET_USER_IDS)
    
    input_pairs = []
    for user_id, source_img_id in user_source_images.items():
        if source_img_id is None:
            print(f"User {user_id} has no clicked items. Assigning a random image as source.")
            source_img_id = get_random_image(conn)
            if source_img_id is None:
                print(f"Could not get a random image for user {user_id}. Skipping.")
                continue
        input_pairs.append((user_id, source_img_id))

    if not input_pairs:
        print("No (user, source_image) pairs to process. Exiting.")
        conn.close()
        return
        
    print(f"Generating recommendations for {len(input_pairs)} user/source image pairs: {input_pairs}")

    # Cache for image metadata to reduce DB queries
    all_metadata_cache = {} 

    for user_id, source_image_id in input_pairs:
        print(f"\nProcessing: User '{user_id}', Source Image '{source_image_id}'")
        
        recommended_ids, reasons = generate_recommendations_for_pair(conn, user_id, source_image_id, all_metadata_cache)
        
        if recommended_ids:
            print(f"  Recommendations for {user_id} (based on {source_image_id}):")
            for i, img_id in enumerate(recommended_ids):
                print(f"    - {img_id}: {reasons[i]}")
            insert_recommendations(conn, user_id, source_image_id, recommended_ids, reasons)
        else:
            print(f"  No recommendations generated for {user_id} based on {source_image_id}.")
            
    conn.close()
    print("\nRecommendation engine process completed.")

if __name__ == "__main__":
    from datetime import datetime # Ensure datetime is available for direct script run.
    main()
