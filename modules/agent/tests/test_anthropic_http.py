"""Runs the real `anthropic` client against a fake HTTP transport, so an SDK upgrade that changes
retries, streaming, the request shape or error classes fails here instead of in a live run."""

import json
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx2
import pytest

from scopesteps.agent.domain.model import (
    ModelProviderError,
    ModelRequest,
    ModelTurn,
    ToolCall,
    ToolResult,
    ToolResults,
    ToolSpec,
    UserMessage,
)
from scopesteps.agent.infrastructure.providers.anthropic_messages import (
    ANSWER_WITH_A_TOOL,
    NO_TOOL_CALL,
    NOT_STRICT_WARNING,
    SYSTEM_STEP,
    AnthropicMessagesProvider,
    only_these_tools,
    schema_as_instructions,
)

API_KEY = "local-test-key-123"
SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"
ECHOED_BODY = "echoed source text that must never be recorded"
LOOKUP = ToolSpec(
    "lookup_source",
    "Read a paragraph.",
    {"type": "object", "properties": {"block_id": {"type": "string"}}, "required": ["block_id"]},
)
REPLY = ToolSpec(
    "reply",
    "Answer the reviewer.",
    {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
)


@dataclass
class FakeAnthropic:
    """Answers each request with the next queued response; records what was sent."""

    responses: list[httpx2.Response | Exception] = field(default_factory=list[Any])
    requests: list[httpx2.Request] = field(default_factory=list[httpx2.Request])

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def body(self, index: int = 0) -> dict[str, Any]:
        return json.loads(self.requests[index].content)


@pytest.fixture
def fake() -> FakeAnthropic:
    return FakeAnthropic()


def _provider(fake: FakeAnthropic) -> AnthropicMessagesProvider:
    return AnthropicMessagesProvider(
        api_key=API_KEY,
        base_url="http://anthropic.test",
        http_client=httpx2.Client(transport=httpx2.MockTransport(fake.handle)),
    )


def _events(message: Mapping[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    usage: dict[str, Any] = dict(message.get("usage", {}))
    start: dict[str, Any] = {
        **message,
        "content": [],
        "stop_reason": None,
        "usage": {**usage, "output_tokens": 0},
    }
    yield "message_start", {"type": "message_start", "message": start}
    blocks: list[dict[str, Any]] = message["content"]
    for index, block in enumerate(blocks):
        kind = block["type"]
        empties: dict[str, dict[str, Any]] = {
            "text": {"type": "text", "text": ""},
            "thinking": {"type": "thinking", "thinking": "", "signature": ""},
            "tool_use": {**block, "input": {}},
        }
        empty = empties[kind]
        yield (
            "content_block_start",
            {"type": "content_block_start", "index": index, "content_block": empty},
        )
        deltas: list[dict[str, Any]] = {
            "text": [{"type": "text_delta", "text": block.get("text", "")}],
            "thinking": [
                {"type": "thinking_delta", "thinking": block.get("thinking", "")},
                {"type": "signature_delta", "signature": block.get("signature", "")},
            ],
            "tool_use": [
                {"type": "input_json_delta", "partial_json": json.dumps(block.get("input", {}))}
            ],
        }[kind]
        for delta in deltas:
            yield (
                "content_block_delta",
                {"type": "content_block_delta", "index": index, "delta": delta},
            )
        yield "content_block_stop", {"type": "content_block_stop", "index": index}
    yield (
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": message["stop_reason"], "stop_sequence": None},
            "usage": usage,
        },
    )
    yield "message_stop", {"type": "message_stop"}


def _stream(message: Mapping[str, Any], request_id: str = "req_ok") -> httpx2.Response:
    body = "".join(
        f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in _events(message)
    )
    return httpx2.Response(
        200,
        headers={"content-type": "text/event-stream", "request-id": request_id},
        content=body.encode(),
    )


def _message(
    content: list[dict[str, Any]],
    stop_reason: str = "end_turn",
    usage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": SONNET,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": dict(usage or {"input_tokens": 10, "output_tokens": 5}),
    }


def _error(status: int, error_type: str, message: str, **headers: str) -> httpx2.Response:
    body = {"type": "error", "error": {"type": error_type, "message": f"{message} {ECHOED_BODY}"}}
    return httpx2.Response(status, headers={"request-id": "req_failed", **headers}, json=body)


def _request(**overrides: Any) -> ModelRequest:
    values: dict[str, Any] = {
        "system_instruction": "Policy",
        "history": (UserMessage("Sources and the question"),),
        "max_output_tokens": 4000,
        "model": SONNET,
        "effort": "medium",
        "timeout_seconds": 42.0,
    }
    return ModelRequest(**{**values, **overrides})


TEXT_OK = _message([{"type": "text", "text": "Hello"}])


def test_request_shape_follows_the_binding_and_sends_no_thinking_or_sampling(
    fake: FakeAnthropic,
) -> None:
    fake.responses = [_stream(TEXT_OK)]

    _provider(fake).generate(_request(tools=(LOOKUP,)))

    sent = fake.body()
    assert sent["model"] == SONNET
    assert sent["max_tokens"] == 4000
    assert sent["stream"] is True
    assert sent["output_config"] == {"effort": "medium"}
    assert not {"thinking", "temperature", "top_p", "top_k", "fallbacks"} & set(sent)
    assert sent["tools"][0]["strict"] is True
    assert sent["tools"][0]["input_schema"]["additionalProperties"] is False
    headers = fake.requests[0].headers
    assert headers["x-api-key"] == API_KEY
    assert API_KEY not in fake.requests[0].content.decode()
    assert fake.requests[0].extensions["timeout"]["read"] == 42.0


def test_one_cache_breakpoint_follows_the_system_prompt_and_the_first_user_message(
    fake: FakeAnthropic,
) -> None:
    fake.responses = [_stream(TEXT_OK)]
    earlier = ModelTurn(
        steps=({"type": "tool_use", "id": "t1", "name": "lookup_source", "input": {}},)
    )
    history = (
        UserMessage("Sources and the question"),
        earlier,
        ToolResults((ToolResult("t1", "lookup_source", {"text": "B1"}),)),
    )

    _provider(fake).generate(_request(history=history, tools=(LOOKUP,)))

    sent = fake.body()
    assert json.dumps(sent).count("cache_control") == 1
    first = sent["messages"][0]["content"][-1]
    assert first["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in sent["system"][0]


def test_without_a_model_nothing_is_sent(fake: FakeAnthropic) -> None:
    with pytest.raises(ModelProviderError) as raised:
        _provider(fake).generate(_request(model=None))

    assert raised.value.kind == "invalid_request"
    assert fake.requests == []


def test_output_schema_keeps_only_keywords_structured_outputs_accept(fake: FakeAnthropic) -> None:
    fake.responses = [_stream(TEXT_OK)]
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "maxLength": 80, "pattern": "^S", "format": "date"},
            "note": {"type": "string", "format": "not-a-format"},
            "count": {"type": "integer", "minimum": 1, "maximum": 9},
            "ids": {"type": "array", "items": {"enum": ["B1", "B2"]}, "minItems": 1, "maxItems": 4},
            "many": {"type": "array", "items": {"type": "string"}, "minItems": 3},
        },
        "required": ["title"],
        "additionalProperties": True,
    }

    _provider(fake).generate(_request(output_schema=schema))

    sent = fake.body()["output_config"]
    assert sent["effort"] == "medium"
    stripped = sent["format"]["schema"]
    assert sent["format"]["type"] == "json_schema"
    assert stripped["additionalProperties"] is False
    assert stripped["properties"]["title"] == {"type": "string", "format": "date"}
    assert stripped["properties"]["note"] == {"type": "string"}
    assert stripped["properties"]["count"] == {"type": "integer"}
    assert stripped["properties"]["ids"] == {
        "type": "array",
        "items": {"enum": ["B1", "B2"]},
        "minItems": 1,
    }
    assert "minItems" not in stripped["properties"]["many"]


@pytest.mark.parametrize(
    ("model", "choice", "expected", "asks_in_prompt"),
    [
        (HAIKU, "any", {"type": "any"}, False),
        (SONNET, "any", {"type": "auto"}, True),
        ("claude-unknown", "any", {"type": "auto"}, True),
        (SONNET, "auto", {"type": "auto"}, False),
        (SONNET, "validated", {"type": "auto"}, False),
        (SONNET, "none", {"type": "none"}, False),
    ],
)
def test_tool_choice_follows_what_each_model_accepts(
    fake: FakeAnthropic, model: str, choice: Any, expected: dict[str, str], asks_in_prompt: bool
) -> None:
    fake.responses = [_stream(TEXT_OK)]

    _provider(fake).generate(_request(model=model, tools=(LOOKUP, REPLY), tool_choice=choice))

    sent = fake.body()
    assert sent["tool_choice"] == expected
    assert (ANSWER_WITH_A_TOOL in sent["system"][0]["text"]) is asks_in_prompt


def test_haiku_is_narrowed_to_one_tool_by_a_forced_choice_with_every_tool_still_sent(
    fake: FakeAnthropic,
) -> None:
    fake.responses = [_stream(TEXT_OK)]

    result = _provider(fake).generate(
        _request(model=HAIKU, tools=(LOOKUP, REPLY), tool_choice="any", allowed_tools=("reply",))
    )

    sent = fake.body()
    assert [tool["name"] for tool in sent["tools"]] == ["lookup_source", "reply"]
    assert sent["tool_choice"] == {"type": "tool", "name": "reply"}
    assert all(message["role"] != "system" for message in sent["messages"])
    assert all(step.get("type") != SYSTEM_STEP for step in result.turn.steps)


@pytest.mark.parametrize(
    ("model", "choice", "expected"),
    [
        (SONNET, "any", {"type": "auto"}),
        ("claude-unknown", "any", {"type": "auto"}),
        (SONNET, "auto", {"type": "auto"}),
        (HAIKU, "auto", {"type": "auto"}),
    ],
)
def test_other_narrowed_calls_append_a_system_message_with_every_tool_still_sent(
    fake: FakeAnthropic, model: str, choice: Any, expected: dict[str, str]
) -> None:
    fake.responses = [_stream(TEXT_OK)]

    result = _provider(fake).generate(
        _request(model=model, tools=(LOOKUP, REPLY), tool_choice=choice, allowed_tools=("reply",))
    )

    sent = fake.body()
    note = only_these_tools(["reply"])
    assert [tool["name"] for tool in sent["tools"]] == ["lookup_source", "reply"]
    assert sent["tool_choice"] == expected
    assert sent["messages"][-1] == {"role": "system", "content": note}
    assert result.turn.steps[-1] == {"type": SYSTEM_STEP, "text": note}


def test_allowed_tools_naming_every_tool_narrow_nothing(fake: FakeAnthropic) -> None:
    fake.responses = [_stream(TEXT_OK)]

    _provider(fake).generate(
        _request(model=HAIKU, tools=(REPLY,), tool_choice="any", allowed_tools=("reply",))
    )

    sent = fake.body()
    assert sent["tool_choice"] == {"type": "any"}
    assert all(message["role"] != "system" for message in sent["messages"])


def test_a_text_answer_when_a_tool_call_was_required_is_bad_output(fake: FakeAnthropic) -> None:
    fake.responses = [_stream(TEXT_OK)]

    result = _provider(fake).generate(_request(tools=(REPLY,), tool_choice="any"))

    assert result.tool_calls == ()
    assert (result.finish_reason, result.provider_status) == ("other", NO_TOOL_CALL)
    assert result.warnings


@pytest.mark.parametrize(
    ("stop_reason", "finish"),
    [
        ("end_turn", "completed"),
        ("max_tokens", "max_tokens"),
        ("refusal", "blocked"),
        ("pause_turn", "other"),
        ("stop_sequence", "other"),
    ],
)
def test_stop_reasons_map_to_finish_reasons(
    fake: FakeAnthropic, stop_reason: str, finish: str
) -> None:
    fake.responses = [_stream(_message([{"type": "text", "text": "x"}], stop_reason))]

    assert _provider(fake).generate(_request()).finish_reason == finish


def test_tool_use_is_parsed_and_thinking_kept_verbatim(fake: FakeAnthropic) -> None:
    thinking = {"type": "thinking", "thinking": "", "signature": "c2lnbmF0dXJl"}
    call = {
        "type": "tool_use",
        "id": "toolu_1",
        "name": "lookup_source",
        "input": {"block_id": "B2"},
    }
    fake.responses = [_stream(_message([thinking, call], "tool_use"), request_id="req_42")]

    result = _provider(fake).generate(_request(tools=(LOOKUP,)))

    assert result.finish_reason == "tool_calls"
    assert result.tool_calls == (ToolCall("toolu_1", "lookup_source", {"block_id": "B2"}),)
    assert result.request_id == "req_42"
    assert result.turn.steps == (thinking, call)


def test_thinking_goes_back_unchanged_while_the_prefix_is_the_same(fake: FakeAnthropic) -> None:
    thinking = {"type": "thinking", "thinking": "", "signature": "c2lnbmF0dXJl"}
    call = {
        "type": "tool_use",
        "id": "toolu_1",
        "name": "lookup_source",
        "input": {"block_id": "B2"},
    }
    fake.responses = [_stream(_message([thinking, call], "tool_use")), _stream(TEXT_OK)]
    provider = _provider(fake)
    first = provider.generate(_request(tools=(LOOKUP,)))
    results = ToolResults((ToolResult("toolu_1", "lookup_source", {"text": "B2"}),))

    provider.generate(_request(tools=(LOOKUP,), history=(*_request().history, first.turn, results)))

    sent = fake.body(1)["messages"]
    assert sent[1] == {"role": "assistant", "content": [thinking, call]}
    assert sent[2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "toolu_1",
        "content": json.dumps({"text": "B2"}),
        "is_error": False,
    }


def test_a_narrowed_last_call_keeps_the_history_append_only(fake: FakeAnthropic) -> None:
    """The prefix stays the same across the step, so earlier thinking goes back unchanged, and
    the system message appended for a call goes back before the turn it produced."""
    thinking = {"type": "thinking", "thinking": "", "signature": "c2lnbmF0dXJl"}
    call = {
        "type": "tool_use",
        "id": "toolu_1",
        "name": "lookup_source",
        "input": {"block_id": "B2"},
    }
    answer = {"type": "tool_use", "id": "toolu_2", "name": "reply", "input": {"text": "x"}}
    fake.responses = [
        _stream(_message([thinking, call], "tool_use")),
        _stream(_message([thinking, answer], "tool_use")),
        _stream(TEXT_OK),
    ]
    provider = _provider(fake)
    tools = (LOOKUP, REPLY)
    first = provider.generate(_request(tools=tools, tool_choice="any"))
    looked_up = ToolResults((ToolResult("toolu_1", "lookup_source", {"text": "B2"}),))
    history = (*_request().history, first.turn, looked_up)
    last = provider.generate(
        _request(tools=tools, tool_choice="any", allowed_tools=("reply",), history=history)
    )
    rejected = ToolResults((ToolResult("toolu_2", "reply", {"error": "bad"}, is_error=True),))

    provider.generate(
        _request(tools=tools, tool_choice="any", history=(*history, last.turn, rejected))
    )

    second, third = fake.body(1), fake.body(2)
    assert fake.body(0)["system"] == second["system"] == third["system"]
    assert fake.body(0)["tools"] == second["tools"] == third["tools"]
    note = {"role": "system", "content": only_these_tools(["reply"])}
    assert third["messages"][: len(second["messages"])] == second["messages"]
    assert third["messages"][1] == {"role": "assistant", "content": [thinking, call]}
    assert third["messages"][3:5] == [note, {"role": "assistant", "content": [thinking, answer]}]


def test_usage_separates_thinking_and_cache_tokens(fake: FakeAnthropic) -> None:
    usage = {
        "input_tokens": 100,
        "cache_read_input_tokens": 50,
        "cache_creation_input_tokens": 25,
        "output_tokens": 40,
        "output_tokens_details": {"thinking_tokens": 15},
    }
    fake.responses = [_stream(_message([{"type": "text", "text": "x"}], usage=usage))]

    result = _provider(fake).generate(_request())

    counted = result.usage
    assert (counted.input_tokens, counted.output_tokens, counted.thinking_tokens) == (100, 25, 15)
    assert (counted.cache_read_tokens, counted.cache_write_tokens) == (50, 25)
    assert counted.total_tokens == 215


ERRORS: list[tuple[Callable[[], httpx2.Response], str]] = [
    (lambda: _error(429, "rate_limit_error", "Too many requests", **{"retry-after": "7"}), "quota"),
    (lambda: _error(429, "rate_limit_error", "ramp_limit_exceeded: slow down"), "quota"),
    (lambda: _error(429, "rate_limit_error", "enforced_spend_limit_reached"), "spend_limit"),
    (
        lambda: _error(
            400,
            "invalid_request_error",
            "You have reached your specified API usage limits. You will regain access later.",
        ),
        "spend_limit",
    ),
    (lambda: _error(529, "overloaded_error", "Overloaded"), "unavailable"),
    (lambda: _error(500, "api_error", "Internal error"), "unavailable"),
    (lambda: _error(504, "timeout_error", "Deadline exceeded"), "timeout"),
    (lambda: _error(413, "request_too_large", "Request too large"), "request_too_large"),
    (lambda: _error(401, "authentication_error", "Bad key"), "auth"),
    (lambda: _error(402, "billing_error", "Billing"), "auth"),
    (lambda: _error(403, "permission_error", "Forbidden"), "auth"),
    (lambda: _error(400, "invalid_request_error", "Bad parameter"), "invalid_request"),
    (lambda: _error(404, "not_found_error", "No such model"), "invalid_request"),
    (
        lambda: _error(400, "invalid_request_error", "The compiled grammar is too large."),
        "schema_too_complex",
    ),
    (
        lambda: _error(400, "invalid_request_error", "Schema is too complex for compilation."),
        "schema_too_complex",
    ),
]


@pytest.mark.parametrize(("response", "kind"), ERRORS)
def test_errors_are_classified_after_exactly_one_request(
    fake: FakeAnthropic, response: Callable[[], httpx2.Response], kind: str
) -> None:
    fake.responses = [response(), _stream(TEXT_OK)]

    with pytest.raises(ModelProviderError) as raised:
        _provider(fake).generate(_request())

    error = raised.value
    assert error.kind == kind
    assert len(fake.requests) == 1, "the SDK must not retry behind the budget's back"
    assert error.request_id == "req_failed"
    assert "req_failed" in error.message
    assert ECHOED_BODY not in f"{error.message} {error.details}"
    assert error.retryable is (kind in {"quota", "unavailable", "timeout"})


def test_a_rate_limit_reports_when_to_try_again(fake: FakeAnthropic) -> None:
    fake.responses = [_error(429, "rate_limit_error", "Too many", **{"retry-after": "7"})]

    with pytest.raises(ModelProviderError) as raised:
        _provider(fake).generate(_request())

    assert raised.value.retry_after_seconds == 7


@pytest.mark.parametrize(
    ("failure", "kind"),
    [
        (httpx2.ReadTimeout("slow"), "timeout"),
        (httpx2.ConnectError("refused"), "unavailable"),
    ],
)
def test_transport_failures_are_classified_without_retrying(
    fake: FakeAnthropic, failure: Exception, kind: str
) -> None:
    fake.responses = [failure, _stream(TEXT_OK)]

    with pytest.raises(ModelProviderError) as raised:
        _provider(fake).generate(_request())

    assert raised.value.kind == kind
    assert len(fake.requests) == 1


class _DropsMidStream(httpx2.SyncByteStream):
    """Sends the first event of an answer, then fails the way a dropped connection does."""

    def __init__(self, first: bytes, failure: Exception) -> None:
        self._first, self._failure = first, failure

    def __iter__(self) -> Iterator[bytes]:
        yield self._first
        raise self._failure


@pytest.mark.parametrize(
    ("failure", "kind"),
    [
        (httpx2.ReadError("Connection reset by peer"), "unavailable"),
        (httpx2.ReadTimeout("slow"), "timeout"),
    ],
)
def test_a_network_failure_while_the_answer_streams_is_classified(
    fake: FakeAnthropic, failure: Exception, kind: str
) -> None:
    name, data = next(_events(TEXT_OK))
    first = f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()
    fake.responses = [
        httpx2.Response(
            200,
            headers={"content-type": "text/event-stream", "request-id": "req_drop"},
            stream=_DropsMidStream(first, failure),
        )
    ]

    with pytest.raises(ModelProviderError) as raised:
        _provider(fake).generate(_request())

    assert raised.value.kind == kind
    assert len(fake.requests) == 1


def test_an_error_inside_the_stream_is_classified(fake: FakeAnthropic) -> None:
    error = {"type": "error", "error": {"type": "overloaded_error", "message": ECHOED_BODY}}
    body = f"event: error\ndata: {json.dumps(error)}\n\n"
    fake.responses = [
        httpx2.Response(
            200,
            headers={"content-type": "text/event-stream", "request-id": "req_mid"},
            content=body.encode(),
        )
    ]

    with pytest.raises(ModelProviderError) as raised:
        _provider(fake).generate(_request())

    assert raised.value.kind == "unavailable"
    assert ECHOED_BODY not in raised.value.message


ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string", "maxLength": 80}},
    "required": ["summary"],
}
TOO_COMPLEX = "The compiled grammar is too large, which would cause performance issues."


def test_a_schema_sent_as_instructions_goes_in_an_appended_system_message(
    fake: FakeAnthropic,
) -> None:
    answer = 'Here it is:\n```json\n{"summary": "Done"}\n```'
    fake.responses = [_stream(_message([{"type": "text", "text": answer}]))]

    result = _provider(fake).generate(_request(output_schema=ANSWER_SCHEMA, strict_output=False))

    body = fake.body()
    assert "format" not in body["output_config"], "no strict decoding"
    assert body["system"][0]["text"] == "Policy", "the system prompt stays the step's own"
    assert body["messages"][-1] == {
        "role": "system",
        "content": schema_as_instructions(ANSWER_SCHEMA),
    }
    assert '"maxLength":80' in body["messages"][-1]["content"], "the full schema, unstripped"
    assert result.text == '{"summary": "Done"}'
    assert result.warnings == (NOT_STRICT_WARNING,)
    assert result.turn.steps[-1] == {
        "type": SYSTEM_STEP,
        "text": schema_as_instructions(ANSWER_SCHEMA),
    }, "kept in the history, so later calls stay append-only"


def test_a_schema_sent_as_instructions_joins_a_narrowing_message(fake: FakeAnthropic) -> None:
    fake.responses = [_stream(TEXT_OK)]

    _provider(fake).generate(
        _request(
            output_schema=ANSWER_SCHEMA,
            strict_output=False,
            tools=(LOOKUP, REPLY),
            allowed_tools=("reply",),
            tool_choice="any",
        )
    )

    note = fake.body()["messages"][-1]
    assert note["role"] == "system"
    assert note["content"] == (
        f"{only_these_tools(['reply'])}\n\n{schema_as_instructions(ANSWER_SCHEMA)}"
    )


def test_a_schema_the_api_cannot_compile_is_sent_as_instructions_from_then_on(
    fake: FakeAnthropic,
) -> None:
    fake.responses = [
        _error(400, "invalid_request_error", TOO_COMPLEX),
        _stream(_message([{"type": "text", "text": '{"summary": "Done"}'}])),
        _stream(TEXT_OK),
    ]
    provider = _provider(fake)

    with pytest.raises(ModelProviderError) as raised:
        provider.generate(_request(output_schema=ANSWER_SCHEMA))
    assert raised.value.kind == "schema_too_complex"
    assert not raised.value.retryable
    assert "format" in fake.body(0)["output_config"]

    result = provider.generate(_request(output_schema=ANSWER_SCHEMA))
    assert "format" not in fake.body(1)["output_config"], "the refused request is not repeated"
    assert result.warnings == (NOT_STRICT_WARNING,)

    other = {**ANSWER_SCHEMA, "required": []}
    provider.generate(_request(output_schema=other))
    assert "format" in fake.body(2)["output_config"], "another schema stays strict"
