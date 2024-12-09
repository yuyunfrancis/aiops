#!/bin/bash

# Fault Injection Test Script for AIOps Lab

# Configuration
NAMESPACE="default"
LOAD_GENERATOR_POD=$(kubectl get pods -n $NAMESPACE | grep load-generator | awk '{print $1}')
INCIDENT_DETECTOR_POD=$(kubectl get pods -n $NAMESPACE | grep boutique-incident-detector | awk '{print $1}')

# Function to apply fault injection
apply_fault_injection() {
    local scenario=$1
    echo "Applying $scenario Fault Injection..."
    
    if [ "$scenario" == "single" ]; then
        # Single service delay configuration
        kubectl apply -f frontend-checkoutservice-delay-injection.yaml
    elif [ "$scenario" == "dual" ]; then
        # Dual service delay configuration
        kubectl apply -f frontend-checkoutservice-delay-injection.yaml
    fi
    
    sleep 5  # Wait for changes to propagate
}

# Function to check incident status
check_incident_status() {
    echo "Checking Incident Detector Logs:"
    kubectl logs $INCIDENT_DETECTOR_POD | grep -E "SEV 1|SEV 2 INCIDENT"
}

# Main test execution
main() {
    # Scenario 1: Single Service Delay
    echo "=== Testing Single Service Delay (Sev 2) ==="
    apply_fault_injection "single"
    check_incident_status
    
    # Optional: Start load generator if not running
    if [ -z "$LOAD_GENERATOR_POD" ]; then
        echo "Starting load generator..."
        # Add your load generator start command
    fi
    
    # Wait and observe
    sleep 180  # 3 minutes observation
    
    # Scenario 2: Dual Service Delay
    echo "=== Testing Dual Service Delay (Sev 1) ==="
    apply_fault_injection "dual"
    check_incident_status
    
    # Wait and observe
    sleep 180  # 3 minutes observation
    
    # Cleanup
    echo "=== Cleaning Up ==="
    kubectl delete -f frontend-checkoutservice-delay-injection.yaml
}

# Execute main function
main