FROM python:3
RUN wget -O /usr/local/bin/dumb-init https://github.com/Yelp/dumb-init/releases/download/v1.2.5/dumb-init_1.2.5_x86_64
RUN chmod +x /usr/local/bin/dumb-init

# Set working directory
WORKDIR /app

# Copy requirements file
# You'll need to create a requirements.txt for the incident detector
COPY requirements.txt .

# Install dependencies
RUN pip install -r requirements.txt

# Copy the incident detector script
COPY incident_detector.py .

# Expose the Prometheus metrics port
EXPOSE 8082

# Define environment variable
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python3", "incident_detector.py"]

# Default command (can be overridden)
CMD ["python3", "incident_detector.py", "frontend", "checkoutservice"]