import json
import requests
import pandas as pd
from prophet import Prophet
from prometheus_client import Gauge, start_http_server
import time
from datetime import datetime
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
from tabulate import tabulate

def load_training_data():
    """Load and prepare training data with proper time alignment"""
    with open("./boutique_training.json") as f:
        prom = json.load(f)
        
    metric_data = prom['data']['result'][0]['values']
    df_train = pd.DataFrame(metric_data, columns=['ds', 'y'])
    df_train['y'] = pd.to_numeric(df_train['y'], errors='coerce')
    df_train.dropna(subset=['y'], inplace=True)
    
    df_train['ds'] = df_train['ds'] - df_train['ds'].iloc[0]
    df_train['ds'] = df_train['ds'].apply(lambda sec: datetime.fromtimestamp(sec))
    
    return df_train

def initialize_model(df_train):
    """Initialize and train Prophet model with hourly seasonality"""
    model = Prophet(
        interval_width=0.99,
        yearly_seasonality=False,
        weekly_seasonality=False,
        daily_seasonality=False,
        growth='flat'    )
    model.add_seasonality(name='hourly', period=1/24, fourier_order=5)
    model.fit(df_train)
    return model

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
        response = requests.get('http://34.168.42.170:9090/api/v1/query', params={'query': query})
        # response = requests.get('http://prometheus.istio-system:9090/api/v1/query', params={'query': query})
        response.raise_for_status()
        data = response.json()['data']['result']
        if not data:
            print("No data returned from Prometheus.", flush=True)
            return None, None
        timestamp, value = data[0]['value']
        return float(timestamp), float(value)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}", flush=True)
        return None, None

def print_phase_header(phase_name):
    """Print a clearly visible phase header"""
    border = "=" * 80
    print(f"\n{border}", flush=True)
    print(f"PHASE: {phase_name}", flush=True)
    print(f"Timestamp: {datetime.now()}", flush=True)
    print(f"{border}\n", flush=True)

def print_results(df_results, window=5):
    """Print results in a formatted table"""
    headers = ['Timestamp', 'Actual', 'Predicted', 'Lower Bound', 'Upper Bound', 'Anomaly', 'MAE', 'MAPE']
    print("\nMonitoring Results:", flush=True)
    print(tabulate(df_results.tail(window)[headers], headers=headers, 
                  tablefmt='grid', floatfmt='.3f', showindex=False), flush=True)
    
    # Print summary statistics
    anomaly_count = df_results.tail(window)['Anomaly'].sum()
    avg_mae = df_results.tail(window)['MAE'].mean()
    avg_mape = df_results.tail(window)['MAPE'].mean()

    print("\nWindow Summary:", flush=True)
    print(f"Total Anomalies: {anomaly_count}", flush=True)
    print(f"Average MAE: {avg_mae:.3f}", flush=True)
    print(f"Average MAPE: {avg_mape:.3f}\n", flush=True)

def monitor():
    """Main monitoring function"""
    print_phase_header("STARTUP - Loading Model")
    df_train = load_training_data()
    model = initialize_model(df_train)
    metrics = setup_prometheus_metrics()
    
    # Start Prometheus server
    start_http_server(8080)
    results = []
    test_start_time = time.time()
    
    print_phase_header("NORMAL OPERATION - No Delay Injection")
    print("Monitor started - waiting for initial data points...", flush=True)
    
    iteration = 0
    current_phase = "normal"
    while True:
        timestamp, value = fetch_current_data()
        if value is None:
            print("Failed to fetch data, retrying in 60 seconds...", flush=True)
            time.sleep(60)
            continue
            
        # Phase transition logic based on iteration count
        if iteration == 10 and current_phase == "normal":
            print_phase_header("DELAY INJECTION PHASE - Istio Delay Active")
            current_phase = "delay"
        elif iteration == 20 and current_phase == "delay":
            print_phase_header("RECOVERY PHASE - Delay Removed")
            current_phase = "recovery"
            
        # Create aligned test datapoint
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
            mae = mape = float('nan')
            
        # Update Prometheus metrics
        metrics['anomaly_count'].set(anomaly_count)
        metrics['current_value'].set(value)
        metrics['predicted_value'].set(predicted_value)
        metrics['yhat_min'].set(lower_bound)
        metrics['yhat_max'].set(upper_bound)
        if not pd.isna(mae):
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
            'MAE': mae,
            'MAPE': mape
        })
        
        # Print results with phase-specific summary
        df_results = pd.DataFrame(results)
        print_results(df_results)
        
        iteration += 1
        time.sleep(60)

if __name__ == "__main__":
    monitor()