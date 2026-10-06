from app.api.admin import router as admin_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.keys import router as keys_router
from app.api.plugins import admin_router as plugins_admin_router
from app.api.plugins import router as plugins_router

__all__ = [
    "admin_router",
    "audit_router",
    "auth_router",
    "chat_router",
    "keys_router",
    "plugins_admin_router",
    "plugins_router",
]
