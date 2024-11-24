import json
import requests
import pandas as pd
from prophet import Prophet
from prometheus_client import Gauge, start_http_server
import time
from datetime import datetime
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
from tabulate import tabulate

# Load and prepare training data
def load_training_data():
    """Load and prepare training data with proper time alignment"""
    with open("../boutique_training1.json") as f:
        prom = json.load(f)
    
    # Extract values from the training data
    metric_data = prom['data']['result'][0]['values']
    df_train = pd.DataFrame(metric_data, columns=['ds', 'y'])
    df_train['y'] = pd.to_numeric(df_train['y'], errors='coerce')
    df_train.dropna(subset=['y'], inplace=True)
    
    # Reset training data to start from 0 for proper alignment
    df_train['ds'] = df_train['ds'] - df_train['ds'].iloc[0]
    df_train['ds'] = df_train['ds'].apply(lambda sec: datetime.fromtimestamp(sec))
    
    return df_train

# Initialize Prophet model with seasonality settings
def initialize_model(df_train):
    """Initialize and train Prophet model with proper seasonality settings"""
    model = Prophet(interval_width=0.99, 
                   yearly_seasonality=False, 
                   weekly_seasonality=False, 
                   daily_seasonality=False, 
                   growth='flat')
    model.add_seasonality(name='hourly', period=1/24, fourier_order=5)
    model.fit(df_train)
    return model

# Define Prometheus metrics
def setup_prometheus_metrics():
    """Setup all required Prometheus metrics"""
    metrics = {
        'anomaly_count': Gauge('anomaly_count', 'Number of detected anomalies'),
        'mae_score': Gauge('mae_score', 'Mean Absolute Error (MAE)'),
        'mape_score': Gauge('mape_score', 'Mean Absolute Percentage Error (MAPE)'),
        'current_value': Gauge('current_value', 'Current observed value'),
        'predicted_value': Gauge('predicted_value', 'Predicted value by Prophet'),
        'yhat_min': Gauge('yhat_min', 'Lower bound of prediction'),
        'yhat_max': Gauge('yhat_max', 'Upper bound of prediction')
    }
    return metrics

def fetch_current_data():
    """Fetch single current datapoint from Prometheus"""
    query = "histogram_quantile(0.5, sum(rate(istio_request_duration_milliseconds_bucket{source_app='frontend', destination_app='shippingservice', reporter='source'}[1m])) by (le))"
    try:
        response = requests.get('http://34.168.151.60:9090/api/v1/query', params={'query': query})
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
    """Main monitoring function"""
    # Load and prepare training data
    df_train = load_training_data()
    
    # Initialize Prophet model
    model = initialize_model(df_train)
    
    # Setup Prometheus metrics
    metrics = setup_prometheus_metrics()
    
    # Start Prometheus server
    start_http_server(8080)
    
    # Store results for analysis
    results = []
    
    # Record start time for test data alignment
    test_start_time = time.time()
    
    while True:
        # Fetch current data point
        timestamp, value = fetch_current_data()
        if value is None:
            print("Failed to fetch data, retrying in 60 seconds...")
            time.sleep(60)
            continue
            
        # Create aligned test datapoint (starting from 0 like training data)
        current_time = timestamp - test_start_time
        df_test = pd.DataFrame({
            'ds': [datetime.fromtimestamp(current_time)],
            'y': [value]
        })
        
        # Make prediction
        forecast = model.predict(df_test)
        predicted_value = forecast['yhat'].values[0]
        lower_bound = forecast['yhat_lower'].values[0]
        upper_bound = forecast['yhat_upper'].values[0]
        
        # Detect anomaly
        is_anomaly = value < lower_bound or value > upper_bound
        anomaly_count = 1 if is_anomaly else 0
        
        # Calculate metrics
        if not (pd.isna(value) or pd.isna(predicted_value)):
            mae = mean_absolute_error([value], [predicted_value])
            mape = mean_absolute_percentage_error([value], [predicted_value])
        else:
            mae = mape = None
            
        # Update Prometheus metrics
        metrics['anomaly_count'].set(anomaly_count)
        metrics['current_value'].set(value)
        metrics['predicted_value'].set(predicted_value)
        metrics['yhat_min'].set(lower_bound)
        metrics['yhat_max'].set(upper_bound)
        if mae is not None:
            metrics['mae_score'].set(mae)
            metrics['mape_score'].set(mape)
            
        # Store results
        results.append({
            'Timestamp': datetime.now(),
            'Actual': value,
            'Predicted': predicted_value,
            'Lower Bound': lower_bound,
            'Upper Bound': upper_bound,
            'Anomaly': anomaly_count,
            'MAE': mae if mae is not None else 'N/A',
            'MAPE': mape if mape is not None else 'N/A'
        })
        
        # Print results in tabular format
        df_results = pd.DataFrame(results)
        print("\nCurrent Monitoring Results:")
        print(tabulate(df_results.tail(5), headers='keys', tablefmt='grid', showindex=False))
        
        # Wait before next iteration
        time.sleep(60)

if __name__ == "__main__":
    monitor()