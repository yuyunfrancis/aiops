import requests
from prometheus_client import start_http_server, Gauge, Summary, Histogram, Counter
import sys, getopt
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error

import numpy as np
np.float_ = np.float64
# Prophet model for time series forecast
from prophet import Prophet

# Data processing

import pandas as pd
from datetime import datetime
import time
from urllib.parse import urlencode
import json
from dotenv import load_dotenv
import os

load_dotenv()

np.float_ = np.float64

def extract_first_y(test_json):
    print(test_json, flush=True)
    result = test_json['data']['result']   # step into the result json string to get to the value
    val = result[0]['value'][1]            # reference the value part of the remaining structure
    print(val, flush=True)                 # debugging print, remove if desired, flush True to see immediately
    return float(val)                      # return as float so we can use to set a gauge metric

def main():                
    url_test_data_50 = {
        "query": "histogram_quantile( 0.5, sum by (le) (rate(istio_request_duration_milliseconds_bucket{source_app='frontend', destination_app='shippingservice', reporter='source'}[1m])))"
    }
    url_test_data_95 = {
    "query": "histogram_quantile( 0.95, sum by (le) (rate(istio_request_duration_milliseconds_bucket{source_app='frontend', destination_app='shippingservice', reporter='source'}[1m])))"
    }
    # test_url = "http://34.150.178.7:9090/api/v1/query"
    # test_url = os.getenv("PROMETHEUS_URL","http://35.221.23.103:9090")+ "/api/v1/query"
    test_url = os.getenv("PROMETHEUS_URL","http://34.127.18.133:9090/api/v1/query")

    g_req50 = Gauge("frontend_to_shipping_req_50", "request seconds frontend to shipping service")
    g_req50.set(0)

    g_req95 = Gauge("frontend_to_shipping_req_95", "request seconds frontend to shipping service")
    g_req95.set(0)

    while True:
        r = requests.get(test_url, params=url_test_data_50)  # fetch the test json from prometheus 
        req_time_50 = extract_first_y(r.json())              # extract the request time estimate from the json string
        print(f"50th percentile request time: {req_time_50}")
        g_req50.set(req_time_50)                             # set g_req50

        r = requests.get(test_url, params=url_test_data_95)  # fetch the test json from prometheus 
        req_time_95 = extract_first_y(r.json())              # extract the request time estimate from the json string
        print(f"95th percentile request time: {req_time_95}")
        g_req95.set(req_time_95)                             # set g_req95
        
        time.sleep(15)

if __name__ == '__main__':
    np.float_ = np.float64
    start_http_server(8099)
    main()
    
    

