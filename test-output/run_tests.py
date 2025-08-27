#!/usr/bin/env python3
"""
Test runner script for the Slack API Mock Server test suite.
Provides different test execution modes and reporting options.
"""

import os
import sys
import argparse
import subprocess
from typing import List, Optional


def run_command(cmd: List[str], description: str) -> int:
    """Run a command and return its exit code"""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print('='*60)
    
    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except Exception as e:
        print(f"Error running command: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(description="Run Slack API Mock Server tests")
    
    # Test selection options
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")  
    parser.add_argument("--scenario", action="store_true", help="Run scenario tests only")
    parser.add_argument("--performance", action="store_true", help="Run performance tests only")
    parser.add_argument("--all", action="store_true", help="Run all tests (default)")
    
    # Test execution options
    parser.add_argument("--parallel", action="store_true", help="Run tests in parallel")
    parser.add_argument("--slow", action="store_true", help="Include slow tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet output")
    
    # Coverage options
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--cov-html", action="store_true", help="Generate HTML coverage report")
    parser.add_argument("--cov-fail-under", type=int, default=80, help="Minimum coverage percentage")
    
    # Output options
    parser.add_argument("--junit-xml", help="Generate JUnit XML report")
    parser.add_argument("--html-report", help="Generate HTML test report")
    
    # Filtering options  
    parser.add_argument("--filter", "-k", help="Filter tests by name pattern")
    parser.add_argument("--file", help="Run specific test file")
    
    # Other options
    parser.add_argument("--install-deps", action="store_true", help="Install dependencies first")
    parser.add_argument("--dry-run", action="store_true", help="Show commands without executing")
    
    args = parser.parse_args()
    
    # Install dependencies if requested
    if args.install_deps:
        install_cmd = [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
        if args.dry_run:
            print(f"Would run: {' '.join(install_cmd)}")
        else:
            if run_command(install_cmd, "Installing dependencies") != 0:
                print("Failed to install dependencies")
                return 1
    
    # Build pytest command
    cmd = [sys.executable, "-m", "pytest"]
    
    # Add verbosity options
    if args.verbose:
        cmd.append("-v")
    elif args.quiet:
        cmd.append("-q")
    
    # Add test selection markers
    markers = []
    if args.unit:
        markers.append("unit")
    if args.integration:
        markers.append("integration") 
    if args.scenario:
        markers.append("scenario")
    if args.performance:
        markers.append("performance")
    
    if markers:
        marker_expr = " or ".join(markers)
        cmd.extend(["-m", marker_expr])
    elif not args.all:
        # Default: run all except slow tests
        if not args.slow:
            cmd.extend(["-m", "not slow"])
    
    # Add parallel execution
    if args.parallel:
        cmd.extend(["-n", "auto"])
    
    # Add filtering
    if args.filter:
        cmd.extend(["-k", args.filter])
    
    # Add specific file
    if args.file:
        cmd.append(args.file)
    
    # Add coverage options
    if args.coverage or args.cov_html:
        cmd.extend(["--cov=server", "--cov=data"])
        cmd.extend(["--cov-report=term-missing"])
        cmd.extend([f"--cov-fail-under={args.cov_fail_under}"])
        
        if args.cov_html:
            cmd.append("--cov-report=html")
    
    # Add output formats
    if args.junit_xml:
        cmd.extend([f"--junit-xml={args.junit_xml}"])
        
    if args.html_report:
        cmd.extend([f"--html={args.html_report}"])
    
    # Show or run the command
    if args.dry_run:
        print(f"Would run: {' '.join(cmd)}")
        return 0
    else:
        return run_command(cmd, "Running tests")


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)