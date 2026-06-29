"""
FastAPI dependency providers.

Routes import ``get_container`` via ``Depends()`` to receive the
``ServiceContainer`` for the current request.  The container is stored on
``app.state.container`` by ``create_app()``.
"""
from fastapi import Request

from core.container import ServiceContainer


def get_container(request: Request) -> ServiceContainer:
    """Return the application-level service container."""
    return request.app.state.container
