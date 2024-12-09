import requests
from prometheus_client import start_http_server, Gauge, Summary, Histogram, Counter
import sys, getopt
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error

# Prophet model for time series forecast
from prophet import Prophet

# Data processing
import numpy as np
import pandas as pd
from datetime import datetime
import time
from urllib.parse import urlencode
import json

def extract_first_y(test_json):
    print(test_json, flush=True)
    result = test_json['data']['result']  # step into the result json string to get to the value
    val = result[0]['value'][1]           # reference the value part of the remaining structure
    print(val, flush=True)                # debugging print, remove if desired, flush True to see immediately
    return float(val)                     # return as float so we can use to set a gauge metric

def main():                
    # Define the query parameters for the 50th and 95th quantile request times
    url_test_data_50 = {
        "query": "histogram_quantile(0.5, rate(istio_request_duration_milliseconds_bucket{source_app='frontend', destination_app='shippingservice', reporter='source'}[1m]))"
    }
    url_test_data_95 = {
        "query": "histogram_quantile(0.95, rate(istio_request_duration_milliseconds_bucket{source_app='frontend', destination_app='shippingservice', reporter='source'}[1m]))"
    }
    test_url = "http://localhost:9090/api/v1/query"  # Replace with your Prometheus server URL
    
    # Initialize Prometheus Gauges
    g_req50 = Gauge("frontend_to_shipping_req_50", "request seconds frontend to shipping service")
    g_req50.set(0)

    g_req95 = Gauge("frontend_to_shipping_req_95", "request seconds frontend to shipping service")
    g_req95.set(0)

    while True:
        # Fetch the test json from Prometheus for the 50th quantile
        r = requests.get(test_url, params=url_test_data_50)
        req_time_50 = extract_first_y(r.json())  # Extract the request time estimate from the json string
        print(f"50th quantile request time: {req_time_50}")
        g_req50.set(req_time_50)  # Set the gauge for the 50th quantile request time

        # Fetch the test json from Prometheus for the 95th quantile
        r = requests.get(test_url, params=url_test_data_95)
        req_time_95 = extract_first_y(r.json())  # Extract the request time estimate from the json string
        print(f"95th quantile request time: {req_time_95}")
        g_req95.set(req_time_95)  # Set the gauge for the 95th quantile request time
        
        time.sleep(15)  # Sleep for 15 seconds before the next iteration

if __name__ == '__main__':
    start_http_server(8099)  # Start the Prometheus HTTP server on port 8099
    main()  # Run the main function