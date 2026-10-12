"""Identifier helpers. IDs are UUIDs; time-ordered v7 keeps index locality."""

import uuid


def new_id() -> uuid.UUID:
    return uuid.uuid7()
