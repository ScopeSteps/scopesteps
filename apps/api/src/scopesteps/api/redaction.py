"""Keeps one-time link tokens out of the server's access log.

An invitation's token is part of its API path (`/invitations/{token}`), and the access log
writes every path. Whoever reads the log must not be able to join a project with it.
"""

import logging
import re

_TOKEN_IN_PATH = re.compile(r"(/invitations/)[A-Za-z0-9_-]{20,}")


class LinkTokenFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                _TOKEN_IN_PATH.sub(r"\1[redacted]", arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        record.msg = _TOKEN_IN_PATH.sub(r"\1[redacted]", str(record.msg))
        return True


def redact_link_tokens_in_access_log() -> None:
    access_log = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, LinkTokenFilter) for f in access_log.filters):
        access_log.addFilter(LinkTokenFilter())
