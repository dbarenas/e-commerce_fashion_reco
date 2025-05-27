import glob
import os
import psycopg2
from psycopg2 import sql

# Attempt to import FashionTagger and config
try:
    from fashion_tagger import FashionTagger
except ImportError:
    print("Error: fashion_tagger.py not found. Please ensure it's in the same directory or Python path.")
    # No need to exit here, FashionTagger instantiation will handle it
    FashionTagger = None # So that the check `if not fashion_tagger_instance:` works later

# config.py is primarily used by fashion_tagger.py, direct imports not strictly needed here
# unless ETL specific configurations were to be added to config.py.

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
    # This function will also create other tables defined in schema.sql if they are not present.
    try:
        with open("schema.sql", "r") as f:
            schema_sql = f.read()
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
        print("Tables from schema.sql checked/created successfully.")
    except (FileNotFoundError) as e:
        print(f"Error: schema.sql not found. {e}")
        return False
    except (psycopg2.Error) as e:
        print(f"Error creating tables from schema.sql: {e}")
        conn.rollback() # Rollback in case of error during table creation
        return False
    return True

def insert_metadata_to_db(conn, metadata_dict):
    """Inserts image metadata into the image_metadata table."""
    # Ensure all required keys are present, using defaults from FashionTagger if any were missing
    # The FashionTagger.get_metadata should always return the full structure.
    required_keys = ["image_id", "file_path", "description", "dominant_colors", 
                     "style_tags", "garment_type", "accessories", "gender", "season"]
    for key in required_keys:
        if key not in metadata_dict:
            print(f"Warning: Key '{key}' missing from metadata for {metadata_dict.get('image_id', 'Unknown Image')}. Using default.")
            if key.endswith("s"): # for list types like dominant_colors, style_tags, accessories
                metadata_dict[key] = [] 
            else:
                metadata_dict[key] = "unknown"


    insert_query = sql.SQL("""
        INSERT INTO image_metadata (
            image_id, file_path, description, dominant_colors, 
            style_tags, garment_type, accessories, gender, season
        ) VALUES (
            %(image_id)s, %(file_path)s, %(description)s, %(dominant_colors)s,
            %(style_tags)s, %(garment_type)s, %(accessories)s, %(gender)s, %(season)s
        ) ON CONFLICT (image_id) DO UPDATE SET
            file_path = EXCLUDED.file_path,
            description = EXCLUDED.description,
            dominant_colors = EXCLUDED.dominant_colors,
            style_tags = EXCLUDED.style_tags,
            garment_type = EXCLUDED.garment_type,
            accessories = EXCLUDED.accessories,
            gender = EXCLUDED.gender,
            season = EXCLUDED.season,
            created_at = now();
    """)
    try:
        with conn.cursor() as cur:
            cur.execute(insert_query, metadata_dict)
        return True
    except psycopg2.Error as e:
        print(f"Database Error inserting metadata for {metadata_dict.get('image_id', 'Unknown image')}: {e}")
        return False
    except Exception as e:
        print(f"General Error inserting metadata for {metadata_dict.get('image_id', 'Unknown image')}: {e}")
        return False


def process_images_and_store_metadata(fashion_tagger_instance):
    """
    Uses FashionTagger to get metadata for images and stores it in PostgreSQL.
    """
    conn = get_db_connection()
    if not conn:
        return

    if not create_table_if_not_exists(conn):
        print("Exiting: Table creation failed.")
        conn.close()
        return

    image_files = glob.glob("./images/img_*.jpg")
    if not image_files:
        print("No images found in the ./images directory (e.g., ./images/img_*.jpg).")
        conn.close()
        return
    
    print(f"Found {len(image_files)} images to process.")

    inserted_count = 0
    error_count = 0
    processed_count = 0

    for img_path in sorted(image_files):
        processed_count +=1
        print(f"\nProcessing image ({processed_count}/{len(image_files)}): {img_path}")
        try:
            metadata = fashion_tagger_instance.get_metadata(img_path)
            if metadata is None: # FashionTagger.get_metadata can return None on critical error for that image
                print(f"Error: Failed to extract metadata for {img_path}. Skipping.")
                error_count += 1
                continue
            
            # The metadata dictionary from FashionTagger should now be directly usable.
            # Example:
            # metadata = {
            #     "image_id": "img_001.jpg", "file_path": "/app/images/img_001.jpg",
            #     "description": "ViT predicted label", "dominant_colors": ["(r,g,b)", ...],
            #     "style_tags": ["tag1", "tag2"], "garment_type": "unknown",
            #     "accessories": [], "gender": "unisex", "season": "summer"
            # }

            if insert_metadata_to_db(conn, metadata):
                print(f"Successfully processed and saved metadata for {metadata['image_id']}")
                inserted_count += 1
            else:
                # Error already printed by insert_metadata_to_db
                error_count += 1
                conn.rollback() # Rollback the failed transaction for this image

        except Exception as e: # Catch errors from fashion_tagger.get_metadata or other unexpected issues
            print(f"Critical error processing {img_path}: {e}. Skipping.")
            error_count += 1
            # No need to rollback here as transaction is per image or at the end

    if error_count == 0 and inserted_count > 0:
        conn.commit() 
        print(f"\nSuccessfully processed and inserted/updated metadata for all {inserted_count} images.")
    elif inserted_count > 0 and error_count > 0:
        conn.commit() 
        print(f"\nCompleted processing. Successfully inserted/updated metadata for {inserted_count} images, but {error_count} images encountered errors.")
    elif error_count > 0 and inserted_count == 0:
        print(f"\nAll {error_count} images encountered errors during processing. No metadata was saved.")
    elif inserted_count == 0 and error_count == 0 and processed_count > 0:
        print(f"\nProcessed {processed_count} images, but no new metadata was inserted/updated (possibly all images already existed and were identical or encountered non-critical issues not leading to 'error_count').")
    else: # processed_count == 0
        print("\nNo images were processed.")


    conn.close()

if __name__ == "__main__":
    # Ensure psycopg2 is installed
    try:
        import psycopg2
    except ImportError:
        print("Error: psycopg2 is not installed. Please install it by running: pip install psycopg2-binary")
        exit(1)
    
    if FashionTagger is None: # Check if FashionTagger failed to import earlier
        print("Exiting: FashionTagger module could not be imported.")
        exit(1)

    print("Initializing FashionTagger...")
    fashion_tagger_instance = None
    try:
        fashion_tagger_instance = FashionTagger()
        if fashion_tagger_instance.model is None or fashion_tagger_instance.processor is None:
            print("Exiting: FashionTagger failed to load its model or processor. Please check its logs and config.py.")
            exit(1)
        print("FashionTagger initialized successfully.")
    except Exception as e:
        print(f"Fatal Error: Could not initialize FashionTagger: {e}")
        print("Please ensure the model name in config.py is correct, you have internet access for the first download, and sufficient disk space.")
        exit(1)
        
    process_images_and_store_metadata(fashion_tagger_instance)

    print("\nETL process finished.")
    print("Note: Some fields like 'garment_type', 'accessories', and 'gender' are currently placeholders ('unknown', [], 'unisex')")
    print("as the general ViT model used by FashionTagger is not fine-tuned for specific fashion attribute extraction.")
    print("The 'style_tags' are derived from general ImageNet class predictions from the ViT model.")
