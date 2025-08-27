"""
Data layer for Slack-like API simulation

This package provides:
- SQLAlchemy models for Slack-like entities
- Database connection and session management
- Sample data generation utilities
"""

from .models import (
    Base,
    Team,
    App, 
    User,
    Channel,
    ChannelMembership,
    Message,
    Reaction,
    GenericEventWrapper,
    EventAuthedUser
)

from .database import (
    db_manager,
    init_database,
    get_db_session,
    reset_database,
    check_database_health,
    database_transaction
)

from .sample_data import SampleDataGenerator, populate_database

__all__ = [
    # Models
    'Base',
    'Team',
    'App',
    'User', 
    'Channel',
    'ChannelMembership',
    'Message',
    'Reaction',
    'GenericEventWrapper',
    'EventAuthedUser',
    
    # Database
    'db_manager',
    'init_database',
    'get_db_session',
    'reset_database',
    'check_database_health', 
    'database_transaction',
    
    # Sample data
    'SampleDataGenerator',
    'populate_database'
]