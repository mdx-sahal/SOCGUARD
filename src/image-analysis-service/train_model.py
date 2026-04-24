
import os
import torch
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, roc_curve, auc, classification_report, accuracy_score, precision_recall_fscore_support
from datasets import load_dataset, Image
from transformers import ViTForImageClassification, ViTImageProcessor, TrainingArguments, Trainer
from torchvision.transforms import (
    CenterCrop,
    Compose,
    Normalize,
    RandomHorizontalFlip,
    RandomResizedCrop,
    Resize,
    ToTensor,
)

# Configuration
DATASET_PATH = "C:/Users/ASUS/Downloads/archive (2)/Dataset" 
MODEL_NAME = "google/vit-base-patch16-224-in21k"
OUTPUT_DIR = "./fine_tuned_model"
BATCH_SIZE = 16
EPOCHS = 3
LEARNING_RATE = 2e-5

def compute_metrics(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    precision, recall, f1, _ = precision_recall_fscore_support(labels, predictions, average='binary')
    acc = accuracy_score(labels, predictions)
    return {
        'accuracy': acc,
        'f1': f1,
        'precision': precision,
        'recall': recall
    }

def train():
    # Check for CUDA
    if not torch.cuda.is_available():
        print("WARNING: CUDA (GPU) is NOT available. Training will be extremely SLOW on CPU.") 
        print("To ensure GPU usage, please verify your PyTorch installation with CUDA support.")
        # Uncomment to strictly enforce GPU usage as requested
        # raise RuntimeError("GPU not found! Please install PyTorch with CUDA support to proceed.")
    else:
        print(f"CUDA is available! Training on {torch.cuda.get_device_name(0)}")

    print(f"Loading dataset from {DATASET_PATH}...")
    
    # Check if dataset exists
    if not os.path.exists(DATASET_PATH):
        print(f"Error: Dataset not found at {DATASET_PATH}. Please ensure the path is correct.")
        return

    # Load dataset using ImageFolder structure
    # This automatically detects train/test/validation splits if present in the folder
    dataset = load_dataset("imagefolder", data_dir=DATASET_PATH)
    
    print(f"Dataset structure: {dataset}")

    # Ensure splits exist or create them
    if "train" not in dataset:
        print("Error: No training split found.")
        return
        
    # If no validation set, split train
    if "validation" not in dataset:
        if "test" in dataset:
            print("Using 'test' split as validation.")
            # Rename test to validation for consistency or just use it
            dataset["validation"] = dataset["test"]
        else:
            print("Splitting training set to create validation set.")
            split_dataset = dataset["train"].train_test_split(test_size=0.1)
            dataset["train"] = split_dataset["train"]
            dataset["validation"] = split_dataset["test"]
    
    # Load Processor
    processor = ViTImageProcessor.from_pretrained(MODEL_NAME)

    # Transforms
    normalize = Normalize(mean=processor.image_mean, std=processor.image_std)
    
    _train_transforms = Compose(
        [
            RandomResizedCrop(processor.size["height"]),
            RandomHorizontalFlip(),
            ToTensor(),
            normalize,
        ]
    )

    _val_transforms = Compose(
        [
            Resize(processor.size["height"]),
            CenterCrop(processor.size["height"]),
            ToTensor(),
            normalize,
        ]
    )

    def train_transforms(examples):
        examples["pixel_values"] = [_train_transforms(image.convert("RGB")) for image in examples["image"]]
        return examples

    def val_transforms(examples):
        examples["pixel_values"] = [_val_transforms(image.convert("RGB")) for image in examples["image"]]
        return examples

    # Apply transforms
    print("Applying transforms...")
    dataset["train"].set_transform(train_transforms)
    dataset["validation"].set_transform(val_transforms)

    # Labels
    labels = dataset["train"].features["label"].names
    id2label = {str(i): label for i, label in enumerate(labels)}
    label2id = {label: str(i) for i, label in enumerate(labels)}
    print(f"Labels: {id2label}")

    # Load Model
    print(f"Loading base model: {MODEL_NAME}...")
    model = ViTForImageClassification.from_pretrained(
        MODEL_NAME,
        num_labels=len(labels),
        id2label=id2label,
        label2id=label2id,
    )

    # Training Arguments
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        eval_strategy="epoch",  # Changed from evaluation_strategy
        save_strategy="epoch",
        num_train_epochs=EPOCHS,
        learning_rate=LEARNING_RATE,
        save_total_limit=2,
        remove_unused_columns=False,
        push_to_hub=False,
        report_to="none",
        load_best_model_at_end=True,
        metric_for_best_model="accuracy",
    )

    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["validation"],
        processing_class=processor, # Changed from tokenizer
        data_collator=collate_fn,
        compute_metrics=compute_metrics,
    )

    print("Starting training...")
    train_result = trainer.train()
    
    print(f"Training complete. Saving model to {OUTPUT_DIR}...")
    trainer.save_model(OUTPUT_DIR)
    processor.save_pretrained(OUTPUT_DIR)
    
    # Save training metrics
    trainer.save_state()
    
    # Evaluate model
    print("Evaluating model...")
    metrics = trainer.evaluate()
    print(f"Evaluation metrics: {metrics}")

    # Plot graphs
    plot_results(trainer, dataset["validation"], model, processor, id2label)
    
    print("All tasks completed successfully.")

def collate_fn(examples):
    pixel_values = torch.stack([example["pixel_values"] for example in examples])
    labels = torch.tensor([example["label"] for example in examples])
    return {"pixel_values": pixel_values, "labels": labels}

def plot_results(trainer, eval_dataset, model, processor, id2label):
    print("Generating performance plots...")
    
    # 1. Training Loss Curve
    log_history = trainer.state.log_history
    steps = []
    losses = []
    
    for entry in log_history:
        if "loss" in entry:
            steps.append(entry["step"])
            losses.append(entry["loss"])
            
    if steps:
        plt.figure(figsize=(10, 6))
        plt.plot(steps, losses, label="Training Loss")
        plt.xlabel("Step")
        plt.ylabel("Loss")
        plt.title("Training Loss Curve")
        plt.legend()
        plt.savefig(os.path.join(OUTPUT_DIR, "training_loss.png"))
        plt.close()
        print("Training loss graph saved.")
    
    # 2. Confusion Matrix & ROC
    # We need predictions on the validation set
    print("Running inference on validation set for Confusion Matrix & ROC...")
    
    # Use a subset if validation is too large, e.g. 1000 samples, to save time
    # But evaluating on full set is better for accuracy.
    # Let's use the Trainer's predict method which is optimized
    predictions_output = trainer.predict(eval_dataset)
    logits = predictions_output.predictions
    labels = predictions_output.label_ids
    
    pred_labels = np.argmax(logits, axis=-1)
    
    # Confusion Matrix
    cm = confusion_matrix(labels, pred_labels)
    plt.figure(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
                xticklabels=[id2label[str(i)] for i in range(len(id2label))],
                yticklabels=[id2label[str(i)] for i in range(len(id2label))])
    plt.xlabel('Predicted')
    plt.ylabel('Actual')
    plt.title('Confusion Matrix')
    plt.savefig(os.path.join(OUTPUT_DIR, "confusion_matrix.png"))
    plt.close()
    print("Confusion Matrix saved.")
    
    # ROC Curve (Binary Classification)
    if len(id2label) == 2:
        probs = torch.nn.functional.softmax(torch.tensor(logits), dim=-1).numpy()
        # Assuming class 1 is the positive class (e.g. Real)
        # Check mapping to be sure. Usually 0 and 1.
        
        fpr, tpr, thresholds = roc_curve(labels, probs[:, 1])
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
        plt.savefig(os.path.join(OUTPUT_DIR, "roc_curve.png"))
        plt.close()
        print("ROC Curve saved.")

if __name__ == "__main__":
    train()
