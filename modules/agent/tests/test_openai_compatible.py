"""The OpenAI-compatible adapter (Groq), run against a local server with the real openai SDK, so
an SDK upgrade that changes retries or parsing fails here instead of in a live run."""

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from scopesteps.agent.application.schemas import DraftBacklog, LookupSourceArgs, provider_schema
from scopesteps.agent.domain.model import (
    ModelProviderError,
    ModelRequest,
    ModelTurn,
    ToolResult,
    ToolResults,
    ToolSpec,
    UserMessage,
)
from scopesteps.agent.infrastructure.providers.openai_compatible import (
    OpenAICompatibleProvider,
    build_request_body,
    strict_schema,
)

API_KEY = "local-test-key-123"
LOOKUP = ToolSpec("lookup_source", "Search sources.", provider_schema(LookupSourceArgs))
REQUEST = ModelRequest(
    system_instruction="Policy", history=(UserMessage("Hi"),), max_output_tokens=8000
)


@dataclass
class FakeServer:
    status: int = 200
    response: Any = None
    headers: dict[str, str] = field(default_factory=dict[str, str])
    requests: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    url: str = ""


@pytest.fixture
def server() -> Iterator[FakeServer]:
    state = FakeServer()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("content-length", 0))
            state.requests.append(json.loads(self.rfile.read(length) or b"{}"))
            payload = json.dumps(state.response).encode()
            self.send_response(state.status)
            self.send_header("content-type", "application/json")
            for name, value in state.headers.items():
                self.send_header(name, value)
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    state.url = f"http://127.0.0.1:{httpd.server_port}/openai/v1"
    yield state
    httpd.shutdown()


def _provider(server: FakeServer, cap: int | None = None) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        provider="groq",
        api_key=API_KEY,
        model_id="openai/gpt-oss-120b",
        base_url=server.url,
        timeout_seconds=5,
        thinking_level="minimal",
        max_output_tokens_cap=cap,
        reasoning_effort_models=("openai/gpt-oss",),
    )


def _completion(message: dict[str, Any], finish: str = "stop") -> dict[str, Any]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "openai/gpt-oss-120b",
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {
            "prompt_tokens": 1200,
            "completion_tokens": 300,
            "total_tokens": 1500,
            "completion_tokens_details": {"reasoning_tokens": 100},
        },
    }


def test_text_reply_is_parsed_with_usage_split_into_output_and_reasoning(
    server: FakeServer,
) -> None:
    server.response = _completion({"role": "assistant", "content": "READY"})

    result = _provider(server, cap=6000).generate(REQUEST)

    assert (result.text, result.finish_reason, result.model_id) == (
        "READY",
        "completed",
        "openai/gpt-oss-120b",
    )
    assert (result.usage.input_tokens, result.usage.output_tokens) == (1200, 200)
    assert (result.usage.thinking_tokens, result.usage.total_tokens) == (100, 1500)
    sent = server.requests[0]
    assert sent["messages"] == [
        {"role": "system", "content": "Policy"},
        {"role": "user", "content": "Hi"},
    ]
    assert sent["max_completion_tokens"] == 6000, "capped below the run's per-call limit"
    assert (sent["reasoning_effort"], sent["include_reasoning"]) == ("low", False)


def test_tool_calls_round_trip_through_history(server: FakeServer) -> None:
    server.response = _completion(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "lookup_source", "arguments": '{"query": "rooms"}'},
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "lookup_source", "arguments": "{not json"},
                },
            ],
        },
        finish="tool_calls",
    )
    provider = _provider(server)

    result = provider.generate(
        ModelRequest(
            system_instruction="Policy",
            history=(UserMessage("Hi"),),
            max_output_tokens=100,
            tools=(LOOKUP,),
        )
    )

    assert result.finish_reason == "tool_calls"
    assert [(call.id, dict(call.arguments)) for call in result.tool_calls] == [
        ("call_1", {"query": "rooms"}),
        ("call_2", {"unparseable_arguments": "{not json"}),
    ]
    assert server.requests[0]["tool_choice"] == "auto"
    assert server.requests[0]["tools"][0]["function"]["name"] == "lookup_source"

    follow_up = build_request_body(
        ModelRequest(
            system_instruction="Policy",
            history=(
                UserMessage("Hi"),
                result.turn,
                ToolResults((ToolResult("call_1", "lookup_source", {"blocks": []}),)),
            ),
            max_output_tokens=100,
        ),
        "openai/gpt-oss-120b",
        "minimal",
    )
    assistant, tool = follow_up["messages"][2:]
    assert assistant["tool_calls"][0]["id"] == "call_1"
    assert tool == {"role": "tool", "tool_call_id": "call_1", "content": '{"blocks": []}'}


def test_a_forced_single_tool_names_it() -> None:
    body = build_request_body(
        ModelRequest(
            system_instruction="P",
            history=(UserMessage("Hi"),),
            max_output_tokens=10,
            tools=(LOOKUP,),
            tool_choice="any",
            allowed_tools=("lookup_source",),
        ),
        "openai/gpt-oss-120b",
        "low",
    )

    assert body["tool_choice"] == {"type": "function", "function": {"name": "lookup_source"}}


def test_structured_output_drops_tools_and_uses_strict_mode_when_the_schema_allows() -> None:
    body = build_request_body(
        ModelRequest(
            system_instruction="P",
            history=(UserMessage("Hi"),),
            max_output_tokens=10,
            tools=(LOOKUP,),
            tool_choice="none",
            output_schema=provider_schema(DraftBacklog),
        ),
        "qwen/qwen3.8-27b",
        "low",
    )

    assert "tools" not in body
    assert "reasoning_effort" not in body, "only gpt-oss models take reasoning_effort"
    format_ = body["response_format"]["json_schema"]
    assert format_["strict"] is True
    assert "maxItems" not in json.dumps(format_["schema"])


def test_a_schema_with_optional_fields_falls_back_to_best_effort() -> None:
    _, strict = strict_schema(provider_schema(LookupSourceArgs))

    assert strict is False


@pytest.mark.parametrize(
    ("status", "headers", "kind", "retry_after"),
    [
        (429, {"retry-after": "7"}, "quota", 7.0),
        (413, {}, "request_too_large", None),
        (401, {}, "auth", None),
        (400, {}, "invalid_request", None),
        (503, {}, "unavailable", None),
    ],
)
def test_errors_are_classified_and_sent_exactly_once(
    server: FakeServer,
    status: int,
    headers: dict[str, str],
    kind: str,
    retry_after: float | None,
) -> None:
    server.status, server.headers = status, headers
    server.response = {"error": {"message": "echoes the prompt: SECRET-SOURCE-TEXT"}}

    with pytest.raises(ModelProviderError) as raised:
        _provider(server).generate(REQUEST)

    assert (raised.value.kind, raised.value.retry_after_seconds) == (kind, retry_after)
    assert "SECRET-SOURCE-TEXT" not in raised.value.message
    assert len(server.requests) == 1, "the adapter never retries"


def test_replayed_model_turns_from_another_provider_are_ignored() -> None:
    gemini_turn = ModelTurn(({"type": "model_output", "content": []},))

    body = build_request_body(
        ModelRequest(system_instruction="P", history=(gemini_turn,), max_output_tokens=10),
        "openai/gpt-oss-120b",
        "low",
    )

    assert body["messages"] == [{"role": "system", "content": "P"}]


def test_output_the_provider_rejects_against_the_schema_comes_back_as_empty_output(
    server: FakeServer,
) -> None:
    server.status = 400
    server.response = {"error": {"code": "json_validate_failed", "message": "max tokens"}}

    result = _provider(server).generate(REQUEST)

    assert (result.text, result.provider_status) == ("", "json_validate_failed")
    assert result.warnings
    assert not result.usage_reported, "zero usage here means unknown, not free"


def test_the_output_budget_shrinks_to_fit_the_per_request_token_limit() -> None:
    history = (UserMessage("x" * 9000),)  # about 3000 tokens at the pessimistic estimate

    body = build_request_body(
        ModelRequest(system_instruction="P", history=history, max_output_tokens=6000),
        "openai/gpt-oss-120b",
        "low",
        cap=6000,
        request_token_limit=8000,
    )

    assert 4000 < body["max_completion_tokens"] < 5000, "8000 minus input, not the full cap"


def test_a_request_that_cannot_fit_fails_before_it_is_sent(server: FakeServer) -> None:
    provider = OpenAICompatibleProvider(
        provider="groq",
        api_key=API_KEY,
        model_id="openai/gpt-oss-120b",
        base_url=server.url,
        timeout_seconds=5,
        thinking_level="low",
        request_token_limit=8000,
    )
    huge = ModelRequest(
        system_instruction="P", history=(UserMessage("x" * 30000),), max_output_tokens=6000
    )

    with pytest.raises(ModelProviderError) as raised:
        provider.generate(huge)

    assert raised.value.kind == "request_too_large"
    assert server.requests == [], "nothing is spent on a request that cannot succeed"
