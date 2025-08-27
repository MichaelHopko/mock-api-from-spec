import json
import time
import random
from datetime import datetime, timedelta
from faker import Faker
from .models import (
    Team, App, User, Channel, ChannelMembership, Message, Reaction, 
    GenericEventWrapper, EventAuthedUser
)
from .database import database_transaction
import uuid

fake = Faker()


class SampleDataGenerator:
    """Generate sample data for the Slack-like API simulation"""
    
    def __init__(self):
        self.teams = []
        self.apps = []
        self.users = []
        self.channels = []
        self.messages = []
        
    def generate_team_id(self):
        """Generate Slack-style team ID"""
        chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        return f"T{''.join(random.choices(chars, k=8))}"
    
    def generate_user_id(self):
        """Generate Slack-style user ID"""
        chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        return f"U{''.join(random.choices(chars, k=8))}"
    
    def generate_channel_id(self):
        """Generate Slack-style channel ID"""
        chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        return f"C{''.join(random.choices(chars, k=8))}"
    
    def generate_app_id(self):
        """Generate Slack-style app ID"""
        chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        return f"A{''.join(random.choices(chars, k=8))}"
    
    def generate_event_id(self):
        """Generate Slack-style event ID"""
        chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        return f"Ev{''.join(random.choices(chars, k=8))}"
    
    def generate_timestamp(self, days_ago=30):
        """Generate Slack-style timestamp"""
        base_time = datetime.utcnow() - timedelta(days=random.randint(0, days_ago))
        return f"{int(base_time.timestamp())}.{random.randint(100000, 999999)}"
    
    def create_sample_teams(self, count=3):
        """Create sample teams"""
        teams = []
        for _ in range(count):
            team = Team(
                id=self.generate_team_id(),
                name=fake.company(),
                domain=fake.domain_word()
            )
            teams.append(team)
        self.teams = teams
        return teams
    
    def create_sample_apps(self, count=2):
        """Create sample apps"""
        if not self.teams:
            raise ValueError("Teams must be created before apps")
            
        apps = []
        
        # Ensure each team has at least one app
        for team in self.teams:
            app = App(
                id=self.generate_app_id(),
                name=fake.word().capitalize() + " Bot",
                team_id=team.id
            )
            apps.append(app)
        
        # Create additional apps if count > number of teams
        remaining_count = max(0, count - len(self.teams))
        for _ in range(remaining_count):
            app = App(
                id=self.generate_app_id(),
                name=fake.word().capitalize() + " Bot",
                team_id=random.choice(self.teams).id
            )
            apps.append(app)
            
        self.apps = apps
        return apps
    
    def create_sample_users(self, count=20):
        """Create sample users"""
        if not self.teams:
            raise ValueError("Teams must be created before users")
            
        users = []
        for _ in range(count):
            user = User(
                id=self.generate_user_id(),
                name=fake.user_name(),
                display_name=fake.first_name(),
                real_name=fake.name(),
                email=fake.email(),
                is_bot=fake.boolean(chance_of_getting_true=10),
                team_id=random.choice(self.teams).id
            )
            users.append(user)
        self.users = users
        return users
    
    def create_sample_channels(self, count=10):
        """Create sample channels"""
        if not self.teams:
            raise ValueError("Teams must be created before channels")
            
        channels = []
        channel_types = ['channel', 'group', 'im', 'mpim', 'app_home']
        
        for _ in range(count):
            channel_type = random.choice(channel_types)
            name = None if channel_type in ['im', 'mpim'] else fake.word().lower()
            
            channel = Channel(
                id=self.generate_channel_id(),
                name=name,
                channel_type=channel_type,
                is_private=fake.boolean(chance_of_getting_true=30),
                topic=fake.sentence() if fake.boolean() else None,
                purpose=fake.sentence() if fake.boolean() else None,
                team_id=random.choice(self.teams).id
            )
            channels.append(channel)
        self.channels = channels
        return channels
    
    def create_sample_channel_memberships(self):
        """Create sample channel memberships"""
        if not self.users or not self.channels:
            raise ValueError("Users and channels must be created before memberships")
            
        memberships = []
        
        # Ensure each user is in at least 2-5 channels
        for user in self.users:
            user_channels = random.sample(self.channels, random.randint(2, min(5, len(self.channels))))
            for channel in user_channels:
                membership = ChannelMembership(
                    user_id=user.id,
                    channel_id=channel.id,
                    is_admin=fake.boolean(chance_of_getting_true=20)
                )
                memberships.append(membership)
        
        return memberships
    
    def create_sample_messages(self, count=100):
        """Create sample messages"""
        if not self.users or not self.channels:
            raise ValueError("Users and channels must be created before messages")
            
        messages = []
        
        for _ in range(count):
            user = random.choice(self.users)
            channel = random.choice(self.channels)
            ts = self.generate_timestamp()
            
            # 20% chance of being a threaded message
            thread_ts = None
            if fake.boolean(chance_of_getting_true=20) and messages:
                parent_message = random.choice(messages)
                if parent_message.channel_id == channel.id:
                    thread_ts = parent_message.ts
            
            message = Message(
                id=str(uuid.uuid4()),
                ts=ts,
                text=fake.sentence(nb_words=random.randint(3, 20)),
                user_id=user.id,
                channel_id=channel.id,
                thread_ts=thread_ts,
                message_type='message',
                subtype=None if fake.boolean(chance_of_getting_true=90) else 'bot_message'
            )
            messages.append(message)
        
        self.messages = messages
        return messages
    
    def create_sample_reactions(self, count=50):
        """Create sample reactions"""
        if not self.messages or not self.users:
            raise ValueError("Messages and users must be created before reactions")
            
        reactions = []
        emojis = ['👍', '❤️', '😂', '😮', '😢', '😡', '👎', '🎉', '🔥', '👏']
        used_combinations = set()
        
        attempts = 0
        max_attempts = count * 10  # Allow up to 10x attempts to find unique combinations
        
        while len(reactions) < count and attempts < max_attempts:
            message = random.choice(self.messages)
            user = random.choice(self.users)
            emoji = random.choice(emojis)
            
            # Create a unique key for this combination
            combination_key = (message.id, user.id, emoji)
            
            # Skip if this combination already exists
            if combination_key not in used_combinations:
                reaction = Reaction(
                    message_id=message.id,
                    user_id=user.id,
                    emoji=emoji
                )
                reactions.append(reaction)
                used_combinations.add(combination_key)
            
            attempts += 1
        
        return reactions
    
    def create_sample_events(self, count=50):
        """Create sample GenericEventWrapper events"""
        if not self.teams or not self.apps or not self.users or not self.channels or not self.messages:
            raise ValueError("All other entities must be created before events")
            
        events = []
        event_types = ['message', 'app_mention', 'reaction_added', 'member_joined_channel', 'channel_created']
        
        for _ in range(count):
            team = random.choice(self.teams)
            team_apps = [a for a in self.apps if a.team_id == team.id]
            if not team_apps:
                continue  # Skip if no apps for this team
            app = random.choice(team_apps)
            event_type = random.choice(event_types)
            
            # Generate event data based on type
            if event_type == 'message':
                # Find channels for this team, then messages for those channels
                team_channels = [c for c in self.channels if c.team_id == team.id]
                team_channel_ids = [c.id for c in team_channels]
                team_messages = [m for m in self.messages if m.channel_id in team_channel_ids]
                
                if team_messages:
                    message = random.choice(team_messages)
                    # Find the channel for this message
                    message_channel = next(c for c in team_channels if c.id == message.channel_id)
                    event_data = {
                        "type": "message",
                        "channel": message.channel_id,
                        "user": message.user_id,
                        "text": message.text,
                        "ts": message.ts,
                        "event_ts": message.ts,
                        "channel_type": message_channel.channel_type
                    }
                else:
                    # Fallback event data if no messages found
                    event_data = {
                        "type": "message",
                        "event_ts": self.generate_timestamp()
                    }
            elif event_type == 'app_mention':
                # Find channels for this team, then messages for those channels
                team_channels = [c for c in self.channels if c.team_id == team.id]
                team_channel_ids = [c.id for c in team_channels]
                team_messages = [m for m in self.messages if m.channel_id in team_channel_ids]
                
                if team_messages:
                    message = random.choice(team_messages)
                    event_data = {
                        "type": "app_mention",
                        "channel": message.channel_id,
                        "user": message.user_id,
                        "text": f"<@{app.id}> {message.text}",
                        "ts": message.ts,
                        "event_ts": message.ts
                    }
                else:
                    # Fallback event data if no messages found
                    event_data = {
                        "type": "app_mention",
                        "event_ts": self.generate_timestamp()
                    }
            else:
                event_data = {
                    "type": event_type,
                    "event_ts": self.generate_timestamp()
                }
            
            # Select authed users from the same team
            team_users = [u.id for u in self.users if u.team_id == team.id]
            authed_users = random.sample(team_users, random.randint(1, min(3, len(team_users))))
            
            event = GenericEventWrapper(
                event_id=self.generate_event_id(),
                token=fake.sha256(),
                team_id=team.id,
                api_app_id=app.id,
                event_type="event_callback",
                event_time=int(time.time()) - random.randint(0, 86400 * 30),  # Last 30 days
                event_data=event_data,
                authed_users=authed_users
            )
            events.append(event)
        
        return events
    
    def generate_all_sample_data(self):
        """Generate all sample data and return as dictionary"""
        teams = self.create_sample_teams(3)
        apps = self.create_sample_apps(2)
        users = self.create_sample_users(20)
        channels = self.create_sample_channels(10)
        memberships = self.create_sample_channel_memberships()
        messages = self.create_sample_messages(100)
        reactions = self.create_sample_reactions(50)
        events = self.create_sample_events(50)
        
        return {
            'teams': teams,
            'apps': apps,
            'users': users,
            'channels': channels,
            'memberships': memberships,
            'messages': messages,
            'reactions': reactions,
            'events': events
        }


def populate_database():
    """Populate the database with sample data"""
    generator = SampleDataGenerator()
    sample_data = generator.generate_all_sample_data()
    
    with database_transaction() as session:
        # Add all data to session
        for category, items in sample_data.items():
            for item in items:
                session.add(item)
        
        print(f"Successfully populated database with:")
        for category, items in sample_data.items():
            print(f"  - {len(items)} {category}")

# Alias for easier importing
populate_sample_data = populate_database


if __name__ == "__main__":
    from .database import init_database
    
    # Initialize database
    init_database()
    
    # Populate with sample data
    populate_database()
    
    print("Sample data generation completed!")