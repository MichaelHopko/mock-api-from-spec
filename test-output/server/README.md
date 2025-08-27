# Slack Events API Mock Server

A comprehensive Flask-based mock server that implements the Slack Events API with full state persistence using SQLite.

## Features

- **Complete Slack Events API Implementation**
  - Event callbacks and URL verification
  - Conversations API (list, history, info)
  - Chat API (post, update, delete messages)
  - Reactions API (add, remove reactions)
  - Users API (list, info)
  - Team API (info)
  - Auth API (test)

- **Full State Persistence**
  - SQLite database with proper relationships
  - Message threading support
  - Channel membership management
  - User authentication simulation
  - Reaction handling

- **Development Features**
  - CORS support for frontend testing
  - Comprehensive logging
  - Health checks
  - Sample data generation
  - Realistic Slack-style IDs and timestamps

## Quick Start

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Server**
   ```bash
   python server/run.py
   ```
   
   Or directly:
   ```bash
   python server/app.py
   ```

3. **Access the API**
   - Server URL: http://localhost:5000
   - Health check: http://localhost:5000/health
   - API test: http://localhost:5000/api/test

## Finding Available IDs

The server generates random IDs for channels, users, and teams. To find the actual IDs for testing, query the SQLite database:

### List Available Channels
```bash
sqlite3 data/database.db "SELECT id, name, channel_type FROM channels;"
```

### List Available Users
```bash
sqlite3 data/database.db "SELECT id, name, real_name FROM users;"
```

### List Available Teams
```bash
sqlite3 data/database.db "SELECT id, name FROM teams;"
```

### Example Query Results
```
# Channels
C02974UO1|general|channel
C0Q0VLM10|random|channel
C14TKZ2T1||im

# Users
U08NMP06Y|johnsmith|John Smith
U08WYSWVS|janedoe|Jane Doe
U0OU9E19B|testbot|Test Bot
```

Use these actual IDs in your API calls instead of the placeholder IDs shown in the examples below.

## Configuration

Set these environment variables to customize the server:

- `HOST`: Server host (default: 127.0.0.1)
- `PORT`: Server port (default: 5000)
- `DEBUG`: Enable debug mode (default: true)
- `RESET_DB`: Reset database on startup (default: false)
- `POPULATE_SAMPLE_DATA`: Load sample data (default: true)
- `SECRET_KEY`: Flask secret key (default: dev key)

## Authentication

All API endpoints (except health and test) require authentication. Include the Authorization header:

```
Authorization: Bearer your-token-here
```

For testing, any token with 10+ characters will work.

## API Endpoints

### Events API
- `POST /api/events` - Handle Slack events and URL verification

### Conversations API
- `GET /api/conversations.list` - List conversations
- `GET /api/conversations.history` - Get conversation history
- `GET /api/conversations.info` - Get conversation info

### Chat API
- `POST /api/chat.postMessage` - Post a message
- `POST /api/chat.update` - Update a message
- `POST /api/chat.delete` - Delete a message

### Reactions API
- `POST /api/reactions.add` - Add reaction to message
- `POST /api/reactions.remove` - Remove reaction from message

### Users API
- `GET /api/users.list` - List users
- `GET /api/users.info` - Get user info

### Team API
- `GET /api/team.info` - Get team info

### Auth API
- `GET /api/auth.test` - Test authentication

## Example Usage

**Note**: Replace `C12345678` and `U12345678` with actual IDs from your database (see "Finding Available IDs" section above).

### Post a Message
```bash
curl -X POST http://localhost:5000/api/chat.postMessage \
  -H "Authorization: Bearer test-token-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "C12345678",
    "text": "Hello, World!",
    "user": "U12345678"
  }'
```

### Get Conversation History
```bash
curl "http://localhost:5000/api/conversations.history?channel=C12345678&limit=10" \
  -H "Authorization: Bearer test-token-12345"
```

### Add a Reaction
```bash
curl -X POST http://localhost:5000/api/reactions.add \
  -H "Authorization: Bearer test-token-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "thumbsup",
    "channel": "C12345678",
    "timestamp": "1234567890.123456"
  }'
```

## Database

The server uses SQLite for persistence with the following models:

- **Team**: Slack workspaces
- **App**: Slack applications
- **User**: Team members and bots
- **Channel**: Conversations (channels, DMs, etc.)
- **ChannelMembership**: User-channel relationships
- **Message**: Chat messages with threading
- **Reaction**: Message reactions
- **GenericEventWrapper**: Event storage
- **EventAuthedUser**: Event-user relationships

Database file: `data/database.db`

## Development

The server is designed to behave like the real Slack API:

- Proper HTTP status codes
- Slack-style response formats
- Realistic error handling
- Pagination support
- Thread-aware messaging
- Comprehensive logging

Perfect for developing and testing Slack applications locally!