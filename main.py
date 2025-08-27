#!/usr/bin/env python3
"""
API Simulator Generator

Takes an OpenAPI specification and generates a fully functional API simulator
with persistent SQLite state that replicates the behavior of the real API.
"""

import json
import subprocess
import sys
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
import argparse


class APISimulatorGenerator:
    """Generates a stateful API simulator from OpenAPI specifications"""
    
    def __init__(self, openapi_spec_path: str, output_dir: str = "api-simulation", verbose: bool = False):
        self.openapi_spec_path = Path(openapi_spec_path)
        self.output_dir = Path(output_dir)
        self.verbose = verbose
        self.spec_data: Optional[Dict[str, Any]] = None
        
    def load_openapi_spec(self) -> Dict[str, Any]:
        """Load and parse the OpenAPI specification"""
        if not self.openapi_spec_path.exists():
            raise FileNotFoundError(f"OpenAPI spec not found: {self.openapi_spec_path}")
            
        with open(self.openapi_spec_path, 'r') as f:
            if self.openapi_spec_path.suffix in ['.yaml', '.yml']:
                self.spec_data = yaml.safe_load(f)
            else:
                self.spec_data = json.load(f)
                
        if self.verbose:
            print(f"Loaded OpenAPI spec: {self.spec_data.get('info', {}).get('title', 'Unknown')}")
            print(f"Endpoints: {len(self.spec_data.get('paths', {}))}")
            print(f"Schemas: {len(self.spec_data.get('components', {}).get('schemas', {}))}")
            
        return self.spec_data
    
    def analyze_spec(self) -> Dict[str, Any]:
        """Analyze the OpenAPI spec to understand entities and relationships"""
        if not self.spec_data:
            self.load_openapi_spec()
            
        analysis = {
            "api_info": self.spec_data.get('info', {}),
            "base_url": self.spec_data.get('servers', [{}])[0].get('url', ''),
            "entities": [],
            "endpoints": [],
            "relationships": []
        }
        
        # Extract entities from schemas
        schemas = self.spec_data.get('components', {}).get('schemas', {})
        for name, schema in schemas.items():
            if schema.get('type') == 'object' or 'properties' in schema:
                entity = {
                    "name": name,
                    "properties": schema.get('properties', {}),
                    "required": schema.get('required', []),
                    "table_name": self._to_table_name(name)
                }
                analysis["entities"].append(entity)
        
        # Extract endpoints
        paths = self.spec_data.get('paths', {})
        for path, methods in paths.items():
            for method, spec in methods.items():
                if method.lower() in ['get', 'post', 'put', 'patch', 'delete']:
                    endpoint = {
                        "path": path,
                        "method": method.upper(),
                        "summary": spec.get('summary', ''),
                        "operation_id": spec.get('operationId', f"{method}_{path}".replace('/', '_')),
                        "request_body": spec.get('requestBody'),
                        "responses": spec.get('responses', {}),
                        "parameters": spec.get('parameters', [])
                    }
                    analysis["endpoints"].append(endpoint)
        
        return analysis
    
    def _to_table_name(self, schema_name: str) -> str:
        """Convert schema name to database table name"""
        # Convert CamelCase to snake_case and pluralize
        import re
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', schema_name)
        table_name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
        
        # Simple pluralization
        if not table_name.endswith('s'):
            if table_name.endswith('y'):
                table_name = table_name[:-1] + 'ies'
            elif table_name.endswith(('s', 'x', 'z', 'ch', 'sh')):
                table_name += 'es'
            else:
                table_name += 's'
        
        return table_name
    
    def call_claude_code(self, prompt: str) -> tuple[bool, str]:
        """Execute a Claude Code command with real-time output"""
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        cmd = ['claude', '--permission-mode', 'acceptEdits', prompt]
        
        try:
            if self.verbose:
                print(f"Calling Claude Code: {prompt[:100]}...")
            
            print("Claude Code Output:")
            print("-" * 30)
            
            # Use Popen for real-time output
            process = subprocess.Popen(
                cmd,
                cwd=self.output_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            output_lines = []
            while True:
                line = process.stdout.readline()
                if line:
                    print(line.rstrip())  # Print to terminal in real-time
                    output_lines.append(line)
                elif process.poll() is not None:
                    break
            
            # Get any remaining output
            remaining = process.stdout.read()
            if remaining:
                print(remaining.rstrip())
                output_lines.append(remaining)
            
            return_code = process.poll()
            full_output = ''.join(output_lines)
            
            print("-" * 30)
            
            if return_code == 0:
                return True, full_output
            else:
                return False, f"Command failed with code {return_code}: {full_output}"
                
        except Exception as e:
            return False, f"Failed to execute Claude Code: {str(e)}"
    
    def generate_database_schema(self, analysis: Dict[str, Any]) -> bool:
        """Generate SQLite database schema based on the analysis"""
        entities_json = json.dumps(analysis["entities"], indent=2)
        
        prompt = f"""Create a SQLite database schema for this API simulation based on these entities:

{entities_json}

Requirements:
1. Create data/models.py file with SQLAlchemy models for each entity
2. Include proper primary keys, foreign keys, and relationships
3. Add created_at and updated_at timestamps to all models
4. Create data/database.py file with database initialization and connection handling
5. Generate appropriate indexes for performance
6. Include sample data generation functions
7. Database file should be stored as data/database.db

The models should support the full CRUD operations needed for the API endpoints.
Make sure to handle common Slack-like relationships:
- Users can be members of channels
- Messages belong to channels and users
- Reactions belong to messages and users
- Support for threading (messages can have parent messages)

Save the schema files in the data/ directory and create a requirements.txt with necessary dependencies."""
        
        success, output = self.call_claude_code(prompt)
        if not success:
            print(f"Failed to generate database schema: {output}")
            return False
            
        print("✓ Database schema generated")
        return True
    
    def generate_api_server(self, analysis: Dict[str, Any]) -> bool:
        """Generate the API server with all endpoints"""
        endpoints_json = json.dumps(analysis["endpoints"], indent=2)
        api_info = analysis["api_info"]
        
        prompt = f"""Create a Flask API server that implements all these endpoints with full state persistence:

API Info: {json.dumps(api_info, indent=2)}

Endpoints to implement:
{endpoints_json}

Requirements:
1. Create server/app.py with a Flask server that implements every endpoint
2. Each endpoint should:
   - Validate request data according to the OpenAPI spec
   - Perform appropriate database operations (CRUD)
   - Return responses that match the OpenAPI response schemas
   - Handle authentication (simulate with simple token validation)
   - Generate realistic timestamps, IDs, and other dynamic data
3. Implement proper error handling and HTTP status codes
4. Add CORS support for frontend testing
5. Include database initialization on startup (connecting to data/database.db)
6. Add logging for all operations
7. Support pagination where specified in the original spec
8. Import models from data/models.py

The server should behave as close to the real Slack API as possible, with:
- Message threading support
- Channel membership management
- User authentication simulation
- Reaction handling
- Conversation history with proper ordering

Make it feel like working with the real API, just with local SQLite persistence.
Save the server files in the server/ directory."""
        
        success, output = self.call_claude_code(prompt)
        if not success:
            print(f"Failed to generate API server: {output}")
            return False
            
        print("✓ API server generated")
        return True
    
    def generate_test_suite(self, analysis: Dict[str, Any]) -> bool:
        """Generate comprehensive tests for the API simulation"""
        prompt = f"""Create a comprehensive test suite for the API simulation:

1. Create test_api.py with tests for all endpoints:
   - Test successful operations (CRUD)
   - Test error conditions and edge cases
   - Test authentication requirements
   - Test data persistence across requests
   - Test relationships between entities

2. Create test_scenarios.py with realistic usage scenarios:
   - Complete workflows (create user, join channel, send messages)
   - Multi-user interactions
   - Threading conversations
   - Reaction management

3. Include setup and teardown to ensure clean test state
4. Use pytest with fixtures for database management
5. Add performance tests for endpoints with large datasets

The tests should verify that the simulation behaves identically to how the real API would work."""
        
        success, output = self.call_claude_code(prompt)
        if not success:
            print(f"Failed to generate test suite: {output}")
            return False
            
        print("✓ Test suite generated")
        return True
    
    def create_project_files(self, analysis: Dict[str, Any]) -> None:
        """Create additional project files"""
        api_title = analysis["api_info"].get("title", "API Simulation")
        api_description = analysis["api_info"].get("description", "Generated API simulation")
        
        readme_content = f"""# {api_title} Simulation

{api_description}

This is a fully functional simulation of the {api_title} that maintains state in SQLite.

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

## Generated from OpenAPI spec: {self.openapi_spec_path.name}
"""
        
        (self.output_dir / "README.md").write_text(readme_content)
        print("✓ Project files created")
    
    def create_directory_structure(self):
        """Create the required directory structure"""
        dirs = ["data", "api", "server"]
        for dir_name in dirs:
            (self.output_dir / dir_name).mkdir(parents=True, exist_ok=True)
        print("✓ Directory structure created (data/, api/, server/)")

    def run(self) -> bool:
        """Run the complete API simulation generation process"""
        print(f"Generating API simulation from: {self.openapi_spec_path}")
        print(f"Output directory: {self.output_dir}")
        print("-" * 50)
        
        try:
            # Step 1: Create directory structure
            print("1. Creating directory structure...")
            self.create_directory_structure()
            
            # Step 2: Load and analyze the OpenAPI spec
            print("2. Analyzing OpenAPI specification...")
            analysis = self.analyze_spec()
            
            # Step 3: Generate database schema in data/
            print("\n3. Generating database schema...")
            if not self.generate_database_schema(analysis):
                return False
            
            # Step 4: Generate API server in server/
            print("\n4. Generating API server...")
            if not self.generate_api_server(analysis):
                return False
                
            # Step 5: Generate test suite
            print("\n5. Generating test suite...")
            if not self.generate_test_suite(analysis):
                return False
            
            # Step 6: Create project files
            print("\n6. Creating project files...")
            self.create_project_files(analysis)
            
            print("\n" + "=" * 50)
            print("✅ API Simulation Generated Successfully!")
            print(f"\nNext steps:")
            print(f"cd {self.output_dir}")
            print(f"pip install -r requirements.txt")
            print(f"python server/app.py")
            print(f"\nThe API will be available at http://localhost:5000")
            print(f"Database will be stored in data/database.db")
            
            return True
            
        except Exception as e:
            print(f"❌ Generation failed: {str(e)}")
            return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Generate API simulator from OpenAPI specification")
    parser.add_argument("spec_path", help="Path to OpenAPI specification file (.yaml or .json)")
    parser.add_argument("-o", "--output", default="api-simulation", 
                       help="Output directory for generated API simulation")
    parser.add_argument("-v", "--verbose", action="store_true",
                       help="Enable verbose output")
    
    args = parser.parse_args()
    
    generator = APISimulatorGenerator(
        openapi_spec_path=args.spec_path,
        output_dir=args.output,
        verbose=args.verbose
    )
    
    success = generator.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()