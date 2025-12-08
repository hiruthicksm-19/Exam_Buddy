"""
Database utilities for Exam Buddy.
Handles all database operations with proper connection management.
"""
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from pymongo import MongoClient, server_api
from pymongo.errors import PyMongoError

class MongoDBManager:
    """MongoDB database manager for Exam Buddy."""
    
    def __init__(self):
        """Initialize MongoDB connection and setup collections."""
        # Try MONGODB_URI first, fall back to MONGO_URI if not found
        self.uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
        if not self.uri:
            raise ValueError("Neither MONGODB_URI nor MONGO_URI environment variable is set")
            
        print(f"🔌 Connecting to MongoDB...")
        print(f"   URI: {self.uri}")
        
        try:
            # Connect with a 5-second timeout
            self.client = MongoClient(
                self.uri, 
                server_api=server_api.ServerApi('1'),
                connectTimeoutMS=5000,
                serverSelectionTimeoutMS=5000
            )
            
            # Test the connection
            self.client.admin.command('ping')
            print("✅ Successfully connected to MongoDB!")
            
            # Set the database
            self.db = self.client['zenark_db']
            
            # Initialize collections
            self.sessions = self.db['exam_buddy_session']
            self.students = self.db['student_marks']
            
            # Create indexes
            self._create_indexes()
            
            # Print database info
            #self._print_db_info()
            
        except Exception as e:
            print(f"❌ Failed to connect to MongoDB: {e}")
            raise

    def _create_indexes(self):
        """Create necessary indexes for optimal query performance."""
        try:
            # Drop all existing indexes first to avoid conflicts
            self.sessions.drop_indexes()
            
            # TTL index for session expiration (7 days)
            self.sessions.create_index("expires_at", expireAfterSeconds=0, name="expires_at_ttl")
            
            # Index for faster lookups - sparse unique index on student_id
            self.sessions.create_index(
                "session_id", 
                unique=True, 
                name="session_id_unique"
            )
            
            # Sparse unique index on student_id to allow multiple nulls
            self.sessions.create_index(
                [("student_id", 1)], 
                unique=True, 
                sparse=True,
                name="student_id_unique_sparse"
            )
            
            # Index for student marks
            self.students.create_index(
                "student_id", 
                unique=True, 
                sparse=True,  # Allow multiple null values
                name="student_marks_id_unique"
            )
            
            print("✅ Database indexes created/verified")
            
        except Exception as e:
            print(f"❌ Error creating indexes: {e}")
            print("⚠️ Continuing with existing indexes...")

    def _print_db_info(self):
        """Print database information for debugging."""
        try:
            # List all databases
            db_list = self.client.list_database_names()
            print(f"\n📚 Available databases ({len(db_list)}):")
            for db_name in sorted(db_list):
                if db_name in ['admin', 'local', 'config']:
                    continue
                print(f"   - {db_name}")
            
            # Access the pqe_db database
           # print(f"\n📂 Using database: zenark_db")
            
            # List all collections for debugging
            # print("\n📁 Available collections:")
            # for coll_name in self.db.list_collection_names():
            #     print(f"   - {coll_name}")
                
            # Print collection counts
            print("\n📊 Collection counts:")
            for coll_name in self.db.list_collection_names():
                count = self.db[coll_name].count_documents({})
                print(f"   - {coll_name}: {count} documents")
                
        except Exception as e:
            print(f"⚠️ Could not print database info: {e}")

    # Session management methods
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session by ID and update last activity timestamp."""
        try:
            return self.sessions.find_one_and_update(
                {"session_id": session_id},
                {"$set": {"last_activity": datetime.utcnow()}},
                return_document=True
            )
        except PyMongoError as e:
            print(f"Error getting session: {e}")
            return None

    def create_session(self, session_data: Dict) -> Optional[str]:
        """Create a new session and return the session ID."""
        try:
            result = self.sessions.insert_one(session_data)
            return str(result.inserted_id)
        except PyMongoError as e:
            print(f"Error creating session: {e}")
            return None

    def update_session(self, session_id: str, update_data: Dict) -> bool:
        """Update an existing session."""
        try:
            result = self.sessions.update_one(
                {"session_id": session_id},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            print(f"Error updating session: {e}")
            return False

    # Student management methods
    def get_student(self, student_id: str) -> Optional[Dict]:
        """Get student by ID."""
        try:
            student = self.students.find_one({"student_id": student_id})
            if student and '_id' in student:
                student['_id'] = str(student['_id'])
            return student
        except PyMongoError as e:
            print(f"Error getting student: {e}")
            return None

    def update_student(self, student_id: str, update_data: Dict) -> bool:
        """Update student data."""
        try:
            result = self.students.update_one(
                {"student_id": student_id},
                {"$set": update_data},
                upsert=True
            )
            return result.modified_count > 0 or result.upserted_id is not None
        except PyMongoError as e:
            print(f"Error updating student: {e}")
            return False

    # Message management methods
    def save_message(self, student_id: str, role: str, content: str) -> bool:
        """Save a message to the conversation history."""
        try:
            message = {
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow()
            }
            
            # Update the conversation in the session
            result = self.sessions.update_one(
                {"student_id": student_id},
                {
                    "$push": {"conversation": {"$each": [message], "$slice": -80}},  # Keep last 80 messages
                    "$set": {
                        "last_activity": datetime.utcnow(),
                        "expires_at": datetime.utcnow() + timedelta(days=7)
                    }
                },
                upsert=True
            )
            
            return result.modified_count > 0 or result.upserted_id is not None
        except PyMongoError as e:
            print(f"Error saving message: {e}")
            return False

    def get_conversation(self, student_id: str, limit: int = 80) -> List[Dict]:
        """Get conversation for a student."""
        try:
            session = self.sessions.find_one(
                {"student_id": student_id},
                {"conversation": {"$slice": -limit}}  # Get last N messages
            )
            return session.get("conversation", []) if session else []
        except PyMongoError as e:
            print(f"Error getting conversation: {e}")
            return []

    # Context management
    def save_context(self, student_id: str, context: str) -> bool:
        """Save context for a student's session."""
        try:
            result = self.sessions.update_one(
                {"student_id": student_id},
                {"$set": {"context": context}},
                upsert=True
            )
            return result.modified_count > 0 or result.upserted_id is not None
        except PyMongoError as e:
            print(f"Error saving context: {e}")
            return False

    def get_context(self, student_id: str) -> str:
        """Get context for a student's session."""
        try:
            session = self.sessions.find_one(
                {"student_id": student_id},
                {"context": 1}
            )
            return session.get("context", "") if session else ""
        except PyMongoError as e:
            print(f"Error getting context: {e}")
            return ""

    def get_recent_messages(self, student_id: str, limit: int = 3) -> List[Dict]:
        """
        Get the most recent messages for a student.
        
        Args:
            student_id: The student's ID
            limit: Maximum number of recent messages to return (default: 3)
            
        Returns:
            List of message dictionaries with 'role' and 'content' keys
        """
        try:
            # Get the most recent session for the student
            session = self.sessions.find_one(
                {"student_id": student_id},
                sort=[("last_activity", -1)]  # Get most recent session first
            )
            
            if not session or "conversation" not in session:
                return []
                
            # Return the most recent messages
            return session["conversation"][-limit:]
            
        except PyMongoError as e:
            print(f"Error getting recent messages: {e}")
            return []

# Create a global instance
db_manager = MongoDBManager()