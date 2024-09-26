# Prometheus SandBox - Anomaly Lab 3

## Summary Answers

### Reasonable Baseline of Data

To use a Prophet model in production, you'd want at least a few weeks to a few months of past data. This depends on how often you collect data and if there are seasonal patterns. Using this much data for training can be challenging. It might need more computer power and time, and you'll need good ways to store and access all that data.

### Continuous Retraining in Production

Letting a Prophet model retrain itself all the time in production can help it adjust to new patterns. But be careful - it's risky to let it run completely on its own. Someone should probably check and approve changes. If you let it run automatically, it might:

- Fit too closely to recent data (overfitting)
- Slowly change in ways you don't want (model drift)
- Learn from weird or wrong data, leading to bad predictions

## Description

This is a Docker setup for trying out Prometheus and Grafana with Facebook Prophet for 3forecasting and predictions

## How to get started

### Prerequisites

- Make sure you have Anaconda installed on your computer.

### Running the project

1. Create a new environment:

   ```
   conda create --name myenv python=3.8
   ```

2. Activate the environment:

   ```
   conda activate myenv
   ```

3. Install pip:
   ```
   conda install pip
   ```

### Build and Run Docker Containers:

Run this command to start everything up:

```
docker compose up --build
```

## Additional Information

- You can find screenshots for all activities in the `screenshots` folder.
- Check the `documentation` folder for more detailed information.
