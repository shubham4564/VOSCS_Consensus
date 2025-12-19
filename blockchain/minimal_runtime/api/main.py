import uvicorn
import threading
from fastapi import FastAPI

from api.api_v1.api import router as api_router
from api.utils.log_middleware import LogMiddleware
from blockchain.utils.logger import logger

app = FastAPI(
    docs_url="/api/v1/docs/",
    title="Blockchain API",
    description="This is an API communication interface to the node blockchain.",
    version="0.1.0",
)
app.add_middleware(LogMiddleware)


class NodeAPI:
    def __init__(self):
        global app
        self.app = app
        self.server_thread = None
        self.server = None

    def start(self, ip, api_port):
        """Start the API server in a separate thread to prevent blocking"""
        try:
            def run_server():
                try:
                    # Configure uvicorn with better error handling
                    config = uvicorn.Config(
                        self.app, 
                        host=ip, 
                        port=api_port, 
                        log_config=None,
                        access_log=False,  # Reduce log spam
                        loop="auto"
                    )
                    self.server = uvicorn.Server(config)
                    logger.info({
                        "message": "API server starting",
                        "host": ip,
                        "port": api_port
                    })
                    self.server.run()
                except Exception as e:
                    logger.error({
                        "message": "API server error",
                        "error": str(e),
                        "error_type": type(e).__name__
                    })
                    
            # Start server in daemon thread so it doesn't prevent shutdown
            self.server_thread = threading.Thread(target=run_server)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            # Give the server a moment to start
            import time
            time.sleep(2)
            
            logger.info({
                "message": "API server thread started",
                "host": ip,
                "port": api_port
            })
            
        except Exception as e:
            logger.error({
                "message": "Failed to start API server",
                "error": str(e),
                "error_type": type(e).__name__
            })
            raise

    def stop(self):
        """Stop the API server gracefully"""
        try:
            if self.server:
                logger.info({"message": "Stopping API server"})
                self.server.should_exit = True
        except Exception as e:
            logger.error({
                "message": "Error stopping API server",
                "error": str(e)
            })

    def inject_node(self, injected_node):
        self.app.state.node = injected_node


@app.get("/ping/", name="Healthcheck", tags=["Healthcheck"])
async def healthcheck():
    return {"success": "pong!"}


app.include_router(api_router, prefix="/api/v1")
