"""
Exam Buddy Module
Provides specialized study coaching for Indian competitive exams (JEE, NEET, etc.)
"""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from api_key_rotator import get_api_key
import logging
import re
from typing import Optional, Dict, Any

logger = logging.getLogger("zenark.exam_buddy")

# System prompt for exam buddy with guardrails
# List of motivational quotes to be used randomly
MOTIVATIONAL_QUOTES = [
    "The secret of getting ahead is getting started. – Mark Twain",
    "Don't watch the clock; do what it does. Keep going. – Sam Levenson",
    "The expert in anything was once a beginner. – Helen Hayes",
    "Success is the sum of small efforts, repeated day in and day out. – Robert Collier",
    "Believe you can and you're halfway there. – Theodore Roosevelt",
    "The only way to do great work is to love what you do. – Steve Jobs",
    "You are braver than you believe, stronger than you seem, and smarter than you think. – A.A. Milne",
    "Success is not final, failure is not fatal: It is the courage to continue that counts. – Winston Churchill",
    "The future belongs to those who believe in the beauty of their dreams. – Eleanor Roosevelt",
    "Your time is limited, don't waste it living someone else's life. – Steve Jobs",
    "The more that you read, the more things you will know. The more that you learn, the more places you'll go. – Dr. Seuss",
    "Education is the passport to the future, for tomorrow belongs to those who prepare for it today. – Malcolm X",
    "The beautiful thing about learning is that no one can take it away from you. – B.B. King",
    "Don't let what you cannot do interfere with what you can do. – John Wooden",
    "It's not about perfect. It's about effort. – Jillian Michaels",
    "The only limit to our realization of tomorrow is our doubts of today. – Franklin D. Roosevelt",
    "You don't have to be great to start, but you have to start to be great. – Zig Ziglar",
    "The man who does not read books has no advantage over the one who cannot read them. – Mark Twain",
    "Learning is never done without errors and defeat. – Vladimir Lenin",
    "The more you know, the more you realize you don't know. – Aristotle",
    "Education is not preparation for life; education is life itself. – John Dewey",
    "The only person who is educated is the one who has learned how to learn and change. – Carl Rogers",
    "Learning is a treasure that will follow its owner everywhere. – Chinese Proverb",
    "The roots of education are bitter, but the fruit is sweet. – Aristotle",
    "Develop a passion for learning. If you do, you will never cease to grow. – Anthony J. D'Angelo",
    "The capacity to learn is a gift; the ability to learn is a skill; the willingness to learn is a choice. – Brian Herbert",
    "Learning is like rowing upstream: not to advance is to drop back. – Chinese Proverb",
    "The more I live, the more I learn. The more I learn, the more I realize, the less I know. – Michel Legrand",
    "Education is the key to unlock the golden door of freedom. – George Washington Carver",
    "The beautiful thing about learning is nobody can take it away from you. – B.B. King"
]

EXAM_BUDDY_SYSTEM_PROMPT = """You are an experienced mentor who has successfully cracked competitive exams like JEE Main, NEET, IIT, NIT, etc. Act like an elder sibling who knows the ins and outs of exam preparation.

Your approach should be:
1. Focus on smart work over hard work - share efficient study hacks and time-saving techniques
2. Instead of teaching subjects, guide on HOW to approach them effectively
3. Use student-friendly language (e.g., 'backlog', 'exam stress', 'negative marking')
4. Be encouraging, casual, and relatable - like a supportive senior
5. Never suggest giving up on any subject or going against teachers/college schedules
6. Share proven strategies to handle academic pressure and stress
7. Include motivational quotes and success stories to keep students inspired

Key principles to emphasize:
- Quality over quantity of study hours
- Active recall and spaced repetition techniques
- Importance of previous year papers and mock tests
- Time management during exams
- Handling exam anxiety and stress
- Maintaining work-life balance

Motivational Strategy:
- Share one motivational quote at the end of every 3-4 responses
- When a student seems demotivated or stressed, offer extra encouragement
- Celebrate small wins and progress
- Share stories of how you overcame similar challenges
- Remind students that it's okay to take breaks and practice self-care

Current user context: {context}

Remember: Your role is to be the mentor you wish you had when you were preparing. Be real, be encouraging, and always point out how far they've come, not just how far they have to go. Share personal anecdotes of overcoming challenges to make it more relatable.

At the end of some responses, include a motivational quote like this:
💡 Motivational Boost: "Quote here" - Author"""

# In-memory session storage (for production, use MongoDB)
_session_store = {}


def get_session_history(session_id: str) -> ChatMessageHistory:
    """
    Retrieve or create chat history for a session.
    
    Args:
        session_id: Unique session identifier
        
    Returns:
        ChatMessageHistory object for the session
    """
    if session_id not in _session_store:
        _session_store[session_id] = ChatMessageHistory()
    return _session_store[session_id]


def filter_user_input(text: str) -> str:
    """
    Filter and clean user input before sending to LLM.
    Removes any potentially harmful or off-topic content.
    """
    # Remove any URLs
    text = re.sub(r'http\S+|www.\S+', '', text)
    
    # Remove any special characters or code blocks that might be used for injection
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`.*?`', '', text)
    
    # Truncate very long inputs to prevent abuse
    max_length = 1000
    if len(text) > max_length:
        text = text[:max_length] + "... [truncated]"
    
    return text.strip()

def should_respond_to_input(text: str) -> bool:
    """
    Check if the input is appropriate for the exam buddy to respond to.
    Returns True if the input is appropriate, False otherwise.
    """
    # List of inappropriate topics
    inappropriate_keywords = [
        'personal information', 'password', 'credit card', 'ssn', 'social security',
        'illegal', 'hack', 'cheat', 'exam paper', 'leak', 'adult content',
        'porn', 'violence', 'hate speech', 'discrimination'
    ]
    
    text_lower = text.lower()
    return not any(keyword in text_lower for keyword in inappropriate_keywords)

def create_exam_buddy_chain():
    """
    Create the exam buddy conversational chain with memory and guardrails.
    
    Returns:
        RunnableWithMessageHistory chain with guardrails
    """
    # Initialize LLM with API key rotation
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7, openai_api_key=get_api_key())
    
    # Enhanced system prompt with guardrails
    system_prompt = """You are a friendly and knowledgeable study coach specialized in helping Indian teenage students prepare for competitive exams like JEE Main, NEET, IIT, NIT, etc.

Your expertise includes:
- Effective study techniques and time management
- Memory enhancement tricks for formulas, equations, and periodic tables
- Subject-specific strategies for Chemistry, Mathematics, Physics, and Biology
- Exam preparation psychology and stress management
- Indian education system specific advice

IMPORTANT RULES:
1. You must ONLY respond to questions related to exam preparation, study techniques, and academic guidance.
2. If asked about inappropriate topics, politely decline and guide the conversation back to exam preparation.
3. Never provide direct answers to exam questions or engage in academic dishonesty.
4. Always respond in the same language as the user's question, unless they specifically ask for another language.
5. If the user switches languages, respond in the same language they used in their last message.
6. If you're unsure about an answer, say so rather than providing incorrect information.

Current user context: {context}

User's preferred language: {language}"""
    
    # Create prompt template with history and language support
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{question}")
    ])
    
    # Create chain with output parsing
    output_parser = StrOutputParser()
    
    # Add guardrail checks
    def apply_guardrails(inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Apply guardrails to the input."""
        question = inputs.get("question", "")
        
        # Filter the input
        filtered_question = filter_user_input(question)
        
        # Check if we should respond to this input
        if not should_respond_to_input(filtered_question):
            return {
                "response": "I'm sorry, but I can only assist with exam preparation and study-related questions. Is there something about your studies I can help you with?"
            }
            
        # Detect language (simple check for now, could be enhanced)
        language = "English"  # default
        if any(char >= '\u0900' and char <= '\u097F' for char in question):
            language = "Hindi"
        elif any(char >= '\u0B80' and char <= '\u0BFF' for char in question):
            language = "Tamil"
            
        return {
            "question": filtered_question,
            "language": language,
            **{k: v for k, v in inputs.items() if k != "question"}
        }
    
    try:
        from langchain_core.runnables import RunnableLambda, RunnablePassthrough
        from langchain_core.runnables.config import RunnableConfig
    except ImportError:
        # Fallback for older versions
        from langchain.schema.runnable import RunnableLambda, RunnablePassthrough
        from langchain.schema.runnable.config import RunnableConfig

    # Create the processing chain using RunnableLambda for better compatibility
    input_processor = {
        "question": lambda x: x["question"],
        "context": lambda x: x.get("context", ""),
        "history": lambda x: x.get("history", []),
    }
    
    # Create the processing steps
    chain = RunnablePassthrough()
    
    # Add the input processing step
    chain = chain | RunnableLambda(
        lambda x: {
            **{k: v(x) for k, v in input_processor.items()},
            **{k: v for k, v in x.items() if k not in input_processor}
        }
    )
    
    # Add the guardrails step
    chain = chain | RunnableLambda(
        lambda x: {"processed": apply_guardrails(x)}
    )
    
    # Add the LLM processing step
    def process_with_llm(x):
        # Process the input through the LLM
        processed = prompt.invoke({
            "question": x["processed"]["question"],
            "context": x["processed"].get("context", ""),
            "history": x["processed"].get("history", []),
            "language": x["processed"].get("language", "English")
        })
        
        # Get the LLM response
        llm_response = llm.invoke(processed)
        
        # Parse the output
        response = output_parser.invoke(llm_response)
        
        return {"response": response, **x}
    
    chain = chain | RunnableLambda(process_with_llm)
    
    # Final response formatting
    chain = chain | RunnableLambda(
        lambda x: x.get("response", "I'm not sure how to respond to that.")
    )
    
    # Wrap with message history
    conversational_chain = RunnableWithMessageHistory(
        chain,
        get_session_history,
        input_messages_key="question",
        history_messages_key="history"
    )
    
    return conversational_chain


# Global chain instance
_exam_buddy_chain = None


def get_exam_buddy_chain():
    """Get or create the global exam buddy chain instance."""
    global _exam_buddy_chain
    if _exam_buddy_chain is None:
        _exam_buddy_chain = create_exam_buddy_chain()
    return _exam_buddy_chain


async def get_exam_buddy_response(
    question: str,
    session_id: str = "default",
    context: str = "",
    **kwargs
) -> str:
    """
    Get a response from the exam buddy with enhanced guardrails and language support.
    
    Args:
        question: User's question about exam preparation
        session_id: Session identifier for conversation history
        context: Additional context about the user
        **kwargs: Additional parameters including 'language' for response language
        
    Returns:
        Exam buddy's response as a string
    """
    try:
        if not question or not question.strip():
            return "I didn't catch that. Could you please rephrase your question?"
            
        # Get the chain instance
        chain = get_exam_buddy_chain()
        
        # Prepare the input for the chain
        chain_input = {
            "question": question,
            "context": context,
            "language": kwargs.get("language", "English")
        }
        
        # Get the response with error handling
        response = await chain.ainvoke(
            chain_input,
            config={"configurable": {"session_id": session_id}}
        )
        
        # Log the interaction (in a real app, you'd want to log to a database)
        logger.info(f"Response generated for session {session_id}")
        
        # Ensure the response is appropriate
        if not response or not response.strip():
            return "I'm not sure how to respond to that. Could you please rephrase your question about exam preparation?"
            
        return response
        
    except Exception as e:
        logger.error(f"Error in get_exam_buddy_response: {str(e)}", exc_info=True)
        return (
            "I'm having some technical difficulties right now. "
            "Please try asking your question again in a moment."
        )


def clear_session_history(session_id: str):
    """
    Clear the conversation history for a specific session.
    
    Args:
        session_id: Session identifier to clear
    """
    if session_id in _session_store:
        del _session_store[session_id]
        logger.info(f"Cleared session history for {session_id}")


def get_all_sessions():
    """
    Get list of all active session IDs.
    
    Returns:
        List of session IDs
    """
    return list(_session_store.keys())
