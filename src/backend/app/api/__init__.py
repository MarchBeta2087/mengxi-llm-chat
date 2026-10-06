from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.keys import router as keys_router

__all__ = ["admin_router", "auth_router", "keys_router"]
