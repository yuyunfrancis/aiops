# # Get python 3 image from dockerhub
# FROM python:3

# RUN wget -O /usr/local/bin/dumb-init https://github.com/Yelp/dumb-init/releases/download/v1.2.5/dumb-init_1.2.5_x86_64
# RUN chmod +x /usr/local/bin/dumb-init

# # Copy repo contents into working directory
# COPY . /app
# WORKDIR /app

# # Install prometheus client library
# RUN pip install prometheus_client
# RUN pip install prophet
# RUN pip install requests
# RUN pip install numpy
# RUN pip install pandas
# RUN pip install datetime
# RUN pip install scikit-learn

# # Dumb init
# ENTRYPOINT ["/usr/local/bin/dumb-init", "--"]

# # Run the application
# CMD ["python", "monskeleton.py", "-t1", "-f10"]

# Get python 3 image from dockerhub
FROM python:3
RUN wget -O /usr/local/bin/dumb-init https://github.com/Yelp/dumb-init/releases/download/v1.2.5/dumb-init_1.2.5_x86_64
RUN chmod +x /usr/local/bin/dumb-init
# Copy repo contents into working directory

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install -r requirements.txt

# Copy monitor code and training data
COPY monitor1.py .
COPY boutique_training.json .

# Expose port for Prometheus metrics
EXPOSE 8080

# Run monitor
CMD ["python3", "monitor1.py"]

