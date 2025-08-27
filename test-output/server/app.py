#!/usr/bin/env python3
"""
Slack Events API Flask Server
Implements a comprehensive mock Slack Events API with full state persistence.
"""

import os
import sys
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any

from flask import Flask, request, jsonify, g
from flask_cors import CORS
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc

# Add parent directory to path to import data modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.database import db_manager, init_database, check_database_health
from data.models import (
    Team, App, User, Channel, ChannelMembership, Message, Reaction, 
    GenericEventWrapper, EventAuthedUser
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Enable CORS
CORS(app, origins="*", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

# Global variables for request tracking
REQUEST_COUNT = 0
STARTUP_TIME = datetime.utcnow()

def generate_slack_id(prefix: str = "T") -> str:
    """Generate a Slack-style ID with the given prefix"""
    import random
    import string
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"{prefix}{suffix}"

def generate_timestamp() -> str:
    """Generate a Slack-style timestamp"""
    return f"{time.time():.6f}"

def get_db_session() -> Session:
    """Get database session for the current request"""
    if not hasattr(g, 'db_session'):
        g.db_session = db_manager.session_factory()
    return g.db_session

@app.teardown_appcontext
def close_db_session(error):
    """Close database session after request"""
    if hasattr(g, 'db_session'):
        if error:
            g.db_session.rollback()
        else:
            try:
                g.db_session.commit()
            except Exception as e:
                logger.error(f"Error committing session: {e}")
                g.db_session.rollback()
        g.db_session.close()

def require_auth(f):
    """Decorator to require authentication via token"""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'ok': False, 'error': 'missing_auth', 'message': 'Authentication required'}), 401
        
        token = auth_header[7:]  # Remove 'Bearer ' prefix
        
        # Simple token validation - in production, use proper JWT validation
        if len(token) < 10:
            return jsonify({'ok': False, 'error': 'invalid_auth', 'message': 'Invalid token'}), 401
            
        g.auth_token = token
        return f(*args, **kwargs)
    
    return decorated_function

def log_request():
    """Log incoming requests"""
    global REQUEST_COUNT
    REQUEST_COUNT += 1
    logger.info(f"Request #{REQUEST_COUNT}: {request.method} {request.path}")

# Middleware to log all requests
@app.before_request
def before_request():
    log_request()

# Health check endpoints
@app.route('/health')
def health_check():
    """Health check endpoint"""
    db_healthy = check_database_health()
    
    return jsonify({
        'status': 'healthy' if db_healthy else 'unhealthy',
        'database': 'connected' if db_healthy else 'disconnected',
        'uptime_seconds': (datetime.utcnow() - STARTUP_TIME).total_seconds(),
        'requests_served': REQUEST_COUNT,
        'timestamp': datetime.utcnow().isoformat()
    }), 200 if db_healthy else 503

@app.route('/api/test')
def api_test():
    """Test endpoint for API connectivity"""
    return jsonify({
        'ok': True,
        'message': 'Slack Events API Mock Server is running',
        'version': '1.0.0',
        'timestamp': datetime.utcnow().isoformat()
    })

# Events API endpoints
@app.route('/api/events', methods=['POST'])
def handle_events():
    """Main events API endpoint - handles URL verification and events"""
    # Check content type first
    if not request.content_type or 'application/json' not in request.content_type:
        return jsonify({'ok': False, 'error': 'invalid_request', 'message': 'Content-Type must be application/json'}), 415
    
    data = request.get_json()
    
    if not data:
        return jsonify({'ok': False, 'error': 'invalid_request', 'message': 'JSON body required'}), 400
    
    # Handle URL verification challenge
    if data.get('type') == 'url_verification':
        challenge = data.get('challenge')
        if challenge:
            logger.info("Responding to URL verification challenge")
            return {'challenge': challenge}
        else:
            return jsonify({'error': 'missing_challenge'}), 400
    
    # Handle event callbacks
    if data.get('type') == 'event_callback':
        return handle_event_callback(data)
    
    logger.warning(f"Unknown event type: {data.get('type')}")
    return jsonify({'ok': True})

def handle_event_callback(data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle event callback from Slack"""
    db = get_db_session()
    
    try:
        # Extract event wrapper data
        event_data = data.get('event', {})
        event_type = event_data.get('type')
        team_id = data.get('team_id')
        api_app_id = data.get('api_app_id')
        event_id = data.get('event_id', generate_slack_id('Ev'))
        event_time = data.get('event_time', int(time.time()))
        token = data.get('token', 'default_token')
        authed_users = data.get('authed_users', [])
        
        logger.info(f"Processing event: {event_type} for team {team_id}")
        
        # Store the event in the database
        event_wrapper = GenericEventWrapper(
            event_id=event_id,
            token=token,
            team_id=team_id,
            api_app_id=api_app_id,
            event_type='event_callback',
            event_time=event_time,
            event_data=event_data,
            authed_users=authed_users
        )
        
        db.add(event_wrapper)
        db.flush()  # Get the ID
        
        # Store authed users relationships
        for user_id in authed_users:
            auth_user = EventAuthedUser(
                event_wrapper_id=event_wrapper.id,
                user_id=user_id
            )
            db.add(auth_user)
        
        # Handle specific event types
        if event_type == 'message':
            handle_message_event(db, event_data, team_id)
        elif event_type == 'member_joined_channel':
            handle_member_joined_channel(db, event_data, team_id)
        elif event_type == 'member_left_channel':
            handle_member_left_channel(db, event_data, team_id)
        elif event_type == 'reaction_added':
            handle_reaction_added(db, event_data, team_id)
        elif event_type == 'reaction_removed':
            handle_reaction_removed(db, event_data, team_id)
        
        db.commit()
        logger.info(f"Event {event_type} processed successfully")
        
        return jsonify({'ok': True})
        
    except Exception as e:
        logger.error(f"Error processing event: {e}")
        db.rollback()
        return jsonify({'error': 'processing_error', 'message': str(e)}), 500

def handle_message_event(db: Session, event_data: Dict, team_id: str):
    """Handle message events"""
    user_id = event_data.get('user')
    channel_id = event_data.get('channel')
    text = event_data.get('text', '')
    ts = event_data.get('ts', generate_timestamp())
    thread_ts = event_data.get('thread_ts')
    subtype = event_data.get('subtype')
    
    # Create or update message
    message = Message(
        ts=ts,
        text=text,
        user_id=user_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
        message_type='message',
        subtype=subtype
    )
    
    db.add(message)

def handle_member_joined_channel(db: Session, event_data: Dict, team_id: str):
    """Handle member joined channel events"""
    user_id = event_data.get('user')
    channel_id = event_data.get('channel')
    
    # Create membership if it doesn't exist
    existing = db.query(ChannelMembership).filter_by(
        user_id=user_id, channel_id=channel_id
    ).first()
    
    if not existing:
        membership = ChannelMembership(
            user_id=user_id,
            channel_id=channel_id
        )
        db.add(membership)

def handle_member_left_channel(db: Session, event_data: Dict, team_id: str):
    """Handle member left channel events"""
    user_id = event_data.get('user')
    channel_id = event_data.get('channel')
    
    # Remove membership
    membership = db.query(ChannelMembership).filter_by(
        user_id=user_id, channel_id=channel_id
    ).first()
    
    if membership:
        db.delete(membership)

def handle_reaction_added(db: Session, event_data: Dict, team_id: str):
    """Handle reaction added events"""
    user_id = event_data.get('user')
    emoji = event_data.get('reaction')
    item = event_data.get('item', {})
    
    if item.get('type') == 'message':
        # Find message by timestamp and channel
        message = db.query(Message).filter_by(
            ts=item.get('ts'),
            channel_id=item.get('channel')
        ).first()
        
        if message:
            # Check if reaction already exists
            existing = db.query(Reaction).filter_by(
                message_id=message.id,
                user_id=user_id,
                emoji=emoji
            ).first()
            
            if not existing:
                reaction = Reaction(
                    message_id=message.id,
                    user_id=user_id,
                    emoji=emoji
                )
                db.add(reaction)

def handle_reaction_removed(db: Session, event_data: Dict, team_id: str):
    """Handle reaction removed events"""
    user_id = event_data.get('user')
    emoji = event_data.get('reaction')
    item = event_data.get('item', {})
    
    if item.get('type') == 'message':
        # Find message by timestamp and channel
        message = db.query(Message).filter_by(
            ts=item.get('ts'),
            channel_id=item.get('channel')
        ).first()
        
        if message:
            # Remove reaction
            reaction = db.query(Reaction).filter_by(
                message_id=message.id,
                user_id=user_id,
                emoji=emoji
            ).first()
            
            if reaction:
                db.delete(reaction)

# Conversations API endpoints
@app.route('/api/conversations.list', methods=['GET', 'POST'])
@require_auth
def conversations_list():
    """List conversations (channels)"""
    db = get_db_session()
    
    # Parse parameters
    types = request.args.get('types', 'public_channel,private_channel,mpim,im')
    limit = min(int(request.args.get('limit', 100)), 1000)
    cursor = request.args.get('cursor', '')
    exclude_archived = request.args.get('exclude_archived', 'false').lower() == 'true'
    
    try:
        # Build query
        query = db.query(Channel)
        
        # Filter by types
        type_list = types.split(',')
        if type_list and type_list != ['']:
            # Map Slack types to our channel types
            type_mapping = {
                'public_channel': 'channel',
                'private_channel': 'group',
                'mpim': 'mpim',
                'im': 'im'
            }
            our_types = [type_mapping.get(t, t) for t in type_list if t in type_mapping]
            query = query.filter(Channel.channel_type.in_(our_types))
        
        # Handle pagination with cursor
        if cursor:
            query = query.filter(Channel.id > cursor)
        
        query = query.order_by(Channel.id).limit(limit + 1)  # +1 to check if more exist
        channels = query.all()
        
        # Check if there are more results
        has_more = len(channels) > limit
        if has_more:
            channels = channels[:-1]  # Remove the extra channel
        
        # Convert to Slack format
        slack_channels = []
        for channel in channels:
            slack_channel = {
                'id': channel.id,
                'name': channel.name,
                'is_channel': channel.channel_type == 'channel',
                'is_group': channel.channel_type == 'group',
                'is_im': channel.channel_type == 'im',
                'is_mpim': channel.channel_type == 'mpim',
                'is_private': channel.is_private,
                'created': int(channel.created_at.timestamp()),
                'is_archived': False,
                'is_general': channel.name == 'general',
                'unlinked': 0,
                'name_normalized': channel.name.lower() if channel.name else '',
                'is_shared': False,
                'is_ext_shared': False,
                'is_org_shared': False,
                'purpose': {
                    'value': channel.purpose or '',
                    'creator': '',
                    'last_set': 0
                },
                'topic': {
                    'value': channel.topic or '',
                    'creator': '',
                    'last_set': 0
                },
                'is_member': True,  # Simplified - assume user is member
                'last_read': generate_timestamp(),
                'latest': None,  # Could populate with latest message
                'unread_count': 0,
                'unread_count_display': 0
            }
            slack_channels.append(slack_channel)
        
        response = {
            'ok': True,
            'channels': slack_channels,
            'response_metadata': {}
        }
        
        if has_more:
            response['response_metadata']['next_cursor'] = channels[-1].id
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error listing conversations: {e}")
        return jsonify({
            'ok': False,
            'error': 'internal_error',
            'message': str(e)
        }), 500

@app.route('/api/conversations.history', methods=['GET', 'POST'])
@require_auth
def conversations_history():
    """Get conversation history"""
    db = get_db_session()
    
    # Parse parameters - handle both GET (query params) and POST (JSON body)
    channel = request.args.get('channel')
    if not channel and request.method == 'POST' and request.content_type and 'application/json' in request.content_type:
        json_data = request.get_json(silent=True)
        if json_data:
            channel = json_data.get('channel')
    cursor = request.args.get('cursor', '')
    limit = min(int(request.args.get('limit', 100)), 1000)
    oldest = request.args.get('oldest')
    latest = request.args.get('latest')
    inclusive = request.args.get('inclusive', 'false').lower() == 'true'
    
    if not channel:
        return jsonify({
            'ok': False,
            'error': 'channel_not_found',
            'message': 'Channel parameter required'
        }), 400
    
    try:
        # Build query
        query = db.query(Message).filter(Message.channel_id == channel)
        
        # Filter by timestamp range
        if oldest:
            if inclusive:
                query = query.filter(Message.ts >= oldest)
            else:
                query = query.filter(Message.ts > oldest)
        
        if latest:
            if inclusive:
                query = query.filter(Message.ts <= latest)
            else:
                query = query.filter(Message.ts < latest)
        
        # Handle pagination with cursor
        if cursor:
            query = query.filter(Message.ts < cursor)
        
        query = query.order_by(desc(Message.ts)).limit(limit + 1)  # +1 to check if more exist
        messages = query.all()
        
        # Check if there are more results
        has_more = len(messages) > limit
        if has_more:
            messages = messages[:-1]  # Remove the extra message
        
        # Convert to Slack format
        slack_messages = []
        for message in messages:
            user = db.query(User).get(message.user_id)
            
            slack_message = {
                'type': 'message',
                'subtype': message.subtype,
                'user': message.user_id,
                'text': message.text,
                'ts': message.ts
            }
            
            # Add thread info if applicable
            if message.thread_ts:
                slack_message['thread_ts'] = message.thread_ts
            
            if message.reply_count > 0:
                slack_message['reply_count'] = message.reply_count
                slack_message['reply_users_count'] = message.reply_count  # Simplified
                slack_message['latest_reply'] = message.ts
                slack_message['reply_users'] = [message.user_id]  # Simplified
            
            # Add reactions
            reactions = db.query(Reaction).filter(Reaction.message_id == message.id).all()
            if reactions:
                reaction_dict = {}
                for reaction in reactions:
                    emoji = reaction.emoji
                    if emoji not in reaction_dict:
                        reaction_dict[emoji] = {
                            'name': emoji,
                            'users': [],
                            'count': 0
                        }
                    reaction_dict[emoji]['users'].append(reaction.user_id)
                    reaction_dict[emoji]['count'] += 1
                
                slack_message['reactions'] = list(reaction_dict.values())
            
            slack_messages.append(slack_message)
        
        response = {
            'ok': True,
            'messages': slack_messages,
            'has_more': has_more,
            'pin_count': 0,
            'response_metadata': {}
        }
        
        if has_more:
            response['response_metadata']['next_cursor'] = messages[-1].ts
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error getting conversation history: {e}")
        return jsonify({
            'ok': False,
            'error': 'internal_error',
            'message': str(e)
        }), 500

@app.route('/api/conversations.info', methods=['GET', 'POST'])
@require_auth
def conversations_info():
    """Get conversation info"""
    db = get_db_session()
    
    # Handle both GET (query params) and POST (JSON body)
    channel = request.args.get('channel')
    if not channel and request.method == 'POST' and request.content_type and 'application/json' in request.content_type:
        json_data = request.get_json(silent=True)
        if json_data:
            channel = json_data.get('channel')
    include_locale = request.args.get('include_locale', 'false').lower() == 'true'
    
    if not channel:
        return jsonify({
            'ok': False,
            'error': 'channel_not_found',
            'message': 'Channel parameter required'
        }), 400
    
    try:
        channel_obj = db.query(Channel).get(channel)
        
        if not channel_obj:
            return jsonify({
                'ok': False,
                'error': 'channel_not_found'
            }), 404
        
        # Get member count
        member_count = db.query(ChannelMembership).filter(
            ChannelMembership.channel_id == channel
        ).count()
        
        slack_channel = {
            'id': channel_obj.id,
            'name': channel_obj.name,
            'is_channel': channel_obj.channel_type == 'channel',
            'is_group': channel_obj.channel_type == 'group',
            'is_im': channel_obj.channel_type == 'im',
            'is_mpim': channel_obj.channel_type == 'mpim',
            'is_private': channel_obj.is_private,
            'created': int(channel_obj.created_at.timestamp()),
            'is_archived': False,
            'is_general': channel_obj.name == 'general',
            'unlinked': 0,
            'name_normalized': channel_obj.name.lower() if channel_obj.name else '',
            'is_shared': False,
            'is_ext_shared': False,
            'is_org_shared': False,
            'purpose': {
                'value': channel_obj.purpose or '',
                'creator': '',
                'last_set': 0
            },
            'topic': {
                'value': channel_obj.topic or '',
                'creator': '',
                'last_set': 0
            },
            'is_member': True,
            'last_read': generate_timestamp(),
            'latest': None,
            'unread_count': 0,
            'unread_count_display': 0,
            'num_members': member_count
        }
        
        if include_locale:
            slack_channel['locale'] = 'en-US'
        
        return jsonify({
            'ok': True,
            'channel': slack_channel
        })
        
    except Exception as e:
        logger.error(f"Error getting conversation info: {e}")
        return jsonify({
            'ok': False,
            'error': 'internal_error',
            'message': str(e)
        }), 500

# Chat API endpoints
@app.route('/api/chat.postMessage', methods=['POST'])
@require_auth
def chat_post_message():
    """Post a message to a channel"""
    db = get_db_session()
    
    data = request.get_json() or {}
    channel = data.get('channel')
    text = data.get('text', '')
    user_id = data.get('user', 'USLACKBOT')  # Default to Slackbot
    thread_ts = data.get('thread_ts')
    
    if not channel:
        return jsonify({
            'ok': False,
            'error': 'channel_not_found',
            'message': 'Channel parameter required'
        }), 400
    
    try:
        # Generate message timestamp
        ts = generate_timestamp()
        
        # Create message
        message = Message(
            ts=ts,
            text=text,
            user_id=user_id,
            channel_id=channel,
            thread_ts=thread_ts,
            message_type='message'
        )
        
        db.add(message)
        db.commit()
        
        # Update reply count if this is a thread reply
        if thread_ts:
            parent_message = db.query(Message).filter(
                Message.ts == thread_ts,
                Message.channel_id == channel
            ).first()
            if parent_message:
                parent_message.reply_count += 1
                db.commit()
        
        return jsonify({
            'ok': True,
            'channel': channel,
            'ts': ts,
            'message': {
                'type': 'message',
                'user': user_id,
                'text': text,
                'ts': ts,
                'thread_ts': thread_ts
            }
        })
        
    except Exception as e:
        logger.error(f"Error posting message: {e}")
        return jsonify({
            'ok': False,
            'error': 'internal_error',
            'message': str(e)
        }), 500

@app.route('/api/chat.update', methods=['POST'])
@require_auth
def chat_update():
    """Update a message"""
    db = get_db_session()
    
    data = request.get_json() or {}
    channel = data.get('channel')
    ts = data.get('ts')
    text = data.get('text', '')
    
    if not channel or not ts:
        return jsonify({
            'ok': False,
            'error': 'missing_parameter',
            'message': 'Channel and ts parameters required'
        }), 400
    
    try:
        message = db.query(Message).filter(
            Message.ts == ts,
            Message.channel_id == channel
        ).first()
        
        if not message:
            return jsonify({
                'ok': False,
                'error': 'message_not_found'
            }), 404
        
        message.text = text
        db.commit()
        
        return jsonify({
            'ok': True,
            'channel': channel,
            'ts': ts,
            'text': text
        })
        
    except Exception as e:
        logger.error(f"Error updating message: {e}")
        return jsonify({
            'ok': False,
            'error': 'internal_error',
            'message': str(e)
        }), 500

@app.route('/api/chat.delete', methods=['POST'])
@require_auth
def chat_delete():
    """Delete a message"""
    db = get_db_session()
    
    data = request.get_json() or {}
    channel = data.get('channel')
    ts = data.get('ts')
    
    if not channel or not ts:
        return jsonify({
            'ok': False,
            'error': 'missing_parameter',
            'message': 'Channel and ts parameters required'
        }), 400
    
    try:
        message = db.query(Message).filter(
            Message.ts == ts,
            Message.channel_id == channel
        ).first()
        
        if not message:
            return jsonify({
                'ok': False,
                'error': 'message_not_found'
            }), 404
        
        db.delete(message)
        db.commit()
        
        return jsonify({
            'ok': True,
            'channel': channel,
            'ts': ts
        })
        
    except Exception as e:
        logger.error(f"Error deleting message: {e}")
        return jsonify({
            'ok': False,
            'error': 'internal_error',
            'message': str(e)
        }), 500

# Reactions API endpoints
@app.route('/api/reactions.add', methods=['POST'])
@require_auth
def reactions_add():
    """Add a reaction to a message"""
    db = get_db_session()
    
    data = request.get_json() or {}
    name = data.get('name')  # emoji name
    channel = data.get('channel')
    timestamp = data.get('timestamp')
    user_id = data.get('user', 'U12345678')  # Default user
    
    if not all([name, channel, timestamp]):
        return jsonify({
            'ok': False,
            'error': 'missing_parameter',
            'message': 'Name, channel, and timestamp parameters required'
        }), 400
    
    try:
        # Find the message
        message = db.query(Message).filter(
            Message.ts == timestamp,
            Message.channel_id == channel
        ).first()
        
        if not message:
            return jsonify({
                'ok': False,
                'error': 'message_not_found'
            }), 404
        
        # Check if reaction already exists
        existing_reaction = db.query(Reaction).filter(
            Reaction.message_id == message.id,
            Reaction.user_id == user_id,
            Reaction.emoji == name
        ).first()
        
        if existing_reaction:
            return jsonify({
                'ok': False,
                'error': 'already_reacted'
            }), 400
        
        # Add reaction
        reaction = Reaction(
            message_id=message.id,
            user_id=user_id,
            emoji=name
        )
        
        db.add(reaction)
        db.commit()
        
        return jsonify({'ok': True})
        
    except Exception as e:
        logger.error(f"Error adding reaction: {e}")
        return jsonify({
            'ok': False,
            'error': 'internal_error',
            'message': str(e)
        }), 500

@app.route('/api/reactions.remove', methods=['POST'])
@require_auth
def reactions_remove():
    """Remove a reaction from a message"""
    db = get_db_session()
    
    data = request.get_json() or {}
    name = data.get('name')  # emoji name
    channel = data.get('channel')
    timestamp = data.get('timestamp')
    user_id = data.get('user', 'U12345678')  # Default user
    
    if not all([name, channel, timestamp]):
        return jsonify({
            'ok': False,
            'error': 'missing_parameter',
            'message': 'Name, channel, and timestamp parameters required'
        }), 400
    
    try:
        # Find the message
        message = db.query(Message).filter(
            Message.ts == timestamp,
            Message.channel_id == channel
        ).first()
        
        if not message:
            return jsonify({
                'ok': False,
                'error': 'message_not_found'
            }), 404
        
        # Find and remove reaction
        reaction = db.query(Reaction).filter(
            Reaction.message_id == message.id,
            Reaction.user_id == user_id,
            Reaction.emoji == name
        ).first()
        
        if not reaction:
            return jsonify({
                'ok': False,
                'error': 'no_reaction'
            }), 404
        
        db.delete(reaction)
        db.commit()
        
        return jsonify({'ok': True})
        
    except Exception as e:
        logger.error(f"Error removing reaction: {e}")
        return jsonify({
            'ok': False,
            'error': 'internal_error',
            'message': str(e)
        }), 500

# Users API endpoints
@app.route('/api/users.list', methods=['GET', 'POST'])
@require_auth
def users_list():
    """List users"""
    db = get_db_session()
    
    limit = min(int(request.args.get('limit', 100)), 1000)
    cursor = request.args.get('cursor', '')
    include_locale = request.args.get('include_locale', 'false').lower() == 'true'
    
    try:
        # Build query
        query = db.query(User)
        
        # Handle pagination with cursor
        if cursor:
            query = query.filter(User.id > cursor)
        
        query = query.order_by(User.id).limit(limit + 1)  # +1 to check if more exist
        users = query.all()
        
        # Check if there are more results
        has_more = len(users) > limit
        if has_more:
            users = users[:-1]  # Remove the extra user
        
        # Convert to Slack format
        slack_users = []
        for user in users:
            slack_user = {
                'id': user.id,
                'team_id': user.team_id,
                'name': user.name,
                'deleted': False,
                'color': 'e7392d',  # Default color
                'real_name': user.real_name or user.name,
                'tz': 'America/Los_Angeles',
                'tz_label': 'Pacific Standard Time',
                'tz_offset': -28800,
                'profile': {
                    'title': '',
                    'phone': '',
                    'skype': '',
                    'real_name': user.real_name or user.name,
                    'real_name_normalized': (user.real_name or user.name).lower(),
                    'display_name': user.display_name or user.name,
                    'display_name_normalized': (user.display_name or user.name).lower(),
                    'email': user.email or '',
                    'image_original': f'https://avatars.slack-edge.com/2023-01-01/{user.id}_original.png',
                    'image_24': f'https://avatars.slack-edge.com/2023-01-01/{user.id}_24.png',
                    'image_32': f'https://avatars.slack-edge.com/2023-01-01/{user.id}_32.png',
                    'image_48': f'https://avatars.slack-edge.com/2023-01-01/{user.id}_48.png',
                    'image_72': f'https://avatars.slack-edge.com/2023-01-01/{user.id}_72.png',
                    'image_192': f'https://avatars.slack-edge.com/2023-01-01/{user.id}_192.png',
                    'image_512': f'https://avatars.slack-edge.com/2023-01-01/{user.id}_512.png',
                    'team': user.team_id
                },
                'is_admin': False,
                'is_owner': False,
                'is_primary_owner': False,
                'is_restricted': False,
                'is_ultra_restricted': False,
                'is_bot': user.is_bot,
                'is_app_user': False,
                'updated': int(user.updated_at.timestamp()),
                'has_2fa': False
            }
            
            if include_locale:
                slack_user['locale'] = 'en-US'
            
            slack_users.append(slack_user)
        
        response = {
            'ok': True,
            'members': slack_users,
            'cache_ts': int(time.time()),
            'response_metadata': {}
        }
        
        if has_more:
            response['response_metadata']['next_cursor'] = users[-1].id
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        return jsonify({
            'ok': False,
            'error': 'internal_error',
            'message': str(e)
        }), 500

@app.route('/api/users.info', methods=['GET', 'POST'])
@require_auth
def users_info():
    """Get user info"""
    db = get_db_session()
    
    # Handle both GET (query params) and POST (JSON body)
    user_id = request.args.get('user')
    if not user_id and request.method == 'POST' and request.content_type and 'application/json' in request.content_type:
        json_data = request.get_json(silent=True)
        if json_data:
            user_id = json_data.get('user')
    include_locale = request.args.get('include_locale', 'false').lower() == 'true'
    
    if not user_id:
        return jsonify({
            'ok': False,
            'error': 'user_not_found',
            'message': 'User parameter required'
        }), 400
    
    try:
        user = db.query(User).get(user_id)
        
        if not user:
            return jsonify({
                'ok': False,
                'error': 'user_not_found'
            }), 404
        
        slack_user = {
            'id': user.id,
            'team_id': user.team_id,
            'name': user.name,
            'deleted': False,
            'color': 'e7392d',
            'real_name': user.real_name or user.name,
            'tz': 'America/Los_Angeles',
            'tz_label': 'Pacific Standard Time',
            'tz_offset': -28800,
            'profile': {
                'title': '',
                'phone': '',
                'skype': '',
                'real_name': user.real_name or user.name,
                'real_name_normalized': (user.real_name or user.name).lower(),
                'display_name': user.display_name or user.name,
                'display_name_normalized': (user.display_name or user.name).lower(),
                'email': user.email or '',
                'image_original': f'https://avatars.slack-edge.com/2023-01-01/{user.id}_original.png',
                'image_24': f'https://avatars.slack-edge.com/2023-01-01/{user.id}_24.png',
                'image_32': f'https://avatars.slack-edge.com/2023-01-01/{user.id}_32.png',
                'image_48': f'https://avatars.slack-edge.com/2023-01-01/{user.id}_48.png',
                'image_72': f'https://avatars.slack-edge.com/2023-01-01/{user.id}_72.png',
                'image_192': f'https://avatars.slack-edge.com/2023-01-01/{user.id}_192.png',
                'image_512': f'https://avatars.slack-edge.com/2023-01-01/{user.id}_512.png',
                'team': user.team_id
            },
            'is_admin': False,
            'is_owner': False,
            'is_primary_owner': False,
            'is_restricted': False,
            'is_ultra_restricted': False,
            'is_bot': user.is_bot,
            'is_app_user': False,
            'updated': int(user.updated_at.timestamp()),
            'has_2fa': False
        }
        
        if include_locale:
            slack_user['locale'] = 'en-US'
        
        return jsonify({
            'ok': True,
            'user': slack_user
        })
        
    except Exception as e:
        logger.error(f"Error getting user info: {e}")
        return jsonify({
            'ok': False,
            'error': 'internal_error',
            'message': str(e)
        }), 500

# Team API endpoints
@app.route('/api/team.info', methods=['GET', 'POST'])
@require_auth
def team_info():
    """Get team info"""
    db = get_db_session()
    
    try:
        # Get the first team (in a real app, you'd identify by token)
        team = db.query(Team).first()
        
        if not team:
            return jsonify({
                'ok': False,
                'error': 'team_not_found'
            }), 404
        
        slack_team = {
            'id': team.id,
            'name': team.name,
            'domain': team.domain,
            'email_domain': team.domain,
            'icon': {
                'image_34': f'https://avatars.slack-edge.com/2023-01-01/{team.id}_34.png',
                'image_44': f'https://avatars.slack-edge.com/2023-01-01/{team.id}_44.png',
                'image_68': f'https://avatars.slack-edge.com/2023-01-01/{team.id}_68.png',
                'image_88': f'https://avatars.slack-edge.com/2023-01-01/{team.id}_88.png',
                'image_102': f'https://avatars.slack-edge.com/2023-01-01/{team.id}_102.png',
                'image_132': f'https://avatars.slack-edge.com/2023-01-01/{team.id}_132.png',
                'image_original': f'https://avatars.slack-edge.com/2023-01-01/{team.id}_original.png'
            },
            'enterprise_id': None,
            'enterprise_name': None
        }
        
        return jsonify({
            'ok': True,
            'team': slack_team
        })
        
    except Exception as e:
        logger.error(f"Error getting team info: {e}")
        return jsonify({
            'ok': False,
            'error': 'internal_error',
            'message': str(e)
        }), 500

# Auth test endpoint
@app.route('/api/auth.test', methods=['GET', 'POST'])
@require_auth
def auth_test():
    """Test authentication"""
    db = get_db_session()
    
    try:
        # Get the first team and user for testing
        team = db.query(Team).first()
        user = db.query(User).first()
        
        return jsonify({
            'ok': True,
            'url': 'https://myteam.slack.com/',
            'team': team.name if team else 'Test Team',
            'user': user.name if user else 'testuser',
            'team_id': team.id if team else 'T12345678',
            'user_id': user.id if user else 'U12345678',
            'bot_id': None,
            'is_enterprise_install': False
        })
        
    except Exception as e:
        logger.error(f"Error in auth test: {e}")
        return jsonify({
            'ok': False,
            'error': 'internal_error',
            'message': str(e)
        }), 500

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({
        'ok': False,
        'error': 'not_found',
        'message': 'Endpoint not found'
    }), 404

@app.errorhandler(405)
def method_not_allowed_error(error):
    return jsonify({
        'ok': False,
        'error': 'method_not_allowed',
        'message': 'HTTP method not allowed for this endpoint'
    }), 405

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'ok': False,
        'error': 'internal_error',
        'message': 'Internal server error'
    }), 500

# Initialize database on startup
def initialize_app():
    """Initialize the application"""
    logger.info("Initializing Slack Events API Mock Server...")
    
    try:
        # Initialize database
        init_database()
        logger.info("Database initialized successfully")
        
        # Check database health
        if not check_database_health():
            logger.warning("Database health check failed")
        
        logger.info("Slack Events API Mock Server initialized successfully")
        
    except Exception as e:
        logger.error(f"Error initializing application: {e}")
        raise

if __name__ == '__main__':
    initialize_app()
    
    # Run the development server
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'true').lower() == 'true'
    
    logger.info(f"Starting Slack Events API Mock Server on port {port}")
    logger.info(f"Debug mode: {debug}")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug,
        threaded=True
    )