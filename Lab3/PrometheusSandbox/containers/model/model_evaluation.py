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


def fetch_metrics(prom, metric_name, start_time, end_time):
    """Fetch the data from Prometheus server"""
    metric_data = prom.get_metric_range_data(metric_name, start_time=start_time, end_time=end_time)
    if not metric_data or 'values' not in metric_data[0]:
        logging.error(f"No data found for metric {metric_name}")
        return pd.DataFrame(columns=['ds', 'y'])

    df = pd.DataFrame(metric_data[0]['values'], columns=['ds', 'y'])
    df['ds'] = pd.to_datetime(df['ds'], unit='s')
    logging.info(f"Fetched data for {metric_name}: {df.head()}")
    return df


def evaluate_model(train_data, test_data):
    """Train and evaluate the prophet model"""
    if train_data.dropna().shape[0] < 2:
        raise ValueError("Training data has less than 2 non-NaN rows.")

    model = Prophet(interval_width=0.99, growth='flat', yearly_seasonality=False, weekly_seasonality=False,
                    daily_seasonality=False)
    model.fit(train_data)
    future = model.make_future_dataframe(periods=len(test_data), freq='s')
    forecast = model.predict(future)
    test_data = test_data.rename(columns={'ds': 'timestamp', 'y': 'value'})
    test_data['value'] = pd.to_numeric(test_data['value'], errors='coerce')
    forecast['yhat'] = pd.to_numeric(forecast['yhat'], errors='coerce')
    evaluation = pd.merge(test_data, forecast[['ds', 'yhat']], left_on='timestamp', right_on='ds')
    evaluation['error'] = evaluation['value'] - evaluation['yhat']
    logging.info(f"Evaluation data: {evaluation.head()}")
    return evaluation


def print_anomalies(evaluation):
    """Print anomalies to the console"""
    anomalies = evaluation[evaluation['error'].abs() > 0.1]
    logging.info(f"Total anomalies detected: {len(anomalies)}")
    if not anomalies.empty:
        logging.info("Anomalies detected:")
        logging.info(anomalies)
    return len(anomalies)


def calculate_mae_and_mape(evaluation):
    """Calculate Mean Absolute Error (MAE) and Mean Absolute Percentage Error (MAPE)"""
    evaluation['abs_error'] = evaluation['error'].abs()
    mae = evaluation['abs_error'].mean()
    mape = (evaluation['abs_error'] / evaluation['value']).mean() * 100
    logging.info(f"Mean Absolute Error (MAE): {mae}")
    logging.info(f"Mean Absolute Percentage Error (MAPE): {mape}")
    return mae, mape


def main():
    url = os.getenv('PROMETHEUS_URL', 'http://localhost:9090')
    prom = prometheus_connection(url)

    # Check if the Prometheus client server is already running
    if not any(isinstance(handler, ThreadingWSGIServer) for handler in REGISTRY._collector_to_names.values()):
        start_http_server(8000)

    anomaly_gauge = Gauge('anomaly_count', 'Number of anomalies detected')
    mae_gauge = Gauge('mae', 'Mean Absolute Error')
    mape_gauge = Gauge('mape', 'Mean Absolute Percentage Error')

    while True:
        end_time = datetime.datetime.now()
        start_time = end_time - datetime.timedelta(minutes=5)

        train_data = fetch_metrics(prom, 'train_gauge', start_time, end_time)
        if train_data.dropna().shape[0] < 2:
            logging.error("Insufficient training data. Skipping this iteration.")
            continue
        logging.info("Waiting for 60 seconds before fetching test data...")
        time.sleep(60)

        test_end_time = datetime.datetime.now()
        test_start_time = test_end_time - datetime.timedelta(minutes=1)
        test_data = fetch_metrics(prom, 'test_gauge', test_start_time, test_end_time)
        if test_data.empty:
            logging.error("No test data found. Skipping this iteration.")
            continue

        evaluation = evaluate_model(train_data, test_data)
        anomaly_count = print_anomalies(evaluation)
        anomaly_gauge.set(anomaly_count)
        logging.info(f"Anomaly count set to: {anomaly_count}")

        mae, mape = calculate_mae_and_mape(evaluation)
        mae_gauge.set(mae)
        mape_gauge.set(mape)
        logging.info(f"MAE set to: {mae}")
        logging.info(f"MAPE set to: {mape}")


if __name__ == '__main__':
    main()