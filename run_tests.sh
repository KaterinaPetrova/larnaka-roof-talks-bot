#!/bin/bash

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Run tests
echo "Running registration tests..."
pytest tests/test_registration.py -v

echo "Tests completed!"