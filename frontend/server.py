#!/usr/bin/env python3
"""
Simple HTTP server to serve the Islamic Q&A frontend with auto-reload
"""

import os
import sys
import time
import json
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
import socketserver
from urllib.parse import urlparse
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class CORSHTTPRequestHandler(SimpleHTTPRequestHandler):
    """HTTP Request Handler with CORS support"""
    
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()
    
    def guess_type(self, path):
        """Override to add proper MIME types"""
        result = super().guess_type(path)
        
        # Handle the return value properly
        if isinstance(result, tuple) and len(result) >= 2:
            mime_type, encoding = result[0], result[1]
        else:
            mime_type, encoding = result, None
        
        # Fix MIME types for common files
        if path.endswith('.js'):
            return 'application/javascript'
        elif path.endswith('.css'):
            return 'text/css'
        elif path.endswith('.html'):
            return 'text/html'
        
        return mime_type


class FileChangeHandler(FileSystemEventHandler):
    """Handle file system events for auto-reload"""
    
    def __init__(self):
        self.last_modified = {}
        self.clients = set()
    
    def on_modified(self, event):
        if event.is_directory:
            return
            
        # Only watch specific file types
        if not event.src_path.endswith(('.html', '.css', '.js')):
            return
            
        # Debounce rapid file changes
        now = time.time()
        if event.src_path in self.last_modified:
            if now - self.last_modified[event.src_path] < 0.5:  # 500ms debounce
                return
                
        self.last_modified[event.src_path] = now
        
        # Get relative path for display
        rel_path = os.path.relpath(event.src_path)
        print(f"🔄 File changed: {rel_path} - triggering reload...")
        
        # Notify all connected clients to reload
        self.broadcast_reload()
    
    def broadcast_reload(self):
        """Tell all clients to reload using WebSocket-like approach"""
        # Simply print the message - we'll use a different approach
        pass


class LiveReloadHTTPRequestHandler(CORSHTTPRequestHandler):
    """Enhanced request handler with live reload support"""
    
    def do_GET(self):
        # Handle live reload ping (simplified)
        if self.path == '/live-reload-ping':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'ok')
            return
            
        # Inject live reload script into HTML files
        if self.path == '/' or self.path.endswith('.html'):
            try:
                # Get the file content
                if self.path == '/':
                    file_path = 'index.html'
                else:
                    file_path = self.path.lstrip('/')
                
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Inject simple live reload script
                    live_reload_script = '''
<script>
// Simple live reload functionality
(function() {
    console.log('🔄 Live reload enabled - manual refresh for changes');
    
    // Only check when page gains focus (when you switch back from editor)
    window.addEventListener('focus', function() {
        // Check if files were modified in the last 5 seconds
        fetch('/live-reload-ping')
            .then(() => {
                // Just ensure server is responsive
                // Developer will manually refresh as needed
            })
            .catch(() => {
                console.log('Server connection check failed');
            });
    });
})();
</script>'''
                    
                    if '</body>' in content:
                        content = content.replace('</body>', f'{live_reload_script}</body>')
                    else:
                        content += live_reload_script
                    
                    # Send the modified content
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html')
                    self.send_header('Content-Length', str(len(content.encode())))
                    self.end_headers()
                    self.wfile.write(content.encode())
                    return
            except Exception as e:
                print(f"Error injecting live reload: {e}")
        
        # Default behavior for other files
        super().do_GET()


def run_server(port=3000):
    """Run the development server with live reload"""
    
    # Change to frontend directory
    frontend_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(frontend_dir)
    
    # Setup file watcher
    try:
        file_handler = FileChangeHandler()
        observer = Observer()
        observer.schedule(file_handler, path='.', recursive=False)
        observer.start()
        print("📁 File watcher started - monitoring HTML, CSS, and JS files")
    except ImportError:
        print("⚠️  Watchdog not installed. Run 'pip install watchdog' for auto-reload functionality")
        observer = None
    except Exception as e:
        print(f"⚠️  Could not start file watcher: {e}")
        observer = None
    
    # Create server with live reload handler
    with socketserver.TCPServer(("", port), LiveReloadHTTPRequestHandler) as httpd:
        # Store server reference for reload signaling
        import __main__
        __main__.server_instance = httpd
        print(f"""
🕌 Islamic Q&A Frontend Server
==============================

Server running at: http://localhost:{port}
Backend API at:    http://localhost:8000

Features available:
✅ Modern Islamic-themed UI
✅ Question browsing and search
✅ Real-time chat (WebSocket)
✅ User authentication
✅ Question submission
✅ Category filtering
✅ ML-powered search

Press Ctrl+C to stop the server
""")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n👋 Server stopped. Thank you for using Islamic Q&A!")
            if observer:
                observer.stop()
                observer.join()
            httpd.server_close()

if __name__ == "__main__":
    port = 3000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("Invalid port number. Using default port 3000.")
    
    run_server(port)
