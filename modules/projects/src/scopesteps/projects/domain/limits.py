from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectLimits:
    """The ceilings that apply to work in a project, as this deployment is configured.

    The composition root fills this in from settings and the owning modules' constants; the
    values are enforced where they are owned, and only reported here.
    """

    source_max_bytes: int
    source_max_words: int
    run_max_turns: int
    run_max_tool_calls: int
    run_max_clarification_rounds: int
    backlog_max_epics: int
    backlog_max_stories: int
