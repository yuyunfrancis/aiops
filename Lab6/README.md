# LAB 6: Anomaly Detection in GKE with Prophet and Istio

# Task 1

## Overview

In this task, worked on setting up anomaly detection using Prophet and Istio in a Google Kubernetes Engine (GKE) environment. The goal was to detect abnormal behavior in our microservices by monitoring request duration metrics from Istio, generating training data, and applying the Prophet model for seasonality and anomaly detection.

## Steps Taken

### 1. Set Up Load Generator

We used **Locust** as a load generator to simulate traffic between microservices. The following environment variables were set to control the load generation:

```bash
export TIMELIMIT=3600  # 1 hour run
export CYCLETIME=1200  # 20 minutes per cycle
export MAXUSERS=250    # Maximum 250 users
export NUMSTEPS=10     # Number of steps per cycle
export SPAWNRATE=10    # Users spawned per second
```

The command to run Locust locally:

```bash
locust --host="http://<Boutique IP>" -f locustfile_step.py
```

### 2. Monitor Request Duration with Prometheus

Queried Prometheus for the `istio_request_duration_milliseconds_bucket` metric to monitor the request duration between source and destination microservices.

Example curl command to fetch the metric and save the result in a json file:

```bash
curl -g -s "http://<PROMETHEUS_IP>:9090/api/v1/query_range" \
    --data-urlencode "query=sum(rate(istio_request_duration_milliseconds_bucket{source_workload='frontend', destination_workload='shippingservice', reporter='source'}[1m])) by (le)" \
    --data-urlencode "start=$(date -u --date='10 minutes ago' +%FT%TZ)" \
    --data-urlencode "end=$(date -u +%FT%TZ)" \
    --data-urlencode "step=30s" | jq '.' > boutique_training.json
```

### 3. Export Training Data

The data collected from Prometheus was saved to a local file and uploaded to github and was fetched from there(`boutique_training.json`) for use in training the anomaly detection model.

### 4. Train the Prophet Model

I used the `prom.ipynb` notebook to plug in the training data and train a Prophet model. The model was used to detect anomalies and seasonality. During this step, observed that there were a few outliers, which are expected in normal operation.

### 5. Model Evaluation

The following evaluation metrics were used:

- **MAE (Mean Absolute Error)**: 3.98 (indicating the average prediction error in units)
- **MAPE (Mean Absolute Percentage Error)**: 5.85% (indicating the average error as a percentage of actual values)

## Final Remarks Task 1

The model performed reasonably well with an MAE of 3.98 and a MAPE of 5.85%, indicating decent accuracy for anomaly detection. A few outliers were detected, which is expected in a normal traffic pattern. Further tuning of the model or data collection might help reduce errors and improve anomaly detection.
