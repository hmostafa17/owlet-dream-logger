"""
Session management for storing user credentials.
"""

from typing import Dict, Optional
import secrets

# Simple in-memory session store
# In production, use proper session management (Redis, database, etc.)
_sessions: Dict[str, Dict[str, str]] = {}


def create_session(email: str, password: str, region: str) -> str:
    """
    Create a new session for the user.
    
    Args:
        email: User's email
        password: User's password
        region: Owlet API region
        
    Returns:
        Session ID
    """
    session_id = secrets.token_urlsafe(32)
    _sessions[session_id] = {
        "email": email,
        "password": password,
        "region": region
    }
    return session_id


def get_session(session_id: str) -> Optional[Dict[str, str]]:
    """
    Retrieve session data by session ID.
    
    Args:
        session_id: The session ID
        
    Returns:
        Session data dictionary or None if not found
    """
    return _sessions.get(session_id)


def delete_session(session_id: str) -> None:
    """
    Delete a session.
    
    Args:
        session_id: The session ID to delete
    """
    if session_id in _sessions:
        del _sessions[session_id]
