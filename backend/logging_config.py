import logging
import sys

def setup_logging():
    """
    Sets up unified logging configuration for the VISTA-SL Middleware Backend.
    Sets levels and output formats.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    # Ensure standard libraries logs aren't too verbose
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# Export a helper logger instance
logger = logging.getLogger("vista-middleware")
