import os
from PIL import Image, ImageDraw
import random

# Create the images directory if it doesn't exist
if not os.path.exists("images"):
    os.makedirs("images")

# Image dimensions
width = 23
height = 23

# List of summer colors
summer_colors = [
    (255, 228, 181),  # Moccasin (sand)
    (135, 206, 250),  # Light Sky Blue
    (255, 182, 193),  # Light Pink
    (240, 230, 140),  # Khaki (light yellow)
    (152, 251, 152),  # Pale Green
    (255, 160, 122),  # Light Salmon
    (224, 255, 255),  # Light Cyan
    (255, 250, 205),  # Lemon Chiffon
    (173, 216, 230),  # Light Blue
    (244, 164, 96),   # Sandy Brown
]

# Function to generate a random color
def get_random_color():
    return (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

# Generate 30 images
for i in range(1, 31):
    # Create a new image with a random summer background color
    bg_color = random.choice(summer_colors)
    image = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(image)

    # Add a simple geometric shape with a random color
    shape_color = get_random_color()
    # Ensure shape color is different from background color
    while shape_color == bg_color:
        shape_color = get_random_color()

    # Randomly choose a shape type
    shape_type = random.choice(["rectangle", "ellipse", "line"])

    # Define shape coordinates (can be randomized further)
    x1 = random.randint(3, 8)
    y1 = random.randint(3, 8)
    x2 = random.randint(15, 20)
    y2 = random.randint(15, 20)

    if shape_type == "rectangle":
        draw.rectangle([(x1, y1), (x2, y2)], fill=shape_color)
    elif shape_type == "ellipse":
        draw.ellipse([(x1, y1), (x2, y2)], fill=shape_color)
    elif shape_type == "line":
        # For a line, make it thicker
        draw.line([(x1, y1), (x2, y2)], fill=shape_color, width=random.randint(2,4))
        # Add another line to make it more visible
        draw.line([(x1, y2), (x2, y1)], fill=shape_color, width=random.randint(2,3))


    # Save the image
    image_name = f"img_{i:03d}.jpg"
    image_path = os.path.join("images", image_name)
    image.save(image_path)

print("Generated 30 images in the 'images' directory.")
