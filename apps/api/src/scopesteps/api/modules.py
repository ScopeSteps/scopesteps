"""Modules this deployable can mount, keyed by their ENABLED_MODULES name."""

from importlib import import_module
from importlib.util import find_spec

from fastapi import APIRouter

MODULE_NAMES = (
    "identity",
    "projects",
    "sources",
    "evidence",
    "backlog",
    "change_control",
    "agent",
    "audit",
)


def load_router(module_name: str) -> APIRouter:
    router: APIRouter = import_module(f"scopesteps.{module_name}.http.router").router
    return router


def register_all_tables() -> None:
    """Import every module's ORM so its tables join the shared metadata (for Alembic)."""
    for module_name in MODULE_NAMES:
        orm_module = f"scopesteps.{module_name}.infrastructure.orm"
        if find_spec(orm_module) is not None:
            import_module(orm_module)
