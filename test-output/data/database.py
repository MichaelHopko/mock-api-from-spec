import os
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import Engine
import sqlite3
from contextlib import contextmanager
from .models import Base
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(DATABASE_DIR, 'database.db')
DATABASE_URL = f'sqlite:///{DATABASE_PATH}'


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign key constraints and optimize SQLite settings"""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        # Enable foreign key constraints
        cursor.execute("PRAGMA foreign_keys=ON")
        # Set WAL mode for better concurrency
        cursor.execute("PRAGMA journal_mode=WAL")
        # Optimize synchronous mode for better performance
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Set cache size (in KB)
        cursor.execute("PRAGMA cache_size=10000")
        cursor.close()


class DatabaseManager:
    """Database manager for handling connections and sessions"""
    
    def __init__(self, database_url: str = DATABASE_URL):
        self.database_url = database_url
        self.engine = None
        self.session_factory = None
        
    def initialize(self):
        """Initialize the database engine and create tables"""
        logger.info(f"Initializing database at: {self.database_url}")
        
        # Create engine
        self.engine = create_engine(
            self.database_url,
            echo=False,  # Set to True for SQL debugging
            pool_pre_ping=True,
            connect_args={'check_same_thread': False}
        )
        
        # Create session factory
        self.session_factory = sessionmaker(bind=self.engine)
        
        # Create all tables
        self.create_tables()
        
        logger.info("Database initialized successfully")
        
    def create_tables(self):
        """Create all database tables"""
        if self.engine is None:
            raise RuntimeError("Database engine not initialized. Call initialize() first.")
            
        logger.info("Creating database tables...")
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created successfully")
        
    def drop_tables(self):
        """Drop all database tables (useful for testing)"""
        if self.engine is None:
            raise RuntimeError("Database engine not initialized. Call initialize() first.")
            
        logger.info("Dropping database tables...")
        Base.metadata.drop_all(self.engine)
        logger.info("Database tables dropped successfully")
        
    def recreate_tables(self):
        """Drop and recreate all tables"""
        self.drop_tables()
        self.create_tables()
        
    @contextmanager
    def get_session(self) -> Session:
        """Get a database session with automatic cleanup"""
        if self.session_factory is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
            
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
            
    def get_session_factory(self):
        """Get the session factory for dependency injection"""
        if self.session_factory is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self.session_factory


# Global database manager instance
db_manager = DatabaseManager()


def init_database():
    """Initialize the database (convenience function)"""
    db_manager.initialize()


def get_db_session():
    """Get a database session (convenience function)"""
    return db_manager.get_session()


def reset_database():
    """Reset the database (drop and recreate all tables)"""
    db_manager.recreate_tables()


# Database health check
def check_database_health() -> bool:
    """Check if the database is accessible and healthy"""
    try:
        with db_manager.get_session() as session:
            # Simple query to test connectivity
            session.execute(text("SELECT 1"))
            return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


# Context manager for transactions
@contextmanager
def database_transaction():
    """Context manager for database transactions with automatic rollback on error"""
    with db_manager.get_session() as session:
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Transaction failed: {e}")
            raise