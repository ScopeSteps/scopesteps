"""Runs the real google-genai client against a local server, so SDK upgrades that change retry,
storage or parsing behaviour fail here instead of in a live run."""

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from scopesteps.agent.domain.model import ModelProviderError, ModelRequest, UserMessage
from scopesteps.agent.infrastructure.providers.gemini import GeminiProvider

API_KEY = "local-test-key-123"


@dataclass
class FakeGemini:
    status: int = 200
    response: Any = None
    requests: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    headers: list[dict[str, str]] = field(default_factory=list[dict[str, str]])
    url: str = ""


@pytest.fixture
def server() -> Iterator[FakeGemini]:
    state = FakeGemini()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("content-length", 0))
            state.requests.append(json.loads(self.rfile.read(length) or b"{}"))
            state.headers.append(dict(self.headers))
            payload = json.dumps(state.response).encode()
            self.send_response(state.status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    state.url = f"http://127.0.0.1:{httpd.server_port}"
    yield state
    httpd.shutdown()


def _provider(server: FakeGemini) -> GeminiProvider:
    return GeminiProvider(
        api_key=API_KEY,
        model_id="gemini-test",
        timeout_seconds=5,
        thinking_level="low",
        base_url=server.url,
    )


REQUEST = ModelRequest(
    system_instruction="Policy", history=(UserMessage("Hi"),), max_output_tokens=50
)


@pytest.mark.parametrize(
    ("status", "body", "kind"),
    [
        (
            429,
            {
                "error": {
                    "code": 429,
                    "status": "RESOURCE_EXHAUSTED",
                    "details": [{"retryDelay": "17s"}],
                }
            },
            "quota",
        ),
        (500, {"error": {"code": 500, "status": "INTERNAL"}}, "unavailable"),
        (503, {"error": {"code": 503, "status": "UNAVAILABLE"}}, "unavailable"),
        (
            400,
            [
                {
                    "error": {
                        "code": 400,
                        "status": "INVALID_ARGUMENT",
                        "details": [{"reason": "API_KEY_INVALID"}],
                    }
                }
            ],
            "auth",
        ),
    ],
)
def test_failures_are_classified_after_exactly_one_request(
    server: FakeGemini, status: int, body: Any, kind: str
) -> None:
    server.status, server.response = status, body

    with pytest.raises(ModelProviderError) as raised:
        _provider(server).generate(REQUEST)

    assert raised.value.kind == kind
    assert len(server.requests) == 1, "the SDK must not retry behind the budget's back"


def test_quota_error_reports_retry_delay(server: FakeGemini) -> None:
    server.status = 429
    server.response = {"error": {"code": 429, "details": [{"retryDelay": "17s"}]}}

    with pytest.raises(ModelProviderError) as raised:
        _provider(server).generate(REQUEST)

    assert raised.value.retry_after_seconds == 17


def test_successful_response_is_parsed_and_request_is_stateless(server: FakeGemini) -> None:
    server.response = {
        "id": "interaction-1",
        "status": "requires_action",
        "model": "gemini-test",
        "steps": [
            {"type": "thought", "signature": "c2lnbmF0dXJl"},
            {
                "type": "function_call",
                "id": "call-1",
                "name": "lookup_source",
                "arguments": {"query": "cancel"},
            },
        ],
        "usage": {"total_input_tokens": 12, "total_output_tokens": 4, "total_tokens": 16},
    }

    result = _provider(server).generate(REQUEST)

    assert result.finish_reason == "tool_calls"
    assert result.tool_calls[0].arguments == {"query": "cancel"}
    assert result.usage.total_tokens == 16
    assert [step["type"] for step in result.turn.steps] == ["thought", "function_call"]
    sent = server.requests[0]
    assert sent["store"] is False
    assert sent["model"] == "gemini-test"
    assert API_KEY not in json.dumps(sent), "the key belongs in a header, never the body"
    assert {k.lower(): v for k, v in server.headers[0].items()}.get("x-goog-api-key") == API_KEY
