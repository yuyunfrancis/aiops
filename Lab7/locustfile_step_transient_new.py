#!/usr/bin/python
#
# Copyright 2024 Google LLC
# Modified for AIOps Lab Task 5: Transient Load Generation

import random
import os
import datetime
from locust import FastHttpUser, TaskSet, between, LoadTestShape
from faker import Faker

# Faker for generating realistic test data
fake = Faker()

# Predefined list of product IDs from the Boutique application
products = [
    '0PUK6V6EV0', '1YMWWN1N4O', '2ZYFJ3GM2N', 
    '66VCHSJNUP', '6E92ZMYYFZ', '9SIQT8TOJO', 
    'L9ECAV7KIM', 'LS4PSXUNUM', 'OLJCESPC7Z'
]

# User interaction functions
def index(l):
    l.client.get("/")

def setCurrency(l):
    currencies = ['EUR', 'USD', 'JPY', 'CAD', 'GBP', 'TRY']
    l.client.post("/setCurrency", 
        {'currency_code': random.choice(currencies)})

def browseProduct(l):
    l.client.get("/product/" + random.choice(products))

def viewCart(l):
    l.client.get("/cart")

def addToCart(l):
    product = random.choice(products)
    l.client.get("/product/" + product)
    l.client.post("/cart", {
        'product_id': product,
        'quantity': random.randint(1,10)})
    
def empty_cart(l):
    l.client.post('/cart/empty')

def checkout(l):
    addToCart(l)
    current_year = datetime.datetime.now().year+1
    l.client.post("/cart/checkout", {
        'email': fake.email(),
        'street_address': fake.street_address(),
        'zip_code': fake.zipcode(),
        'city': fake.city(),
        'state': fake.state_abbr(),
        'country': fake.country(),
        'credit_card_number': fake.credit_card_number(card_type="visa"),
        'credit_card_expiration_month': random.randint(1, 12),
        'credit_card_expiration_year': random.randint(current_year, current_year + 70),
        'credit_card_cvv': f"{random.randint(100, 999)}",
    })
    
    
    
    
def logout(l):
    l.client.get('/logout')  

# User behavior class
class UserBehavior(TaskSet):
    def on_start(self):
        index(self)

    tasks = {
        index: 1,
        setCurrency: 2,
        browseProduct: 10,
        addToCart: 2,
        viewCart: 3,
        checkout: 1
    }

# Transient load detection function
def transient_in_effect(run_secs):
    """
    Define transient load scenarios
    
    Configurable parameters for transient load generation:
    - Multiple transient windows
    - Varying user load surge
    - Flexible timing
    """
    # Configurable transient parameters
    transient_configs = [
        {
            'min_time': 60,    # First transient start time
            'max_time': 180,   # First transient end time
            'surge': 500       # User load surge for first transient
        },
        {
            'min_time': 600,   # Second transient start time
            'max_time': 720,   # Second transient end time
            'surge': 1000      # User load surge for second transient
        }
    ]

    for config in transient_configs:
        if config['min_time'] <= run_secs <= config['max_time']:
            print(f"Applying transient of {config['surge']} users "
                  f"between {config['min_time']} and {config['max_time']} seconds")
            return config['surge']
    return 0

# Load test shape configuration
class TransientLoadShape(LoadTestShape):
    # Configurable test parameters
    time_limit = int(os.environ.get("TIMELIMIT", 1800))    # Total test duration
    spawn_rate = int(os.environ.get("SPAWNRATE", 100))     # User spawn rate
    max_users = int(os.environ.get("MAXUSERS", 300))       # Maximum concurrent users
    cycle_time = int(os.environ.get("CYCLETIME", 1200))    # Total cycle duration
    num_steps = int(os.environ.get("NUMSTEPS", 10))        # Number of load steps

    # Initialization of load parameters
    last_target_users = 50
    current_steps = 0

    # Detailed logging of test configuration
    print(f'Test Configuration:')
    print(f' - Total Runtime: {time_limit} seconds')
    print(f' - Spawn Rate: {spawn_rate} users/second')
    print(f' - Maximum Users: {max_users}')
    print(f' - Cycle Time: {cycle_time} seconds')
    print(f' - Load Steps: {num_steps}')

    # Calculate step-specific parameters
    seconds_per_step = int(cycle_time / num_steps)
    users_per_step = int(max_users / num_steps) * 2
    next_update_time = seconds_per_step

    def tick(self):   
        # Get current runtime
        run_time = self.get_run_time()
        
        # Check if within test time limit
        if run_time < self.time_limit:
            # Detect transient load
            transient_spike = transient_in_effect(run_time)

            # Manage load steps
            if run_time >= self.next_update_time:
                self.next_update_time += self.seconds_per_step
                self.current_steps += 1

                # Determine target user load (up and down)
                if self.current_steps < self.num_steps / 2 + 1:
                    target_users = self.last_target_users + self.users_per_step
                else:
                    target_users = self.last_target_users - self.users_per_step
                    target_users = max(0, target_users)
                    
                    # Reset cycle when completed
                    if self.current_steps == self.num_steps:
                        self.current_steps = 0

                self.last_target_users = target_users

                # Return target users with transient spike
                return (target_users + transient_spike, self.spawn_rate)
            
            # Maintain current user load with transient spike
            return (self.last_target_users + transient_spike, self.spawn_rate)

        # End test when time limit reached
        return None   

# User simulation class
class WebsiteUser(FastHttpUser):
    tasks = [UserBehavior]
    wait_time = between(1, 10)