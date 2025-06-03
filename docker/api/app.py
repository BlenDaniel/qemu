# Unified Android Emulator Management API and Web Interface
import logging
import atexit
from flask import Flask, jsonify, render_template

# Import our custom modules
from docker_manager import discover_existing_containers, get_docker_client
from vnc_manager import cleanup_vnc_proxies
from api_routes import register_api_routes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# In-memory mapping of emulator sessions: id -> container
sessions = {}

# Discover existing containers on module load
discover_existing_containers(sessions)

# Register all API routes
register_api_routes(app, sessions)

# ============================================================================
# CORE WEB INTERFACE ROUTES
# ============================================================================

@app.route('/health')
def health_check():
    """Health check endpoint"""
    docker_client = get_docker_client()
    if docker_client is None:
        return jsonify({
            "status": "unhealthy",
            "docker": "disconnected",
            "message": "Cannot connect to Docker daemon"
        }), 503
    
    try:
        docker_client.ping()
        return jsonify({
            "status": "healthy", 
            "docker": "connected",
            "message": "API and Docker are working properly"
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "docker": "error", 
            "message": f"Docker ping failed: {str(e)}"
        }), 503

@app.route('/')
def index():
    """Render the main dashboard"""
    return render_template('index.html')

# ============================================================================
# APPLICATION STARTUP AND CLEANUP
# ============================================================================

# Cleanup on exit
atexit.register(cleanup_vnc_proxies)

if __name__ == '__main__':
    logger.info("Starting Android Emulator Management API...")
    logger.info(f"Discovered {len(sessions)} existing containers")
    app.run(host='0.0.0.0', port=5001, debug=True)