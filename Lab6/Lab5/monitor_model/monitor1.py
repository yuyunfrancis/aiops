import json
import requests
import pandas as pd
from prophet import Prophet
from prometheus_client import Gauge, start_http_server
import time
from datetime import datetime
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
from tabulate import tabulate

# Load training data from boutique_training.json
with open("../boutique_training.json") as f:
    prom = json.load(f)

# Extract values based on the known structure
# Adjust the index in result[0] if you're interested in another metric
metric_data = prom['data']['result'][0]['values']

# Convert to DataFrame
df_train = pd.DataFrame(metric_data, columns=['ds', 'y'])

# Convert 'ds' column from timestamp to datetime and 'y' column to numeric
# df_train['ds'] = pd.to_datetime(df_train['ds'], unit='s')
df_train['y'] = pd.to_numeric(df_train['y'], errors='coerce')  # Convert 'y' to numeric, setting invalid parsing as NaN
df_train.dropna(subset=['y'], inplace=True)  # Drop any rows with NaN values in 'y'

# Verify the DataFrame structure
print(df_train.dtypes)
print(df_train.head())

# reset training data to 0 origin before HMS conversion 
df_train['ds'] = df_train['ds'] - df_train['ds'].iloc[0]     
 
# then do the HMS conversion as usual 
# df_train['ds'] = df_train['ds'].apply(lambda sec: datetime.fromtimestamp(sec))
df_train['ds'] = df_train['ds'].apply(lambda sec: datetime.fromtimestamp(sec))

# Train the Prophet model on the training data
model = Prophet()
model.fit(df_train)


# Define Prometheus metrics to expose
anomaly_gauge = Gauge('anomaly_count', 'Number of detected anomalies')
mae_gauge = Gauge('mae_score', 'Mean Absolute Error (MAE)')
mape_gauge = Gauge('mape_score', 'Mean Absolute Percentage Error (MAPE)')
y_gauge = Gauge('current_value', 'Current value of the metric')
yhat_gauge = Gauge('predicted_value', 'Predicted value by Prophet')

# Start the Prometheus server to expose metrics on port 8000
start_http_server(8080)

results = []

def fetch_current_data():
    """Fetch current metric data from Prometheus."""
    query = "histogram_quantile(0.5, sum(rate(istio_request_duration_milliseconds_bucket{source_app='frontend', destination_app='shippingservice', reporter='source'}[1m])) by (le))"
    try:
        response = requests.get('http://34.127.18.133:9090/api/v1/query', params={'query': query})
        response.raise_for_status()
        data = response.json()['data']['result']
        if not data:
            print("No data returned from Prometheus.")
            return None, None
        timestamp, value = data[0]['value']
        return float(timestamp), float(value)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None, None



def monitor():
    """Continuously fetch data, make predictions, and update Prometheus metrics."""
    
    # global anomaly_counter

    # Fetch the current data point
    test_start_time = time.time()
    while True:
        # Fetch the current data point
        timestamp, value = fetch_current_data()
        if value is None:
            print("Data fetch failed. Pick a god and pray")
            time.sleep(60)  # Wait and try again if data fetch failed
            continue

        # Create test datapoint
        current_time = time.time() - test_start_time
        df_test = pd.DataFrame({'ds': [datetime.fromtimestamp(current_time)], 
                               'y': [value]})
        
        # Make a prediction using the Prophet model
        forecast = model.predict(df_test)
        predicted_value = forecast['yhat'].values[0]
        print(f"Actual value: {value}")
        print(f"Predicted value: {predicted_value}")
        
        # Calculate residual (error) between actual and predicted
        residual = abs(value - predicted_value)
        
        # Determine if this is an anomaly
        threshold = df_train['y'].std() * 2  # 3 standard deviations as an example threshold
        is_anomaly = residual > threshold

        # Count anomalies in current iteration
        anomaly_count = 1 if is_anomaly else 0


        # if is_anomaly:
        #     anomaly_counter += 1
        #     print(f"Anomaly detected at {datetime.now()}. Residual: {residual}, Threshold: {threshold}")

        # anomaly_counter = sum([1 for row in results if row['Anomalies'] > 0])

        # Update Prometheus metrics
        anomaly_gauge.set(anomaly_count)
        y_gauge.set(value)
        yhat_gauge.set(predicted_value)

        # Only calculate MAE and MAPE if values are valid
        if not(pd.isna(value) or pd.isna(predicted_value)):
            # Calculate MAE and MAPE
            mae = mean_absolute_error([value], [predicted_value])
            mape = mean_absolute_percentage_error([value], [predicted_value])
            mae_gauge.set(mae)
            mape_gauge.set(mape)
        else:
            mae = None
            mape = None

        # Add the new row to the results list
        results.append({
            'Timestamp': datetime.now(),
            'Anomalies': anomaly_count,
            'MAE': mae if mae is not None else 'N/A',
            'MAPE': mape if mape is not None else 'N/A'
        })
        # print(results)
        # Print the results in tabular form
        df_results = pd.DataFrame(results)
        print(tabulate(df_results, headers='keys', tablefmt='grid', showindex=False))


        # Print the results to console
        # print(f"{pd.Timestamp.now()} - Actual: {actual_value}, Predicted: {predicted_value}, Anomaly: {is_anomaly}, Residual: {residual}, MAE: {mae}, MAPE: {mape}")

        # Wait before the next iteration
        time.sleep(60)  # Check every minute


if __name__ == "__main__":
    monitor()