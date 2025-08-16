# src/codegraphcontext/core/database.py
import os
import logging
import threading
from typing import Optional

from neo4j import GraphDatabase, Driver

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    Singleton class to manage Neo4j database connections.
    """
    _instance = None
    _driver: Optional[Driver] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return

        self.neo4j_uri = os.getenv('NEO4J_URI')
        self.neo4j_username = os.getenv('NEO4J_USERNAME', 'neo4j')
        self.neo4j_password = os.getenv('NEO4J_PASSWORD')
        self._initialized = True

    def get_driver(self) -> Driver:
        """Get the Neo4j driver instance"""
        if self._driver is None:
            with self._lock:
                if self._driver is None:
                    if not all([self.neo4j_uri, self.neo4j_username, self.neo4j_password]):
                        raise ValueError(
                            "Neo4j credentials must be set via environment variables:\n"
                            "- NEO4J_URI\n"
                            "- NEO4J_USERNAME\n"
                            "- NEO4J_PASSWORD"
                        )

                    logger.info(f"Creating Neo4j driver connection to {self.neo4j_uri}")
                    self._driver = GraphDatabase.driver(
                        self.neo4j_uri,
                        auth=(self.neo4j_username, self.neo4j_password)
                    )
                    # Test the connection
                    try:
                        with self._driver.session() as session:
                            session.run("RETURN 1").consume()
                        logger.info("Neo4j connection established successfully")
                    except Exception as e:
                        logger.error(f"Failed to connect to Neo4j: {e}")
                        if self._driver:
                            self._driver.close()
                        self._driver = None
                        raise
        return self._driver

    def close_driver(self):
        """Close the Neo4j driver"""
        if self._driver is not None:
            with self._lock:
                if self._driver is not None:
                    logger.info("Closing Neo4j driver")
                    self._driver.close()
                    self._driver = None

    def is_connected(self) -> bool:
        """Check if connected to database"""
        if self._driver is None:
            return False
        try:
            with self._driver.session() as session:
                session.run("RETURN 1").consume()
            return True
        except Exception:
            return False