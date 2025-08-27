#!/usr/bin/env python3
"""
Startup script for the Slack Events API Mock Server
"""

import os
import sys
import logging
from pathlib import Path

# Add parent directory to path to import data modules
sys.path.append(str(Path(__file__).parent.parent))

from data.database import db_manager, init_database, reset_database
from data.sample_data import populate_sample_data
from server.app import app, initialize_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_database():
    """Set up database with sample data"""
    try:
        logger.info("Setting up database...")
        
        # Check if we should reset the database
        reset_db = os.environ.get('RESET_DB', 'false').lower() == 'true'
        
        if reset_db:
            logger.info("Resetting database...")
            reset_database()
        
        # Initialize database
        init_database()
        
        # Check if we should populate sample data
        populate_sample = os.environ.get('POPULATE_SAMPLE_DATA', 'true').lower() == 'true'
        
        if populate_sample:
            logger.info("Populating sample data...")
            populate_sample_data()
        
        logger.info("Database setup complete")
        
    except Exception as e:
        logger.error(f"Error setting up database: {e}")
        raise

def main():
    """Main function to run the server"""
    logger.info("=" * 60)
    logger.info("🚀 Starting Slack Events API Mock Server")
    logger.info("=" * 60)
    
    try:
        # Setup database
        setup_database()
        
        # Initialize Flask app
        initialize_app()
        
        # Get configuration
        host = os.environ.get('HOST', '127.0.0.1')
        port = int(os.environ.get('PORT', 5000))
        debug = os.environ.get('DEBUG', 'true').lower() == 'true'
        
        logger.info(f"🌐 Server URL: http://{host}:{port}")
        logger.info(f"🔧 Debug mode: {debug}")
        logger.info(f"📊 Health check: http://{host}:{port}/health")
        logger.info(f"🧪 API test: http://{host}:{port}/api/test")
        logger.info("-" * 60)
        logger.info("📋 Available API endpoints:")
        logger.info("   Events API:")
        logger.info(f"   • POST   http://{host}:{port}/api/events")
        logger.info("   Conversations API:")
        logger.info(f"   • GET    http://{host}:{port}/api/conversations.list")
        logger.info(f"   • GET    http://{host}:{port}/api/conversations.history")
        logger.info(f"   • GET    http://{host}:{port}/api/conversations.info")
        logger.info("   Chat API:")
        logger.info(f"   • POST   http://{host}:{port}/api/chat.postMessage")
        logger.info(f"   • POST   http://{host}:{port}/api/chat.update")
        logger.info(f"   • POST   http://{host}:{port}/api/chat.delete")
        logger.info("   Reactions API:")
        logger.info(f"   • POST   http://{host}:{port}/api/reactions.add")
        logger.info(f"   • POST   http://{host}:{port}/api/reactions.remove")
        logger.info("   Users API:")
        logger.info(f"   • GET    http://{host}:{port}/api/users.list")
        logger.info(f"   • GET    http://{host}:{port}/api/users.info")
        logger.info("   Team API:")
        logger.info(f"   • GET    http://{host}:{port}/api/team.info")
        logger.info("   Auth API:")
        logger.info(f"   • GET    http://{host}:{port}/api/auth.test")
        logger.info("-" * 60)
        logger.info("🔑 Authentication: Include 'Authorization: Bearer <token>' header")
        logger.info("   (Any token with 10+ characters will work for testing)")
        logger.info("=" * 60)
        
        # Run the Flask development server
        app.run(
            host=host,
            port=port,
            debug=debug,
            threaded=True
        )
        
    except KeyboardInterrupt:
        logger.info("👋 Server stopped by user")
    except Exception as e:
        logger.error(f"💥 Server error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()