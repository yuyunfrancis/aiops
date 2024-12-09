
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
# Make port 8080 available to the world outside this container

# Copy the current directory contents into the container at /app
COPY monitor1.py .
# COPY incident_detector.py .
COPY *.json /app/

EXPOSE 8080

# Define environment variable
ENV PYTHONUNBUFFERED=1

# # Run monitor1.py when the container launches
ENTRYPOINT ["python3", "monitor1.py"]

# # Default arguments (can be overridden)
# CMD ["frontend", "shippingservice", "boutique_training.json"]

