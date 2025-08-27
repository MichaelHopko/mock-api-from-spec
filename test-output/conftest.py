#!/usr/bin/env python3
"""
Pytest configuration and shared fixtures for the Slack API Mock Server tests.
Provides database management, test data setup, and utility functions.
"""

import os
import sys
import pytest
import tempfile
import shutil
import uuid
from datetime import datetime
from typing import Dict, Any, Generator

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.app import app, initialize_app
from data.database import db_manager, init_database, check_database_health
from data.models import (
    Team, App, User, Channel, ChannelMembership, Message, Reaction, 
    GenericEventWrapper, EventAuthedUser, Base
)

# Test configuration constants
TEST_DATABASE_PREFIX = "test_slack_api_"
TEST_TOKENS = {
    "admin": "xoxb-admin-token-123456789",
    "user1": "xoxb-user1-token-123456789",
    "user2": "xoxb-user2-token-123456789", 
    "user3": "xoxb-user3-token-123456789",
    "bot": "xoxb-bot-token-123456789"
}

# Pytest configuration
pytest_plugins = []


def pytest_configure(config):
    """Configure pytest with custom markers and settings"""
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "scenario: mark test as scenario test")
    config.addinivalue_line("markers", "performance: mark test as performance test")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test names and modules"""
    for item in items:
        # Add markers based on test file names
        if "scenario" in str(item.fspath):
            item.add_marker(pytest.mark.scenario)
        if "performance" in item.name.lower():
            item.add_marker(pytest.mark.performance)
        if "integration" in item.name.lower():
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def temp_dir():
    """Create a temporary directory for the test session"""
    temp_path = tempfile.mkdtemp(prefix=TEST_DATABASE_PREFIX)
    yield temp_path
    # Cleanup
    try:
        shutil.rmtree(temp_path)
    except Exception as e:
        print(f"Warning: Could not remove temp directory {temp_path}: {e}")


@pytest.fixture(scope="session")
def test_database_url(temp_dir):
    """Create a unique test database URL for the session"""
    db_path = os.path.join(temp_dir, "test_slack_api.db")
    return f"sqlite:///{db_path}"


@pytest.fixture(scope="session", autouse=True)
def setup_test_database(test_database_url):
    """Set up the test database for the entire session"""
    # Store original database URL
    original_db_url = getattr(db_manager, 'database_url', None)
    
    # Set test database URL
    db_manager.database_url = test_database_url
    
    try:
        # Initialize database
        init_database()
        
        # Verify database health
        assert check_database_health(), "Test database health check failed"
        
        yield test_database_url
        
    finally:
        # Restore original database URL
        if original_db_url:
            db_manager.database_url = original_db_url


@pytest.fixture(scope="session")
def flask_app(setup_test_database):
    """Create and configure Flask app for testing"""
    app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key'
    })
    
    # Initialize the app
    with app.app_context():
        yield app


@pytest.fixture(scope="function")
def client(flask_app):
    """Create a test client for each test"""
    with flask_app.test_client() as test_client:
        with flask_app.app_context():
            yield test_client


@pytest.fixture(scope="function")
def db_session(flask_app):
    """Provide a database session for each test with automatic cleanup"""
    with flask_app.app_context():
        session = db_manager.session_factory()
        try:
            yield session
        finally:
            session.rollback()
            session.close()


@pytest.fixture(scope="function")
def clean_database(db_session):
    """Clean database before each test to ensure test isolation"""
    # Delete all data in reverse order of dependencies
    db_session.query(EventAuthedUser).delete()
    db_session.query(GenericEventWrapper).delete()
    db_session.query(Reaction).delete()
    db_session.query(Message).delete()
    db_session.query(ChannelMembership).delete()
    db_session.query(Channel).delete()
    db_session.query(User).delete()
    db_session.query(App).delete()
    db_session.query(Team).delete()
    
    db_session.commit()
    
    yield db_session


@pytest.fixture
def sample_team(clean_database):
    """Create a sample team for testing"""
    unique_id = str(uuid.uuid4()).replace('-', '')[:8].upper()
    
    team = Team(
        id=f"T_{unique_id}",
        name="Test Team",
        domain="testteam"
    )
    clean_database.add(team)
    clean_database.commit()
    return team


@pytest.fixture
def sample_app(clean_database, sample_team):
    """Create a sample app for testing"""
    unique_id = str(uuid.uuid4()).replace('-', '')[:8].upper()
    
    app_obj = App(
        id=f"A_{unique_id}",
        name="Test App",
        team_id=sample_team.id
    )
    clean_database.add(app_obj)
    clean_database.commit()
    return app_obj


@pytest.fixture
def sample_users(clean_database, sample_team):
    """Create sample users for testing"""
    base_id = str(uuid.uuid4()).replace('-', '')[:6].upper()
    
    users = [
        User(
            id=f"U_ALICE_{base_id}",
            name="alice",
            real_name="Alice Smith",
            display_name="Alice",
            email="alice@test.com",
            team_id=sample_team.id
        ),
        User(
            id=f"U_BOB_{base_id}", 
            name="bob",
            real_name="Bob Jones",
            display_name="Bob",
            email="bob@test.com",
            team_id=sample_team.id
        ),
        User(
            id=f"U_CAROL_{base_id}",
            name="carol",
            real_name="Carol Davis", 
            display_name="Carol",
            email="carol@test.com",
            team_id=sample_team.id
        ),
        User(
            id=f"U_TESTBOT_{base_id}",
            name="testbot",
            real_name="Test Bot",
            display_name="TestBot",
            email="bot@test.com",
            is_bot=True,
            team_id=sample_team.id
        )
    ]
    
    for user in users:
        clean_database.add(user)
    
    clean_database.commit()
    return {user.name: user for user in users}


@pytest.fixture
def sample_channels(clean_database, sample_team):
    """Create sample channels for testing"""
    channels = [
        Channel(
            id="C_GENERAL",
            name="general",
            channel_type="channel",
            is_private=False,
            topic="General discussion",
            purpose="Company-wide discussions",
            team_id=sample_team.id
        ),
        Channel(
            id="C_RANDOM",
            name="random", 
            channel_type="channel",
            is_private=False,
            topic="Random chatter",
            purpose="Non-work discussions",
            team_id=sample_team.id
        ),
        Channel(
            id="G_PRIVATE",
            name="private-group",
            channel_type="group",
            is_private=True,
            topic="Private discussions",
            purpose="Confidential team discussions",
            team_id=sample_team.id
        ),
        Channel(
            id="D_ALICE_BOB",
            name=None,
            channel_type="im",
            is_private=True,
            team_id=sample_team.id
        )
    ]
    
    for channel in channels:
        clean_database.add(channel)
        
    clean_database.commit()
    return {channel.name or channel.id: channel for channel in channels}


@pytest.fixture
def sample_memberships(clean_database, sample_users, sample_channels):
    """Create sample channel memberships"""
    memberships = [
        # Everyone in general
        ChannelMembership(user_id=sample_users["alice"].id, channel_id=sample_channels["general"].id),
        ChannelMembership(user_id=sample_users["bob"].id, channel_id=sample_channels["general"].id),
        ChannelMembership(user_id=sample_users["carol"].id, channel_id=sample_channels["general"].id),
        
        # Subset in random
        ChannelMembership(user_id=sample_users["alice"].id, channel_id=sample_channels["random"].id),
        ChannelMembership(user_id=sample_users["bob"].id, channel_id=sample_channels["random"].id),
        
        # Private group
        ChannelMembership(user_id=sample_users["alice"].id, channel_id=sample_channels["private-group"].id, is_admin=True),
        ChannelMembership(user_id=sample_users["carol"].id, channel_id=sample_channels["private-group"].id),
        
        # Direct message
        ChannelMembership(user_id=sample_users["alice"].id, channel_id=sample_channels["D_ALICE_BOB"].id),
        ChannelMembership(user_id=sample_users["bob"].id, channel_id=sample_channels["D_ALICE_BOB"].id),
    ]
    
    for membership in memberships:
        clean_database.add(membership)
        
    clean_database.commit()
    return memberships


@pytest.fixture
def full_workspace(sample_team, sample_app, sample_users, sample_channels, sample_memberships):
    """Complete workspace setup with team, app, users, channels, and memberships"""
    return {
        'team': sample_team,
        'app': sample_app, 
        'users': sample_users,
        'channels': sample_channels,
        'memberships': sample_memberships
    }


@pytest.fixture
def auth_headers():
    """Provide authentication headers for different user types"""
    def _get_headers(user_type: str = "admin"):
        if user_type not in TEST_TOKENS:
            raise ValueError(f"Unknown user type: {user_type}. Available: {list(TEST_TOKENS.keys())}")
        return {"Authorization": f"Bearer {TEST_TOKENS[user_type]}"}
    
    return _get_headers


@pytest.fixture
def message_helper(client, auth_headers):
    """Helper function for posting messages in tests"""
    def _post_message(channel_id: str, text: str, user_id: str = "U_ALICE", 
                      thread_ts: str = None, auth_type: str = "user1") -> Dict[str, Any]:
        message_data = {
            "channel": channel_id,
            "text": text,
            "user": user_id
        }
        if thread_ts:
            message_data["thread_ts"] = thread_ts
            
        response = client.post('/api/chat.postMessage',
                               json=message_data,
                               headers=auth_headers(auth_type),
                               content_type='application/json')
        
        assert response.status_code == 200, f"Failed to post message: {response.get_json()}"
        return response.get_json()
    
    return _post_message


@pytest.fixture  
def reaction_helper(client, auth_headers):
    """Helper function for adding reactions in tests"""
    def _add_reaction(channel_id: str, timestamp: str, emoji: str, 
                      user_id: str = "U_BOB", auth_type: str = "user2") -> Dict[str, Any]:
        reaction_data = {
            "name": emoji,
            "channel": channel_id, 
            "timestamp": timestamp,
            "user": user_id
        }
        
        response = client.post('/api/reactions.add',
                               json=reaction_data,
                               headers=auth_headers(auth_type),
                               content_type='application/json')
        
        assert response.status_code == 200, f"Failed to add reaction: {response.get_json()}"
        return response.get_json()
    
    return _add_reaction


@pytest.fixture
def conversation_helper(client, auth_headers):
    """Helper function for retrieving conversation data"""
    def _get_history(channel_id: str, limit: int = 100, cursor: str = None,
                     auth_type: str = "admin") -> Dict[str, Any]:
        params = f"channel={channel_id}&limit={limit}"
        if cursor:
            params += f"&cursor={cursor}"
            
        response = client.get(f'/api/conversations.history?{params}',
                              headers=auth_headers(auth_type))
        
        assert response.status_code == 200, f"Failed to get history: {response.get_json()}"
        return response.get_json()
    
    return _get_history


# Performance testing utilities
@pytest.fixture
def performance_timer():
    """Timer utility for performance testing"""
    import time
    
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
            
        def start(self):
            self.start_time = time.time()
            return self
            
        def stop(self):
            self.end_time = time.time()
            return self
            
        @property
        def elapsed(self):
            if self.start_time is None or self.end_time is None:
                return None
            return self.end_time - self.start_time
            
        def __enter__(self):
            self.start()
            return self
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            self.stop()
    
    return Timer


# Utility functions for test data generation
def generate_test_messages(count: int = 10, channel_id: str = "C_GENERAL", 
                          user_ids: list = None) -> list:
    """Generate test message data"""
    import time
    
    if user_ids is None:
        user_ids = ["U_ALICE", "U_BOB", "U_CAROL"]
    
    messages = []
    base_time = time.time()
    
    for i in range(count):
        user_id = user_ids[i % len(user_ids)]
        timestamp = f"{base_time + i:.6f}"
        
        messages.append({
            "ts": timestamp,
            "text": f"Test message {i + 1}",
            "user_id": user_id,
            "channel_id": channel_id,
            "message_type": "message"
        })
    
    return messages


def create_test_messages(db_session, messages_data: list) -> list:
    """Create message objects in database"""
    messages = []
    for msg_data in messages_data:
        message = Message(**msg_data)
        db_session.add(message)
        messages.append(message)
    
    db_session.commit()
    return messages


# Test validation utilities
def assert_slack_api_response(response_data: Dict[str, Any], should_succeed: bool = True):
    """Assert response follows Slack API format"""
    assert 'ok' in response_data, "Response missing 'ok' field"
    
    if should_succeed:
        assert response_data['ok'] is True, f"Expected successful response, got: {response_data}"
    else:
        assert response_data['ok'] is False, f"Expected error response, got: {response_data}"
        assert 'error' in response_data, "Error response missing 'error' field"


def assert_message_format(message: Dict[str, Any]):
    """Assert message follows Slack message format"""
    required_fields = ['type', 'user', 'text', 'ts']
    for field in required_fields:
        assert field in message, f"Message missing required field: {field}"
    
    assert message['type'] == 'message', f"Expected message type 'message', got: {message['type']}"


def assert_channel_format(channel: Dict[str, Any]):
    """Assert channel follows Slack channel format"""
    required_fields = ['id', 'name', 'is_channel', 'is_group', 'is_im', 'is_mpim']
    for field in required_fields:
        assert field in channel, f"Channel missing required field: {field}"


def assert_user_format(user: Dict[str, Any]):
    """Assert user follows Slack user format"""
    required_fields = ['id', 'name', 'real_name', 'profile', 'is_bot']
    for field in required_fields:
        assert field in user, f"User missing required field: {field}"
    
    # Verify profile structure
    profile_fields = ['real_name', 'display_name', 'email']
    for field in profile_fields:
        assert field in user['profile'], f"User profile missing field: {field}"