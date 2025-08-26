#!/usr/bin/env python3
"""
Automated Mock API Generator with Stateful Object Management
Orchestrates creation of mock APIs that maintain state across operations
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict, field
from enum import Enum
import yaml
import argparse
import shutil
from datetime import datetime

class TaskType(Enum):
    """Types of tasks the orchestrator can execute"""
    ANALYZE_SPEC = "analyze_spec"
    CREATE_STATE_MANAGER = "create_state_manager"
    CREATE_MODELS = "create_models"
    CREATE_REPOSITORIES = "create_repositories"
    CREATE_ENDPOINTS = "create_endpoints"
    CREATE_VALIDATORS = "create_validators"
    CREATE_MOCK_DATA = "create_mock_data"
    CREATE_RELATIONSHIPS = "create_relationships"
    CREATE_LIFECYCLE = "create_lifecycle"
    CREATE_TESTS = "create_tests"
    CREATE_SCENARIOS = "create_scenarios"
    FIX_ERRORS = "fix_errors"
    OPTIMIZE = "optimize"

class TaskStatus(Enum):
    """Status of individual tasks"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class ObjectRelationship:
    """Represents a relationship between objects"""
    from_object: str
    to_object: str
    relationship_type: str  # one-to-one, one-to-many, many-to-many
    field_name: str
    cascade_delete: bool = False
    nullable: bool = True

@dataclass
class ObjectLifecycle:
    """Represents the lifecycle of an object through API operations"""
    object_name: str
    create_endpoints: List[str]
    read_endpoints: List[str]
    update_endpoints: List[str]
    delete_endpoints: List[str]
    state_transitions: Dict[str, List[str]]  # status -> [possible_next_statuses]
    id_field: str = "id"
    soft_delete: bool = False

@dataclass
class APIOperation:
    """Represents an API operation and its effects on objects"""
    endpoint: str
    method: str
    creates: List[str]  # Object types created
    reads: List[str]    # Object types read
    updates: List[str]  # Object types updated
    deletes: List[str]  # Object types deleted
    requires: List[str] # Object types that must exist
    side_effects: List[Dict[str, Any]]  # Other operations triggered

@dataclass
class Task:
    """Represents a single task for Claude Code"""
    id: str
    type: TaskType
    prompt: str
    dependencies: List[str]
    context: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3

@dataclass
class APIComponent:
    """Represents a component of the API to be mocked"""
    name: str
    type: str  # model, endpoint, middleware, etc.
    spec: Dict[str, Any]
    dependencies: List[str]
    operations: List[APIOperation] = field(default_factory=list)
    relationships: List[ObjectRelationship] = field(default_factory=list)
    generated: bool = False
    file_path: Optional[str] = None

class ClaudeCodeExecutor:
    """Handles execution of Claude Code commands"""

    def __init__(self, project_dir: Path, model: str = "sonnet", verbose: bool = False, test_mode: bool = False):
        self.project_dir = project_dir
        self.model = model
        self.verbose = verbose
        self.test_mode = test_mode

    def execute(self, prompt: str, allow_edits: bool = True) -> Tuple[bool, str]:
        """Execute a Claude Code command and return success status and output"""

        if self.test_mode:
            # In test mode, just log the prompt and return success
            if self.verbose:
                print(f"TEST MODE: Would execute prompt: '{prompt[:100]}...'")
            return True, f"Test mode: Successfully processed prompt for {prompt.split()[0] if prompt else 'task'}"

        cmd = [
            "claude",
            "-p",
            "--model", self.model,
            "--output-format", "json"
        ]

        if allow_edits:
            cmd.extend(["--permission-mode", "acceptEdits"])

        # Add project directory access
        cmd.extend(["--add-dir", str(self.project_dir)])

        # Add the prompt
        cmd.append(prompt)

        try:
            if self.verbose:
                print(f"Executing: {' '.join(cmd[:6])}... '{prompt[:50]}...'")

            result = subprocess.run(
                cmd,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                try:
                    output = json.loads(result.stdout)
                    return True, output.get('content', result.stdout)
                except json.JSONDecodeError:
                    return True, result.stdout
            else:
                return False, result.stderr or "Command failed"

        except Exception as e:
            return False, f"Failed to execute command: {str(e)}"

class StateAnalyzer:
    """Analyzes API specs to understand stateful object relationships"""

    def __init__(self, spec_data: Dict[str, Any]):
        self.spec_data = spec_data
        self.objects: Dict[str, ObjectLifecycle] = {}
        self.relationships: List[ObjectRelationship] = []
        self.operations: List[APIOperation] = []

    def analyze_state_requirements(self) -> Tuple[Dict[str, ObjectLifecycle], List[ObjectRelationship], List[APIOperation]]:
        """Analyze the API spec to understand state management needs"""

        # Extract objects and their lifecycles
        self._extract_objects()

        # Analyze CRUD operations
        self._analyze_crud_operations()

        # Detect relationships between objects
        self._detect_relationships()

        # Analyze operation side effects
        self._analyze_side_effects()

        return self.objects, self.relationships, self.operations

    def _extract_objects(self):
        """Extract object types from schemas"""
        if 'components' in self.spec_data and 'schemas' in self.spec_data['components']:
            for name, schema in self.spec_data['components']['schemas'].items():
                # Skip enums and simple types
                if schema.get('type') == 'object' or 'properties' in schema:
                    self.objects[name] = ObjectLifecycle(
                        object_name=name,
                        create_endpoints=[],
                        read_endpoints=[],
                        update_endpoints=[],
                        delete_endpoints=[],
                        state_transitions={},
                        id_field=self._find_id_field(schema)
                    )

    def _find_id_field(self, schema: Dict) -> str:
        """Find the ID field in a schema"""
        props = schema.get('properties', {})
        for field_name in ['id', '_id', 'uuid', f"{schema.get('title', '').lower()}Id"]:
            if field_name in props:
                return field_name
        # Default to 'id'
        return 'id'

    def _analyze_crud_operations(self):
        """Analyze endpoints to determine CRUD operations"""
        if 'paths' not in self.spec_data:
            return

        for path, methods in self.spec_data['paths'].items():
            for method, spec in methods.items():
                if method not in ['get', 'post', 'put', 'patch', 'delete']:
                    continue

                operation = self._create_operation(path, method, spec)
                self.operations.append(operation)

                # Map to object lifecycles
                self._map_to_lifecycle(operation)

    def _create_operation(self, path: str, method: str, spec: Dict) -> APIOperation:
        """Create an APIOperation from endpoint spec"""
        operation = APIOperation(
            endpoint=path,
            method=method.upper(),
            creates=[],
            reads=[],
            updates=[],
            deletes=[],
            requires=[],
            side_effects=[]
        )

        # Analyze based on method and path patterns
        path_parts = path.strip('/').split('/')

        # Try to identify the resource
        resource = None
        for part in path_parts:
            if not part.startswith('{') and part not in ['api', 'v1', 'v2']:
                # Try to singularize to match schema names
                resource = part.rstrip('s').capitalize()
                if resource in self.objects:
                    break
                # Try plural form
                resource = part.capitalize()
                if resource in self.objects:
                    break

        if not resource:
            return operation

        # Determine operation type based on method
        if method == 'post':
            if '{' not in path:  # Collection endpoint
                operation.creates.append(resource)
            else:  # Might be an action endpoint
                operation.updates.append(resource)

        elif method == 'get':
            operation.reads.append(resource)

        elif method in ['put', 'patch']:
            operation.updates.append(resource)
            operation.requires.append(resource)

        elif method == 'delete':
            operation.deletes.append(resource)
            operation.requires.append(resource)

        # Analyze request/response schemas for more details
        self._analyze_schemas_for_objects(spec, operation)

        return operation

    def _analyze_schemas_for_objects(self, spec: Dict, operation: APIOperation):
        """Analyze request/response schemas to find object references"""
        # Check request body
        if 'requestBody' in spec:
            refs = self._find_schema_refs(spec['requestBody'])
            for ref in refs:
                obj_name = ref.split('/')[-1]
                if obj_name in self.objects and obj_name not in operation.creates:
                    if operation.method == 'POST':
                        operation.creates.append(obj_name)
                    elif operation.method in ['PUT', 'PATCH']:
                        operation.updates.append(obj_name)

        # Check responses
        if 'responses' in spec:
            for status, response in spec['responses'].items():
                if status.startswith('2'):  # Success responses
                    refs = self._find_schema_refs(response)
                    for ref in refs:
                        obj_name = ref.split('/')[-1]
                        if obj_name in self.objects and obj_name not in operation.reads:
                            operation.reads.append(obj_name)

    def _find_schema_refs(self, spec: Dict) -> List[str]:
        """Recursively find all $ref values in a spec"""
        refs = []
        if isinstance(spec, dict):
            if '$ref' in spec:
                refs.append(spec['$ref'])
            for value in spec.values():
                refs.extend(self._find_schema_refs(value))
        elif isinstance(spec, list):
            for item in spec:
                refs.extend(self._find_schema_refs(item))
        return refs

    def _map_to_lifecycle(self, operation: APIOperation):
        """Map operation to object lifecycles"""
        for obj_name in operation.creates:
            if obj_name in self.objects:
                self.objects[obj_name].create_endpoints.append(
                    f"{operation.method} {operation.endpoint}"
                )

        for obj_name in operation.reads:
            if obj_name in self.objects:
                self.objects[obj_name].read_endpoints.append(
                    f"{operation.method} {operation.endpoint}"
                )

        for obj_name in operation.updates:
            if obj_name in self.objects:
                self.objects[obj_name].update_endpoints.append(
                    f"{operation.method} {operation.endpoint}"
                )

        for obj_name in operation.deletes:
            if obj_name in self.objects:
                self.objects[obj_name].delete_endpoints.append(
                    f"{operation.method} {operation.endpoint}"
                )

    def _detect_relationships(self):
        """Detect relationships between objects based on schemas"""
        if 'components' not in self.spec_data or 'schemas' not in self.spec_data['components']:
            return

        for name, schema in self.spec_data['components']['schemas'].items():
            if name not in self.objects:
                continue

            props = schema.get('properties', {})
            for prop_name, prop_spec in props.items():
                # Check for references to other objects
                if '$ref' in prop_spec:
                    ref_obj = prop_spec['$ref'].split('/')[-1]
                    if ref_obj in self.objects:
                        self.relationships.append(ObjectRelationship(
                            from_object=name,
                            to_object=ref_obj,
                            relationship_type='many-to-one',
                            field_name=prop_name,
                            cascade_delete=False,
                            nullable=prop_name not in schema.get('required', [])
                        ))

                # Check for arrays of references
                elif prop_spec.get('type') == 'array' and 'items' in prop_spec:
                    if '$ref' in prop_spec['items']:
                        ref_obj = prop_spec['items']['$ref'].split('/')[-1]
                        if ref_obj in self.objects:
                            self.relationships.append(ObjectRelationship(
                                from_object=name,
                                to_object=ref_obj,
                                relationship_type='one-to-many',
                                field_name=prop_name,
                                cascade_delete=False,
                                nullable=True
                            ))

                # Check for ID references (e.g., userId, document_id)
                elif prop_name.endswith('Id') or prop_name.endswith('_id'):
                    # Try to guess the object name
                    possible_obj = prop_name.replace('Id', '').replace('_id', '')
                    possible_obj = possible_obj[0].upper() + possible_obj[1:]
                    if possible_obj in self.objects:
                        self.relationships.append(ObjectRelationship(
                            from_object=name,
                            to_object=possible_obj,
                            relationship_type='many-to-one',
                            field_name=prop_name,
                            cascade_delete=False,
                            nullable=prop_name not in schema.get('required', [])
                        ))

    def _analyze_side_effects(self):
        """Analyze potential side effects of operations"""
        # Look for webhook definitions, event triggers, etc.
        for operation in self.operations:
            # Example: Creating an order might trigger inventory update
            if 'Order' in operation.creates:
                operation.side_effects.append({
                    'trigger': 'create_order',
                    'effect': 'update_inventory',
                    'objects': ['Inventory', 'Product']
                })

            # Example: Deleting a user might cascade to their documents
            if 'User' in operation.deletes:
                for rel in self.relationships:
                    if rel.to_object == 'User' and rel.cascade_delete:
                        operation.side_effects.append({
                            'trigger': 'delete_user',
                            'effect': f'cascade_delete_{rel.from_object.lower()}',
                            'objects': [rel.from_object]
                        })

class APISpecAnalyzer:
    """Enhanced analyzer that understands stateful operations"""

    def __init__(self, spec_path: Path):
        self.spec_path = spec_path
        self.spec_data = None
        self.components = []
        self.state_analyzer = None
        self.lifecycles = {}
        self.relationships = []
        self.operations = []

    def load_spec(self) -> bool:
        """Load API specification from file"""
        try:
            with open(self.spec_path, 'r') as f:
                if self.spec_path.suffix in ['.yaml', '.yml']:
                    self.spec_data = yaml.safe_load(f)
                elif self.spec_path.suffix == '.json':
                    self.spec_data = json.load(f)
                else:
                    content = f.read()
                    self.spec_data = {"raw": content, "type": "text"}

            # Initialize state analyzer if we have structured data
            if isinstance(self.spec_data, dict) and 'openapi' in self.spec_data:
                self.state_analyzer = StateAnalyzer(self.spec_data)

            return True
        except Exception as e:
            print(f"Failed to load spec: {e}")
            return False

    def analyze(self) -> List[APIComponent]:
        """Analyze spec and extract components with state information"""
        if not self.spec_data:
            return []

        components = []

        # Perform state analysis first
        if self.state_analyzer:
            self.lifecycles, self.relationships, self.operations = \
                self.state_analyzer.analyze_state_requirements()

        # Handle OpenAPI/Swagger specs
        if isinstance(self.spec_data, dict):
            if 'openapi' in self.spec_data or 'swagger' in self.spec_data:
                components.extend(self._analyze_openapi())
            elif 'raw' in self.spec_data:
                components.extend(self._analyze_raw_text())

        return components

    def _analyze_openapi(self) -> List[APIComponent]:
        """Extract components from OpenAPI spec with state information"""
        components = []

        # Extract models/schemas with lifecycle info
        if 'components' in self.spec_data and 'schemas' in self.spec_data['components']:
            for name, schema in self.spec_data['components']['schemas'].items():
                component = APIComponent(
                    name=name,
                    type='model',
                    spec=schema,
                    dependencies=self._find_schema_deps(schema)
                )

                # Add lifecycle information
                if name in self.lifecycles:
                    component.spec['lifecycle'] = asdict(self.lifecycles[name])

                # Add relationships
                component.relationships = [r for r in self.relationships
                                         if r.from_object == name or r.to_object == name]

                components.append(component)

        # Extract endpoints with operation info
        if 'paths' in self.spec_data:
            for path, methods in self.spec_data['paths'].items():
                for method, spec in methods.items():
                    if method in ['get', 'post', 'put', 'delete', 'patch']:
                        component = APIComponent(
                            name=f"{method.upper()} {path}",
                            type='endpoint',
                            spec=spec,
                            dependencies=self._find_endpoint_deps(spec)
                        )

                        # Add operation information
                        matching_ops = [op for op in self.operations
                                      if op.endpoint == path and op.method == method.upper()]
                        if matching_ops:
                            component.operations = matching_ops

                        components.append(component)

        return components

    def _analyze_raw_text(self) -> List[APIComponent]:
        """Extract components from raw text documentation"""
        return [APIComponent(
            name="api_structure",
            type="analysis",
            spec={"raw": self.spec_data['raw']},
            dependencies=[]
        )]

    def _find_schema_deps(self, schema: Dict) -> List[str]:
        """Find dependencies in a schema"""
        deps = []
        if '$ref' in schema:
            deps.append(schema['$ref'].split('/')[-1])
        for value in schema.values():
            if isinstance(value, dict):
                deps.extend(self._find_schema_deps(value))
        return list(set(deps))

    def _find_endpoint_deps(self, spec: Dict) -> List[str]:
        """Find dependencies in an endpoint spec"""
        deps = []
        for key in ['requestBody', 'responses']:
            if key in spec:
                deps.extend(self._find_schema_deps(spec[key]))
        return list(set(deps))

class MockAPIOrchestrator:
    """Enhanced orchestrator with state management capabilities"""

    def __init__(self, spec_path: Path, output_dir: Path, config: Dict[str, Any]):
        self.spec_path = spec_path
        self.output_dir = output_dir
        self.config = config
        self.executor = ClaudeCodeExecutor(
            output_dir,
            model=config.get('model', 'sonnet'),
            verbose=config.get('verbose', False),
            test_mode=config.get('test_mode', False)
        )
        self.analyzer = APISpecAnalyzer(spec_path)
        self.tasks: List[Task] = []
        self.components: List[APIComponent] = []
        self.state_file = output_dir / '.orchestrator_state.json'

    def initialize_project(self):
        """Initialize the mock API project structure"""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Create enhanced project structure
        dirs = [
            'models',
            'endpoints',
            'middleware',
            'tests',
            'data',
            'validators',
            'state',        # State management
            'repositories', # Data access layer
            'events',       # Event handlers for side effects
            'scenarios'     # Test scenarios
        ]
        for dir_name in dirs:
            (self.output_dir / dir_name).mkdir(exist_ok=True)

        # Create initial files
        self._create_initial_files()

    def _create_initial_files(self):
        """Create initial project files with state management"""
        framework = self.config.get('framework', 'python-flask')

        if 'python' in framework:
            requirements = [
                "flask==2.3.0",
                "flask-restful==0.3.10",
                "flask-sqlalchemy==3.0.0",
                "marshmallow==3.20.0",
                "faker==20.0.0",
                "pytest==7.4.0",
                "pytest-flask==1.3.0",
                "pydantic==2.5.0",
                "redis==5.0.0",  # For state management
                "sqlalchemy==2.0.0"
            ]
            (self.output_dir / 'requirements.txt').write_text('\n'.join(requirements))

            # Create enhanced main app file
            app_content = '''"""
Mock API Server with State Management
Auto-generated by API Mock Generator
"""
from flask import Flask, g
from flask_restful import Api
from flask_sqlalchemy import SQLAlchemy
import redis
import json

app = Flask(__name__)
api = Api(app)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mock_state.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['REDIS_URL'] = 'redis://localhost:6379/0'

# Database for persistent state
db = SQLAlchemy(app)

# Redis for fast state access and caching
redis_client = redis.from_url(app.config.get('REDIS_URL', 'redis://localhost:6379/0'))

# Import state manager
from state.manager import StateManager
state_manager = StateManager(db, redis_client)

# Import repositories
from repositories import *

# Import endpoints (will be generated)
# from endpoints import *

@app.before_request
def before_request():
    """Initialize request context with state manager"""
    g.state = state_manager

@app.after_request
def after_request(response):
    """Commit any pending state changes"""
    if hasattr(g, 'state'):
        g.state.commit()
    return response

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
'''
            (self.output_dir / 'app.py').write_text(app_content)

            # Create state manager base
            state_manager_content = '''"""
State Manager for Mock API
Handles object lifecycle and relationships
"""
from typing import Dict, Any, List, Optional
import uuid
import json
from datetime import datetime

class StateManager:
    """Manages stateful objects across API operations"""
    
    def __init__(self, db, redis_client):
        self.db = db
        self.redis = redis_client
        self.repositories = {}
        self.pending_changes = []
        
    def create(self, object_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new object instance"""
        if 'id' not in data:
            data['id'] = str(uuid.uuid4())
        
        # Store in appropriate repository
        repo = self._get_repository(object_type)
        obj = repo.create(data)
        
        # Track for relationships and side effects
        self.pending_changes.append(('create', object_type, obj))
        
        # Cache in Redis for fast access
        self._cache_object(object_type, obj['id'], obj)
        
        return obj
    
    def read(self, object_type: str, object_id: str) -> Optional[Dict[str, Any]]:
        """Read an object by ID"""
        # Try cache first
        cached = self._get_cached_object(object_type, object_id)
        if cached:
            return cached
        
        # Fall back to repository
        repo = self._get_repository(object_type)
        obj = repo.get(object_id)
        
        if obj:
            self._cache_object(object_type, object_id, obj)
        
        return obj
    
    def update(self, object_type: str, object_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an existing object"""
        repo = self._get_repository(object_type)
        obj = repo.update(object_id, data)
        
        if obj:
            self.pending_changes.append(('update', object_type, obj))
            self._cache_object(object_type, object_id, obj)
        
        return obj
    
    def delete(self, object_type: str, object_id: str, cascade: bool = True) -> bool:
        """Delete an object, optionally cascading"""
        repo = self._get_repository(object_type)
        
        if cascade:
            # Handle cascade deletes based on relationships
            self._handle_cascade_delete(object_type, object_id)
        
        success = repo.delete(object_id)
        
        if success:
            self.pending_changes.append(('delete', object_type, object_id))
            self._remove_from_cache(object_type, object_id)
        
        return success
    
    def query(self, object_type: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Query objects with optional filters"""
        repo = self._get_repository(object_type)
        return repo.query(filters)
    
    def commit(self):
        """Process pending changes and trigger side effects"""
        for change_type, object_type, data in self.pending_changes:
            self._trigger_side_effects(change_type, object_type, data)
        
        self.pending_changes = []
        self.db.session.commit()
    
    def _get_repository(self, object_type: str):
        """Get or create repository for object type"""
        if object_type not in self.repositories:
            from repositories.base import BaseRepository
            self.repositories[object_type] = BaseRepository(object_type, self.db)
        return self.repositories[object_type]
    
    def _cache_object(self, object_type: str, object_id: str, obj: Dict[str, Any]):
        """Cache object in Redis"""
        key = f"{object_type}:{object_id}"
        self.redis.set(key, json.dumps(obj), ex=3600)  # 1 hour TTL
    
    def _get_cached_object(self, object_type: str, object_id: str) -> Optional[Dict[str, Any]]:
        """Get object from cache"""
        key = f"{object_type}:{object_id}"
        data = self.redis.get(key)
        return json.loads(data) if data else None
    
    def _remove_from_cache(self, object_type: str, object_id: str):
        """Remove object from cache"""
        key = f"{object_type}:{object_id}"
        self.redis.delete(key)
    
    def _handle_cascade_delete(self, object_type: str, object_id: str):
        """Handle cascade deletes based on relationships"""
        # This will be enhanced by the orchestrator based on detected relationships
        pass
    
    def _trigger_side_effects(self, change_type: str, object_type: str, data):
        """Trigger side effects for state changes"""
        # This will be enhanced based on detected side effects
        pass
'''
            (self.output_dir / 'state' / '__init__.py').write_text('')
            (self.output_dir / 'state' / 'manager.py').write_text(state_manager_content)

    def plan_tasks(self) -> List[Task]:
        """Create an enhanced task plan with state management"""
        tasks = []
        task_id = 0

        # Analyze spec if raw text
        if any(c.type == 'analysis' for c in self.components):
            tasks.append(Task(
                id=f"task_{task_id}",
                type=TaskType.ANALYZE_SPEC,
                prompt=self._generate_analysis_prompt(),
                dependencies=[],
                context={"spec_path": str(self.spec_path)}
            ))
            task_id += 1

        # Create state manager first
        state_task = Task(
            id=f"task_{task_id}",
            type=TaskType.CREATE_STATE_MANAGER,
            prompt=self._generate_state_manager_prompt(),
            dependencies=[],
            context={
                "lifecycles": {k: asdict(v) for k, v in self.analyzer.lifecycles.items()},
                "relationships": [asdict(r) for r in self.analyzer.relationships]
            }
        )
        tasks.append(state_task)
        task_id += 1

        # Create models with state awareness
        model_tasks = {}
        for component in self.components:
            if component.type == 'model':
                task = Task(
                    id=f"task_{task_id}",
                    type=TaskType.CREATE_MODELS,
                    prompt=self._generate_stateful_model_prompt(component),
                    dependencies=[state_task.id],
                    context={"component": asdict(component)}
                )
                tasks.append(task)
                model_tasks[component.name] = task.id
                task_id += 1

        # Create repositories for data access
        repo_task = None
        if model_tasks:
            repo_task = Task(
                id=f"task_{task_id}",
                type=TaskType.CREATE_REPOSITORIES,
                prompt=self._generate_repositories_prompt(),
                dependencies=list(model_tasks.values()),
                context={"models": list(model_tasks.keys())}
            )
            tasks.append(repo_task)
            task_id += 1

        # Create relationship handlers
        if self.analyzer.relationships and repo_task:
            rel_task = Task(
                id=f"task_{task_id}",
                type=TaskType.CREATE_RELATIONSHIPS,
                prompt=self._generate_relationships_prompt(),
                dependencies=[repo_task.id],
                context={"relationships": [asdict(r) for r in self.analyzer.relationships]}
            )
            tasks.append(rel_task)
            task_id += 1

        # Create endpoints with state management
        endpoint_tasks = []
        for component in self.components:
            if component.type == 'endpoint':
                deps = [model_tasks.get(dep, None) for dep in component.dependencies]
                deps = [d for d in deps if d]
                deps.append(state_task.id)  # All endpoints depend on state manager

                task = Task(
                    id=f"task_{task_id}",
                    type=TaskType.CREATE_ENDPOINTS,
                    prompt=self._generate_stateful_endpoint_prompt(component),
                    dependencies=deps,
                    context={"component": asdict(component),
                            "operations": [asdict(op) for op in component.operations]}
                )
                tasks.append(task)
                endpoint_tasks.append(task.id)
                task_id += 1

        # Create lifecycle handlers
        if self.analyzer.lifecycles:
            lifecycle_task = Task(
                id=f"task_{task_id}",
                type=TaskType.CREATE_LIFECYCLE,
                prompt=self._generate_lifecycle_prompt(),
                dependencies=endpoint_tasks,
                context={"lifecycles": {k: asdict(v) for k, v in self.analyzer.lifecycles.items()}}
            )
            tasks.append(lifecycle_task)
            task_id += 1

        # Create validators
        if model_tasks:
            tasks.append(Task(
                id=f"task_{task_id}",
                type=TaskType.CREATE_VALIDATORS,
                prompt=self._generate_validators_prompt(),
                dependencies=list(model_tasks.values()),
                context={"models": list(model_tasks.keys())}
            ))
            task_id += 1

        # Create mock data generators
        if model_tasks:
            tasks.append(Task(
                id=f"task_{task_id}",
                type=TaskType.CREATE_MOCK_DATA,
                prompt=self._generate_mock_data_prompt(),
                dependencies=list(model_tasks.values()),
                context={"models": list(model_tasks.keys()),
                        "relationships": [asdict(r) for r in self.analyzer.relationships]}
            ))
            task_id += 1

        # Create test scenarios
        if endpoint_tasks:
            tasks.append(Task(
                id=f"task_{task_id}",
                type=TaskType.CREATE_SCENARIOS,
                prompt=self._generate_scenarios_prompt(),
                dependencies=endpoint_tasks,
                context={"lifecycles": {k: asdict(v) for k, v in self.analyzer.lifecycles.items()},
                        "operations": [asdict(op) for op in self.analyzer.operations]}
            ))
            task_id += 1

        # Create comprehensive tests
        if endpoint_tasks:
            tasks.append(Task(
                id=f"task_{task_id}",
                type=TaskType.CREATE_TESTS,
                prompt=self._generate_stateful_tests_prompt(),
                dependencies=endpoint_tasks,
                context={"endpoints": [c.name for c in self.components if c.type == 'endpoint'],
                        "scenarios": True}
            ))
            task_id += 1

        return tasks

    def _generate_state_manager_prompt(self) -> str:
        """Generate prompt for creating state management system"""
        lifecycles = {k: asdict(v) for k, v in self.analyzer.lifecycles.items()}
        relationships = [asdict(r) for r in self.analyzer.relationships]

        return f"""Enhance the state manager in state/manager.py to handle these specific objects and relationships:

Objects to manage:
{json.dumps(lifecycles, indent=2)}

Relationships:
{json.dumps(relationships, indent=2)}

Requirements:
1. Implement proper cascade delete logic based on relationships
2. Add relationship validation (e.g., foreign key constraints)
3. Implement state transitions for objects with status fields
4. Add event triggers for side effects
5. Include transaction support for atomic operations
6. Add query methods for relationship traversal (e.g., get all documents for a user)
7. Implement soft delete where appropriate
8. Add audit logging for all state changes"""

    def _generate_stateful_model_prompt(self, component: APIComponent) -> str:
        """Generate prompt for creating a stateful model"""
        framework = self.config.get('framework', 'python-flask')
        lifecycle = component.spec.get('lifecycle', {})

        return f"""Create a stateful model for '{component.name}' in models/{component.name.lower()}.py.

Model specification: {json.dumps(component.spec, indent=2)}
Lifecycle: {json.dumps(lifecycle, indent=2)}
Relationships: {json.dumps([asdict(r) for r in component.relationships], indent=2)}

Requirements:
1. Create SQLAlchemy model with proper columns and types
2. Include relationship definitions for foreign keys
3. Add validation methods that check business rules
4. Include state transition methods if object has status
5. Add to_dict() and from_dict() serialization methods
6. Include mock data generation that respects relationships
7. Add lifecycle hooks (before_create, after_update, before_delete, etc.)
8. Include query helpers for common access patterns"""

    def _generate_repositories_prompt(self) -> str:
        """Generate prompt for creating repository pattern"""
        return """Create a repository layer in repositories/ directory:

1. Create repositories/base.py with BaseRepository class that provides:
   - Generic CRUD operations (create, read, update, delete)
   - Query builder interface
   - Pagination support
   - Filtering and sorting
   - Bulk operations
   - Transaction management

2. For each model, create a specific repository (e.g., repositories/user_repository.py) that:
   - Extends BaseRepository
   - Adds model-specific query methods
   - Implements complex business logic queries
   - Handles relationship loading (eager/lazy)
   - Provides aggregation queries

3. Create repositories/__init__.py that exports all repositories"""

    def _generate_relationships_prompt(self) -> str:
        """Generate prompt for relationship handlers"""
        relationships = [asdict(r) for r in self.analyzer.relationships]

        return f"""Create relationship management in state/relationships.py that handles:

Relationships to implement:
{json.dumps(relationships, indent=2)}

Requirements:
1. Enforce referential integrity
2. Handle cascade operations (delete, update)
3. Implement bi-directional relationship updates
4. Add methods to traverse relationships
5. Include validation for relationship constraints
6. Handle many-to-many relationships with junction tables
7. Implement lazy vs eager loading strategies
8. Add relationship-aware query builders"""

    def _generate_stateful_endpoint_prompt(self, component: APIComponent) -> str:
        """Generate prompt for creating a stateful endpoint"""
        framework = self.config.get('framework', 'python-flask')
        operations = component.operations[0] if component.operations else None

        return f"""Create a stateful endpoint for '{component.name}' in endpoints/{component.name.replace(' ', '_').replace('/', '_').lower()}.py.

Endpoint specification: {json.dumps(component.spec, indent=2)}
Operations: {json.dumps([asdict(op) for op in component.operations], indent=2) if component.operations else 'None'}

Requirements:
1. Use the state manager (g.state) for all data operations
2. Implement proper transaction handling
3. Validate relationships before operations
4. Handle cascade effects for deletes
5. Trigger appropriate side effects
6. Return proper status codes and error messages
7. Include pagination for list endpoints
8. Add filtering and sorting support
9. Implement optimistic locking for updates
10. Register the endpoint in app.py

Example structure:
```python
from flask import g, request, jsonify
from flask_restful import Resource

class {component.name.replace(' ', '').replace('/', '')}(Resource):
    def {component.name.split()[0].lower()}(self, *args, **kwargs):
        # Validate request
        # Use g.state for operations
        # Handle relationships
        # Return appropriate response
```"""

    def _generate_lifecycle_prompt(self) -> str:
        """Generate prompt for lifecycle management"""
        lifecycles = {k: asdict(v) for k, v in self.analyzer.lifecycles.items()}

        return f"""Create lifecycle handlers in state/lifecycle.py for managing object state transitions:

Lifecycles to implement:
{json.dumps(lifecycles, indent=2)}

Requirements:
1. Implement state transition validation
2. Create before/after hooks for each transition
3. Add business rule enforcement
4. Include audit trail for state changes
5. Handle concurrent state modifications
6. Implement state-specific behaviors
7. Add query methods for objects in specific states
8. Create state machine visualization helpers"""

    def _generate_mock_data_prompt(self) -> str:
        """Generate prompt for creating relationship-aware mock data"""
        models = [c.name for c in self.components if c.type == 'model']
        relationships = [asdict(r) for r in self.analyzer.relationships]

        return f"""Create sophisticated mock data generators in data/generators.py that:

Models to generate data for: {json.dumps(models, indent=2)}
Relationships to respect: {json.dumps(relationships, indent=2)}

Requirements:
1. Generate realistic fake data using Faker
2. Respect all relationship constraints
3. Create connected data graphs (e.g., users with their documents)
4. Support configurable data volumes
5. Include edge cases (null values, empty arrays, etc.)
6. Generate time-series data where appropriate
7. Create deterministic test data for scenarios
8. Support data generation profiles (minimal, normal, stress-test)
9. Include methods to reset and reseed data

Example:
```python
def generate_connected_data(num_users=10, docs_per_user=5):
    # Create users first
    # Then create documents linked to users
    # Respect all foreign key constraints
```"""

    def _generate_scenarios_prompt(self) -> str:
        """Generate prompt for creating test scenarios"""
        lifecycles = {k: asdict(v) for k, v in self.analyzer.lifecycles.items()}
        operations = [asdict(op) for op in self.analyzer.operations]

        return f"""Create comprehensive test scenarios in scenarios/ directory that simulate real usage:

Lifecycles: {json.dumps(lifecycles, indent=2)}
Operations: {json.dumps(operations, indent=2)}

Create these scenario files:
1. scenarios/basic_crud.py - Test all CRUD operations with state persistence
2. scenarios/relationships.py - Test relationship integrity and cascades
3. scenarios/concurrent.py - Test concurrent modifications
4. scenarios/lifecycle.py - Test complete object lifecycles
5. scenarios/edge_cases.py - Test error conditions and edge cases

Each scenario should:
- Set up initial state
- Execute a series of operations
- Verify state consistency
- Test side effects
- Clean up after completion

Example scenario:
```python
def test_document_lifecycle():
    # Create user
    user = create_user({{"name": "Test User"}})
    
    # Create document for user
    doc = create_document({{"title": "Test", "userId": user["id"]}})
    
    # Verify relationship
    user_docs = get_user_documents(user["id"])
    assert doc["id"] in [d["id"] for d in user_docs]
    
    # Delete user and verify cascade
    delete_user(user["id"])
    assert get_document(doc["id"]) is None
```"""

    def _generate_stateful_tests_prompt(self) -> str:
        """Generate prompt for comprehensive stateful tests"""
        endpoints = [c.name for c in self.components if c.type == 'endpoint']

        return f"""Create comprehensive stateful tests in tests/ directory:

Endpoints to test: {json.dumps(endpoints, indent=2)}

Test files to create:
1. tests/test_state_persistence.py - Verify state persists across requests
2. tests/test_relationships.py - Test all relationship operations
3. tests/test_transactions.py - Test transaction rollback on errors
4. tests/test_concurrency.py - Test race conditions and locks
5. tests/test_lifecycle.py - Test complete object lifecycles
6. tests/test_side_effects.py - Verify side effects trigger correctly
7. tests/test_validation.py - Test all validation rules
8. tests/test_performance.py - Measure response times with state

Include:
- Setup and teardown for clean state
- Helper methods for common operations
- Assertions for state consistency
- Tests for error conditions
- Integration tests across multiple endpoints

Use pytest fixtures for state management:
```python
@pytest.fixture
def clean_state():
    # Reset database
    # Clear cache
    # Return fresh state manager
```"""

    def _generate_analysis_prompt(self) -> str:
        """Generate prompt for analyzing raw API documentation"""
        return f"""Analyze the API documentation in {self.spec_path} and create a structured 
        analysis that identifies stateful operations:
        
        1. Identify all objects/resources and their properties
        2. Map CRUD operations to endpoints
        3. Detect relationships between objects (foreign keys, references)
        4. Identify lifecycle patterns (create -> update -> delete)
        5. Find side effects and triggers
        6. Detect authentication and authorization patterns
        7. Identify business rules and constraints
        
        Save as analysis/api_structure.json with sections for:
        - objects (with properties and types)
        - endpoints (with operations and effects)
        - relationships (with cardinality and constraints)
        - lifecycles (with state transitions)
        - side_effects (with triggers and impacts)"""

    def _generate_validators_prompt(self) -> str:
        """Generate prompt for creating validators"""
        return """Create comprehensive validators in validators/validate.py that:
        1. Validate schema compliance
        2. Check relationship constraints
        3. Enforce business rules
        4. Validate state transitions
        5. Check for circular dependencies
        6. Validate bulk operations
        7. Include custom validation decorators"""

    def execute_tasks(self) -> Dict[str, Any]:
        """Execute all planned tasks"""
        results = {
            "total": len(self.tasks),
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "tasks": []
        }

        # Load previous state if exists
        self._load_state()

        for task in self.tasks:
            if task.status == TaskStatus.COMPLETED:
                results["completed"] += 1
                continue

            # Check dependencies
            if not self._dependencies_met(task):
                task.status = TaskStatus.SKIPPED
                task.error = "Dependencies not met"
                results["skipped"] += 1
                continue

            # Execute task
            print(f"\nExecuting task {task.id}: {task.type.value}")
            task.status = TaskStatus.IN_PROGRESS
            self._save_state()

            # Add context to prompt
            prompt = task.prompt
            if task.context:
                prompt = prompt.replace("context=", f"context={json.dumps(task.context, indent=2)}")

            while task.attempts < task.max_attempts:
                task.attempts += 1
                success, output = self.executor.execute(prompt)

                if success:
                    task.status = TaskStatus.COMPLETED
                    task.result = output
                    results["completed"] += 1
                    print(f"✓ Task {task.id} completed")
                    break
                else:
                    task.error = output
                    if task.attempts >= task.max_attempts:
                        task.status = TaskStatus.FAILED
                        results["failed"] += 1
                        print(f"✗ Task {task.id} failed: {output}")
                    else:
                        print(f"⚠ Task {task.id} attempt {task.attempts} failed, retrying...")
                        time.sleep(2)

            results["tasks"].append({
                "id": task.id,
                "type": task.type.value,
                "status": task.status.value,
                "attempts": task.attempts
            })

            self._save_state()

        return results

    def _dependencies_met(self, task: Task) -> bool:
        """Check if all dependencies for a task are completed"""
        for dep_id in task.dependencies:
            dep_task = next((t for t in self.tasks if t.id == dep_id), None)
            if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                return False
        return True

    def _save_state(self):
        """Save current orchestration state"""
        state = {
            "timestamp": datetime.now().isoformat(),
            "tasks": [asdict(t) for t in self.tasks]
        }
        self.state_file.write_text(json.dumps(state, indent=2, default=str))

    def _load_state(self):
        """Load previous orchestration state if exists"""
        if self.state_file.exists():
            try:
                state = json.loads(self.state_file.read_text())
                for task_data in state.get("tasks", []):
                    task = next((t for t in self.tasks if t.id == task_data["id"]), None)
                    if task:
                        task.status = TaskStatus(task_data["status"])
                        task.result = task_data.get("result")
                        task.error = task_data.get("error")
                        task.attempts = task_data.get("attempts", 0)
            except Exception as e:
                print(f"Warning: Could not load previous state: {e}")

    def validate_mock_api(self) -> Dict[str, Any]:
        """Run validation tests against the generated mock API"""
        print("\nValidating generated mock API...")

        validation_prompt = """Test the stateful mock API:
        1. Run all tests in tests/ directory
        2. Execute all scenarios in scenarios/ directory
        3. Verify state persistence across server restarts
        4. Test relationship integrity
        5. Validate cascade operations
        6. Check side effect triggers
        7. Measure performance with populated state
        8. Create validation_report.json with results"""

        success, output = self.executor.execute(validation_prompt)

        if success:
            print("✓ Validation completed")
            return {"status": "success", "output": output}
        else:
            print("✗ Validation failed")
            return {"status": "failed", "error": output}

    def compare_with_real_api(self, real_api_url: Optional[str] = None) -> Dict[str, Any]:
        """Compare mock API with real API including state behavior"""
        if not real_api_url:
            return {"status": "skipped", "reason": "No real API URL provided"}

        comparison_prompt = f"""Create stateful comparison tests in tests/comparison.py:
        
        1. Execute identical operation sequences on both APIs
        2. Compare not just responses but state persistence
        3. Test CRUD cycles (create, read, update, delete)
        4. Verify relationship handling matches
        5. Compare error responses for invalid operations
        6. Test pagination and filtering
        7. Measure response time differences
        8. Generate compatibility score
        
        Real API: {real_api_url}
        Mock API: http://localhost:5000
        
        Save detailed results to comparison_report.json"""

        success, output = self.executor.execute(comparison_prompt)

        return {
            "status": "success" if success else "failed",
            "output": output if success else None,
            "error": None if success else output
        }

    def run(self) -> Dict[str, Any]:
        """Run the complete orchestration process"""
        print("Starting Stateful Mock API Generation")
        print(f"Spec: {self.spec_path}")
        print(f"Output: {self.output_dir}")
        print("-" * 50)

        # Initialize project
        print("\n1. Initializing project structure...")
        self.initialize_project()

        # Load and analyze spec
        print("\n2. Loading API specification...")
        if not self.analyzer.load_spec():
            return {"status": "failed", "error": "Could not load API specification"}

        print("\n3. Analyzing API components and state requirements...")
        self.components = self.analyzer.analyze()
        print(f"Found {len(self.components)} components")
        print(f"Found {len(self.analyzer.lifecycles)} stateful objects")
        print(f"Found {len(self.analyzer.relationships)} relationships")
        print(f"Found {len(self.analyzer.operations)} operations")

        # Plan tasks
        print("\n4. Planning generation tasks...")
        self.tasks = self.plan_tasks()
        print(f"Created {len(self.tasks)} tasks")

        # Execute tasks
        print("\n5. Executing generation tasks...")
        execution_results = self.execute_tasks()

        # Validate
        print("\n6. Validating stateful mock API...")
        validation_results = self.validate_mock_api()

        # Compare with real API if configured
        comparison_results = None
        if self.config.get('real_api_url'):
            print("\n7. Comparing with real API...")
            comparison_results = self.compare_with_real_api(self.config.get('real_api_url'))

        # Generate final report
        report = {
            "timestamp": datetime.now().isoformat(),
            "spec_path": str(self.spec_path),
            "output_dir": str(self.output_dir),
            "analysis": {
                "components": len(self.components),
                "stateful_objects": len(self.analyzer.lifecycles),
                "relationships": len(self.analyzer.relationships),
                "operations": len(self.analyzer.operations)
            },
            "tasks": execution_results,
            "validation": validation_results,
            "comparison": comparison_results,
            "status": "success" if execution_results["failed"] == 0 else "partial"
        }

        report_path = self.output_dir / 'generation_report.json'
        report_path.write_text(json.dumps(report, indent=2))

        print("\n" + "=" * 50)
        print("Stateful Mock API Generation Complete!")
        print(f"Tasks: {execution_results['completed']}/{execution_results['total']} completed")
        print(f"Report saved to: {report_path}")

        return report

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Automated Stateful Mock API Generator")
    parser.add_argument("spec", type=Path, help="Path to API specification file")
    parser.add_argument("-o", "--output", type=Path, default=Path("./mock_api"),
                      help="Output directory for generated mock API")
    parser.add_argument("-f", "--framework", default="python-flask",
                      choices=["python-flask", "python-fastapi", "node-express"],
                      help="Framework to use for mock API")
    parser.add_argument("-m", "--model", default="sonnet",
                      help="Claude model to use (sonnet, opus, etc.)")
    parser.add_argument("--real-api-url", help="Real API URL for comparison testing")
    parser.add_argument("-v", "--verbose", action="store_true",
                      help="Enable verbose output")
    parser.add_argument("--continue", dest="continue_run", action="store_true",
                      help="Continue from previous state if exists")
    parser.add_argument("--state-backend", default="sqlite",
                      choices=["sqlite", "postgres", "memory"],
                      help="Backend for state storage")
    parser.add_argument("--test-mode", action="store_true",
                      help="Run in test mode without executing Claude Code commands")

    args = parser.parse_args()

    if not args.spec.exists():
        print(f"Error: Spec file {args.spec} not found")
        sys.exit(1)

    config = {
        "framework": args.framework,
        "model": args.model,
        "real_api_url": args.real_api_url,
        "verbose": args.verbose,
        "state_backend": args.state_backend,
        "test_mode": args.test_mode
    }

    # Clean output directory unless continuing
    if not args.continue_run and args.output.exists():
        print(f"Output directory {args.output} exists. Remove it? [y/N]: ", end="")
        if input().lower() == 'y':
            shutil.rmtree(args.output)

    orchestrator = MockAPIOrchestrator(args.spec, args.output, config)
    report = orchestrator.run()

    sys.exit(0 if report.get("status") == "success" else 1)

if __name__ == "__main__":
    main()
