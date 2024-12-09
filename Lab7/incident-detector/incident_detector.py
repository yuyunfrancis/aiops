import json
import argparse
import requests
import time
import logging
from datetime import datetime
from prometheus_client import Gauge, start_http_server
import pandas as pd
from tabulate import tabulate

def parse_arguments():
    """Parse command-line arguments for incident detector"""
    parser = argparse.ArgumentParser(description='Boutique Service Incident Detector')
    parser.add_argument('service1', help='First service name')
    parser.add_argument('service2', help='Second service name')
    parser.add_argument('--port', type=int, default=8082, help='Prometheus scrape port')
    parser.add_argument('--prometheus-url', 
                        default='http://prometheus.istio-system:9090', 
                        help='Prometheus server URL')
    parser.add_argument('--incident-threshold', type=int, default=5, 
                        help='Threshold for declaring an incident')
    
    # Add debug print to verify arguments
    args = parser.parse_args()
    print(f"Debug: Parsed Arguments:", flush=True)
    print(f"Service 1: {args.service1}", flush=True)
    print(f"Service 2: {args.service2}", flush=True)
    print(f"Port: {args.port}", flush=True)
    print(f"Prometheus URL: {args.prometheus_url}", flush=True)
    print(f"Incident Threshold: {args.incident_threshold}", flush=True)
    
    return args

def setup_prometheus_metrics(service1, service2):
    """Setup Prometheus metrics with prefixed and service-specific names"""
    prefix = f'lab7_incident_{service1}_{service2}'
    return {
        'total_temperature': Gauge(f'{prefix}_total_temperature', 'Total accumulator temperature'),
        'service1_temperature': Gauge(f'{prefix}_service1_temperature', f'Accumulator for {service1}'),
        'service2_temperature': Gauge(f'{prefix}_service2_temperature', f'Accumulator for {service2}'),
        'sev1_incident': Gauge(f'{prefix}_sev1_incident', 'Severity 1 Incident Status'),
        'sev2_incident': Gauge(f'{prefix}_sev2_incident', 'Severity 2 Incident Status')
    }

def print_phase_header(phase_name):
    """Print a clearly visible phase header"""
    border = "=" * 80
    print(f"\n{border}", flush=True)
    print(f"PHASE: {phase_name}", flush=True)
    print(f"Timestamp: {datetime.now()}", flush=True)
    print(f"{border}\n", flush=True)

def fetch_anomaly_metrics(prometheus_url, service1, service2):
    """
    Fetch anomaly metrics with detailed debugging
    
    Args:
        prometheus_url (str): URL of Prometheus server
        service1 (str): First service name
        service2 (str): Second service name
    
    Returns:
        tuple: (service1_anomaly, service2_anomaly)
    """
    print(f"Attempting to fetch anomaly metrics:", flush=True)
    print(f"Prometheus URL: {prometheus_url}", flush=True)
    print(f"Service 1: {service1}", flush=True)
    print(f"Service 2: {service2}", flush=True)

    try:
        # Construct more robust query
        query1 = f'sum({{__name__="lab7_{service1}_2_shippingservice_anomaly_count"}}) or vector(0)'
        query2 = f'sum({{__name__="lab7_{service2}_2_shippingservice_anomaly_count"}}) or vector(0)'

        print(f"Query 1: {query1}", flush=True)
        print(f"Query 2: {query2}", flush=True)

        # Add timeout and detailed error handling
        response1 = requests.get(
            f'{prometheus_url}/api/v1/query', 
            params={'query': query1},
            timeout=10
        )
        response2 = requests.get(
            f'{prometheus_url}/api/v1/query', 
            params={'query': query2},
            timeout=10
        )

        # Log full response for debugging
        print(f"Response 1 Status: {response1.status_code}", flush=True)
        print(f"Response 1 Content: {response1.text}", flush=True)
        print(f"Response 2 Status: {response2.status_code}", flush=True)
        print(f"Response 2 Content: {response2.text}", flush=True)

        # Extract anomaly values
        anomaly1 = float(response1.json()['data']['result'][0]['value'][1]) if response1.json()['data']['result'] else 0
        anomaly2 = float(response2.json()['data']['result'][0]['value'][1]) if response2.json()['data']['result'] else 0

        print(f"Anomaly 1: {anomaly1}, Anomaly 2: {anomaly2}", flush=True)
        return anomaly1, anomaly2

    except Exception as e:
        print(f"Error in fetch_anomaly_metrics: {e}", flush=True)
        # Print additional context about the error
        import traceback
        traceback.print_exc()
        return 0, 0

def incident_detector(service1, service2, port, prometheus_url, incident_threshold):
    """Main incident detection function"""
    print_phase_header("STARTUP - Incident Detector")
    
    # Setup Prometheus metrics
    metrics = setup_prometheus_metrics(service1, service2)
    
    # Start Prometheus server with dynamic port
    start_http_server(port)
    
    # Accumulators
    accumulator1 = 0
    accumulator2 = 0
    results = []
    
    print_phase_header(f"NORMAL OPERATION - Monitoring {service1} and {service2}")
    print("Incident Detector started - waiting for initial data points...", flush=True)
    
    iteration = 0
    while True:
        # Fetch anomaly metrics
        anomaly1, anomaly2 = fetch_anomaly_metrics(
            prometheus_url, service1, service2
        )
        
        # Update accumulators
        # Rules: 
        # - Add 1 for anomalies 
        # - Subtract 2 if no anomaly (floor at 0)
        # - Cap accumulator values
        accumulator1 = max(0, min(10, 
            accumulator1 + (1 if anomaly1 > 0 else -2)
        ))
        accumulator2 = max(0, min(10, 
            accumulator2 + (1 if anomaly2 > 0 else -2)
        ))
        
        # Calculate total temperature
        total_temperature = accumulator1 + accumulator2
        
        # Update Prometheus metrics
        metrics['total_temperature'].set(total_temperature)
        metrics['service1_temperature'].set(accumulator1)
        metrics['service2_temperature'].set(accumulator2)
        
        # Check for incidents
        incident = None
        if total_temperature >= incident_threshold:
            if accumulator1 > 0 and accumulator2 > 0:
                # Sev 1 Incident: Both services anomalous
                metrics['sev1_incident'].set(1)
                metrics['sev2_incident'].set(0)
                incident = "Sev 1"
                print(f"SEV 1 INCIDENT DETECTED: {service1} and {service2}", flush=True)
            elif accumulator1 > 0 or accumulator2 > 0:
                # Sev 2 Incident: One service anomalous
                metrics['sev1_incident'].set(0)
                metrics['sev2_incident'].set(1)
                incident = "Sev 2"
                print(f"SEV 2 INCIDENT DETECTED: {service1} or {service2}", flush=True)
        else:
            # Reset incident metrics if no incident
            metrics['sev1_incident'].set(0)
            metrics['sev2_incident'].set(0)
        
        # Store results
        results.append({
            'Timestamp': datetime.now(),
            'Service1_Anomaly': anomaly1,
            'Service2_Anomaly': anomaly2,
            'Service1_Temperature': accumulator1,
            'Service2_Temperature': accumulator2,
            'Total_Temperature': total_temperature,
            'Incident': incident
        })
        
        # Print results
        if len(results) > 0:
            df_results = pd.DataFrame(results)
            print("\nIncident Detector Results:", flush=True)
            print(tabulate(df_results.tail(5), 
                           headers='keys', 
                           tablefmt='grid', 
                           showindex=False), flush=True)
        
        iteration += 1
        time.sleep(60)

if __name__ == "__main__":
    args = parse_arguments()
    print(f"Starting Incident Detector for {args.service1} and {args.service2}")
    incident_detector(
        args.service1, 
        args.service2, 
        args.port, 
        args.prometheus_url,
        args.incident_threshold
    )