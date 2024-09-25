FROM python:3

# Install dumb-init to handle signals properly in the container environment
RUN wget -O /usr/local/bin/dumb-init https://github.com/Yelp/dumb-init/releases/download/v1.2.5/dumb-init_1.2.5_x86_64
RUN chmod +x /usr/local/bin/dumb-init

# Copy the contents of the current directory into the working directory of the container
COPY . /app
WORKDIR /app

# Ensure pip is installed
RUN pip install --upgrade pip

# Install the required packages using pip
RUN pip install pandas matplotlib prometheus-api-client prophet numpy==1.26.0 plotly prometheus_client

# Use dumb-init to handle signals properly in the container environment
ENTRYPOINT ["/usr/local/bin/dumb-init", "--"]

# Run the application
CMD ["python", "model_evaluation.py"]