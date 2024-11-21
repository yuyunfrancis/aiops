import os
import time
import datetime
import logging
from prometheus_api_client import PrometheusConnect
import pandas as pd
from prophet import Prophet
from prometheus_client import Gauge, start_http_server, REGISTRY
from prometheus_client.exposition import ThreadingWSGIServer

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def prometheus_connection(url):
    """Connect to Prometheus server"""
    return PrometheusConnect(url, disable_ssl=True)

def fetch_training_data(prom, metric_name):
    """Fetch training data from Prometheus"""
    end_time = datetime.datetime.now()
    start_time = end_time - datetime.timedelta(hours=1)  # Get 1 hour of training data
    metric_data = prom.get_metric_range_data(metric_name, start_time=start_time, end_time=end_time)
    
    if not metric_data or 'values' not in metric_data[0]:
        logging.error(f"No training data found for metric {metric_name}")
        return pd.DataFrame(columns=['ds', 'y'])

    df = pd.DataFrame(metric_data[0]['values'], columns=['ds', 'y'])
    df['y'] = pd.to_numeric(df['y'])
    
    # Reset training data to 0 origin
    df['ds'] = pd.to_numeric(df['ds'])
    df['ds'] = df['ds'] - df['ds'].iloc[0]
    df['ds'] = df['ds'].apply(lambda sec: datetime.datetime.fromtimestamp(sec))
    
    return df

def fetch_current_value(prom, metric_name, test_start_time):
    """Fetch single current value from Prometheus"""
    current_time = datetime.datetime.now()
    metric_data = prom.custom_query(metric_name)
    
    if not metric_data:
        logging.error(f"No current value found for metric {metric_name}")
        return pd.DataFrame(columns=['ds', 'y'])

    # Create single-row dataframe
    df = pd.DataFrame([{
        'ds': float(current_time.timestamp()) - test_start_time,
        'y': float(metric_data[0]['value'][1])
    }])
    
    # Convert timestamp to datetime
    df['ds'] = df['ds'].apply(lambda sec: datetime.datetime.fromtimestamp(sec))
    
    return df

def train_prophet_model(df_train):
    """Train the Prophet model with appropriate seasonality settings"""
    model = Prophet(
        interval_width=0.99,
        growth='flat',
        yearly_seasonality=False,
        weekly_seasonality=False,
        daily_seasonality=False
    )
    model.add_seasonality(name='hourly', period=1/24, fourier_order=5)
    model.fit(df_train)
    return model

def evaluate_datapoint(model, test_data):
    """Evaluate a single datapoint for anomalies"""
    forecast = model.predict(test_data)
    evaluation = pd.merge(
        test_data.rename(columns={'ds': 'timestamp', 'y': 'value'}),
        forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']], 
        left_on='timestamp', 
        right_on='ds'
    )
    evaluation['anomaly'] = evaluation.apply(
        lambda row: 1 if (float(row.value) < row.yhat_lower or float(row.value) > row.yhat_upper) 
        else 0, axis=1
    )
    return evaluation

def main():
    url = os.getenv('PROMETHEUS_URL', 'http://localhost:9090')
    prom = prometheus_connection(url)

    # Initialize Prometheus metrics
    if not any(isinstance(handler, ThreadingWSGIServer) for handler in REGISTRY._collector_to_names.values()):
        start_http_server(8000)

    anomaly_gauge = Gauge('anomaly_detection', 'Anomaly detection status (0 or 1)')
    mae_gauge = Gauge('mae_score', 'Mean Absolute Error')
    mape_gauge = Gauge('mape_score', 'Mean Absolute Percentage Error')
    ymin_gauge = Gauge('y_min', 'Minimum predicted value')
    y_gauge = Gauge('y_actual', 'Actual observed value')
    ymax_gauge = Gauge('y_max', 'Maximum predicted value')

    # Store running metrics
    anomaly_counts = []
    test_start_time = datetime.datetime.now().timestamp()

    while True:
        try:
            # Get training data and train model
            train_data = fetch_training_data(prom, 'response_time_seconds')
            if train_data.empty:
                logging.error("No training data available")
                time.sleep(60)
                continue

            model = train_prophet_model(train_data)

            # Get current value and evaluate
            current_data = fetch_current_value(prom, 'response_time_seconds', test_start_time)
            if current_data.empty:
                logging.error("No current data available")
                time.sleep(60)
                continue

            evaluation = evaluate_datapoint(model, current_data)

            # Update metrics
            anomaly_detected = evaluation['anomaly'].iloc[0]
            anomaly_counts.append(anomaly_detected)
            
            # Set Prometheus gauges
            anomaly_gauge.set(anomaly_detected)
            y_gauge.set(float(evaluation['value'].iloc[0]))
            ymin_gauge.set(float(evaluation['yhat_lower'].iloc[0]))
            ymax_gauge.set(float(evaluation['yhat_upper'].iloc[0]))

            # Calculate and set error metrics
            if len(anomaly_counts) > 0:
                mae = abs(float(evaluation['value'].iloc[0]) - float(evaluation['yhat'].iloc[0]))
                mape = (mae / float(evaluation['value'].iloc[0])) * 100
                mae_gauge.set(mae)
                mape_gauge.set(mape)

                logging.info(f"""
                Metrics Update:
                Anomaly: {anomaly_detected}
                Total Anomalies: {sum(anomaly_counts)}
                MAE: {mae:.4f}
                MAPE: {mape:.4f}%
                Current Value: {float(evaluation['value'].iloc[0]):.4f}
                Predicted Range: [{float(evaluation['yhat_lower'].iloc[0]):.4f}, {float(evaluation['yhat_upper'].iloc[0]):.4f}]
                """)

            time.sleep(60)  # Wait for 1 minute before next evaluation

        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            time.sleep(60)

if __name__ == '__main__':
    main()