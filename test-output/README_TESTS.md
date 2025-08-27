# Slack API Mock Server - Test Suite

This directory contains a comprehensive test suite for the Slack Events API Mock Server. The tests verify that the simulation behaves identically to how the real Slack API would work.

## Test Structure

### 1. `test_api.py` - Core API Tests
Comprehensive tests for all API endpoints including:

- **Health and Authentication Tests**
  - Health check endpoint (`/health`)
  - API connectivity test (`/api/test`)
  - Authentication success and failure scenarios
  - Token validation

- **Events API Tests**
  - URL verification challenges
  - Event callbacks (messages, reactions, member joins/leaves)
  - Error handling for invalid payloads

- **Conversations API Tests**
  - List conversations with pagination and filtering
  - Get conversation info and history
  - Message threading and reactions in history
  - Authentication requirements

- **Chat API Tests**
  - Post messages (including thread replies)
  - Update and delete messages
  - Error handling for missing/invalid parameters

- **Reactions API Tests**
  - Add and remove reactions
  - Duplicate reaction handling
  - Message not found scenarios

- **Users API Tests**
  - List users with pagination
  - Get individual user info
  - Profile data validation

- **Team API Tests**
  - Team information retrieval

- **Error Handling Tests**
  - 404 and 405 error handlers
  - Malformed JSON handling
  - Missing authentication

- **Data Persistence Tests**
  - Message persistence across requests
  - Reaction persistence in message history
  - Thread reply count maintenance

### 2. `test_scenarios.py` - Realistic Usage Scenarios
Complex, multi-step workflow tests including:

- **New Employee Onboarding**
  - Welcome messages and team introductions
  - Channel invitations and Q&A threads
  - Multi-channel interaction flows

- **Project Discussion Workflow**
  - Project kickoffs and planning discussions
  - Threaded conversations with action items
  - Cross-team coordination

- **Crisis Management Workflow**
  - Production incident response
  - Real-time collaboration during outages
  - Post-incident communication

- **Celebration Workflows**
  - Milestone announcements with reactions
  - Team celebration coordination
  - Positive team interactions

- **Complex Threading Tests**
  - Multi-threaded parallel discussions
  - Cross-thread references
  - High-volume conversation handling

- **Performance Scenarios**
  - High-volume conversations (50+ messages)
  - Multiple reactions per message
  - Concurrent multi-channel activity
  - Pagination with large datasets

### 3. `conftest.py` - Test Infrastructure
Shared pytest fixtures and utilities:

- **Database Management**
  - Temporary test databases
  - Clean database state per test
  - Session management

- **Sample Data Fixtures**
  - Realistic workspace setups
  - Teams, users, channels, and memberships
  - Message and reaction helpers

- **Authentication Helpers**
  - Multi-user authentication scenarios
  - Different token types

- **Utility Functions**
  - Message posting helpers
  - Reaction management
  - Conversation retrieval
  - Performance timing utilities
  - Response validation functions

## Running Tests

### Prerequisites
```bash
# Install dependencies
pip install -r requirements.txt
```

### Basic Test Execution

```bash
# Run all tests
python run_tests.py --all

# Run specific test categories
python run_tests.py --unit          # Unit tests only
python run_tests.py --integration   # Integration tests only  
python run_tests.py --scenario      # Scenario tests only
python run_tests.py --performance   # Performance tests only

# Run with coverage
python run_tests.py --coverage --cov-html

# Run specific test file
python run_tests.py --file test_api.py

# Run tests matching pattern
python run_tests.py --filter "test_message"
```

### Advanced Options

```bash
# Parallel execution
python run_tests.py --parallel

# Include slow tests
python run_tests.py --slow

# Generate reports
python run_tests.py --junit-xml results.xml --html-report report.html

# Verbose output
python run_tests.py --verbose

# Dry run (show commands without executing)
python run_tests.py --dry-run --coverage
```

### Direct pytest Usage

```bash
# Basic test run
pytest -v

# Run with coverage
pytest --cov=server --cov=data --cov-report=html --cov-report=term-missing

# Run specific markers
pytest -m "not slow"
pytest -m "scenario"
pytest -m "performance"

# Run specific tests
pytest test_api.py::TestChatAPI::test_chat_post_message
pytest -k "message and not thread"
```

## Test Categories and Markers

Tests are categorized using pytest markers:

- `@pytest.mark.unit` - Fast, isolated unit tests
- `@pytest.mark.integration` - Integration tests with database
- `@pytest.mark.scenario` - Complex workflow scenarios  
- `@pytest.mark.performance` - Performance and load tests
- `@pytest.mark.slow` - Slow-running tests

## Test Data and Isolation

- Each test gets a clean, temporary database
- Sample data is created using realistic Slack IDs and formats
- Tests are isolated and can run in any order
- Database cleanup is automatic

## Coverage Goals

- **Minimum Coverage**: 80%
- **Target Areas**:
  - All API endpoints
  - Error handling paths
  - Database operations
  - Authentication flows
  - Message threading logic
  - Reaction management

## Performance Benchmarks

Performance tests establish baselines for:

- **Message Volume**: Handle 100+ messages per channel
- **Concurrent Users**: Support multiple simultaneous API calls
- **Pagination**: Efficiently handle large result sets
- **Database Operations**: Sub-second response times
- **Memory Usage**: Stable memory consumption

## Continuous Integration

The test suite is designed for CI/CD integration:

```yaml
# Example GitHub Actions
- name: Run Tests
  run: |
    pip install -r requirements.txt
    python run_tests.py --all --coverage --junit-xml results.xml
    
- name: Upload Coverage
  uses: codecov/codecov-action@v1
  with:
    file: ./coverage.xml
```

## Adding New Tests

When adding new functionality:

1. **Add unit tests** in `test_api.py` for new endpoints
2. **Add scenario tests** in `test_scenarios.py` for workflows  
3. **Update fixtures** in `conftest.py` if needed
4. **Use appropriate markers** for test categorization
5. **Follow naming conventions** (`test_*` functions)
6. **Include error cases** and edge conditions

## Test Design Principles

- **Realistic Data**: Use authentic Slack formats and IDs
- **Complete Workflows**: Test entire user journeys
- **Error Coverage**: Test both success and failure paths  
- **Performance Awareness**: Include load and stress tests
- **Maintainability**: Clear, readable test code
- **Isolation**: No test dependencies or side effects

## Troubleshooting

### Common Issues

1. **Database Lock Errors**: Ensure tests clean up properly
2. **Authentication Failures**: Check token formats in conftest.py
3. **Timeout Issues**: Increase timeout for slow tests
4. **Import Errors**: Verify PYTHONPATH includes test directory

### Debug Commands

```bash
# Run single test with full output
pytest -v -s test_api.py::TestChatAPI::test_chat_post_message

# Debug database issues
pytest --pdb test_api.py -k "database"

# Capture logs
pytest --log-cli-level=DEBUG
```

This comprehensive test suite ensures the Slack API simulation provides reliable, authentic behavior that matches real Slack API responses and workflows.