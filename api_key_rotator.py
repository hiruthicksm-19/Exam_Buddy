"""
API Key Rotator for OpenAI
Handles API key management and rotation.
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_api_key():
    """
    Get the OpenAI API key from environment variables.
    
    Returns:
        str: The OpenAI API key
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment variables")
    return api_key
