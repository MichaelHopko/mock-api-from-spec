# Slack Events API Simulation

A webhook-based events bus using a subscription model for Slack apps

This is a fully functional simulation of the Slack Events API that maintains state in SQLite.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
python database.py

# Start the API server
python app.py
```

The API will be available at http://localhost:5000

## Testing

```bash
# Run all tests
pytest

# Run specific test categories
pytest test_api.py          # API endpoint tests
pytest test_scenarios.py    # Usage scenario tests
```

## Features

- ✅ Complete API endpoint implementation
- ✅ SQLite state persistence
- ✅ Request/response validation
- ✅ Authentication simulation
- ✅ Realistic data generation
- ✅ Relationship management
- ✅ Comprehensive test suite

## Generated from OpenAPI spec: slack_openapi_spec.yaml
