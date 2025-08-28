# API Mock Generator Agent

An AI-powered tool that automatically generates complete mock API implementations from OpenAPI specifications.

## Overview

The `main.py` script analyzes OpenAPI specifications and generates:

- **Flask-based mock server** with matching endpoints
- **Database schema** with realistic sample data
- **Comprehensive test suite** (unit and integration tests)
- **Complete project structure** ready to run

## Usage

```bash
# Using uv
uv run main.py path/to/openapi.yaml output-directory

# OR using python
python main.py path/to/openapi.yaml output-directory
```

### Process
1. Analyzes OpenAPI specification
2. Generates database models and schema
3. Creates Flask server with matching endpoints
4. Builds comprehensive test suite
5. Populates database with realistic sample data

## Results

Tested with 2,000+ line Slack API specification:
- 92.3% compatibility with real Slack API
- 20+ endpoints implemented
- 200+ tests generated
- Complete CRUD operations

## Generated Structure

```
output-directory/
├── server/
│   ├── app.py       # Flask API server
│   └── run.py       # Server launcher
├── data/
│   ├── database.py  # Database connection
│   ├── models.py    # SQLAlchemy models
│   └── fixtures.py  # Sample data
├── tests/
│   ├── test_*.py    # Unit tests
│   └── integration/ # Integration tests
└── README.md        # Generated documentation
```

## Use Cases

- **Frontend Development** - Create mock services while APIs are being built
- **Integration Testing** - Generate test doubles for testing
- **Rapid Prototyping** - Quickly stand up API mockups for demos
- **Contract Testing** - Validate API compatibility

## Requirements

- Python 3.8+
- OpenAPI 3.0+ specification
- AI model access (configured in main.py)

## Quick Start

**IMPORTANT**: This repository already contains generated output. You can directly run the server:

```bash
# Run the pre-generated server (from repository root)
uv run output-dir/server/run.py
# OR
python output-dir/server/run.py
```

To generate new output (will overwrite existing):

```bash
# Install dependencies (if using pip)
pip install -r requirements.txt

# Generate new mock API (regenerates everything)
uv run main.py your-api-spec.yaml output-dir
# OR
python main.py your-api-spec.yaml output-dir

# Start the newly generated server
uv run output-dir/server/run.py
# OR
python output-dir/server/run.py
```

The generated mock API runs on http://localhost:5000 with full CRUD functionality.