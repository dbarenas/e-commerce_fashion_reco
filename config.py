# Configuration for FashionViT model and image processing
HUGGING_FACE_MODEL_NAME = "google/vit-base-patch16-224-in21k" # A common ViT model, can be changed later
# Note: This base model is trained on ImageNet and will give general image features.
# For specific fashion attributes like 'garment_type', 'style_tags', 'accessories',
# a model fine-tuned on a fashion dataset (e.g., FashionMNIST, DeepFashion, or a custom one)
# or a multi-modal model like CLIP would be more effective.
# For this step, we'll use a general ViT and acknowledge that post-processing might be needed
# to map its outputs to the desired fashion-specific fields, or that a more specialized model
# would be a further improvement.

IMAGE_SIZE = (224, 224) # Standard input size for many ViT models

# Placeholder for potential future configurations
# E.g., BATCH_SIZE_ETL = 8
# E.g., MODEL_CONFIDENCE_THRESHOLD = 0.5
