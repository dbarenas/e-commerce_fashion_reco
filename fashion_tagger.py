import os
from PIL import Image
import torch
from transformers import AutoModelForImageClassification, AutoProcessor
from collections import Counter

# Import configuration from config.py
try:
    from config import HUGGING_FACE_MODEL_NAME, IMAGE_SIZE
except ImportError:
    print("Error: config.py not found or variables not set. Using default fallbacks.")
    HUGGING_FACE_MODEL_NAME = "google/vit-base-patch16-224-in21k"
    IMAGE_SIZE = (224, 224)


class FashionTagger:
    def __init__(self):
        """
        Initializes the FashionTagger by loading the ViT model and processor.
        """
        self.model = None
        self.processor = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {self.device}")

        try:
            print(f"Loading model: {HUGGING_FACE_MODEL_NAME}...")
            self.model = AutoModelForImageClassification.from_pretrained(HUGGING_FACE_MODEL_NAME).to(self.device)
            self.processor = AutoProcessor.from_pretrained(HUGGING_FACE_MODEL_NAME)
            print("Model and processor loaded successfully.")
        except Exception as e:
            print(f"Error loading model/processor: {e}")
            print(f"Please check HUGGING_FACE_MODEL_NAME in config.py ('{HUGGING_FACE_MODEL_NAME}') and ensure you have an internet connection.")
            print("FashionTagger will not be functional.")

    def _get_dominant_colors(self, pil_image, count=3):
        """
        Extracts dominant colors from a PIL image.
        """
        try:
            small_image = pil_image.resize((50, 50))
            colors = small_image.getcolors(small_image.size[0] * small_image.size[1])
            if not colors:
                return ["unknown"]
            
            # Sort by count (item[0] is count, item[1] is color)
            sorted_colors = sorted(colors, key=lambda item: item[0], reverse=True)
            
            dominant_colors_rgb = []
            for i in range(min(count, len(sorted_colors))):
                # Ensure color is RGB, not RGBA or Palette index
                color = sorted_colors[i][1]
                if isinstance(color, int): # Palette index
                    # Convert palette index to RGB
                    palette = small_image.getpalette()
                    if palette:
                         r, g, b = palette[color*3 : color*3+3]
                         dominant_colors_rgb.append(f"({r},{g},{b})")
                    else: # No palette, likely grayscale or similar
                        dominant_colors_rgb.append(f"({color},{color},{color})") # crude approx for grayscale
                elif len(color) == 4: # RGBA
                     dominant_colors_rgb.append(f"({color[0]},{color[1]},{color[2]})") # strip alpha
                elif len(color) == 3: # RGB
                    dominant_colors_rgb.append(f"({color[0]},{color[1]},{color[2]})")
                else:
                    dominant_colors_rgb.append("unknown_format")


            return dominant_colors_rgb if dominant_colors_rgb else ["unknown"]
        except Exception as e:
            print(f"Error getting dominant colors: {e}")
            return ["error_extracting_colors"] * count

    def get_metadata(self, image_path):
        """
        Extracts metadata from an image using the ViT model and heuristics.

        Args:
            image_path (str): Path to the image file.

        Returns:
            dict: A dictionary containing extracted metadata.
        """
        if self.model is None or self.processor is None:
            print("FashionTagger is not functional because model/processor failed to load.")
            # Return placeholder metadata structure
            return {
                "image_id": os.path.basename(image_path),
                "file_path": os.path.abspath(image_path),
                "description": "Model not loaded",
                "dominant_colors": ["unknown"],
                "style_tags": ["unknown"],
                "garment_type": "unknown",
                "accessories": [],
                "gender": "unisex",
                "season": "summer",
            }

        try:
            pil_image = Image.open(image_path).convert("RGB")
        except FileNotFoundError:
            print(f"Error: Image file not found at {image_path}")
            return None
        except Exception as e:
            print(f"Error opening or processing image {image_path}: {e}")
            return None

        # Image Preprocessing for ViT
        try:
            inputs = self.processor(images=pil_image.resize(IMAGE_SIZE), return_tensors="pt").to(self.device)
        except Exception as e:
            print(f"Error processing image with ViT processor: {e}")
            return None
            
        # Model Inference
        predicted_labels = ["ViT inference error"]
        try:
            with torch.no_grad():
                outputs = self.model(**inputs)
            logits = outputs.logits
            
            # Get top-k predicted class labels (e.g., top 3)
            top_k_preds = torch.topk(logits, k=3)
            predicted_indices = top_k_preds.indices.squeeze().tolist()
            
            if isinstance(predicted_indices, int): # Handles k=1 or if only one logit is returned
                predicted_indices = [predicted_indices]

            predicted_labels = [self.model.config.id2label[idx] for idx in predicted_indices]

        except Exception as e:
            print(f"Error during ViT model inference: {e}")
            # predicted_labels will remain ["ViT inference error"] or similar

        # Dominant Colors (Heuristic using Pillow)
        dominant_colors = self._get_dominant_colors(pil_image, count=3)

        # Metadata Assembly
        description = predicted_labels[0] if predicted_labels else "No ViT description"
        style_tags = predicted_labels # Using top-k ImageNet labels as style tags.
                                      # Limitation: These are general ImageNet labels (e.g., 'tabby cat', 'jersey')
                                      # and not specific fashion styles. A fine-tuned model or different
                                      # approach (e.g., CLIP with fashion text prompts) would be needed for true fashion tags.

        # Placeholders for fashion-specific fields - ViT general model cannot reliably provide these.
        garment_type = "unknown"  # Limitation: ViT base model does not provide garment types.
        accessories = []          # Limitation: ViT base model does not identify accessories.
        gender = "unisex"         # Limitation: ViT base model does not predict gender.

        metadata = {
            "image_id": os.path.basename(image_path),
            "file_path": os.path.abspath(image_path),
            "description": description,
            "dominant_colors": dominant_colors,
            "style_tags": style_tags,
            "garment_type": garment_type,
            "accessories": accessories,
            "gender": gender,
            "season": "summer",  # Fixed as per requirements
        }
        return metadata

if __name__ == '__main__':
    print("Running FashionTagger example...")
    
    # Create a dummy image for testing if ./images doesn't exist or is empty
    dummy_image_dir = "images"
    dummy_image_path = os.path.join(dummy_image_dir, "img_001.jpg")

    if not os.path.exists(dummy_image_path):
        print(f"Test image {dummy_image_path} not found. Creating a dummy image for testing.")
        if not os.path.exists(dummy_image_dir):
            os.makedirs(dummy_image_dir)
        try:
            img = Image.new('RGB', (100, 100), color = (random.randint(0,255), random.randint(0,255), random.randint(0,255)))
            draw = ImageDraw.Draw(img)
            draw.rectangle([(20,20), (80,80)], fill=(random.randint(0,255), random.randint(0,255), random.randint(0,255)))
            img.save(dummy_image_path)
            print(f"Dummy image created at {dummy_image_path}")
            sample_image_path = dummy_image_path
        except ImportError: # PIL.ImageDraw might not be available if Pillow is minimal
            print("Pillow ImageDraw not available to create dummy image. Skipping example unless an image exists.")
            sample_image_path = None # Ensure it's None if not created
        except Exception as e:
            print(f"Could not create dummy image: {e}")
            sample_image_path = None
    else:
        sample_image_path = dummy_image_path
        print(f"Using existing image: {sample_image_path}")

    if sample_image_path:
        tagger = FashionTagger()
        if tagger.model and tagger.processor: # Check if tagger initialized correctly
            print(f"\nExtracting metadata for: {sample_image_path}")
            metadata = tagger.get_metadata(sample_image_path)
            if metadata:
                print("\nExtracted Metadata:")
                for key, value in metadata.items():
                    print(f"  {key}: {value}")
            else:
                print("Metadata extraction failed for the sample image.")
        else:
            print("FashionTagger did not initialize correctly. Cannot run example.")
    else:
        print("No sample image available to run FashionTagger example.")

    # Clean up dummy image if created by this script
    # (For a real test, you might want to keep it or use a dedicated test image)
    # if os.path.exists(dummy_image_path) and "dummy image created" in open(__file__).read(): # Basic check
    #     # This cleanup is a bit too aggressive for a generic test.
    #     # For now, let's not auto-delete it to allow multiple test runs without re-creation.
    #     # print(f"Cleaning up dummy image: {dummy_image_path}")
    #     # os.remove(dummy_image_path)
    #     pass

    print("\nFashionTagger example finished.")
