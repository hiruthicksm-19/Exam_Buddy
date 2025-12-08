# Page configuration must be the first Streamlit command
import streamlit as st
import asyncio
import os
import traceback
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from exam_buddy import get_exam_buddy_response, clear_session_history, get_all_sessions
from auth import login, get_student, logout
from typing import Dict, Any, Optional

# Set page config
st.set_page_config(
    page_title="Exam Buddy",
    page_icon=None
)

# Custom CSS for better UI
st.markdown("""
    <style>
    .stTextInput > div > div > input {
        padding: 10px;
        font-size: 16px;
    }
    .stButton>button {
        width: 100%;
        border-radius: 20px;
        padding: 10px 24px;
        font-weight: bold;
        background-color: #4CAF50;
        color: white;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        max-width: 80%;
        line-height: 1.6;
    }
    .user-message {
        background-color: #e3f2fd;
        margin-left: auto;
        margin-right: 0;
    }
    .bot-message {
        background-color: #f5f5f5;
        margin-right: auto;
        margin-left: 0;
    }
    .bot-message h3, .bot-message h4 {
        color: #2c3e50;
        margin-top: 1em;
        margin-bottom: 0.5em;
    }
    .bot-message ul, .bot-message ol {
        padding-left: 1.5em;
        margin: 0.5em 0;
    }
    .bot-message li {
        margin-bottom: 0.5em;
    }
    .bot-message code {
        background-color: #f0f0f0;
        padding: 0.2em 0.4em;
        border-radius: 3px;
        font-family: monospace;
    }
    """, unsafe_allow_html=True)

def initialize_session_state():
    """Initialize session state variables."""
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'user_info' not in st.session_state:
        st.session_state.user_info = {
            'exam_type': None,
            'subjects': [],
            'context_provided': False,
            'profile_complete': False
        }
    if 'session_id' not in st.session_state:
        st.session_state.session_id = None
    if 'student_id' not in st.session_state:
        st.session_state.student_id = None
    if 'is_authenticated' not in st.session_state:
        st.session_state.is_authenticated = False
    if 'context' not in st.session_state:
        st.session_state.context = ""

async def get_response_async(question, session_id, context, **kwargs):
    """
    Get response from exam buddy asynchronously with conversation history.
    
    Args:
        question: User's question
        session_id: Session identifier
        context: Additional context
        **kwargs: Additional parameters including 'language'
    """
    try:
        from db_utils import db_manager
        
        # Check if user is asking about their last question
        if question.strip().lower() in ["what was the last thing i asked you", 
                                      "what did i just ask", 
                                      "repeat my last question"]:
            history = db_manager.get_conversation(session_id)
            if history:
                # Find the last user message (excluding the current question)
                for msg in reversed(history[:-1]):  # Exclude current message
                    if msg['role'] == 'user':
                        return f"You previously asked: \"{msg['content']}\""
            return "I don't have a record of your previous question. How can I assist you today?"
        
        # Get conversation history for context
        if session_id:
            history = db_manager.get_conversation(session_id)
            if history:
                # Format the last 3 messages for context
                recent_messages = history[-3:]  # Get last 3 messages
                history_context = "\nPrevious conversation:\n"
                for msg in recent_messages:
                    role = "Student" if msg['role'] == 'user' else "Assistant"
                    history_context += f"{role}: {msg['content']}\n"
                # Add history to context
                if isinstance(context, str):
                    context = [context, history_context]
                elif isinstance(context, list):
                    context.append(history_context)
                else:
                    context = [str(context), history_context]
                    
    except Exception as e:
        print(f"Error in get_response_async: {e}")
    
    # Get the response with the enhanced context
    response = await get_exam_buddy_response(question, session_id, context, **kwargs)
    
    # Note: We don't save messages here anymore to prevent duplicates
    # Messages are now saved in the main chat loop
    
    return response

def display_chat():
    """Display the chat messages from the database."""
    if 'session_id' not in st.session_state:
        return
        
    try:
        from db_utils import db_manager
        
        # Get the current session
        session = db_manager.sessions.find_one({
            "session_id": st.session_state.session_id
        })
        
        if not session or 'conversation' not in session:
            return
            
        # Display each message
        for msg in session['conversation']:
            role = "user" if msg.get('role') == 'user' else "assistant"
            with st.chat_message(role):
                st.write(msg.get('content', ''))
                
    except Exception as e:
        print(f"Error displaying chat: {str(e)}")
        # Fallback to session state if database fails
        if 'messages' in st.session_state:
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

MOTIVATIONAL_QUOTES = [
    "Remember: Every challenge is an opportunity to grow. Keep pushing forward!",
    "Progress, no matter how small, is still progress. Keep going!",
    "Success is the sum of small efforts repeated day in and day out.",
    "You're capable of amazing things. Believe in yourself!",
    "Keep going, even when it's tough. The best views come after the hardest climbs.",
    "Turn your 'wow, but' into 'wow, but I'll try anyway!'",
    "The expert in anything was once a beginner. Keep learning!",
    "Small progress is still progress. Celebrate every step forward!",
    "You don't have to be great to start, but you have to start to be great.",
    "Your potential is endless. Keep pushing your limits!"
]

def get_random_quote() -> str:
    """Return a random motivational quote."""
    import random
    return random.choice(MOTIVATIONAL_QUOTES)

def format_response(text):
    """Format the response with proper markdown styling."""
    # Split the text into sections
    sections = text.split('\n\n')
    formatted_text = ""
    
    for section in sections:
        # Check if section is a heading
        if section.strip().endswith(':'):
            formatted_text += f"### {section}\n\n"
        # Check if section is a list item
        elif section.strip().startswith('-'):
            formatted_text += f"{section}\n"
        # Default paragraph
        else:
            formatted_text += f"{section}\n\n"
    
    return formatted_text


def show_initial_message():
    """Show the initial welcome message if needed."""
    if not st.session_state.messages and not st.session_state.user_info["exam_type"]:
        st.session_state.messages.append({
            "role": "assistant",
            "content": "Welcome to Exam Buddy! I'm here to help you prepare for your exams. Let's get started!\n\nWhich exam are you preparing for? (e.g., JEE Mains, NEET)"
        })
        return True
    return False

def collect_user_info():
    """Check if we need to collect more user information."""
    # Show initial message if needed
    if show_initial_message():
        return True
        
    # Check if we need to collect more info
    return not st.session_state.user_info["profile_complete"]

# Define valid exam categories and their keywords
MEDICAL_EXAMS = {
    "NEET": ["NEET", "Medical", "AIPMT", "MBBS", "AIIMS", "JIPMER"],
    "AIIMS": ["AIIMS", "All India Institute of Medical Sciences"],
    "JIPMER": ["JIPMER", "Jawaharlal Institute of Postgraduate Medical Education and Research"],
    "PGIMER": ["PGIMER", "Post Graduate Institute"],
    "AIIMS PG": ["AIIMS PG", "AIIMS Post Graduate"]
}

ENGINEERING_EXAMS = {
    "JEE Mains": ["JEE Mains", "JEE Main", "Joint Entrance Main", "JEE"],
    "JEE Advanced": ["JEE Advanced", "IIT JEE", "IIT-JEE"],
    "BITSAT": ["BITSAT", "BITS Pilani"],
    "VITEEE": ["VITEEE", "VIT", "Vellore"],
    "SRMJEEE": ["SRMJEEE", "SRM", "SRM University"],
    "COMEDK": ["COMEDK", "Karnataka"],
    "WBJEE": ["WBJEE", "West Bengal"],
    "MHT CET": ["MHT CET", "Maharashtra"],
    "KCET": ["KCET", "Karnataka"],
    "AP EAMCET": ["AP EAMCET", "Andhra Pradesh", "EAMCET"],
    "TS EAMCET": ["TS EAMCET", "Telangana", "EAMCET"]
}

def is_valid_exam(exam_name: str) -> tuple[bool, str, str]:
    """Check if the exam name is a valid medical or engineering exam.
    Returns (is_valid, exam_name, exam_type) where exam_type is 'medical' or 'engineering'"""
    exam_lower = exam_name.lower()
    
    # Check medical exams
    for exam, keywords in MEDICAL_EXAMS.items():
        if any(keyword.lower() in exam_lower for keyword in keywords):
            return True, exam, "medical"
    
    # Check engineering exams
    for exam, keywords in ENGINEERING_EXAMS.items():
        if any(keyword.lower() in exam_lower for keyword in keywords):
            return True, exam, "engineering"
    
    return False, exam_name, ""

def process_user_input(prompt: str):
    """Process user input and extract profile information."""
    # Add user's message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Import db_manager here to avoid circular imports
    from db_utils import db_manager
    
    # Process based on what information we're collecting
    if not st.session_state.user_info["exam_type"]:
        is_valid, exam_name, exam_type = is_valid_exam(prompt)
        if not is_valid:
            response = """
            Please enter a valid medical or engineering entrance exam. Examples:
            
            **Medical Exams:**
            - NEET (National Eligibility cum Entrance Test)
            - AIIMS (All India Institute of Medical Sciences)
            - JIPMER (Jawaharlal Institute of Postgraduate Medical Education and Research)
            
            **Engineering Exams:**
            - JEE Mains/Advanced (Joint Entrance Examination)
            - BITSAT (Birla Institute of Technology and Science Admission Test)
            - VITEEE (Vellore Institute of Technology Engineering Entrance Exam)
            - SRMJEEE (SRM Joint Engineering Entrance Exam)
            
            Please enter the full name or common abbreviation of your exam.
            """
        else:
            st.session_state.user_info["exam_type"] = exam_name
            st.session_state.user_info["exam_category"] = exam_type
            response = f"Great! You're preparing for {exam_name}. What subjects are you studying? (Please list them separated by commas, e.g., Physics, Chemistry, Biology)"
            st.session_state.user_info["subjects"] = []  # Initialize empty subjects list
            st.session_state.user_info["subject_marks"] = {}  # Initialize marks dictionary
            st.session_state.user_info["awaiting_subjects"] = True
            
    elif st.session_state.user_info.get("awaiting_subjects", False):
        subjects = [s.strip().lower() for s in prompt.split(",") if s.strip()]
        if not subjects:
            response = "Please enter at least one valid subject name."
        else:
            st.session_state.user_info["pending_subjects"] = subjects
            st.session_state.user_info["current_subject_index"] = 0
            st.session_state.user_info["awaiting_subjects"] = False
            st.session_state.user_info["awaiting_marks"] = True
            response = f"What are your marks in {subjects[0]}? (Enter a number between 0-100)"
            
    elif st.session_state.user_info.get("awaiting_marks", False):
        try:
            marks = float(prompt)
            if 0 <= marks <= 100:
                current_idx = st.session_state.user_info["current_subject_index"]
                subjects = st.session_state.user_info["pending_subjects"]
                current_subject = subjects[current_idx]
                
                # Store the marks for current subject
                st.session_state.user_info["subject_marks"][current_subject] = marks
                
                # Move to next subject or finish
                next_idx = current_idx + 1
                if next_idx < len(subjects):
                    st.session_state.user_info["current_subject_index"] = next_idx
                    response = f"What are your marks in {subjects[next_idx]}? (Enter a number between 0-100)"
                else:
                    # All subjects processed
                    subjects_list = st.session_state.user_info["pending_subjects"]
                    st.session_state.user_info["subjects"] = subjects_list
                    st.session_state.user_info["profile_complete"] = True
                    st.session_state.user_info["context_provided"] = True
                    
                    # Get student ID from session if available
                    student_id = st.session_state.get("student_id")
                    
                    # Clean up
                    if "pending_subjects" in st.session_state.user_info:
                        del st.session_state.user_info["pending_subjects"]
                    if "current_subject_index" in st.session_state.user_info:
                        del st.session_state.user_info["current_subject_index"]
                    if "awaiting_marks" in st.session_state.user_info:
                        del st.session_state.user_info["awaiting_marks"]
                    
                    # Prepare subject list for the welcome message
                    subject_list = ", ".join([s.capitalize() for s in subjects_list])
                    
                    # Show welcome message
                    response = f"""Great! I'm all set to help you with your {st.session_state.user_info['exam_type']} preparation!

You can ask me about:
- Study techniques for {subject_list}
- Time management strategies
- Specific topics you're struggling with
- Practice questions
- And much more!

What would you like to start with?"""
            else:
                response = "Please enter a valid number between 0 and 100."
        except ValueError:
            response = "Please enter a valid number between 0 and 100."
    # Handle case when we're collecting current marks for comparison
    elif "previous_marks" in st.session_state.user_info and ("current_marks" not in st.session_state.user_info or "current_subject_index" in st.session_state.user_info):
        try:
            marks = float(prompt)
            if 0 <= marks <= 100:
                if "current_marks" not in st.session_state.user_info:
                    st.session_state.user_info["current_marks"] = {}
                
                # Get current subject from previous_marks (which is now a list of subjects)
                subjects = st.session_state.user_info["previous_marks"]
                current_idx = st.session_state.user_info.get("current_subject_index", 0)
                current_subject = subjects[current_idx]
                
                # Store the marks for current subject
                st.session_state.user_info["current_marks"][current_subject] = marks
                
                # Move to next subject or finish
                if current_idx < len(subjects) - 1:
                    st.session_state.user_info["current_subject_index"] = current_idx + 1
                    next_subject = subjects[current_idx + 1]
                    response = f"What are your current marks in {next_subject}? (Enter a number between 0-100)"
                else:
                    # All subjects processed, show comparison
                    comparison_results = []
                    # Track overall performance
                    total_improvement = 0
                    improved_subjects = 0
                    total_subjects = len(subjects)
                    
                    # Get previous marks from database for comparison
                    student_id = st.session_state.get("student_id")
                    if student_id:
                        student_data = db_manager.get_student(student_id)
                        if student_data and 'marks' in student_data and student_data['marks']:
                            previous_marks = {m['subject']: m['marks'] for m in student_data['marks']}
                        else:
                            previous_marks = {}
                    else:
                        previous_marks = {}
                    
                    for subject in subjects:
                        curr_mark = st.session_state.user_info["current_marks"].get(subject, 0)
                        prev_mark = previous_marks.get(subject.lower(), 0)
                        mark_difference = curr_mark - prev_mark
                        if mark_difference > 0:
                            improved_subjects += 1
                            total_improvement += mark_difference
                            
                            # Encouraging messages for improvements
                            if mark_difference > 20:
                                comparison_results.append(f"**{subject.capitalize()}**: WOW! You've improved by {mark_difference} marks! ({prev_mark} → {curr_mark}) Keep up this amazing work!")
                            elif mark_difference > 10:
                                comparison_results.append(f"**{subject.capitalize()}**: Great job! You've improved by {mark_difference} marks! ({prev_mark} → {curr_mark}) Your hard work is paying off!")
                            else:
                                comparison_results.append(f"**{subject.capitalize()}**: Good progress! You've improved by {mark_difference} marks ({prev_mark} → {curr_mark}). Every step forward counts!")
                                
                        elif mark_difference < 0:
                            decline = abs(mark_difference)
                            # Supportive messages for declines
                            if decline > 20:
                                comparison_results.append(f"**{subject.capitalize()}**: You scored {curr_mark} (down by {decline} marks). Let's identify areas to improve. You've got this!")
                            elif decline > 10:
                                comparison_results.append(f"**{subject.capitalize()}**: You scored {curr_mark} (down by {decline} marks). A little more practice and you'll be back on track!")
                            else:
                                comparison_results.append(f"**{subject.capitalize()}**: Small dip to {curr_mark} (down by {decline} marks). You're doing great overall!")
                        # This handles the case where there's no previous mark (first attempt)
                        else:
                            comparison_results.append(f"**{subject.capitalize()}**: First recorded score: {curr_mark}. Great start! Let's build on this!")
                    
                    # Save marks to database
                    if student_id:
                        try:
                            from db_utils import db_manager
                            # Prepare marks data for saving
                            marks_data = [
                                {"subject": subject, "marks": float(marks)}
                                for subject, marks in st.session_state.user_info["current_marks"].items()
                            ]
                            
                            # Update student data in database
                            db_manager.students.update_one(
                                {"student_id": student_id},
                                {"$set": {"marks": marks_data}},
                                upsert=True
                            )
                            print(f"Saved marks to database for student {student_id}")
                        except Exception as e:
                            print(f"Error saving marks to database: {e}")
                            print(traceback.format_exc())
                    
                    # Prepare welcome message
                    subject_list = ", ".join(st.session_state.user_info["subjects"])
                    response = f"""Great! I'm all set to help you with your {st.session_state.user_info['exam_type']} preparation!

You can ask me about:
- Study techniques for {subject_list}
- Time management strategies
- Specific topics you're struggling with
- Practice questions
- And much more!

What would you like to start with?"""
                    
                    # Add welcome message
                    st.session_state.messages.append({"role": "assistant", "content": welcome_msg})
                    
                    # Mark profile as complete and clean up
                    st.session_state.user_info["profile_complete"] = True
                    del st.session_state.user_info["previous_marks"]
                    del st.session_state.user_info["current_marks"]
                    if "current_subject_index" in st.session_state.user_info:
                        del st.session_state.user_info["current_subject_index"]
                    
                    # Rerun to update the UI
                    st.rerun()
            else:
                response = "Please enter a valid number between 0 and 100."
        except ValueError:
            response = "Please enter a valid number between 0 and 100."
    # Handle case when no previous marks exist
    elif "previous_marks" not in st.session_state.user_info and not st.session_state.user_info.get("profile_complete", False):
        # Just mark the profile as complete and proceed
        st.session_state.user_info["profile_complete"] = True
        st.session_state.user_info["context_provided"] = True
        
        # Show welcome message
        subject_list = ", ".join(st.session_state.user_info.get("subjects", ["your subjects"]))
        response = f"""Great! I'm all set to help you with your {st.session_state.user_info['exam_type']} preparation!

You can ask me about:
- Study techniques for {subject_list}
- Time management strategies
- Specific topics you're struggling with
- Practice questions
- And much more!

What would you like to start with?"""
    
    # Add assistant's response to chat history
    if 'response' in locals():
        st.session_state.messages.append({"role": "assistant", "content": response})
        return False
        
    return True

def show_login():
    """Show login form and handle authentication."""
    st.title("Login to Exam Buddy")
    with st.form("login_form"):
        student_id = st.text_input("Enter your Student ID")
        if st.form_submit_button("Login"):
            if student_id.strip():
                # Pass the current session_id to the login function for session merging
                current_session_id = st.session_state.get('session_id')
                session = login(student_id, current_session_id=current_session_id)
                if session:
                    st.session_state.session_id = str(session['_id'])
                    st.session_state.student_id = student_id
                    st.session_state.is_authenticated = True
                    st.session_state.conversation_loaded = False  # Reset to load conversation
                    
                    # Load conversation history
                    try:
                        from db_utils import db_manager
                        history = db_manager.get_conversation_history(student_id)
                        if history:
                            st.session_state.messages = history
                    except Exception as e:
                        st.error(f"Error loading conversation history: {e}")
                    
                    st.rerun()
                else:
                    st.error("Invalid Student ID. Please try again.")
            else:
                st.warning("Please enter a valid Student ID")
    
    st.markdown("---")
    st.markdown("### About")
    st.markdown("""
    **Exam Buddy** helps you prepare for competitive exams like JEE, NEET, and more.
    
    Ask about:
    - Study techniques
    - Subject-specific help
    - Time management
    - Exam strategies
    - And more!""")

def show_sidebar():
    """Show sidebar with user controls."""
    with st.sidebar:
        st.session_state.language = st.selectbox(
            "Language",
            ["English", "हिंदी (Hindi)", "தமிழ் (Tamil)", "తెలుగు (Telugu)", "ಕನ್ನಡ (Kannada)", "മലയാളം (Malayalam)"],
            index=0
        )
        
        st.markdown("---")
        
        
        # Show last 3 messages from conversation history
        if st.session_state.get('student_id'):
            from db_utils import db_manager
            recent_messages = db_manager.get_recent_messages(st.session_state.student_id, limit=3)
            
            if recent_messages:
                for msg in reversed(recent_messages):  # Show most recent first
                    role = "" if msg['role'] == 'user' else ""
                    st.markdown(f"{role} *{msg['content'][:50]}...*")
                    st.markdown("---")
        
        st.markdown("### About")
        st.markdown("""
        **Exam Buddy** helps you prepare for competitive exams like JEE, NEET, and more.
        
        Ask about:
        - Study techniques
        - Subject-specific help
        - Time management
        - Exam strategies
        - And more!""")

def get_student_data() -> dict:
    """Helper function to get student data for the current session."""
    from auth import get_student
    if not st.session_state.get('session_id'):
        return {}
    return get_student(st.session_state.session_id) or {}

def save_message(role: str, content: str):
    """Save a message to the conversation history in the database."""
    if 'session_id' not in st.session_state or not st.session_state.session_id:
        return False
        
    try:
        from db_utils import db_manager
        from bson import ObjectId
        
        # Create message object
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc)
        }
        
        # Get the current session
        session = db_manager.sessions.find_one({
            "$or": [
                {"session_id": st.session_state.session_id},
                {"student_id": ObjectId(st.session_state.student_id) if st.session_state.get('student_id') else None}
            ]
        })
        
        if session:
            # Get current messages
            current_messages = session.get('conversation', [])
            
            # Add new message
            current_messages.append(message)
            
            # Trim messages if needed (keep last 80 messages)
            if len(current_messages) > 80:
                current_messages = current_messages[-80:]
            
            # Update the session
            db_manager.sessions.update_one(
                {"_id": session["_id"]},
                {
                    "$set": {
                        "conversation": current_messages,
                        "last_activity": datetime.now(timezone.utc),
                        "expires_at": datetime.now(timezone.utc) + timedelta(days=7)
                    }
                }
            )
        else:
            # Create new session with the first message
            session_data = {
                "session_id": st.session_state.session_id,
                "student_id": ObjectId(st.session_state.student_id) if st.session_state.get('student_id') else None,
                "created_at": datetime.now(timezone.utc),
                "last_activity": datetime.now(timezone.utc),
                "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
                "conversation": [message]
            }
            db_manager.sessions.insert_one(session_data)
            
        return True
        
    except Exception as e:
        print(f"Error saving message: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def handle_logout():
    """Handle user logout, summarize conversation, and store context."""
    if 'session_id' in st.session_state and 'student_id' in st.session_state:
        try:
            from db_utils import db_manager
            from exam_buddy import get_llm_summary
            
            # Get the conversation history
            session = db_manager.sessions.find_one({
                "$or": [
                    {"session_id": st.session_state.session_id},
                    {"student_id": ObjectId(st.session_state.student_id)}
                ]
            })
            
            if session and 'conversation' in session and len(session['conversation']) > 0:
                # Generate summary of the conversation
                summary = get_llm_summary(session['conversation'])
                
                # Store the summary as context for future sessions
                db_manager.sessions.update_one(
                    {"student_id": ObjectId(st.session_state.student_id)},
                    {
                        "$set": {
                            "context": summary,
                            "last_activity": datetime.now(timezone.utc)
                        }
                    },
                    upsert=True
                )
            
            # Update last activity
            db_manager.sessions.update_one(
                {"session_id": st.session_state.session_id},
                {"$set": {"last_activity": datetime.now(timezone.utc)}}
            )
            
        except Exception as e:
            print(f"Error during logout: {str(e)}")
            import traceback
            traceback.print_exc()
    
    # Clear session state and rerun
    st.session_state.clear()
    st.rerun()

def main():
    """Main function to run the Streamlit app."""
    # Initialize session state
    initialize_session_state()
    
    # Show login if not authenticated
    if not st.session_state.get('is_authenticated'):
        show_login()
        return
    
    # Add logout button to sidebar
    with st.sidebar:
        st.write(f"Welcome, {st.session_state.get('user_info', {}).get('name', 'Student')}!")
        if st.button("Logout", type="primary"):
            handle_logout()
            return
    
    # Load conversation history if not already loaded
    if not st.session_state.get('conversation_loaded') and st.session_state.session_id:
        try:
            from db_utils import db_manager
            history = db_manager.get_conversation(st.session_state.session_id)
            if history:
                st.session_state.messages = history
            else:
                print(f"No conversation history found for session {st.session_state.session_id}")
                st.session_state.messages = []
            
            st.session_state.conversation_loaded = True
        except Exception as e:
            error_msg = f"Error loading conversation history: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            st.error("Error loading conversation history. Please refresh the page.")
    
    # Main app interface
    show_sidebar()
    
    # Show cheerful welcome message if it's a new session
    if not st.session_state.messages and 'welcome_shown' not in st.session_state:
        # Get student data to personalize the welcome message
        from auth import get_student
        student = get_student(st.session_state.session_id) if st.session_state.session_id else {}
        student_name = student.get('name', 'future achiever')
        
        welcome_message = f"""
        <div style='background-color:#e8f5e9; padding:20px; border-radius:10px; margin-bottom:20px;'>
            <h2 style='color:#1b5e20;'>Welcome to Exam Buddy, {student_name}!</h2>
            <p style='color:#1b5e20;'>Hello there!</p>
            <p style='color:#1b5e20;'>I'm your personal Exam Buddy, here to help you ace your exams with confidence! Whether you need help with tough concepts, 
            want to practice problems, or just need some motivation, I've got your back!</p>
            <p style='color:#1b5e20;'>Let's get started on your journey to success, {student_name}!</p>
        </div>
        """
        st.markdown(welcome_message, unsafe_allow_html=True)
        st.session_state.welcome_shown = True
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # If user info is not complete, show the appropriate prompt
    if not st.session_state.user_info.get("profile_complete", False):
        # Determine which prompt to show based on current state
        if not st.session_state.user_info["exam_type"]:
            prompt_text = "Which exam are you preparing for? (e.g., JEE Mains, NEET etc.)"
            should_show = not any(msg["content"] == prompt_text for msg in st.session_state.messages)
        elif not st.session_state.user_info["subjects"]:
            # This is handled in process_user_input
            should_show = False
        elif not st.session_state.user_info.get("context_provided", False):
            prompt_text = "Is there any additional context or specific challenges you'd like to share? (e.g., 'I struggle with calculus' or 'I need help with time management')\n\nYou can also type 'skip' if you don't have any specific context to add."
            should_show = not any(msg["content"] == prompt_text for msg in st.session_state.messages)
        else:
            # This block should not be reached as all profile collection is handled in process_user_input
            should_show = False
        
        # Show the prompt if needed
        if should_show:
            with st.chat_message("assistant"):
                st.markdown(prompt_text)
                st.session_state.messages.append({"role": "assistant", "content": prompt_text})
    
    # Chat input
    chat_placeholder = "Type your message here..." if st.session_state.user_info.get("profile_complete", False) else "Type your response here..."
    if prompt := st.chat_input(chat_placeholder):
        # Process user input for profile collection
        if not st.session_state.user_info.get("profile_complete", False):
            process_user_input(prompt)
            st.rerun()  # Rerun to update the UI with the new messages
        else:
            # Save and display user message
            save_message("user", prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            # Display user message in chat message container
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # Get response from exam buddy
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    # Get student data using the utility function
                    student = get_student_data()
                    
                    # Prepare context with student data
                    context = [
                        f"Student: {student.get('name', 'Student')}",
                        f"Exam: {st.session_state.user_info.get('exam_type', 'Not specified')}",
                        f"Subjects: {', '.join(st.session_state.user_info.get('subjects', ['Not specified']))}"
                    ]
                    
                    if st.session_state.context:
                        context.append(f"Additional Context: {st.session_state.context}")
                    
                    # Add student's marks if available
                    if 'marks' in student and student['marks']:
                        context.append("Student's Performance:")
                        for mark in student['marks']:
                            context.append(f"- {mark.get('subject', 'Subject')}: {mark.get('marks', 'N/A')}")
                    
                    try:
                        response = asyncio.run(
                            get_response_async(
                                question=prompt,
                                session_id=st.session_state.session_id,
                                context="\n".join(context),
                                language=st.session_state.language
                            )
                        )
                        
                        # Display the response
                        st.markdown(format_response(response))
                        
                        # Save and add assistant response to chat history
                        save_message("assistant", response)
                        st.session_state.messages.append({"role": "assistant", "content": response})
                        
                    except Exception as e:
                        error_msg = f"I encountered an error while generating a response. Please try again.\nError: {str(e)}"
                        st.error(error_msg)
                        print(f"Error in chat loop: {str(e)}")
                        save_message("assistant", error_msg)
                        st.session_state.messages.append({"role": "assistant", "content": error_msg})

if __name__ == "__main__":
    main()
