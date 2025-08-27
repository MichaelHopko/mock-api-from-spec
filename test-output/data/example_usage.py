#!/usr/bin/env python3
"""
Example usage of the Slack-like database schema

This script demonstrates how to:
1. Initialize the database
2. Create sample data
3. Query the data
4. Perform CRUD operations
"""

from data import (
    init_database, 
    database_transaction,
    populate_database,
    Team, User, Channel, Message, GenericEventWrapper
)


def demonstrate_crud_operations():
    """Demonstrate basic CRUD operations"""
    print("\n=== CRUD Operations Demo ===")
    
    with database_transaction() as session:
        # READ: Query some data
        print("\n1. Reading data:")
        teams = session.query(Team).limit(3).all()
        for team in teams:
            print(f"  Team: {team.name} ({team.id})")
        
        users = session.query(User).limit(5).all()
        for user in users:
            print(f"  User: {user.real_name} (@{user.name}) - {user.email}")
        
        # READ: Complex query with relationships
        print("\n2. Complex query - Messages with user and channel info:")
        messages_with_info = session.query(Message)\
            .join(User)\
            .join(Channel)\
            .limit(5)\
            .all()
        
        for msg in messages_with_info:
            print(f"  [{msg.channel.name or 'DM'}] @{msg.user.name}: {msg.text[:50]}...")
        
        # READ: Query events
        print("\n3. Recent events:")
        events = session.query(GenericEventWrapper)\
            .order_by(GenericEventWrapper.event_time.desc())\
            .limit(5)\
            .all()
        
        for event in events:
            event_type = event.event_data.get('type', 'unknown')
            print(f"  Event {event.event_id}: {event_type} in team {event.team_id}")
        
        # CREATE: Add a new user
        print("\n4. Creating new user:")
        new_user = User(
            id="U123456789",
            name="demo_user",
            display_name="Demo User",
            real_name="Demo User",
            email="demo@example.com",
            team_id=teams[0].id if teams else "T123456789"
        )
        session.add(new_user)
        session.flush()  # Get the ID without committing
        print(f"  Created user: {new_user.real_name} ({new_user.id})")
        
        # UPDATE: Modify the user
        print("\n5. Updating user:")
        new_user.display_name = "Updated Demo User"
        print(f"  Updated display name to: {new_user.display_name}")
        
        # The user will be deleted when transaction rolls back (for demo purposes)
        print("\n6. User will be cleaned up when transaction ends (demo mode)")


def demonstrate_queries():
    """Demonstrate various query patterns"""
    print("\n=== Query Patterns Demo ===")
    
    with database_transaction() as session:
        # Count queries
        print("\n1. Counts:")
        team_count = session.query(Team).count()
        user_count = session.query(User).count()
        message_count = session.query(Message).count()
        event_count = session.query(GenericEventWrapper).count()
        
        print(f"  Teams: {team_count}")
        print(f"  Users: {user_count}")
        print(f"  Messages: {message_count}")
        print(f"  Events: {event_count}")
        
        # Aggregation queries
        print("\n2. Messages per channel:")
        from sqlalchemy import func
        
        channel_message_counts = session.query(
            Channel.name,
            func.count(Message.id).label('message_count')
        ).join(Message).group_by(Channel.id).limit(5).all()
        
        for channel_name, count in channel_message_counts:
            print(f"  #{channel_name or 'unnamed'}: {count} messages")
        
        # Filter queries
        print("\n3. Bot users:")
        bot_users = session.query(User).filter(User.is_bot == True).all()
        for bot in bot_users:
            print(f"  Bot: {bot.name}")
        
        # Event filtering
        print("\n4. Message events:")
        message_events = session.query(GenericEventWrapper)\
            .filter(GenericEventWrapper.event_data['type'].astext == 'message')\
            .limit(3)\
            .all()
        
        for event in message_events:
            event_data = event.event_data
            print(f"  Message event in channel {event_data.get('channel', 'unknown')}")


def main():
    """Main demonstration function"""
    print("Slack-like Database Schema Demo")
    print("=" * 40)
    
    # Initialize database
    print("Initializing database...")
    init_database()
    
    # Check if we need to populate with sample data
    with database_transaction() as session:
        team_count = session.query(Team).count()
        
        if team_count == 0:
            print("No data found. Generating sample data...")
            populate_database()
        else:
            print(f"Found existing data ({team_count} teams)")
    
    # Run demonstrations
    demonstrate_queries()
    demonstrate_crud_operations()
    
    print("\n" + "=" * 40)
    print("Demo completed! Database file: data/database.db")
    print("\nYou can now use this schema for your API simulation.")


if __name__ == "__main__":
    main()