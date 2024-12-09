import json
import argparse
import requests
import pandas as pd
import time
from datetime import datetime
from prophet import Prophet
from prometheus_client import Gauge, start_http_server
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
from tabulate import tabulate

# def parse_arguments():
#     """Parse command-line arguments for monitor configuration"""
#     parser = argparse.ArgumentParser(description='Boutique Service Monitor')
#     parser.add_argument('source_service', help='Source service name')
#     parser.add_argument('destination_service', help='Destination service name')
#     parser.add_argument('training_file', help='Path to training data JSON file')
#     parser.add_argument('--port', type=int, default=8080, help='Prometheus scrape port')
#     parser.add_argument('--prometheus-url', 
#                         default='http://prometheus.istio-system:9090', 
#                         help='Prometheus server URL')
#     return parser.parse_args()

def parse_arguments():
    """Parse command-line arguments for monitor configuration"""
    parser = argparse.ArgumentParser(description='Boutique Service Monitor')
    parser.add_argument('source_service', help='Source service name')
    parser.add_argument('destination_service', help='Destination service name')
    parser.add_argument('training_file', help='Path to training data JSON file')
    parser.add_argument('--port', type=int, default=8080, help='Prometheus scrape port')
    parser.add_argument('--prometheus-url', 
                        default='http://prometheus.istio-system:9090', 
                        help='Prometheus server URL')
    
    # Add debug print to verify arguments
    args = parser.parse_args()
    print(f"Debug: Parsed Arguments:", flush=True)
    print(f"Source Service: {args.source_service}", flush=True)
    print(f"Destination Service: {args.destination_service}", flush=True)
    print(f"Training File: {args.training_file}", flush=True)
    print(f"Port: {args.port}", flush=True)
    print(f"Prometheus URL: {args.prometheus_url}", flush=True)
    
    return args

def load_training_data(training_file):
    """Load and prepare training data with proper time alignment"""
    try:
        with open(training_file) as f:
            prom = json.load(f)
        
        metric_data = prom['data']['result'][0]['values']
        df_train = pd.DataFrame(metric_data, columns=['ds', 'y'])
        df_train['y'] = pd.to_numeric(df_train['y'], errors='coerce')
        df_train.dropna(subset=['y'], inplace=True)
        
        df_train['ds'] = df_train['ds'] - df_train['ds'].iloc[0]
        df_train['ds'] = df_train['ds'].apply(lambda sec: datetime.fromtimestamp(sec))
        
        return df_train
    except Exception as e:
        print(f"Error loading training data: {e}", flush=True)
        raise

def initialize_model(df_train):
    """Initialize and train Prophet model with hourly seasonality"""
    model = Prophet(
        interval_width=0.99,
        yearly_seasonality=False,
        weekly_seasonality=False,
        daily_seasonality=False,
        growth='flat'
    )
    model.add_seasonality(name='hourly', period=1/24, fourier_order=5)
    model.fit(df_train)
    return model

def setup_prometheus_metrics(source_service, destination_service):
    """Setup Prometheus metrics with prefixed and service-specific names"""
    prefix = f'lab7_{source_service}_2_{destination_service}'
    return {
        'anomaly_count': Gauge(f'{prefix}_anomaly_count', 'Number of detected anomalies'),
        'mae_score': Gauge(f'{prefix}_mae_score', 'Mean Absolute Error (MAE)'),
        'mape_score': Gauge(f'{prefix}_mape_score', 'Mean Absolute Percentage Error (MAPE)'),
        'current_value': Gauge(f'{prefix}_current_value', 'Current observed value'),
        'predicted_value': Gauge(f'{prefix}_predicted_value', 'Predicted value by Prophet'),
        'yhat_min': Gauge(f'{prefix}_yhat_min', 'Lower bound of prediction'),
        'yhat_max': Gauge(f'{prefix}_yhat_max', 'Upper bound of prediction')
    }

# def fetch_current_data(prometheus_url, source_service, destination_service):
#     """Fetch single current datapoint from Prometheus with dynamic service names"""
#     query = f"histogram_quantile(0.5, sum(rate(istio_request_duration_milliseconds_bucket{{source_app='{source_service}', destination_app='{destination_service}', reporter='source'}}[1m])) by (le))"
#     try:
#         response = requests.get(f'{prometheus_url}/api/v1/query', params={'query': query})
#         response.raise_for_status()
#         data = response.json()['data']['result']
        
#         if not data:
#             print(f"No data returned from Prometheus for {source_service}->{destination_service}.", flush=True)
#             return None, None
        
#         timestamp, value = data[0]['value']
#         return float(timestamp), float(value)
#     except requests.exceptions.RequestException as e:
#         print(f"Error fetching data for {source_service}->{destination_service}: {e}", flush=True)
#         return None, None


def fetch_current_data(prometheus_url, source_service, destination_service):
    # Add more explicit debugging
    print(f"Attempting to fetch data with:", flush=True)
    print(f"Source Service: {source_service}", flush=True)
    print(f"Destination Service: {destination_service}", flush=True)
    
    query = f"histogram_quantile(0.5, sum(rate(istio_request_duration_milliseconds_bucket{{source_app='{source_service}', destination_app='{destination_service}', reporter='source'}}[1m])) by (le))"
    
    print(f"Generated Prometheus Query: {query}", flush=True)
    
    try:
        response = requests.get(f'{prometheus_url}/api/v1/query', params={'query': query})
        response.raise_for_status()
        data = response.json()['data']['result']
        
        print(f"Prometheus Response: {data}", flush=True)
        
        if not data:
            print(f"No data returned for {source_service}->{destination_service}", flush=True)
            return None, None
        
        timestamp, value = data[0]['value']
        return float(timestamp), float(value)
    except Exception as e:
        print(f"Error in fetch_current_data: {e}", flush=True)
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

def monitor(source_service, destination_service, training_file, port, prometheus_url):
    """Main monitoring function with generalized parameters"""
    print_phase_header("STARTUP - Loading Model")
    df_train = load_training_data(training_file)
    model = initialize_model(df_train)
    metrics = setup_prometheus_metrics(source_service, destination_service)
    
    # Start Prometheus server with dynamic port
    start_http_server(port)
    results = []
    test_start_time = time.time()
    
    print_phase_header(f"NORMAL OPERATION - Monitoring {source_service}->{destination_service}")
    print("Monitor started - waiting for initial data points...", flush=True)
    
    iteration = 0
    current_phase = "normal"
    while True:
        timestamp, value = fetch_current_data(prometheus_url, source_service, destination_service)
        if value is None:
            print(f"Failed to fetch data for {source_service}->{destination_service}, retrying in 60 seconds...", flush=True)
            time.sleep(60)
            continue
            
        # Phase transition logic (optional, can be customized)
        if iteration == 10 and current_phase == "normal":
            print_phase_header("DELAY INJECTION PHASE")
            current_phase = "delay"
        elif iteration == 20 and current_phase == "delay":
            print_phase_header("RECOVERY PHASE")
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
    args = parse_arguments()
    print(f"Starting monitor for {args.source_service}->{args.destination_service}")
    monitor(
        args.source_service, 
        args.destination_service, 
        args.training_file, 
        args.port,
        args.prometheus_url
    )