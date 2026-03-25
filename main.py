"""
Owlet Dream Logger - Main Application Entry Point

This is the main FastAPI application that serves the dashboard and handles
WebSocket connections for real-time data streaming.

Usage:
    python main.py

Then open your browser to http://localhost:8000
"""

import logging
import os
import signal
import asyncio
import uvicorn
from fastapi import FastAPI, WebSocket, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from config import HOST, PORT
from dashboard import HTML_CONTENT
from login_page import LOGIN_HTML
from worker import create_owlet_worker
from session import create_session, get_session, delete_session

# Configure logging to display informational messages
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("owlet_dashboard")

# Initialize FastAPI application
app = FastAPI(title="Owlet Dream Logger")


class LoginRequest(BaseModel):
    """Login request model."""
    email: str
    password: str
    region: str


@app.get("/")
async def root(session_id: str = Cookie(None)):
    """
    Root endpoint - shows login page or redirects to dashboard.
    
    Args:
        session_id: Session cookie
        
    Returns:
        Login page or redirect to dashboard
    """
    logger.info(f"Root endpoint accessed, session_id: {session_id}")
    
    if session_id and get_session(session_id):
        logger.info(f"Valid session found, redirecting to dashboard")
        return RedirectResponse(url="/dashboard")
    
    logger.info("No valid session, showing login page")
    return HTMLResponse(LOGIN_HTML)


@app.post("/login")
async def login(login_data: LoginRequest):
    """
    Handle login request and create session.
    Note: Credentials are validated when connecting to the device, not during login.
    
    Args:
        login_data: Login credentials
        
    Returns:
        Success or error message with session cookie
    """
    try:
        logger.info(f"Login attempt for: {login_data.email}")
        
        # Create session with credentials (validation happens during device connection)
        session_id = create_session(
            login_data.email,
            login_data.password,
            login_data.region
        )
        
        logger.info(f"Session created: {session_id}")
        
        # Create response with cookie
        response = JSONResponse({"success": True, "message": "Login successful"})
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            max_age=86400,  # 24 hours
            samesite="lax",
            path="/"
        )
        
        logger.info(f"User logged in successfully: {login_data.email}")
        return response
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return JSONResponse(
            {"success": False, "error": "An error occurred during login. Please try again."},
            status_code=500
        )


@app.get("/dashboard")
async def get_dashboard(session_id: str = Cookie(None)):
    """
    Serve the main dashboard HTML page.
    Requires valid session.
    
    Args:
        session_id: Session cookie
        
    Returns:
        HTMLResponse containing the complete dashboard interface
    """
    logger.info(f"Dashboard accessed, session_id: {session_id}")
    
    if not session_id or not get_session(session_id):
        logger.warning("No valid session, redirecting to login")
        return RedirectResponse(url="/")
    
    logger.info("Valid session, showing dashboard")
    return HTMLResponse(HTML_CONTENT)


@app.post("/logout")
async def logout(session_id: str = Cookie(None)):
    """
    Handle logout request and destroy session.
    
    Args:
        session_id: Session cookie
        
    Returns:
        Success response and clears session cookie
    """
    logger.info(f"Logout request, session_id: {session_id}")
    
    # Delete session from store
    if session_id:
        delete_session(session_id)
        logger.info(f"Session deleted: {session_id}")
    
    # Create response and clear cookie
    response = JSONResponse({"success": True, "message": "Logged out successfully"})
    response.delete_cookie(key="session_id")
    
    return response


@app.post("/shutdown")
async def shutdown(session_id: str = Cookie(None)):
    """
    Shutdown the application gracefully.
    Requires valid session for security.
    
    Args:
        session_id: Session cookie
        
    Returns:
        Success response before shutting down
    """
    logger.info(f"Shutdown requested, session_id: {session_id}")
    
    # Verify session for security
    if not session_id or not get_session(session_id):
        logger.warning("Unauthorized shutdown attempt")
        return JSONResponse(
            {"success": False, "error": "Unauthorized"},
            status_code=401
        )
    
    logger.info("Shutting down application...")
    
    # Send success response before shutdown
    response = JSONResponse({"success": True, "message": "Application shutting down..."})
    
    # Schedule shutdown after response is sent
    import asyncio
    asyncio.create_task(_shutdown_server())
    
    return response


async def _shutdown_server():
    """Helper function to shutdown server after a short delay."""
    await asyncio.sleep(0.5)  # Give time for response to be sent
    logger.info("Terminating server process...")
    os.kill(os.getpid(), signal.SIGTERM)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, session_id: str = Cookie(None)):
    """
    WebSocket endpoint for real-time data streaming.
    
    Accepts WebSocket connections from the dashboard and starts the worker
    that continuously sends vitals updates.
    
    Args:
        websocket: WebSocket connection object
        session_id: Session cookie for authentication
    """
    await websocket.accept()
    
    # Verify session
    session = get_session(session_id) if session_id else None
    if not session:
        await websocket.send_json({"error": "Not authenticated"})
        await websocket.close()
        return
    
    try:
        # Create worker with session credentials
        worker = create_owlet_worker(
            session["email"],
            session["password"],
            session["region"]
        )
        await worker(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


if __name__ == "__main__":
    # Start the server when run as a script
    # Run FastAPI server on all interfaces, port 8000
    # Access dashboard at http://localhost:8000 or http://<your-ip>:8000
    logger.info(f"Starting Owlet Dream Logger on http://127.0.0.1:{PORT}")
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
