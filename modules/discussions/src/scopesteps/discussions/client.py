"""What other modules may use of discussions: its ids. Discussions are never a source for the
agent; a person sends one on as a change request (ADR 0020)."""

from scopesteps.discussions.domain.ids import CommentId, ThreadId

__all__ = ["CommentId", "ThreadId"]
