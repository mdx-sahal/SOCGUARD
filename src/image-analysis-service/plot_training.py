
import json
import matplotlib.pyplot as plt
import os

# Path to the trainer_state.json
# Using the path found in the previous step
log_file = "src/image-analysis-service/fine_tuned_model/checkpoint-7876/trainer_state.json"
output_image = "src/image-analysis-service/training_loss_graph.png"

if not os.path.exists(log_file):
    print(f"Error: {log_file} not found.")
    exit(1)

with open(log_file, "r") as f:
    data = json.load(f)

log_history = data.get("log_history", [])

steps = []
losses = []

for entry in log_history:
    if "loss" in entry:
        steps.append(entry["step"])
        losses.append(entry["loss"])

if not steps:
    print("No training loss data found in log history.")
    exit(1)

plt.figure(figsize=(10, 6))
plt.plot(steps, losses, label="Training Loss", marker='o')
plt.xlabel("Step")
plt.ylabel("Loss")
plt.title("Training Loss Curve")
plt.legend()
plt.grid(True)
plt.savefig(output_image)
print(f"Graph saved to {output_image}")
