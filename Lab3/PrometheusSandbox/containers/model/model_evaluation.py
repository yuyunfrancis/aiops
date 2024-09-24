import time
import datetime
from prometheus_api_client import PrometheusConnect
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from prophet import Prophet

# Define the Prometheus custom url function
def prometheus_connection(url):
    """Connect to Prometheus server"""
    prom = PrometheusConnect(url, disable_ssl=True)
    return prom

# Fetch the data from Prometheus server
def fetch_metrics(prom, metric_name, start_time, end_time):
    """Fetch the data from Prometheus server"""
    metric_data = prom.get_metric_range_data(metric_name, start_time=start_time, end_time=end_time)

    # Convert the data to a pandas dataframe
    df = pd.DataFrame(metric_data[0]['values'], columns=['ds', 'y']) # Rename columns to 'ds' and 'y'
    df['ds'] = pd.to_datetime(df['ds'], unit='s') # Convert the timestamp to a datetime object

    return df

# Define the function to train and evaluate the model
def evaluate_model(train_data, test_data):
    """Train and evaluate the prophet model"""
    model = Prophet(growth='flat')
    model.fit(train_data)

    future = model.make_future_dataframe(periods=len(test_data), freq='S')
    forecast = model.predict(future)

    # Ensure test_data has the correct column names
    test_data = test_data.rename(columns={'ds': 'timestamp', 'y': 'value'})

    # Convert 'value' and 'yhat' columns to numeric types
    test_data['value'] = pd.to_numeric(test_data['value'], errors='coerce')
    forecast['yhat'] = pd.to_numeric(forecast['yhat'], errors='coerce')

    evaluation = pd.merge(test_data, forecast[['ds', 'yhat']], left_on='timestamp', right_on='ds') # Merge the test data with the forecasted data to evaluate the model performance
    evaluation['error'] = evaluation['value'] - evaluation['yhat'] # Calculate the error

    return evaluation, forecast

# Define the function to print anomalies
def print_anomalies(evaluation):
    """Print anomalies to the console"""
    anomalies = evaluation[evaluation['error'].abs() > 0.1]  # Define your anomaly threshold here
    if not anomalies.empty:
        print("Anomalies detected:")
        print(anomalies)

# Define the function to plot the evaluation results
def plot_evaluation(evaluation, forecast):
    """Plot the evaluation results"""
    plt.figure(figsize=(10, 6))
    plt.plot(evaluation['timestamp'], evaluation['value'], label='Actual')
    plt.plot(forecast['ds'], forecast['yhat'], label='Forecast')
    plt.xlabel('Timestamp')
    plt.ylabel('Value')
    plt.legend()
    plt.show()

# Define the function to plot anomalies
def plot_anomalies(evaluation):
    """Plot anomalies"""
    anomalies = evaluation[evaluation['error'].abs() > 0.1]  # Define your anomaly threshold here
    if not anomalies.empty:
        plt.figure(figsize=(10, 6))
        plt.plot(evaluation['timestamp'], evaluation['value'], label='Actual')
        plt.plot(evaluation['timestamp'], evaluation['yhat'], label='Forecast')
        plt.scatter(anomalies['timestamp'], anomalies['value'], color='red', label='Anomalies')
        plt.xlabel('Timestamp')
        plt.ylabel('Value')
        plt.legend()
        plt.show()

# Define the main function
def main():
    # Define the Prometheus server url
    url = 'http://localhost:9090'

    # Connect to the Prometheus server
    prom = prometheus_connection(url)

    iterations = 10  # Number of iterations to run

    for _ in range(iterations):
        # Define the end time and start time for training data
        end_time = datetime.datetime.now()
        start_time = end_time - datetime.timedelta(minutes=5)

        # Fetch the training data
        train_data = fetch_metrics(prom, 'train_gauge', start_time, end_time)

        # Indicate waiting period
        print("Waiting for 60 seconds before fetching test data...")
        time.sleep(60)

        # Define the end time and start time for test data
        test_end_time = datetime.datetime.now()
        test_start_time = test_end_time - datetime.timedelta(minutes=1)

        # Fetch the test data
        test_data = fetch_metrics(prom, 'test_gauge', test_start_time, test_end_time)

        # Evaluate the model
        evaluation, forecast = evaluate_model(train_data, test_data)

        # Print anomalies
        print_anomalies(evaluation)

        # Plot evaluation results
        plot_evaluation(evaluation, forecast)

        # Plot anomalies
        plot_anomalies(evaluation)

if __name__ == '__main__':
    main()

# def main():
#     # Define the Prometheus server url
#     url = 'http://localhost:9090'
#
#     # Connect to the Prometheus server
#     prom = prometheus_connection(url)
#
#     while True:
#         # Define the end time and start time for training data
#         end_time = datetime.datetime.now()
#         start_time = end_time - datetime.timedelta(minutes=5)
#
#         # Fetch the training data
#         train_data = fetch_metrics(prom, 'train_gauge', start_time, end_time)
#
#         # Indicate waiting period
#         print("Waiting for 60 seconds before fetching test data...")
#         time.sleep(60)
#
#         # Define the end time and start time for test data
#         test_end_time = datetime.datetime.now()
#         test_start_time = test_end_time - datetime.timedelta(minutes=1)
#
#         # Fetch the test data
#         test_data = fetch_metrics(prom, 'test_gauge', test_start_time, test_end_time)
#
#         # Evaluate the model
#         evaluation, forecast = evaluate_model(train_data, test_data)
#
#         # Print anomalies
#         print_anomalies(evaluation)
#
#         # Plot evaluation results
#         plot_evaluation(evaluation, forecast)
#
#         # Plot anomalies
#         plot_anomalies(evaluation)
#
# if __name__ == '__main__':
#     main()