
import os
import torch
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, roc_curve, auc, classification_report
from datasets import load_dataset
from transformers import ViTForImageClassification, ViTImageProcessor

# Configuration
DATASET_PATH = "C:/Users/ASUS/Downloads/archive (2)/Dataset/Train"
MODEL_PATH = "./src/image-analysis-service/fine_tuned_model"  # Adjust relative path if needed
OUTPUT_DIR = "./src/image-analysis-service"

def evaluate():
    print(f"Loading dataset from {DATASET_PATH}...")
    dataset = load_dataset("imagefolder", data_dir=DATASET_PATH)
    
    # Create test split locally as done in training
    if "test" not in dataset:
        dataset = dataset["train"].train_test_split(test_size=0.1, seed=42)
    
    # Use a subset for faster evaluation (e.g., 1000 samples) to generate graph quickly
    # Remove this slicing if you want full evaluation (might take hours on CPU)
    eval_dataset = dataset["test"].shuffle(seed=42).select(range(min(1000, len(dataset["test"]))))
    
    print(f"Evaluating on {len(eval_dataset)} samples...")

    print(f"Loading model from {MODEL_PATH}...")
    try:
        model = ViTForImageClassification.from_pretrained(MODEL_PATH)
        processor = ViTImageProcessor.from_pretrained(MODEL_PATH)
    except Exception as e:
        print(f"Error loading model: {e}")
        # Fallback for path issues
        model = ViTForImageClassification.from_pretrained("c:/Users/ASUS/Desktop/project/pro/v1/src/image-analysis-service/fine_tuned_model")
        processor = ViTImageProcessor.from_pretrained("c:/Users/ASUS/Desktop/project/pro/v1/src/image-analysis-service/fine_tuned_model")

    id2label = model.config.id2label
    
    # Prediction loop
    true_labels = []
    pred_labels = []
    pred_probs = []

    model.eval()
    
    print("Running inference...")
    with torch.no_grad():
        for i, item in enumerate(eval_dataset):
            image = item["image"].convert("RGB")
            label = item["label"]
            
            inputs = processor(images=image, return_tensors="pt")
            outputs = model(**inputs)
            logits = outputs.logits
            probs = torch.nn.functional.softmax(logits, dim=-1)
            
            predicted_class_id = logits.argmax(-1).item()
            probability = probs[0][1].item() # Probability of class 1 (Real usually, or check id2label)

            true_labels.append(label)
            pred_labels.append(predicted_class_id)
            pred_probs.append(probability)
            
            if (i + 1) % 100 == 0:
                print(f"Processed {i + 1} images...")

    # Metrics
    print("\nClassification Report:")
    print(classification_report(true_labels, pred_labels, target_names=[id2label[0], id2label[1]]))

    # 1. Confusion Matrix
    cm = confusion_matrix(true_labels, pred_labels)
    plt.figure(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=[id2label[0], id2label[1]], yticklabels=[id2label[0], id2label[1]])
    plt.xlabel('Predicted')
    plt.ylabel('Actual')
    plt.title('Confusion Matrix')
    cm_path = os.path.join(OUTPUT_DIR, "confusion_matrix.png")
    plt.savefig(cm_path)
    print(f"Confusion Matrix saved to {cm_path}")
    plt.close()

    # 2. ROC Curve
    # Assuming binary classification: 0 = Fake, 1 = Real (or vice versa, strictly checking id2label is better, but binary logic applies)
    # We used probs of class 1
    fpr, tpr, thresholds = roc_curve(true_labels, pred_probs)
    roc_auc = auc(fpr, tpr)

    plt.figure(figsize=(8, 6))
    plt.plot(fpr, tpr, color='darkorange', lw=2, label=f'ROC curve (area = {roc_auc:.2f})')
    plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--')
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.title('Receiver Operating Characteristic (ROC)')
    plt.legend(loc="lower right")
    roc_path = os.path.join(OUTPUT_DIR, "roc_curve.png")
    plt.savefig(roc_path)
    print(f"ROC Curve saved to {roc_path}")
    plt.close()

if __name__ == "__main__":
    evaluate()
