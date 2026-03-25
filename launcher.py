"""
Owlet Dream Logger - Launcher Script

This script launches the Owlet monitoring application and opens the dashboard in your browser.
Can be converted to an .exe using PyInstaller.
"""

import os
import sys
import time
import webbrowser
import threading
import logging

def main():
    # Fix for windowed .exe - redirect stdout/stderr if they don't exist
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        application_path = os.path.dirname(sys.executable)
        
        # Create a log file for debugging
        log_file = os.path.join(application_path, "owlet_app.log")
        
        # If running windowed (no console), redirect output to log file
        if sys.stdout is None or sys.stderr is None:
            sys.stdout = open(log_file, 'w', encoding='utf-8')
            sys.stderr = sys.stdout
    else:
        # Running as script
        application_path = os.path.dirname(os.path.abspath(__file__))
    
    print("=" * 50)
    print("  Owlet Dream Logger")
    print("=" * 50)
    print()
    print("Starting server...")
    print("Dashboard URL: http://localhost:8000")
    print()
    print("Press Ctrl+C in this window to stop the server")
    print("=" * 50)
    print()
    
    # Wait a moment for server to start, then open browser
    def open_browser():
        time.sleep(3)
        print("Opening dashboard in browser...")
        webbrowser.open("http://localhost:8000")
    
    # Start browser opener in background
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    
    # Import and run the FastAPI application directly
    try:
        sys.path.insert(0, application_path)
        os.chdir(application_path)
        
        # Import required modules
        import uvicorn
        from main import app
        from config import HOST, PORT
        
        # Configure uvicorn for windowed mode (no console logging issues)
        # Use minimal logging configuration that doesn't require a TTY
        uvicorn.run(
            app, 
            host=HOST, 
            port=PORT,
            log_config=None if getattr(sys, 'frozen', False) else None,
            access_log=False
        )
        
    except KeyboardInterrupt:
        print("\n\nServer stopped by user.")
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
        
        # Only try to read input if stdin exists
        if sys.stdin is not None:
            try:
                input("Press Enter to exit...")
            except:
                pass
        sys.exit(1)

if __name__ == "__main__":
    main()
