import os
import psycopg2
from psycopg2 import sql, extras
import random

# Database connection details from environment variables
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "fashion_db")
DB_USER = os.environ.get("DB_USER", "postgres") # Default user for postgres image
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres") # Default password for postgres image

PRIMARY_GARMENT_TYPES = ["t-shirt", "shorts", "dress", "skirt", "swimsuit"] # Main clothing items
ACCESSORY_GARMENT_TYPES = ["sunglasses", "hat", "belt", "bag", "watch", "sandals"] # Accessories

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
        return conn
    except psycopg2.OperationalError as e:
        print(f"Error connecting to the database: {e}")
        print("Please ensure PostgreSQL is running and environment variables are set correctly:")
        print(f"DB_HOST={DB_HOST}, DB_NAME={DB_NAME}, DB_USER={DB_USER}, DB_PASSWORD=...")
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

def fetch_image_metadata(conn):
    """Fetches all image metadata from the image_metadata table."""
    try:
        with conn.cursor(cursor_factory=extras.DictCursor) as cur:
            cur.execute("SELECT image_id, style_tags, garment_type, accessories, gender FROM image_metadata;")
            records = cur.fetchall()
            if not records:
                print("No image metadata found in the database. Run ETL script first.")
                return []
            return [dict(record) for record in records]
    except psycopg2.Error as e:
        print(f"Error fetching image metadata: {e}")
        return []

def calculate_similarity_score(source_image, candidate_image, all_images_map):
    """Calculates a similarity score between two images based on defined rules."""
    score = 0.0
    reasons = []

    # Rule 1: Shared Tags or Garment Type
    shared_style_tags = set(source_image['style_tags']) & set(candidate_image['style_tags'])
    if shared_style_tags:
        score += 0.1 * len(shared_style_tags)
        reasons.append(f"Shared style_tags: {', '.join(shared_style_tags)}")
    
    if source_image['garment_type'] == candidate_image['garment_type']:
        score += 0.2 # Higher weight for same garment type initially
        reasons.append(f"Same garment_type: {source_image['garment_type']}")
    elif candidate_image['garment_type'] in source_image['style_tags']: # e.g. source has "dress" style, candidate is a "dress"
        score += 0.1
        reasons.append(f"Candidate garment_type '{candidate_image['garment_type']}' in source style_tags.")


    # Rule 2: Accessory Complementarity
    source_is_primary = source_image['garment_type'] in PRIMARY_GARMENT_TYPES
    candidate_is_accessory = candidate_image['garment_type'] in ACCESSORY_GARMENT_TYPES
    
    source_is_accessory = source_image['garment_type'] in ACCESSORY_GARMENT_TYPES
    candidate_is_primary = candidate_image['garment_type'] in PRIMARY_GARMENT_TYPES

    if source_is_primary and candidate_is_accessory:
        score += 0.25
        reasons.append(f"Accessory complement: source is primary ({source_image['garment_type']}), candidate is accessory ({candidate_image['garment_type']})")
    elif source_is_accessory and candidate_is_primary:
        score += 0.25
        reasons.append(f"Accessory complement: source is accessory ({source_image['garment_type']}), candidate is primary ({candidate_image['garment_type']})")

    # Rule 3: Style Variation (Intentional Detour) - 20% chance
    # Applied later in selection if not enough diverse high-score candidates
    
    return min(score, 1.0), reasons


def generate_navigation_paths(all_images_metadata):
    """Generates navigation paths for each image."""
    navigation_paths = []
    all_images_map = {img['image_id']: img for img in all_images_metadata}

    for source_image in all_images_metadata:
        potential_candidates = []
        for candidate_image_metadata in all_images_metadata:
            if source_image['image_id'] == candidate_image_metadata['image_id']:
                continue

            score, _ = calculate_similarity_score(source_image, candidate_image_metadata, all_images_map)
            if score > 0.1: # Basic threshold to consider a candidate
                potential_candidates.append({
                    "image_id": candidate_image_metadata['image_id'],
                    "score": score,
                    "gender": candidate_image_metadata['gender'], # for style variation rule
                    "style_tags": candidate_image_metadata['style_tags'] # for style variation rule
                })
        
        # Sort candidates by score
        potential_candidates.sort(key=lambda x: x['score'], reverse=True)
        
        selected_next_images = []
        selected_scores = []
        
        # Select top 3-5 candidates
        count = 0
        for cand in potential_candidates:
            if count < 5: # Max 5 suggestions
                if cand['image_id'] not in [img['image_id'] for img in selected_next_images]: # ensure distinct
                    selected_next_images.append(cand)
                    count +=1
            else:
                break
        
        # Try to apply Style Variation if less than 3 candidates or to add diversity
        if len(selected_next_images) < 3 or random.random() < 0.2: # 20% chance to try style variation
            for candidate_image_metadata in all_images_metadata:
                if source_image['image_id'] == candidate_image_metadata['image_id'] or \
                   candidate_image_metadata['image_id'] in [img['image_id'] for img in selected_next_images]:
                    continue

                shared_style_tags = set(source_image['style_tags']) & set(candidate_image_metadata['style_tags'])
                if source_image['gender'] != candidate_image_metadata['gender'] and len(shared_style_tags) >= 2:
                    variation_score = 0.1 + 0.1 * len(shared_style_tags) # Base score for style variation
                    
                    # Check if it's already selected or if we can add/replace with it
                    can_add_variation = True
                    if len(selected_next_images) >= 5: # if full, check if it can replace a lower score one
                        lowest_score_idx = -1
                        min_score = 2.0 # higher than max possible
                        for idx, sel_img in enumerate(selected_next_images):
                            if sel_img['score'] < min_score:
                                min_score = sel_img['score']
                                lowest_score_idx = idx
                        if variation_score > min_score :
                             # Check if this variation candidate is not already there with a different score logic
                            if not any(c['image_id'] == candidate_image_metadata['image_id'] for c in selected_next_images):
                                selected_next_images.pop(lowest_score_idx)
                            else: # already there, maybe update score if this path is stronger (unlikely here)
                                can_add_variation = False

                        else: # variation score not high enough to replace
                            can_add_variation = False
                    
                    if can_add_variation and not any(c['image_id'] == candidate_image_metadata['image_id'] for c in selected_next_images):
                         selected_next_images.append({
                            "image_id": candidate_image_metadata['image_id'],
                            "score": min(variation_score, 1.0),
                            "reason_extra": "Style variation (different gender, similar tags)"
                        })
                         if len(selected_next_images) >=5: break # stop if full

        # Final sort for selected images
        selected_next_images.sort(key=lambda x: x['score'], reverse=True)
        final_selected_images = selected_next_images[:5] # Ensure max 5

        if final_selected_images:
            path_image_ids = [img['image_id'] for img in final_selected_images]
            path_scores = [round(img['score'], 2) for img in final_selected_images]
            
            # General reason based on the top selected image or common themes
            general_reason = "Path generated based on shared styles, garment types, and accessory complementarity."
            if final_selected_images:
                top_candidate_id = final_selected_images[0]['image_id']
                top_candidate_meta = all_images_map[top_candidate_id]
                _, top_reasons = calculate_similarity_score(source_image, top_candidate_meta, all_images_map)
                if "reason_extra" in final_selected_images[0]:
                    top_reasons.append(final_selected_images[0]['reason_extra'])

                if top_reasons:
                    general_reason = f"Primary Link: {source_image['image_id']} to {top_candidate_id} - Reasons: {'; '.join(top_reasons)}. Other suggestions follow similar logic."
            
            navigation_paths.append({
                "source_image_id": source_image['image_id'],
                "next_possible_images": path_image_ids,
                "path_scores": path_scores,
                "reason": general_reason
            })
            
    return navigation_paths

def insert_navigation_paths(conn, navigation_paths_data):
    """Inserts navigation path data into the image_navigation_paths table."""
    if not navigation_paths_data:
        print("No navigation path data to insert.")
        return 0
        
    insert_query = """
        INSERT INTO image_navigation_paths (
            source_image_id, next_possible_images, path_scores, reason
        ) VALUES (
            %(source_image_id)s, %(next_possible_images)s, %(path_scores)s, %(reason)s
        )
        ON CONFLICT (source_image_id) DO UPDATE SET
            next_possible_images = EXCLUDED.next_possible_images,
            path_scores = EXCLUDED.path_scores,
            reason = EXCLUDED.reason,
            created_at = now();
    """
    try:
        with conn.cursor() as cur:
            extras.execute_batch(cur, insert_query, navigation_paths_data)
        conn.commit()
        print(f"Successfully inserted/updated {len(navigation_paths_data)} navigation paths.")
        return len(navigation_paths_data)
    except psycopg2.Error as e:
        print(f"Error inserting navigation paths: {e}")
        conn.rollback()
        return -1 # Indicate error

def main():
    """Main function to run the semantic enrichment process."""
    # Check for psycopg2
    try:
        import psycopg2
        from psycopg2 import extras # Ensure extras is also available
    except ImportError:
        print("psycopg2 or its extras module is not installed. Please install it: pip install psycopg2-binary")
        return

    conn = get_db_connection()
    if not conn:
        return

    if not create_tables_if_not_exist(conn):
        conn.close()
        return

    all_metadata = fetch_image_metadata(conn)
    if not all_metadata:
        print("Exiting: No metadata to process.")
        conn.close()
        return
    
    print(f"Fetched {len(all_metadata)} image metadata records.")

    navigation_paths = generate_navigation_paths(all_metadata)
    if not navigation_paths:
        print("No navigation paths were generated.")
    else:
        print(f"Generated {len(navigation_paths)} navigation path entries.")
        insert_navigation_paths(conn, navigation_paths)

    conn.close()
    print("Semantic enrichment process completed.")

if __name__ == "__main__":
    main()
