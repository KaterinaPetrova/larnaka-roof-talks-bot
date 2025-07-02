from aiogram import Router
from .commands import router as commands_router
from .registration import router as registration_router
from .events import router as events_router
from .admin import router as admin_router

def register_all_handlers(dp):
    """Register all handlers."""
    router = Router()
    
    # Include all routers
    router.include_router(commands_router)
    router.include_router(registration_router)
    router.include_router(events_router)
    router.include_router(admin_router)
    
    # Register the main router
    dp.include_router(router)