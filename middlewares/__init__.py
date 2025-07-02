from .logging_middleware import LoggingMiddleware

def setup_middlewares(dp):
    """Setup all middlewares."""
    dp.update.middleware(LoggingMiddleware())