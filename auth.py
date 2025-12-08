"""
Authentication and session management for Exam Buddy.
"""
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from exam_buddy import get_llm_summary

# MongoDB connection
MONGODB_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
if not MONGODB_URI:
    raise ValueError("Neither MONGODB_URI nor MONGO_URI environment variable is set")

client = MongoClient(MONGODB_URI)
db = client['zenark_db']
students = db['student_marks']
sessions = db['exam_buddy_session']

# Drop any existing problematic indexes
try:
    sessions.drop_indexes()
except:
    pass

# Create TTL index for session expiration (7 days)
sessions.create_index("expires_at", expireAfterSeconds=0)
# Create sparse unique index on student_id to allow multiple nulls
sessions.create_index("student_id", unique=True, sparse=True)

def summarize_previous_conversations(student_id: str) -> str:
    """
    Fetch and summarize previous conversations for a student.
    """
    try:
        # Get all previous sessions for this student
        previous_sessions = sessions.find({
            "student_id": ObjectId(student_id),
            "conversation": {"$exists": True, "$ne": []}
        }).sort("last_activity", -1).limit(5)  # Get last 5 sessions
        
        if not previous_sessions:
            return ""
            
        # Extract conversations
        all_conversations = []
        for session in previous_sessions:
            all_conversations.extend(session.get('conversation', []))
            
        if not all_conversations:
            return ""
            
        # Get summary using the LLM
        summary = get_llm_summary(all_conversations)
        return summary or ""
        
    except Exception as e:
        print(f"Error summarizing conversations: {str(e)}")
        return ""

def login(student_id: str, current_session_id: str = None) -> Optional[Dict]:
    """
    Login a student and maintain conversation history with context from previous sessions.
    
    Args:
        student_id: Student's MongoDB ObjectId as string
        current_session_id: Current session ID (if any)
        
    Returns:
        Session data if login successful, None otherwise
    """
    try:
        # Check if student_id is valid
        if not student_id or not ObjectId.is_valid(student_id):
            print(f"Invalid student ID: {student_id}")
            return None
            
        # Check if student exists
        student = students.find_one({"_id": ObjectId(student_id)})
        if not student:
            print(f"Student not found with ID: {student_id}")
            return None
            
        # Check for existing session first
        existing_session = sessions.find_one(
            {"student_id": ObjectId(student_id)},
            sort=[("last_activity", -1)]  # Get the most recent session
        )
        
        now = datetime.utcnow()
        
        if existing_session:
            # Update existing session
            session_data = {
                "session_id": current_session_id or existing_session.get("session_id", str(ObjectId())),
                "last_activity": now,
                "expires_at": now + timedelta(days=7)
            }
            
            # Update the existing session
            sessions.update_one(
                {"_id": existing_session["_id"]},
                {"$set": session_data}
            )
            
            # Return the updated session data
            session_data.update({
                "_id": str(existing_session["_id"]),
                "student_id": student_id,
                "created_at": existing_session.get("created_at", now),
                "conversation": existing_session.get("conversation", []),
                "context": existing_session.get("context", "")
            })
            
            return session_data
        else:
            # Create new session with context
            session_data = {
                "session_id": current_session_id or str(ObjectId()),
                "student_id": ObjectId(student_id),
                "created_at": now,
                "last_activity": now,
                "expires_at": now + timedelta(days=7),
                "conversation": [],
                "context": ""
            }
            
            # Insert the new session
            result = sessions.insert_one(session_data)
            
            # Convert ObjectId to string for JSON serialization
            session_data['_id'] = str(result.inserted_id)
            session_data['student_id'] = student_id
            
            return session_data
            
    except Exception as e:
        print(f"Login error: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def get_session(session_id: str) -> Optional[Dict]:
    """
    Get session by ID and update last activity.
    
    Args:
        session_id: Session ID
        
    Returns:
        Session data if valid, None otherwise
    """
    try:
        if not session_id or not ObjectId.is_valid(session_id):
            print(f"Invalid session ID format: {session_id}")
            return None
            
        # Update last activity and get session
        session = sessions.find_one_and_update(
            {"$or": [
                {"_id": ObjectId(session_id)},
                {"session_id": ObjectId(session_id)}
            ], "expires_at": {"$gt": datetime.utcnow()}},
            {"$set": {"last_activity": datetime.utcnow()}},
            return_document=True
        )
        
        if not session:
            print(f"No active session found for ID: {session_id}")
            return None
            
        # Convert ObjectId to string for JSON serialization
        if '_id' in session:
            session['_id'] = str(session['_id'])
        if 'student_id' in session:
            session['student_id'] = str(session['student_id'])
            
        return session
    except Exception as e:
        print(f"Error getting session: {str(e)}")
        return None

def get_student(session_id: str) -> Optional[Dict]:
    """
    Get student data from session.
    
    Args:
        session_id: Session ID
        
    Returns:
        Student data if session is valid, None otherwise
    """
    try:
        if not session_id:
            print("No session ID provided")
            return None
            
        session = get_session(session_id)
        if not session:
            print(f"No valid session found for ID: {session_id}")
            return None
            
        if 'student_id' not in session:
            print(f"Session is missing student_id: {session}")
            return None
            
        student = students.find_one({"_id": ObjectId(session["student_id"])})
        if not student:
            print(f"No student found for ID: {session['student_id']}")
            return None
            
        # Convert ObjectId to string for JSON serialization
        student['_id'] = str(student['_id'])
        
        # Convert any ObjectId fields in marks if they exist
        if 'marks' in student and isinstance(student['marks'], list):
            for mark in student['marks']:
                if '_id' in mark:
                    mark['_id'] = str(mark['_id'])
                    
        return student
    except Exception as e:
        print(f"Error getting student: {str(e)}")
        return None

def ensure_session_exists(session_id: str, student_id: Optional[str] = None) -> bool:
    """
    Ensure a session exists, creating it if necessary.
    
    Args:
        session_id: The session ID
        student_id: Optional student ID to associate with the session
        
    Returns:
        bool: True if session exists or was created, False otherwise
    """
    try:
        # Check if session exists
        if sessions.find_one({"$or": [
            {"session_id": session_id},
            {"_id": ObjectId(session_id) if ObjectId.is_valid(session_id) else None}
        ]}):
            return True
            
        # Create new session if it doesn't exist
        session_data = {
            "session_id": session_id,
            "created_at": datetime.utcnow(),
            "last_activity": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(days=7),
            "conversation": []
        }
        
        if student_id:
            session_data["student_id"] = student_id
            
        sessions.insert_one(session_data)
        return True
        
    except Exception as e:
        print(f"Error ensuring session exists: {e}")
        return False

def logout(session_id: str) -> bool:
    """
    Logout by updating the last_activity timestamp.
    The session and student_id are preserved for future reference.
    
    Args:
        session_id: Current session ID
        
    Returns:
        bool: True if logout was successful, False otherwise
    """
    try:
        if not session_id:
            return False
            
        # Just update the last_activity timestamp
        result = sessions.update_one(
            {
                "$or": [
                    {"session_id": session_id},
                    {"_id": ObjectId(session_id) if ObjectId.is_valid(session_id) else None}
                ]
            },
            {
                "$set": {
                    "last_activity": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count > 0:
            print(f"Successfully logged out from session {session_id}")
            return True
        else:
            print(f"No active session found for session_id: {session_id}")
            return False
            
    except Exception as e:
        print(f"Error during logout: {str(e)}")
        import traceback
        traceback.print_exc()
        return False