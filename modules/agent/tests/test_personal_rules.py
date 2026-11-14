"""The prompt versions that keep small talk and personal remarks out: each is the version before
it, unchanged, plus the rule, and none is adopted until it is measured."""

from scopesteps.agent.application.changing import CHANGE_PROMPTS, CHANGE_RUN
from scopesteps.agent.application.drafting import (
    DRAFT_PROMPTS,
    MARKED_PROMPTS,
    PROMPT_CHECKS,
    PROMPT_SCHEMAS,
    STEP_PROMPTS,
)
from scopesteps.agent.application.replying import (
    CONVERSATION_REPLY,
    DISCUSS_REPLIES,
    DISCUSS_REPLY,
    REPLY_PROMPTS,
)
from scopesteps.agent.application.steps import DRAFT_PROMPT

RULE = "Small talk and personal remarks:"


def test_draft_v16_is_draft_v15_plus_the_rule_in_both_steps() -> None:
    assert DRAFT_PROMPTS["draft-v16"].startswith(DRAFT_PROMPTS["draft-v15"])
    assert RULE in DRAFT_PROMPTS["draft-v16"]
    assert STEP_PROMPTS["draft-v16"].startswith(STEP_PROMPTS["draft-v15"])
    assert "a named person's address, email or phone number" in STEP_PROMPTS["draft-v16"]
    assert PROMPT_SCHEMAS["draft-v16"] == PROMPT_SCHEMAS["draft-v15"]
    assert PROMPT_CHECKS["draft-v16"] == PROMPT_CHECKS["draft-v15"]
    assert "draft-v16" in MARKED_PROMPTS


def test_change_v9_and_reply_v6_v7_add_the_rule_to_the_versions_in_use() -> None:
    assert CHANGE_PROMPTS["change-v9"].startswith(CHANGE_PROMPTS["change-v8"])
    assert REPLY_PROMPTS["reply-v6"].startswith(REPLY_PROMPTS["reply-v4"])
    assert REPLY_PROMPTS["reply-v7"].startswith(REPLY_PROMPTS["reply-v5"])
    assert all(
        RULE in prompt
        for prompt in (
            CHANGE_PROMPTS["change-v9"],
            REPLY_PROMPTS["reply-v6"],
            REPLY_PROMPTS["reply-v7"],
        )
    )
    assert "reply-v7" in DISCUSS_REPLIES


def test_new_runs_keep_the_measured_prompts_until_the_rule_is_measured() -> None:
    assert (DRAFT_PROMPT, CHANGE_RUN, CONVERSATION_REPLY, DISCUSS_REPLY) == (
        "draft-v15",
        "change-v8",
        "reply-v4",
        "reply-v5",
    )
