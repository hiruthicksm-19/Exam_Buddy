"""
Streamlit Application for Exam Buddy
A user-friendly interface for interacting with the Exam Buddy AI assistant.
"""

import streamlit as st
import asyncio
import os
from exam_buddy import get_exam_buddy_response, clear_session_history, get_all_sessions
from typing import Dict, Any

# Page configuration
st.set_page_config(
    page_title="Exam Buddy",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
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
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"session_{len(get_all_sessions()) + 1}"
    if "context" not in st.session_state:
        st.session_state.context = ""
    if "language" not in st.session_state:
        st.session_state.language = "English"
    if "user_info" not in st.session_state:
        st.session_state.user_info = {
            "exam_type": "",
            "subjects": [],
            "target_year": ""
        }

async def get_response_async(question, session_id, context, **kwargs):
    """
    Get response from exam buddy asynchronously.
    
    Args:
        question: User's question
        session_id: Session identifier
        context: Additional context
        **kwargs: Additional parameters including 'language'
    """
    return await get_exam_buddy_response(question, session_id, context, **kwargs)

def display_chat():
    """Display chat messages."""
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

def format_response(text):
    """Format the response with proper markdown styling."""
    # Split the text into sections
    sections = text.split('### ')
    formatted = []
    
    for section in sections:
        if not section.strip():
            continue
            
        # Check if this is a list section
        if section.strip().startswith('-'):
            # Format as list
            items = [item.strip() for item in section.split('\n') if item.strip()]
            formatted_section = '\n'.join(f'- {item[1:].strip() if item.startswith("-") else item}' for item in items)
        else:
            # Format as heading and content
            parts = section.split('\n', 1)
            if len(parts) > 1:
                heading, content = parts
                formatted_section = f'**{heading}**\n\n{content}'
            else:
                formatted_section = section
                
        formatted.append(formatted_section)
    
    # Join sections with double newlines
    return '\n\n'.join(formatted)


def main():
    """Main function to run the Streamlit app."""
    st.title("📚 Exam Buddy")
    st.caption("Your personal AI study coach for competitive exams")
    
    # Initialize session state
    initialize_session_state()
    
    # Sidebar for settings
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # Language selection
        st.session_state.language = st.selectbox(
            "🌐 Language",
            ["English", "हिंदी (Hindi)", "தமிழ் (Tamil)", "తెలుగు (Telugu)", "ಕನ್ನಡ (Kannada)", "മലയാളം (Malayalam)"],
            index=0
        )
        
        # User profile
        with st.expander("👤 My Profile"):
            st.session_state.user_info["exam_type"] = st.selectbox(
                "Target Exam",
                ["JEE Mains", "JEE Advanced", "NEET", "UPSC", "GATE", "Other"],
                index=0
            )
            
            subjects = ["Physics", "Chemistry", "Mathematics", "Biology", "English", "General Knowledge"]
            st.session_state.user_info["subjects"] = st.multiselect(
                "Focus Subjects",
                subjects,
                default=subjects[:3] if st.session_state.user_info["exam_type"] != "NEET" else ["Physics", "Chemistry", "Biology"]
            )
            
            st.session_state.user_info["target_year"] = st.selectbox(
                "Target Exam Year",
                ["2023", "2024", "2025", "2026", "2027"],
                index=2
            )
        
        # Context input
        st.session_state.context = st.text_area(
            "📝 Additional context (optional):",
            value=st.session_state.context,
            help="Mention any specific topics, difficulties, or preferences you have."
        )
        
        # New session button
        if st.button("🔄 New Session", use_container_width=True):
            clear_session_history(st.session_state.session_id)
            st.session_state.messages = []
            st.session_state.session_id = f"session_{len(get_all_sessions()) + 1}"
            st.rerun()
            
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
    
    # Display chat messages
    display_chat()
    
    # Chat input
    if prompt := st.chat_input("Ask me anything about exam preparation..."):
        # Add user message to chat
        user_message = {"role": "user", "content": prompt}
        st.session_state.messages.append(user_message)
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Display assistant response
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""
            
            # Prepare context with user info
            user_context = (
                f"Exam: {st.session_state.user_info['exam_type']} "
                f"(Target: {st.session_state.user_info['target_year']})\n"
                f"Subjects: {', '.join(st.session_state.user_info['subjects'])}\n"
                f"Additional context: {st.session_state.context}"
            )
            
            # Get response from exam buddy with language preference
            response = asyncio.run(
                get_response_async(
                    prompt,
                    st.session_state.session_id,
                    user_context,
                    language=st.session_state.language.split(" ")[0]  # Get language code
                )
            )
            
            # Format the response with markdown
            formatted_response = format_response(response)
            
            # Display the formatted response with typing effect
            message_placeholder.markdown(formatted_response, unsafe_allow_html=True)
            full_response = response
        
        # Add assistant response to chat history
        assistant_message = {"role": "assistant", "content": response}
        st.session_state.messages.append(assistant_message)

if __name__ == "__main__":
    main()
