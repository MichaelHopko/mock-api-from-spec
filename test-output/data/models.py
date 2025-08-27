from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, Boolean, JSON, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

Base = declarative_base()


class TimestampMixin:
    """Mixin to add created_at and updated_at timestamps to models"""
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Team(Base, TimestampMixin):
    """Slack team/workspace"""
    __tablename__ = 'teams'
    
    id = Column(String, primary_key=True)  # T1H9RESGL
    name = Column(String, nullable=False)
    domain = Column(String, nullable=True)
    
    # Relationships
    channels = relationship("Channel", back_populates="team")
    users = relationship("User", back_populates="team")
    apps = relationship("App", back_populates="team")
    events = relationship("GenericEventWrapper", back_populates="team")


class App(Base, TimestampMixin):
    """Slack app"""
    __tablename__ = 'apps'
    
    id = Column(String, primary_key=True)  # A2H9RFS1A
    name = Column(String, nullable=False)
    team_id = Column(String, ForeignKey('teams.id'), nullable=False)
    
    # Relationships
    team = relationship("Team", back_populates="apps")
    events = relationship("GenericEventWrapper", back_populates="app")


class User(Base, TimestampMixin):
    """Slack user"""
    __tablename__ = 'users'
    
    id = Column(String, primary_key=True)  # U061F7AUR
    name = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    real_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    is_bot = Column(Boolean, default=False)
    team_id = Column(String, ForeignKey('teams.id'), nullable=False)
    
    # Relationships
    team = relationship("Team", back_populates="users")
    messages = relationship("Message", back_populates="user")
    reactions = relationship("Reaction", back_populates="user")
    channel_memberships = relationship("ChannelMembership", back_populates="user")


class Channel(Base, TimestampMixin):
    """Slack channel"""
    __tablename__ = 'channels'
    
    id = Column(String, primary_key=True)  # D0PNCRP9N
    name = Column(String, nullable=True)  # Can be None for DMs
    channel_type = Column(String, nullable=False)  # channel, group, im, mpim, app_home
    is_private = Column(Boolean, default=False)
    topic = Column(Text, nullable=True)
    purpose = Column(Text, nullable=True)
    team_id = Column(String, ForeignKey('teams.id'), nullable=False)
    
    # Relationships
    team = relationship("Team", back_populates="channels")
    messages = relationship("Message", back_populates="channel")
    memberships = relationship("ChannelMembership", back_populates="channel")


class ChannelMembership(Base, TimestampMixin):
    """User membership in channels"""
    __tablename__ = 'channel_memberships'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    channel_id = Column(String, ForeignKey('channels.id'), nullable=False)
    is_admin = Column(Boolean, default=False)
    
    # Relationships
    user = relationship("User", back_populates="channel_memberships")
    channel = relationship("Channel", back_populates="memberships")
    
    # Indexes
    __table_args__ = (
        Index('idx_channel_memberships_user_channel', 'user_id', 'channel_id', unique=True),
    )


class Message(Base, TimestampMixin):
    """Slack message"""
    __tablename__ = 'messages'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ts = Column(String, nullable=False)  # Slack timestamp
    text = Column(Text, nullable=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    channel_id = Column(String, ForeignKey('channels.id'), nullable=False)
    thread_ts = Column(String, nullable=True)  # Parent message timestamp for threading
    reply_count = Column(Integer, default=0)
    message_type = Column(String, default='message')
    subtype = Column(String, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="messages")
    channel = relationship("Channel", back_populates="messages")
    reactions = relationship("Reaction", back_populates="message")
    
    # Indexes
    __table_args__ = (
        Index('idx_messages_channel_ts', 'channel_id', 'ts'),
        Index('idx_messages_thread_ts', 'thread_ts'),
        Index('idx_messages_user', 'user_id'),
    )


class Reaction(Base, TimestampMixin):
    """Message reactions"""
    __tablename__ = 'reactions'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(String, ForeignKey('messages.id'), nullable=False)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    emoji = Column(String, nullable=False)
    
    # Relationships
    message = relationship("Message", back_populates="reactions")
    user = relationship("User", back_populates="reactions")
    
    # Indexes
    __table_args__ = (
        Index('idx_reactions_message_user_emoji', 'message_id', 'user_id', 'emoji', unique=True),
    )


class GenericEventWrapper(Base, TimestampMixin):
    """Main event wrapper table based on the provided schema"""
    __tablename__ = 'generic_event_wrappers'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String, nullable=False, unique=True)  # Ev0PV52K25
    token = Column(String, nullable=False)
    team_id = Column(String, ForeignKey('teams.id'), nullable=False)
    api_app_id = Column(String, ForeignKey('apps.id'), nullable=False)
    event_type = Column(String, nullable=False)  # event_callback
    event_time = Column(Integer, nullable=False)  # epoch timestamp
    
    # Event data stored as JSON
    event_data = Column(JSON, nullable=False)
    
    # Authed users stored as JSON array
    authed_users = Column(JSON, nullable=False)
    
    # Relationships
    team = relationship("Team", back_populates="events")
    app = relationship("App", back_populates="events")
    
    # Indexes
    __table_args__ = (
        Index('idx_events_team_app', 'team_id', 'api_app_id'),
        Index('idx_events_type_time', 'event_type', 'event_time'),
        Index('idx_events_event_id', 'event_id', unique=True),
    )


class EventAuthedUser(Base, TimestampMixin):
    """Junction table for event authed users (normalized from JSON array)"""
    __tablename__ = 'event_authed_users'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_wrapper_id = Column(String, ForeignKey('generic_event_wrappers.id'), nullable=False)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    
    # Relationships
    event_wrapper = relationship("GenericEventWrapper")
    user = relationship("User")
    
    # Indexes
    __table_args__ = (
        Index('idx_event_authed_users_event_user', 'event_wrapper_id', 'user_id', unique=True),
    )