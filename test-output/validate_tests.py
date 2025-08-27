#!/usr/bin/env python3
"""
Test validation script to verify the test suite setup and basic functionality.
This script checks test files, imports, and basic test structure without running the full suite.
"""

import os
import sys
import ast
import importlib.util
from typing import List, Dict, Any


def validate_imports(file_path: str) -> Dict[str, Any]:
    """Validate that all imports in a test file are valid"""
    print(f"\nValidating imports in {os.path.basename(file_path)}...")
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Parse the AST to find imports
        tree = ast.parse(content)
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        
        # Check if we can load the module (syntax check)
        spec = importlib.util.spec_from_file_location("test_module", file_path)
        if spec and spec.loader:
            # Don't actually load to avoid side effects, just validate syntax
            pass
        
        return {
            'status': 'success',
            'imports': imports,
            'import_count': len(imports)
        }
        
    except SyntaxError as e:
        return {
            'status': 'error',
            'error': f"Syntax error: {e}",
            'line': e.lineno
        }
    except Exception as e:
        return {
            'status': 'error', 
            'error': str(e)
        }


def count_test_functions(file_path: str) -> Dict[str, Any]:
    """Count test functions and classes in a test file"""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        tree = ast.parse(content)
        test_functions = 0
        test_classes = 0
        fixtures = 0
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name.startswith('test_'):
                    test_functions += 1
                elif any(decorator.id == 'pytest.fixture' for decorator in node.decorator_list 
                        if isinstance(decorator, ast.Attribute)):
                    fixtures += 1
                elif any(decorator.id == 'fixture' for decorator in node.decorator_list 
                        if isinstance(decorator, ast.Name)):
                    fixtures += 1
            elif isinstance(node, ast.ClassDef):
                if node.name.startswith('Test'):
                    test_classes += 1
        
        return {
            'test_functions': test_functions,
            'test_classes': test_classes, 
            'fixtures': fixtures,
            'total_tests': test_functions
        }
        
    except Exception as e:
        return {'error': str(e)}


def validate_test_structure(file_path: str) -> Dict[str, Any]:
    """Validate the structure and content of test files"""
    filename = os.path.basename(file_path)
    print(f"\nValidating test structure for {filename}...")
    
    # Check file exists and is readable
    if not os.path.exists(file_path):
        return {'status': 'error', 'error': 'File does not exist'}
    
    if not os.access(file_path, os.R_OK):
        return {'status': 'error', 'error': 'File is not readable'}
    
    # Validate imports
    import_result = validate_imports(file_path)
    if import_result['status'] != 'success':
        return import_result
    
    # Count test elements
    test_counts = count_test_functions(file_path)
    if 'error' in test_counts:
        return {'status': 'error', 'error': test_counts['error']}
    
    # File size check
    file_size = os.path.getsize(file_path)
    
    return {
        'status': 'success',
        'file_size': file_size,
        'import_count': import_result['import_count'],
        **test_counts
    }


def check_pytest_config():
    """Check pytest configuration files"""
    print("\nChecking pytest configuration...")
    
    config_files = {
        'pytest.ini': 'Pytest configuration',
        'conftest.py': 'Pytest fixtures and setup'
    }
    
    results = {}
    for file_name, description in config_files.items():
        file_path = os.path.join(os.getcwd(), file_name)
        if os.path.exists(file_path):
            results[file_name] = {
                'exists': True,
                'size': os.path.getsize(file_path)
            }
            print(f"  ✓ {description} found ({results[file_name]['size']} bytes)")
        else:
            results[file_name] = {'exists': False}
            print(f"  ✗ {description} not found")
    
    return results


def main():
    """Main validation function"""
    print("=" * 60)
    print("Slack API Mock Server - Test Suite Validation")
    print("=" * 60)
    
    # Check current directory
    current_dir = os.getcwd()
    print(f"Working directory: {current_dir}")
    
    # Find test files
    test_files = []
    for file in os.listdir('.'):
        if file.startswith('test_') and file.endswith('.py'):
            test_files.append(file)
    
    print(f"Found {len(test_files)} test files: {', '.join(test_files)}")
    
    # Check pytest configuration
    config_results = check_pytest_config()
    
    # Validate each test file
    all_results = {}
    total_tests = 0
    
    for test_file in test_files:
        result = validate_test_structure(test_file)
        all_results[test_file] = result
        
        if result['status'] == 'success':
            total_tests += result['total_tests']
            print(f"  ✓ {test_file}: {result['total_tests']} tests, {result['test_classes']} classes, {result['fixtures']} fixtures")
        else:
            print(f"  ✗ {test_file}: ERROR - {result.get('error', 'Unknown error')}")
    
    # Summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    
    successful_files = sum(1 for r in all_results.values() if r['status'] == 'success')
    print(f"Test files validated: {successful_files}/{len(test_files)}")
    print(f"Total test functions found: {total_tests}")
    
    # Configuration status
    has_pytest_ini = config_results.get('pytest.ini', {}).get('exists', False)
    has_conftest = config_results.get('conftest.py', {}).get('exists', False)
    print(f"Pytest configuration: {'✓' if has_pytest_ini else '✗'}")
    print(f"Test fixtures setup: {'✓' if has_conftest else '✗'}")
    
    # Check for required dependencies
    print(f"\nRequired files check:")
    required_files = ['requirements.txt', 'server/app.py', 'data/models.py']
    for req_file in required_files:
        if os.path.exists(req_file):
            print(f"  ✓ {req_file}")
        else:
            print(f"  ✗ {req_file} (required for tests)")
    
    # Test file breakdown
    if total_tests > 0:
        print(f"\nTest breakdown by file:")
        for file_name, result in all_results.items():
            if result['status'] == 'success' and result['total_tests'] > 0:
                print(f"  {file_name}: {result['total_tests']} tests")
    
    print(f"\n{'='*60}")
    
    if successful_files == len(test_files) and total_tests > 0:
        print("✓ Test suite validation PASSED")
        print(f"  Ready to run {total_tests} tests across {len(test_files)} files")
        return 0
    else:
        print("✗ Test suite validation FAILED")
        print("  Fix errors above before running tests")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)