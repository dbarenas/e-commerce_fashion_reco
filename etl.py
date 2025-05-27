import glob
import random
import os
import psycopg2
from psycopg2 import sql

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            dbname=os.environ.get("DB_NAME", "fashion_db"),
            user=os.environ.get("DB_USER", "postgres"),
            password=os.environ.get("DB_PASSWORD", "postgres")
        )
        return conn
    except psycopg2.OperationalError as e:
        print(f"Error connecting to the database: {e}")
        print("Please ensure PostgreSQL is running and environment variables are set correctly:")
        print("DB_HOST, DB_NAME, DB_USER, DB_PASSWORD")
        return None

def create_table_if_not_exists(conn):
    """Creates the image_metadata table from schema.sql if it doesn't exist."""
    try:
        with open("schema.sql", "r") as f:
            schema_sql = f.read()
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
        print("Table 'image_metadata' checked/created successfully.")
    except (FileNotFoundError, psycopg2.Error) as e:
        print(f"Error creating table: {e}")
        conn.rollback() # Rollback in case of error during table creation
        return False
    return True

def insert_metadata(conn, metadata):
    """Inserts image metadata into the image_metadata table."""
    insert_query = sql.SQL("""
        INSERT INTO image_metadata (
            image_id, file_path, description, dominant_colors, 
            style_tags, garment_type, accessories, gender, season
        ) VALUES (
            %(image_id)s, %(file_path)s, %(description)s, %(dominant_colors)s,
            %(style_tags)s, %(garment_type)s, %(accessories)s, %(gender)s, %(season)s
        ) ON CONFLICT (image_id) DO NOTHING;
    """) # ON CONFLICT clause to avoid issues if script is run multiple times
    try:
        with conn.cursor() as cur:
            cur.execute(insert_query, metadata)
        return True
    except psycopg2.Error as e:
        print(f"Error inserting metadata for {metadata.get('image_id', 'Unknown image')}: {e}")
        return False

def generate_and_store_metadata():
    """
    Generates placeholder metadata for images and stores it in PostgreSQL.
    """
    conn = get_db_connection()
    if not conn:
        return

    if not create_table_if_not_exists(conn):
        conn.close()
        return

    image_files = glob.glob("./images/img_*.jpg")
    if not image_files:
        print("No images found in the ./images directory.")
        conn.close()
        return

    possible_colors = ["red", "blue", "green", "yellow", "white", "black", "pink", "orange"]
    possible_style_tags = ["casual", "sporty", "beachwear", "formal", "bohemian", "chic"]
    possible_garment_types = ["t-shirt", "shorts", "dress", "skirt", "sandals", "hat", "sunglasses", "swimsuit"]
    possible_accessories = ["sunglasses", "hat", "belt", "bag", "watch", "none"]
    genders = ["men", "women"]
    
    inserted_count = 0
    error_count = 0

    for img_path in sorted(image_files):
        image_id = os.path.basename(img_path)
        file_path = os.path.abspath(img_path)
        description = f"Placeholder summer item {image_id}"
        dominant_colors = random.sample(possible_colors, random.randint(2, 3))
        style_tags = random.sample(possible_style_tags, random.randint(2, 3))
        garment_type = random.choice(possible_garment_types)
        num_accessories = random.randint(1, 2)
        if num_accessories == 1 and random.choice([True, False]):
            accessories = ["none"]
        else:
            accessories = random.sample([acc for acc in possible_accessories if acc != "none"], 
                                        min(num_accessories, len(possible_accessories)-1))
            if not accessories: accessories = ["none"]
        
        gender = random.choice(genders)
        season = "summer"

        metadata = {
            "image_id": image_id,
            "file_path": file_path,
            "description": description,
            "dominant_colors": dominant_colors,
            "style_tags": style_tags,
            "garment_type": garment_type,
            "accessories": accessories,
            "gender": gender,
            "season": season,
        }
        
        if insert_metadata(conn, metadata):
            inserted_count += 1
        else:
            error_count +=1
            conn.rollback() # Rollback the failed transaction

    if error_count == 0 and inserted_count > 0:
        conn.commit() # Commit all successful insertions
        print(f"Successfully inserted metadata for {inserted_count} images.")
    elif inserted_count > 0 and error_count > 0:
        conn.commit() # Commit successful insertions, failed ones were rolled back
        print(f"Successfully inserted metadata for {inserted_count} images, but {error_count} insertions failed.")
    elif error_count > 0 and inserted_count == 0:
        print(f"All {error_count} metadata insertions failed. No data committed.")
    else:
        print("No new metadata was processed.")

    conn.close()

if __name__ == "__main__":
    # Ensure psycopg2 is installed
    try:
        import psycopg2
    except ImportError:
        print("psycopg2 is not installed. Please install it by running: pip install psycopg2-binary")
        exit(1)
        
    generate_and_store_metadata()
