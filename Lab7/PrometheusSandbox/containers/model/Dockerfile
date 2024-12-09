FROM python:3.10

# Install dumb-init to handle signals properly in the container environment
RUN wget -O /usr/local/bin/dumb-init https://github.com/Yelp/dumb-init/releases/download/v1.2.5/dumb-init_1.2.5_x86_64 && \
    chmod +x /usr/local/bin/dumb-init

# Install distutils and other dependencies
RUN apt-get update && \
    apt-get install -y python3-distutils && \
    rm -rf /var/lib/apt/lists/*

# Copy the contents of the current directory into the working directory of the container
COPY . /app
WORKDIR /app

# Ensure pip is up-to-date
RUN pip install --upgrade pip

# Install the required packages using pip
RUN pip install setuptools pandas matplotlib prometheus-api-client prophet numpy==1.25.2 plotly prometheus_client

# Use dumb-init to handle signals properly in the container environment
ENTRYPOINT ["/usr/local/bin/dumb-init", "--"]

# Run the application
CMD ["python", "model_evaluation.py"]
