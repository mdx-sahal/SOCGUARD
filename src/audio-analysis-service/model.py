import torch
import torch.nn as nn
import torch.nn.functional as F

class AudioCNN(nn.Module):
    def __init__(self, n_mfcc=13, n_classes=2):
        super(AudioCNN, self).__init__()
        # Input shape: [batch, 1, n_mfcc, time]
        self.conv1 = nn.Conv2d(1, 16, kernel_size=3, padding=1)
        self.pool = nn.MaxPool2d(2, 2)
        self.conv2 = nn.Conv2d(16, 32, kernel_size=3, padding=1)
        
        # Adaptive pooling to handle variable length audio
        self.adaptive_pool = nn.AdaptiveAvgPool2d((4, 4))
        
        self.fc1 = nn.Linear(32 * 4 * 4, 64)
        self.fc2 = nn.Linear(64, n_classes)

    def forward(self, x):
        # x: [batch, 1, n_mfcc, time]
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        
        x = self.adaptive_pool(x)
        x = x.view(-1, 32 * 4 * 4)
        
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        return x
