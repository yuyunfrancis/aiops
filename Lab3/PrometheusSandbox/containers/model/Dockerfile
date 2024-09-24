FROM python:3

# Install dumb-init to handle signals properly in the container environment
RUN wget -O /usr/local/bin/dumb-init https://github.com/Yelp/dumb-init/releases/download/v1.2.5/dumb-init_1.2.5_x86_64
RUN chmod +x /usr/local/bin/dumb-init # Make the file executable by changing the permissions to 755

# Install Miniconda
RUN wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /miniconda.sh
RUN bash /miniconda.sh -b -p /opt/conda
ENV PATH=/opt/conda/bin:$PATH

# Copy the contents of the current directory into the working directory of the container
COPY . /app
WORKDIR /app

# Copy the requirements.txt file into the container
#COPY requirements.txt /app/requirements.txt

# Install the required packages using conda
RUN conda install -y pandas matplotlib

RUN pip install prometheus-api-client prophet

# Use dumb-init to handle signals properly in the container environment
ENTRYPOINT ["/usr/local/bin/dumb-init", "--"]

# Run the application
CMD ["python", "model_evaluation.py"]