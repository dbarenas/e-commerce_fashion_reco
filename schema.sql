CREATE TABLE IF NOT EXISTS image_metadata (
    image_id TEXT PRIMARY KEY,
    file_path TEXT,
    description TEXT,
    dominant_colors TEXT[],
    style_tags TEXT[],
    garment_type TEXT,
    accessories TEXT[],
    gender TEXT,
    season TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS image_navigation_paths (
    source_image_id TEXT REFERENCES image_metadata(image_id),
    next_possible_images TEXT[],
    path_scores FLOAT[],
    reason TEXT,
    created_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (source_image_id)
);

CREATE TABLE IF NOT EXISTS user_interactions (
    interaction_id SERIAL PRIMARY KEY,
    user_id TEXT,
    image_id TEXT REFERENCES image_metadata(image_id),
    clicked BOOLEAN,
    timestamp TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id SERIAL PRIMARY KEY,
    user_id TEXT,
    source_image_id TEXT REFERENCES image_metadata(image_id),
    recommended_images TEXT[],
    reasoning TEXT[],
    generated_at TIMESTAMP DEFAULT now()
);
