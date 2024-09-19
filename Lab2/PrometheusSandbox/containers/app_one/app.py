from prometheus_client import start_http_server, Gauge, Histogram
import random
import time

# Defining the existing gauge
g = Gauge('demo_gauge', 'Description of demo gauge')

# Defining the two new metrics for app1
# First gauge/histogram combination: random variable between 0 and 1
test_gauge = Gauge('test_gauge', 'Random number between 0 and 1')
test_hist = Histogram('test_hist', 'Random number between 0 and 1')

# Second gauge/histogram combination: random variable between 0 and 0.6
train_gauge = Gauge('train_gauge', 'Random number between 0 and 0.6')
train_hist = Histogram('train_hist', 'Random number between 0 and 0.6')

def generate_random_number(max_value):
    """Generate a random number between 0 and max_value"""
    return random.uniform(0, max_value)

def emit_data():
    """Emit fake data"""
    time.sleep(5)  # Fixed sleep period of 5 seconds
    value1 = generate_random_number(1)
    value2 = generate_random_number(0.6)
    
    g.set(value1)
    test_gauge.set(value1)
    test_hist.observe(value1)
    
    train_gauge.set(value2)
    train_hist.observe(value2)

if __name__ == '__main__':
    start_http_server(8000)
    while True:
        emit_data()

