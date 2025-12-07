import os
from datetime import datetime, timedelta
from bson import ObjectId
from pymongo import MongoClient, ReturnDocument
from pymongo.server_api import ServerApi
from pymongo.errors import DuplicateKeyError
from bson.errors import InvalidId
from dotenv import load_dotenv
from typing import Dict, List, Optional, Any, Tuple

load_dotenv()

class MongoDBManager:
    def __init__(self):
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
                server_api=ServerApi('1'),
                connectTimeoutMS=5000,
                serverSelectionTimeoutMS=5000
            )
            
            # Test the connection
            print("   Testing connection...")
            self.client.admin.command('ping')
            print("   ✓ Successfully connected to MongoDB!")
            
            # List all databases for debugging
            print("\n📊 Available databases:")
            db_names = self.client.list_database_names()
            for db_name in db_names:
                print(f"   - {db_name}")
            
            # Access the zenark_db database
            print(f"\n📂 Using database: zenark_db")
            self.db = self.client['zenark_db']
            
            # List all collections for debugging
            print("\n📁 Available collections:")
            collections = self.db.list_collection_names()
            for collection in collections:
                print(f"   - {collection}")
            
            # Access collections with explicit names
            print("\n🔍 Accessing collections...")
            self.students = self.db['student_marks']
            self.sessions = self.db['exam_buddy_session']
            
            # Verify collections exist
            collections = self.db.list_collection_names()
            if 'student_marks' not in collections:
                print("⚠️ Warning: 'student_marks' collection not found in database")
            if 'exam_buddy_session' not in collections:
                print("ℹ️ 'exam_buddy_session' collection not found, it will be created when needed")
            
            # Create indexes
            print("   ✓ Collections accessed successfully")
            self._create_indexes()
            
            # Print sample data for debugging
            print("\n👤 Sample student data:")
            sample = self.students.find_one()
            if sample:
                print(f"   Found student: {sample}")
                # Print all students for debugging
                print("\n📝 All students:")
                for student in self.students.find({}):
                    print(f"   - {student.get('name')} (ID: {student.get('_id')})")
            else:
                print("   ❌ No student data found in the 'student_marks' collection")
                print("   Make sure your collection name is 'student_marks' and contains student data")
                
            # Additional debug: Try to find the specific student
            print("\n🔍 Looking for student with ID: 693423f8cf67390a52555eef")
            try:
                from bson import ObjectId
                student = self.students.find_one({"_id": ObjectId("693423f8cf67390a52555eef")})
                if student:
                    print(f"   ✓ Found student: {student}")
                else:
                    print("   ❌ Student not found with the specified ID")
                    print("   Available student IDs:")
                    for s in self.students.find({}, {"_id": 1, "name": 1}):
                        print(f"   - {s.get('name')}: {s.get('_id')}")
            except Exception as e:
                print(f"   ❌ Error searching for student: {str(e)}")
                
        except Exception as e:
            print(f"\n❌ MongoDB connection error: {str(e)}")
            print("\n🔧 Please check:")
            print("   1. Your MongoDB URI is correct and includes the database name")
            print("   2. Your network connection to MongoDB is working")
            print("   3. The database and collections exist")
            print("   4. The MongoDB server is running and accessible")
            print("   5. Your IP is whitelisted in MongoDB Atlas (if using Atlas)")
            raise
    
    def _create_indexes(self):
        """Create necessary indexes for the database."""
        self.sessions.create_index("session_id", unique=True)
        self.sessions.create_index("expires_at", expireAfterSeconds=0)  # TTL index
        self.sessions.create_index("last_activity")  # For session cleanup
        
    def update_session(self, session_id: str, update_data: Dict) -> bool:
        """
        Update session data.
        
        Args:
            session_id: Session ID to update
            update_data: Dictionary of fields to update
            
        Returns:
            True if update was successful, False otherwise
        """
        try:
            # Ensure last_activity is always updated if not explicitly set
            if "last_activity" not in update_data:
                update_data["last_activity"] = datetime.utcnow()
                
            # Handle $push operations separately
            push_operations = {k: v for k, v in update_data.items() if k.startswith('$')}
            set_operations = {k: v for k, v in update_data.items() if not k.startswith('$')}
            
            update = {}
            if set_operations:
                update['$set'] = set_operations
            if push_operations:
                update.update(push_operations)
                
            if not update:
                return False
                
            result = self.sessions.update_one(
                {"session_id": session_id},
                update,
                upsert=True  # Create the session if it doesn't exist
            )
            return result.modified_count > 0 or result.upserted_id is not None
        except Exception as e:
            print(f"Error updating session {session_id}: {str(e)}")
            return False
    
    # User Management
    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """
        Get user by ID and prepare user data for the session.
        
        Args:
            user_id: User's MongoDB ObjectId as string
            
        Returns:
            Dictionary with user data including name and marks, or None if not found
        """
        try:
            print(f"🔍 Looking up user with ID: {user_id}")
            user = self.students.find_one({"_id": ObjectId(user_id)})
            
            if not user:
                print("❌ User not found")
                return None
                
            print(f"✅ Found user: {user.get('name')} (ID: {user_id})")
            
            # Prepare user data for the session
            user_data = {
                '_id': str(user['_id']),  # Convert ObjectId to string
                'name': user.get('name', 'Student'),
                'marks': user.get('marks', []),
                'previous_marks': {}
            }
            
            # Create a dictionary of previous marks for easy lookup
            for subject in user_data['marks']:
                if 'subject' in subject and 'marks' in subject:
                    user_data['previous_marks'][subject['subject'].lower()] = subject['marks']
            
            print(f"📊 Found {len(user_data['marks'])} subject marks for {user_data['name']}")
            return user_data
            
        except Exception as e:
            print(f"❌ Error in get_user_by_id: {str(e)}")
            return None
    
    # Session Management
    def create_session(self, user_id: str, session_data: Optional[Dict] = None) -> str:
        """
        Create a new session for a user.
        
        Args:
            user_id: User's ID (MongoDB ObjectId as string)
            session_data: Additional session data to store
            
        Returns:
            Session ID
        """
        from uuid import uuid4
        
        session_id = str(uuid4())
        expires_at = datetime.utcnow() + timedelta(days=7)  # Session expires in 7 days
        
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            "expires_at": expires_at,
            "last_activity": datetime.utcnow(),
            "data": session_data or {}
        }
        
        self.sessions.insert_one(session)
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """
        Get session data by session ID.
        
        Args:
            session_id: Session ID to look up
            
        Returns:
            Session data or None if not found/expired
        """
        session = self.sessions.find_one_and_update(
            {"session_id": session_id, "expires_at": {"$gt": datetime.utcnow()}},
            {"$set": {"last_activity": datetime.utcnow()}},
            return_document=ReturnDocument.AFTER
        )
        
        if session:
            # Convert ObjectId to string for JSON serialization
            session['_id'] = str(session['_id'])
            if 'user_id' in session:
                session['user_id'] = str(session['user_id'])
        
        return session
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: Session ID to delete
            
        Returns:
            True if session was deleted, False otherwise
        """
        result = self.sessions.delete_one({"session_id": session_id})
        return result.deleted_count > 0
    
    def get_student_marks(self, student_name: str) -> Optional[Dict[str, Any]]:
        """Fetch student's marks by name (case-insensitive)"""
        return self.students.find_one({"name": {"$regex": f'^{student_name}$', '$options': 'i'}})
    
    def save_session(self, session_id: str, messages: List[Dict]):
        """Save or update session messages"""
        self.sessions.update_one(
            {"session_id": session_id},
            {"$set": {"messages": messages}},
            upsert=True
        )
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Retrieve session messages"""
        return self.sessions.find_one({"session_id": session_id})
    
    def close(self):
        """Close the MongoDB connection"""
        self.client.close()

    def get_conversation_history(self, session_id: str) -> list:
        """
        Get conversation history for a session.
        
        Args:
            session_id: The session ID
            
        Returns:
            List of conversation messages
        """
        try:
            session = self.sessions.find_one(
                {"session_id": session_id},
                {"conversation": 1}
            )
            return session.get('conversation', []) if session else []
        except Exception as e:
            print(f"Error getting conversation history: {e}")
            return []

    def add_to_conversation_history(self, session_id: str, role: str, content: str) -> None:
        """
        Add a message to the conversation history.
        
        Args:
            session_id: The session ID
            role: 'user' or 'assistant'
            content: The message content
        """
        try:
            message = {
                'role': role,
                'content': content,
                'timestamp': datetime.utcnow()
            }
            self.sessions.update_one(
                {"session_id": session_id},
                {
                    "$push": {"conversation": message},
                    "$set": {
                        "last_updated": datetime.utcnow(),
                        "expires_at": datetime.utcnow() + timedelta(days=7)  # Extend session on activity
                    }
                },
                upsert=True
            )
        except Exception as e:
            print(f"Error updating conversation history: {e}")

    def clear_conversation_history(self, session_id: str) -> None:
        """
        Clear conversation history for a session.
        
        Args:
            session_id: The session ID
        """
        try:
            self.sessions.update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "conversation": [],
                        "last_updated": datetime.utcnow()
                    }
                }
            )
        except Exception as e:
            print(f"Error clearing conversation history: {e}")
            
    def get_recent_messages(self, student_id: str, limit: int = 5) -> list:
        """
        Get the most recent messages from conversation history.
        
        Args:
            student_id: The student's ID
            limit: Maximum number of messages to return
            
        Returns:
            List of recent messages (most recent first)
        """
        try:
            result = self.db.student_marks.aggregate([
                {"$match": {"_id": ObjectId(student_id)}},
                {"$project": {
                    "recent_messages": {
                        "$slice": ["$conversation_history", -limit, limit]
                    }
                }}
            ])
            
            messages = list(result)
            if messages and 'recent_messages' in messages[0]:
                return messages[0]['recent_messages']
            return []
        except Exception as e:
            print(f"Error getting recent messages: {e}")
            return []

# Singleton instance
db_manager = MongoDBManager()
