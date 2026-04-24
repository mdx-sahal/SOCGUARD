# Deepfake Detection Dataset

To train your custom model, please organize your images in this directory structure:

## Directory Structure

```
dataset/
├── train/
│   ├── REAL/      <-- Place authentic, real images here
│   └── FAKE/      <-- Place AI-generated, deepfake images here
```

## Instructions

1.  **Add Images**: 
    - Copy your **Real** images into the `train/REAL` folder.
    - Copy your **Fake** images into the `train/FAKE` folder.
    - Aim for a balanced number of images (e.g., 50 Real and 50 Fake) for initial testing.
    - Supported formats: JPG, PNG, JPEG.

2.  **Run Training**:
    - Open a terminal in the project root.
    - Run the command:
      ```bash
      python src/image-analysis-service/train_model.py
      ```

3.  **Automatic Use**:
    - The system will automatically detect the trained model in `src/image-analysis-service/fine_tuned_model` and use it for future predictions.
