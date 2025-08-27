#!/usr/bin/env python3
"""
Realistic usage scenario tests for the Slack Events API Mock Server.
Tests complete workflows, multi-user interactions, threading, and complex scenarios.
"""

import os
import sys
import pytest
import json
import time
import tempfile
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from server.app import app, initialize_app
from data.database import db_manager, init_database
from data.models import (
    Team, App, User, Channel, ChannelMembership, Message, Reaction, 
    GenericEventWrapper, EventAuthedUser
)

# Test configuration
TEST_TOKENS = {
    "team_admin": "xoxb-team-admin-token-123456789",
    "user1": "xoxb-user1-token-123456789", 
    "user2": "xoxb-user2-token-123456789",
    "bot": "xoxb-bot-token-123456789"
}

def get_auth_headers(user_type: str = "team_admin"):
    """Get auth headers for different user types"""
    return {"Authorization": f"Bearer {TEST_TOKENS[user_type]}"}


class TestScenarioBase:
    """Base class for scenario tests"""
    
    @pytest.fixture(scope="session")
    def app_client(self):
        """Create test client with temporary database"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as f:
            test_db_path = f.name
        
        original_db_path = getattr(db_manager, 'database_url', None)
        db_manager.database_url = f"sqlite:///{test_db_path}"
        
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        
        try:
            initialize_app()
            
            with app.test_client() as client:
                yield client
                
        finally:
            if original_db_path:
                db_manager.database_url = original_db_path
            try:
                os.unlink(test_db_path)
            except FileNotFoundError:
                pass


    @pytest.fixture
    def workspace_setup(self, clean_database):
        """Create a realistic workspace setup"""
        db_session = clean_database
        # Create team
        team = Team(id="T12345678", name="Acme Corp", domain="acmecorp")
        db_session.add(team)
        
        # Create app
        app_obj = App(id="A12345678", name="Company Bot", team_id=team.id)
        db_session.add(app_obj)
        
        # Create users with realistic profiles
        users = [
            User(id="U_ALICE", name="alice", real_name="Alice Johnson", 
                 display_name="Alice", email="alice@acmecorp.com", team_id=team.id),
            User(id="U_BOB", name="bob.smith", real_name="Bob Smith", 
                 display_name="Bob", email="bob@acmecorp.com", team_id=team.id),
            User(id="U_CAROL", name="carol.dev", real_name="Carol Davis", 
                 display_name="Carol", email="carol@acmecorp.com", team_id=team.id),
            User(id="U_DAVID", name="david.pm", real_name="David Wilson", 
                 display_name="David", email="david@acmecorp.com", team_id=team.id),
            User(id="U_BOT", name="companybot", real_name="Company Bot", 
                 display_name="CompanyBot", is_bot=True, team_id=team.id)
        ]
        for user in users:
            db_session.add(user)
        
        # Create channels
        channels = [
            Channel(id="C_GENERAL", name="general", channel_type="channel", 
                    is_private=False, topic="Company-wide announcements", team_id=team.id),
            Channel(id="C_RANDOM", name="random", channel_type="channel", 
                    is_private=False, topic="Random discussions", team_id=team.id),
            Channel(id="C_DEV", name="development", channel_type="channel", 
                    is_private=False, topic="Development discussions", team_id=team.id),
            Channel(id="C_PROJECT", name="project-alpha", channel_type="group", 
                    is_private=True, topic="Secret project discussions", team_id=team.id),
            Channel(id="D_ALICE_BOB", name=None, channel_type="im", 
                    is_private=True, team_id=team.id),
            Channel(id="G_LEADS", name="team-leads", channel_type="mpim", 
                    is_private=True, topic="Team leads discussions", team_id=team.id)
        ]
        for channel in channels:
            db_session.add(channel)
        
        # Create realistic channel memberships
        memberships = [
            # Everyone in general
            ChannelMembership(user_id="U_ALICE", channel_id="C_GENERAL"),
            ChannelMembership(user_id="U_BOB", channel_id="C_GENERAL"),
            ChannelMembership(user_id="U_CAROL", channel_id="C_GENERAL"),
            ChannelMembership(user_id="U_DAVID", channel_id="C_GENERAL"),
            
            # Random channel
            ChannelMembership(user_id="U_ALICE", channel_id="C_RANDOM"),
            ChannelMembership(user_id="U_BOB", channel_id="C_RANDOM"),
            ChannelMembership(user_id="U_CAROL", channel_id="C_RANDOM"),
            
            # Development channel (devs only)
            ChannelMembership(user_id="U_ALICE", channel_id="C_DEV"),
            ChannelMembership(user_id="U_CAROL", channel_id="C_DEV"),
            
            # Private project (subset)
            ChannelMembership(user_id="U_ALICE", channel_id="C_PROJECT"),
            ChannelMembership(user_id="U_DAVID", channel_id="C_PROJECT"),
            
            # Direct messages (Alice & Bob)
            ChannelMembership(user_id="U_ALICE", channel_id="D_ALICE_BOB"),
            ChannelMembership(user_id="U_BOB", channel_id="D_ALICE_BOB"),
            
            # Team leads group
            ChannelMembership(user_id="U_ALICE", channel_id="G_LEADS", is_admin=True),
            ChannelMembership(user_id="U_DAVID", channel_id="G_LEADS", is_admin=True)
        ]
        for membership in memberships:
            db_session.add(membership)
        
        db_session.commit()
        
        return {
            'team': team,
            'app': app_obj,
            'users': {user.name: user for user in users},
            'channels': {channel.name or channel.id: channel for channel in channels}
        }

    def generate_timestamp(self, offset_seconds: float = 0) -> str:
        """Generate timestamp with optional offset"""
        return f"{time.time() + offset_seconds:.6f}"

    def post_message(self, client, channel_id: str, text: str, user_id: str = "U_ALICE", 
                     thread_ts: str = None, auth_type: str = "user1") -> Dict:
        """Helper to post a message"""
        message_data = {
            "channel": channel_id,
            "text": text,
            "user": user_id
        }
        if thread_ts:
            message_data["thread_ts"] = thread_ts
        
        response = client.post('/api/chat.postMessage',
                               json=message_data,
                               headers=get_auth_headers(auth_type),
                               content_type='application/json')
        return response.get_json()

    def add_reaction(self, client, channel_id: str, timestamp: str, emoji: str, 
                     user_id: str = "U_BOB", auth_type: str = "user2") -> Dict:
        """Helper to add a reaction"""
        reaction_data = {
            "name": emoji,
            "channel": channel_id,
            "timestamp": timestamp,
            "user": user_id
        }
        
        response = client.post('/api/reactions.add',
                               json=reaction_data,
                               headers=get_auth_headers(auth_type),
                               content_type='application/json')
        return response.get_json()


class TestOnboardingWorkflow(TestScenarioBase):
    """Test new employee onboarding workflow"""
    
    def test_new_employee_onboarding_flow(self, app_client, workspace_setup):
        """Test complete new employee onboarding scenario"""
        # 1. Welcome message in #general from admin/bot
        welcome_response = self.post_message(
            app_client, "C_GENERAL", 
            "👋 Welcome to Acme Corp! Please join our team channels.",
            user_id="U_BOT", auth_type="bot"
        )
        welcome_ts = welcome_response['ts']
        
        # 2. New employee responds
        intro_response = self.post_message(
            app_client, "C_GENERAL",
            "Hi everyone! I'm excited to join the team. I'm a backend developer.",
            user_id="U_CAROL", auth_type="user2"
        )
        
        # 3. Team members react to welcome
        self.add_reaction(app_client, "C_GENERAL", welcome_ts, "wave", "U_ALICE", "user1")
        self.add_reaction(app_client, "C_GENERAL", welcome_ts, "tada", "U_BOB", "user2")
        
        # 4. Team lead invites to development channel via DM
        dm_response = self.post_message(
            app_client, "D_ALICE_BOB",
            "Hey! I saw Carol joined. Should we add her to #development?",
            user_id="U_ALICE", auth_type="user1"
        )
        
        # 5. Reply in DM thread
        reply_response = self.post_message(
            app_client, "D_ALICE_BOB",
            "Yes, definitely! I'll handle the invitation.",
            user_id="U_BOB", auth_type="user2",
            thread_ts=dm_response['ts']
        )
        
        # 6. Welcome message in development channel
        dev_welcome = self.post_message(
            app_client, "C_DEV",
            "Welcome to the dev team Carol! 🎉 Feel free to ask questions.",
            user_id="U_ALICE", auth_type="user1"
        )
        
        # 7. New employee asks a question
        question_response = self.post_message(
            app_client, "C_DEV",
            "Thanks! Quick question - what's our deployment process?",
            user_id="U_CAROL", auth_type="user2"
        )
        
        # 8. Reply in thread with detailed answer
        answer_response = self.post_message(
            app_client, "C_DEV",
            "We use CI/CD with GitHub Actions. I'll share the docs with you.",
            user_id="U_ALICE", auth_type="user1",
            thread_ts=question_response['ts']
        )
        
        # Verify the complete conversation flow
        # Check general channel history
        general_history = app_client.get('/api/conversations.history?channel=C_GENERAL',
                                         headers=get_auth_headers()).get_json()
        
        assert len(general_history['messages']) >= 2
        general_texts = [msg['text'] for msg in general_history['messages']]
        assert any("Welcome to Acme Corp" in text for text in general_texts)
        assert any("excited to join" in text for text in general_texts)
        
        # Check reactions on welcome message
        welcome_msg = next((msg for msg in general_history['messages'] 
                           if "Welcome to Acme Corp" in msg['text']), None)
        assert welcome_msg is not None
        assert 'reactions' in welcome_msg
        assert len(welcome_msg['reactions']) == 2
        
        # Check DM conversation
        dm_history = app_client.get('/api/conversations.history?channel=D_ALICE_BOB',
                                    headers=get_auth_headers()).get_json()
        assert len(dm_history['messages']) >= 2
        
        # Verify threaded conversation
        parent_msg = next((msg for msg in dm_history['messages'] 
                          if msg.get('reply_count', 0) > 0), None)
        assert parent_msg is not None
        assert parent_msg['reply_count'] == 1
        
        # Check development channel
        dev_history = app_client.get('/api/conversations.history?channel=C_DEV',
                                     headers=get_auth_headers()).get_json()
        assert len(dev_history['messages']) >= 3
        
        # Verify question thread
        question_msg = next((msg for msg in dev_history['messages'] 
                            if "deployment process" in msg['text']), None)
        assert question_msg is not None
        assert question_msg.get('reply_count', 0) == 1


class TestProjectDiscussionWorkflow(TestScenarioBase):
    """Test project planning and discussion workflow"""
    
    def test_project_planning_discussion(self, app_client, workspace_setup):
        """Test a realistic project planning discussion"""
        # 1. Project kickoff in private channel
        kickoff_msg = self.post_message(
            app_client, "C_PROJECT",
            "🚀 Project Alpha kickoff! Let's discuss the timeline and requirements.",
            user_id="U_DAVID", auth_type="user1"  # Project manager
        )
        kickoff_ts = kickoff_msg['ts']
        
        # 2. Team lead asks clarifying questions
        question_msg = self.post_message(
            app_client, "C_PROJECT",
            "What's our target launch date? And do we have the API specs ready?",
            user_id="U_ALICE", auth_type="user1"
        )
        
        # 3. PM responds in thread to first question
        timeline_reply = self.post_message(
            app_client, "C_PROJECT",
            "Target is end of Q2. API specs will be ready by next week.",
            user_id="U_DAVID", auth_type="user1",
            thread_ts=question_msg['ts']
        )
        
        # 4. Follow-up question in same thread
        followup_reply = self.post_message(
            app_client, "C_PROJECT",
            "Should we start with the database schema design then?",
            user_id="U_ALICE", auth_type="user1",
            thread_ts=question_msg['ts']
        )
        
        # 5. Agreement reactions
        self.add_reaction(app_client, "C_PROJECT", kickoff_ts, "rocket", "U_ALICE", "user1")
        self.add_reaction(app_client, "C_PROJECT", kickoff_ts, "fire", "U_DAVID", "user1")
        
        # 6. Action items message
        action_msg = self.post_message(
            app_client, "C_PROJECT",
            "📋 Action Items:\n• API specs by Friday\n• DB schema review Monday\n• Sprint planning Tuesday",
            user_id="U_DAVID", auth_type="user1"
        )
        
        # 7. Team members acknowledge
        self.add_reaction(app_client, "C_PROJECT", action_msg['ts'], "white_check_mark", "U_ALICE", "user1")
        
        # 8. Update in team leads channel
        update_msg = self.post_message(
            app_client, "G_LEADS",
            "Project Alpha kicked off. Timeline looks good for Q2 delivery.",
            user_id="U_DAVID", auth_type="user1"
        )
        
        # Verify the discussion flow
        project_history = app_client.get('/api/conversations.history?channel=C_PROJECT',
                                         headers=get_auth_headers()).get_json()
        
        # Should have kickoff, question, and action items messages
        assert len(project_history['messages']) >= 3
        
        # Verify threaded discussion
        threaded_msgs = [msg for msg in project_history['messages'] 
                        if msg.get('reply_count', 0) > 0]
        assert len(threaded_msgs) >= 1
        
        # Verify thread has multiple replies
        main_thread = threaded_msgs[0]
        assert main_thread['reply_count'] == 2
        
        # Verify reactions on kickoff
        kickoff_msg_history = next((msg for msg in project_history['messages'] 
                                   if "Project Alpha kickoff" in msg['text']), None)
        assert kickoff_msg_history is not None
        assert len(kickoff_msg_history['reactions']) == 2
        
        # Verify action items message has acknowledgment
        action_msg_history = next((msg for msg in project_history['messages'] 
                                  if "Action Items" in msg['text']), None)
        assert action_msg_history is not None
        assert len(action_msg_history['reactions']) == 1
        assert action_msg_history['reactions'][0]['name'] == 'white_check_mark'


class TestCrisisManagementWorkflow(TestScenarioBase):
    """Test incident/crisis management workflow"""
    
    def test_production_incident_response(self, app_client, workspace_setup):
        """Test production incident response workflow"""
        # 1. Alert message from monitoring bot
        alert_msg = self.post_message(
            app_client, "C_DEV",
            "🚨 PRODUCTION ALERT: API response times >5s. Error rate: 15%",
            user_id="U_BOT", auth_type="bot"
        )
        alert_ts = alert_msg['ts']
        
        # 2. Immediate acknowledgment
        ack_msg = self.post_message(
            app_client, "C_DEV",
            "I see it. Looking into it now.",
            user_id="U_ALICE", auth_type="user1",
            thread_ts=alert_ts
        )
        
        # 3. Initial investigation findings
        investigation_msg = self.post_message(
            app_client, "C_DEV",
            "Database connection pool seems to be exhausted. Checking logs...",
            user_id="U_ALICE", auth_type="user1",
            thread_ts=alert_ts
        )
        
        # 4. Another team member offers help
        help_msg = self.post_message(
            app_client, "C_DEV",
            "I can help check the cache layer. Might be related.",
            user_id="U_CAROL", auth_type="user2",
            thread_ts=alert_ts
        )
        
        # 5. Status update
        status_msg = self.post_message(
            app_client, "C_DEV",
            "Found the issue - connection leak in user service. Deploying fix now.",
            user_id="U_ALICE", auth_type="user1",
            thread_ts=alert_ts
        )
        
        # 6. Resolution confirmation
        resolution_msg = self.post_message(
            app_client, "C_DEV",
            "✅ Fix deployed. Response times back to normal. Will monitor for 30 mins.",
            user_id="U_ALICE", auth_type="user1",
            thread_ts=alert_ts
        )
        
        # 7. Reactions indicating urgency/resolution
        self.add_reaction(app_client, "C_DEV", alert_ts, "rotating_light", "U_CAROL", "user2")
        self.add_reaction(app_client, "C_DEV", resolution_msg['ts'], "white_check_mark", "U_CAROL", "user2")
        self.add_reaction(app_client, "C_DEV", resolution_msg['ts'], "tada", "U_BOB", "user2")
        
        # 8. Post-mortem scheduling
        postmortem_msg = self.post_message(
            app_client, "C_DEV",
            "Let's do a quick post-mortem tomorrow at 2 PM. I'll create the doc.",
            user_id="U_ALICE", auth_type="user1"
        )
        
        # 9. Notification to management
        mgmt_update = self.post_message(
            app_client, "G_LEADS",
            "Production incident resolved in ~20 mins. Connection pool issue in user service. Post-mortem scheduled.",
            user_id="U_ALICE", auth_type="user1"
        )
        
        # Verify the incident response flow
        dev_history = app_client.get('/api/conversations.history?channel=C_DEV',
                                     headers=get_auth_headers()).get_json()
        
        # Should have alert and post-mortem messages
        alert_messages = [msg for msg in dev_history['messages'] 
                         if "PRODUCTION ALERT" in msg['text']]
        assert len(alert_messages) == 1
        
        # Verify the alert has multiple thread replies (incident discussion)
        alert_msg_history = alert_messages[0]
        assert alert_msg_history['reply_count'] >= 4
        
        # Verify reactions on alert and resolution
        assert len(alert_msg_history['reactions']) >= 1
        
        # Find resolution message and verify it has positive reactions
        resolution_messages = [msg for msg in dev_history['messages'] 
                              if "✅ Fix deployed" in msg['text']]
        assert len(resolution_messages) == 1
        assert len(resolution_messages[0]['reactions']) >= 2
        
        # Verify management was notified
        leads_history = app_client.get('/api/conversations.history?channel=G_LEADS',
                                       headers=get_auth_headers()).get_json()
        mgmt_messages = [msg for msg in leads_history['messages'] 
                        if "incident resolved" in msg['text']]
        assert len(mgmt_messages) == 1


class TestCelebrationWorkflow(TestScenarioBase):
    """Test team celebration and milestone workflows"""
    
    def test_milestone_celebration(self, app_client, workspace_setup):
        """Test celebrating project milestone"""
        # 1. Milestone announcement in general
        milestone_msg = self.post_message(
            app_client, "C_GENERAL",
            "🎉 Amazing news! We just hit 1 million users! Thank you to everyone who made this possible!",
            user_id="U_DAVID", auth_type="user1"
        )
        milestone_ts = milestone_msg['ts']
        
        # 2. Flood of celebratory reactions
        celebration_emojis = ["tada", "rocket", "fire", "clap", "star", "trophy"]
        users = ["U_ALICE", "U_BOB", "U_CAROL"]
        
        for i, emoji in enumerate(celebration_emojis):
            user_id = users[i % len(users)]
            auth_type = ["user1", "user2", "user2"][i % 3]
            self.add_reaction(app_client, "C_GENERAL", milestone_ts, emoji, user_id, auth_type)
        
        # 3. Team members sharing credit in thread
        credit_msg1 = self.post_message(
            app_client, "C_GENERAL",
            "This is incredible! The whole team crushed it 💪",
            user_id="U_ALICE", auth_type="user1",
            thread_ts=milestone_ts
        )
        
        credit_msg2 = self.post_message(
            app_client, "C_GENERAL",
            "Bob's performance optimizations really made the difference!",
            user_id="U_CAROL", auth_type="user2",
            thread_ts=milestone_ts
        )
        
        # 4. Humble response
        humble_msg = self.post_message(
            app_client, "C_GENERAL",
            "Team effort all the way! Carol's testing caught so many issues early 🙏",
            user_id="U_BOB", auth_type="user2",
            thread_ts=milestone_ts
        )
        
        # 5. Planning celebration
        celebration_msg = self.post_message(
            app_client, "C_RANDOM",
            "We should celebrate! Anyone up for team lunch on Friday?",
            user_id="U_ALICE", auth_type="user1"
        )
        celebration_ts = celebration_msg['ts']
        
        # 6. Team members respond enthusiastically
        self.add_reaction(app_client, "C_RANDOM", celebration_ts, "hamburger", "U_BOB", "user2")
        self.add_reaction(app_client, "C_RANDOM", celebration_ts, "pizza", "U_CAROL", "user2")
        self.add_reaction(app_client, "C_RANDOM", celebration_ts, "yes", "U_DAVID", "user1")
        
        # 7. Logistics coordination
        logistics_msg = self.post_message(
            app_client, "C_RANDOM",
            "Perfect! I'll book us a table at Mario's for 12:30 PM Friday 🍽️",
            user_id="U_DAVID", auth_type="user1"
        )
        
        # Verify the celebration flow
        general_history = app_client.get('/api/conversations.history?channel=C_GENERAL',
                                         headers=get_auth_headers()).get_json()
        
        # Find milestone message
        milestone_messages = [msg for msg in general_history['messages'] 
                             if "1 million users" in msg['text']]
        assert len(milestone_messages) == 1
        milestone_history = milestone_messages[0]
        
        # Should have many celebratory reactions
        assert len(milestone_history['reactions']) == 6
        reaction_names = {r['name'] for r in milestone_history['reactions']}
        assert reaction_names == set(celebration_emojis)
        
        # Should have thread discussion
        assert milestone_history['reply_count'] == 3
        
        # Verify celebration planning in random channel
        random_history = app_client.get('/api/conversations.history?channel=C_RANDOM',
                                        headers=get_auth_headers()).get_json()
        
        celebration_messages = [msg for msg in random_history['messages'] 
                               if "team lunch" in msg['text']]
        assert len(celebration_messages) == 1
        celebration_history = celebration_messages[0]
        
        # Should have food-related reactions
        assert len(celebration_history['reactions']) >= 3
        food_reactions = {r['name'] for r in celebration_history['reactions']}
        assert any(emoji in food_reactions for emoji in ['hamburger', 'pizza'])


class TestComplexThreadingWorkflow(TestScenarioBase):
    """Test complex threading scenarios"""
    
    def test_multi_threaded_discussion(self, app_client, workspace_setup):
        """Test multiple parallel thread discussions"""
        # 1. Main topic message
        main_msg = self.post_message(
            app_client, "C_DEV",
            "Planning our Q3 architecture changes. Let's discuss database migration, API versioning, and frontend refactoring.",
            user_id="U_ALICE", auth_type="user1"
        )
        main_ts = main_msg['ts']
        
        # 2. First thread: Database migration discussion
        db_thread1 = self.post_message(
            app_client, "C_DEV",
            "For database migration, I think we should use blue-green deployment approach.",
            user_id="U_BOB", auth_type="user2",
            thread_ts=main_ts
        )
        
        db_thread2 = self.post_message(
            app_client, "C_DEV",
            "Good idea! We'll need to ensure backward compatibility during the transition.",
            user_id="U_CAROL", auth_type="user2",
            thread_ts=main_ts
        )
        
        db_thread3 = self.post_message(
            app_client, "C_DEV",
            "I can create a migration timeline. Should take about 2 weeks including testing.",
            user_id="U_BOB", auth_type="user2",
            thread_ts=main_ts
        )
        
        # 3. Second discussion thread on API versioning
        api_msg = self.post_message(
            app_client, "C_DEV",
            "Separate topic: What's our strategy for API versioning? Header-based or URL-based?",
            user_id="U_CAROL", auth_type="user2"
        )
        api_ts = api_msg['ts']
        
        api_thread1 = self.post_message(
            app_client, "C_DEV",
            "I vote for header-based. More flexible and cleaner URLs.",
            user_id="U_ALICE", auth_type="user1",
            thread_ts=api_ts
        )
        
        api_thread2 = self.post_message(
            app_client, "C_DEV",
            "Header-based +1. But we need good documentation for developers.",
            user_id="U_BOB", auth_type="user2",
            thread_ts=api_ts
        )
        
        # 4. Third discussion on frontend
        frontend_msg = self.post_message(
            app_client, "C_DEV",
            "Frontend refactoring: should we migrate to TypeScript incrementally or all at once?",
            user_id="U_ALICE", auth_type="user1"
        )
        frontend_ts = frontend_msg['ts']
        
        frontend_thread1 = self.post_message(
            app_client, "C_DEV",
            "Incremental migration is safer. We can start with new components.",
            user_id="U_CAROL", auth_type="user2",
            thread_ts=frontend_ts
        )
        
        frontend_thread2 = self.post_message(
            app_client, "C_DEV",
            "Agreed. Less risky and easier to review in smaller chunks.",
            user_id="U_DAVID", auth_type="user1",
            thread_ts=frontend_ts
        )
        
        # 5. Cross-thread reference
        cross_ref_msg = self.post_message(
            app_client, "C_DEV",
            "The DB migration timeline will affect our API versioning rollout. We should coordinate these efforts.",
            user_id="U_ALICE", auth_type="user1"
        )
        
        # 6. Reactions indicating progress/agreement
        self.add_reaction(app_client, "C_DEV", main_ts, "thinking_face", "U_DAVID", "user1")
        self.add_reaction(app_client, "C_DEV", api_ts, "white_check_mark", "U_DAVID", "user1")
        self.add_reaction(app_client, "C_DEV", frontend_ts, "typescript", "U_BOB", "user2")  # Custom emoji
        
        # Verify the complex threading structure
        dev_history = app_client.get('/api/conversations.history?channel=C_DEV',
                                     headers=get_auth_headers()).get_json()
        
        # Should have multiple parent messages with threads
        threaded_messages = [msg for msg in dev_history['messages'] 
                            if msg.get('reply_count', 0) > 0]
        assert len(threaded_messages) >= 3
        
        # Verify each thread has correct reply count
        thread_counts = {msg['reply_count'] for msg in threaded_messages}
        assert 3 in thread_counts  # DB migration thread has 3 replies
        assert 2 in thread_counts  # API and frontend threads have 2 replies each
        
        # Verify main coordination thread is longest
        main_thread = next((msg for msg in threaded_messages 
                           if "architecture changes" in msg['text']), None)
        assert main_thread is not None
        assert main_thread['reply_count'] == 3


class TestPerformanceScenarios(TestScenarioBase):
    """Test scenarios with large amounts of data"""
    
    def test_high_volume_conversation(self, app_client, workspace_setup):
        """Test handling high-volume conversation with many messages and reactions"""
        channel_id = "C_GENERAL"
        
        # Create a busy conversation with many messages
        base_time = time.time()
        message_timestamps = []
        
        # Post 50 messages from various users
        users = ["U_ALICE", "U_BOB", "U_CAROL", "U_DAVID"]
        for i in range(50):
            user_id = users[i % len(users)]
            auth_type = ["user1", "user2", "user2", "user1"][i % 4]
            
            msg = self.post_message(
                app_client, channel_id,
                f"Message {i+1}: This is part of a busy discussion about our quarterly goals.",
                user_id=user_id, auth_type=auth_type
            )
            message_timestamps.append(msg['ts'])
        
        # Create some threaded discussions FIRST
        thread_parents = message_timestamps[::15]  # Every 15th message becomes a thread parent
        for parent_ts in thread_parents:
            for k in range(5):  # 5 replies per thread
                user_id = users[k % len(users)]
                auth_type = ["user1", "user2", "user2", "user1"][k % 4]
                self.post_message(
                    app_client, channel_id,
                    f"Thread reply {k+1}: Following up on the discussion.",
                    user_id=user_id, auth_type=auth_type,
                    thread_ts=parent_ts
                )
        
        # Now add reactions to some of the thread replies (which are now the most recent)
        # Get the conversation history to find the actual most recent messages
        response = app_client.get('/api/conversations.history?channel=C_GENERAL&limit=10',
                                  headers=get_auth_headers())
        recent_data = response.get_json()
        popular_messages = [msg['ts'] for msg in recent_data['messages'][:5]]  # First 5 (most recent)
        emojis = ["thumbsup", "heart", "fire", "rocket", "tada"]
        
        # Add ALL reactions to just these few messages to guarantee they'll have reactions
        for msg_ts in popular_messages:
            for j, emoji in enumerate(emojis):
                user_id = users[j % len(users)]
                auth_type = ["user1", "user2", "user2", "user1"][j % 4]
                self.add_reaction(app_client, channel_id, msg_ts, emoji, user_id, auth_type)
        
        # Test pagination with large dataset
        response = app_client.get('/api/conversations.history?channel=C_GENERAL&limit=20',
                                  headers=get_auth_headers())
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['ok'] is True
        assert len(data['messages']) == 20
        assert data.get('has_more') is True
        assert 'response_metadata' in data
        
        # Test retrieving next page
        cursor = data['response_metadata']['next_cursor']
        response2 = app_client.get(f'/api/conversations.history?channel=C_GENERAL&limit=20&cursor={cursor}',
                                   headers=get_auth_headers())
        assert response2.status_code == 200
        
        data2 = response2.get_json()
        assert data2['ok'] is True
        assert len(data2['messages']) == 20
        
        # Verify messages are different between pages
        page1_ts = {msg['ts'] for msg in data['messages']}
        page2_ts = {msg['ts'] for msg in data2['messages']}
        assert len(page1_ts.intersection(page2_ts)) == 0  # No overlap
        
        # Test message with many reactions
        messages_with_reactions = [msg for msg in data['messages'] 
                                  if msg.get('reactions')]
        assert len(messages_with_reactions) > 0
        
        # Verify reaction structure
        popular_msg = messages_with_reactions[0]
        assert len(popular_msg['reactions']) == len(emojis)
        
        # Test threaded messages
        threaded_messages = [msg for msg in data['messages'] + data2['messages']
                            if msg.get('reply_count', 0) > 0]
        assert len(threaded_messages) > 0
        
        # Verify thread reply counts
        for thread_msg in threaded_messages:
            assert thread_msg['reply_count'] == 5



if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])