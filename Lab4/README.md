# Deploying, Scaling, and Monitoring the BookInfo Application on Kubernetes

## 1. Creating the Kubernetes Cluster

- **Purpose**: To set up a Kubernetes environment for the BookInfo application.
- **Command**:

  ```bash
  gcloud container clusters create bookinfo   --project=vital-chiller-437317-r9   --zone=us-west1-a   --machine-type=e2-standard-4   --num-nodes=1   --workload-pool vital-chiller-437317-r9.svc.id.goog   --gateway-api "standard"

  ```

- **Description**: I used Google Kubernetes Engine (GKE) to create a cluster named `bookinfo` with 1 node, which provided the foundation to deploy and manage our microservices.

## 2. Deploying the BookInfo Application

- **Purpose**: To deploy the individual microservices (productpage, reviews, details, ratings) that make up the BookInfo application.
- **Command**:
  ```bash
  kubectl apply -f platform/kube/bookinfo.yaml
  ```
- **Description**: The `bookinfo.yaml` file contains the configuration for deploying all the services and their respective pods. This command created the necessary deployments and exposed services.

## 3. Scaling the `reviews` and `ratings` Services

- **Purpose**: To increase the availability and load-handling capacity of the `reviews` and `ratings` services.
- **Commands**:
  ```bash
  kubectl scale deployment reviews --replicas=3
  kubectl scale deployment ratings --replicas=2
  ```
- **Description**: By scaling the replicas to 3 and 2 for both services, I ensured they could handle more traffic and have redundancy. This was crucial for managing increased demand and preventing single points of failure.

## 4. Pushing the BookInfo Image to Docker Hub

- **Purpose**: To ensure that the application image is available for deployment by pushing it to a centralized registry (Docker Hub).
- **Commands**:
  ```bash
  export BOOKINFO_HUB=francisberi/bookinfo
  export BOOKINFO_TAG=latest
  docker tag bookinfo ${BOOKINFO_HUB}:${BOOKINFO_TAG}
  docker push ${BOOKINFO_HUB}:${BOOKINFO_TAG}
  ```
- **Description**: These commands tagged the BookInfo image and pushed it to Docker Hub under the repository `francisberi/bookinfo`, making it accessible for deployments in different environments, including the Kubernetes cluster.

## 5. Editing the Prometheus Configuration to Add BookInfo as a Target

- **Purpose**: To allow Prometheus to scrape metrics from the BookInfo `productpage` service.
- **Steps**:
  - Open the Prometheus configuration file (`prometheus-config.yaml`).
  - Add the following entry under `scrape_configs`:
    ```yaml
    - job_name: "bookinfo"
      static_configs:
        - targets: ["<productpage_external_ip>:9080"]
    ```
- **Description**: We configured Prometheus to scrape metrics from the BookInfo service by specifying the external IP address and port of the `productpage` service. This allowed us to monitor the requests and system performance of the application.

## 6. Verifying Target Status in Prometheus

- **Purpose**: To confirm that Prometheus is successfully scraping metrics from BookInfo.

- **Description**: By navigating to `http://localhost:9090/targets`, we verified that the `bookinfo` job was up and that metrics were being collected. This step was essential to ensure the monitoring setup was correct.

## 7. Visualizing Metrics in Grafana

- **Purpose**: To create a graphical view of the BookInfo application metrics.
- **Steps**:

  - Open Grafana in the browser (`http://localhost:3000`) after setting up port-forwarding:

  - In Grafana, add a new visualization and use a relevant metric such as `request_result_total`.
  - Query
    ```sql
    request_result_total{job="bookinfo"}
    ```
  - **Description**: We used Grafana to visualize metrics from Prometheus. By accessing specific metrics like `request_result_total`, we were able to observe the application’s request rate and other key performance indicators.

These steps provided a structured approach to setting up, scaling, and monitoring the BookInfo application, ensuring that it could handle load effectively and that we could observe its behavior in real-time.
