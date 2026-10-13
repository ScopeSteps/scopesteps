from scopesteps.agent.domain.model import (
    ModelRequest,
    ModelResult,
    ModelTurn,
    Usage,
    UserMessage,
)
from scopesteps.agent.domain.rate import TokenWindow
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider
from scopesteps.agent.infrastructure.providers.paced import PacedProvider

REQUEST = ModelRequest(
    system_instruction="Policy", history=(UserMessage("x" * 3000),), max_output_tokens=6000
)


def _result(total: int) -> ModelResult:
    return ModelResult(
        "groq", "m", ModelTurn(()), "ok", (), "completed",
        Usage(input_tokens=1000, output_tokens=total - 1000, total_tokens=total), 10,
    )  # fmt: skip


def test_calls_wait_only_when_the_next_one_would_pass_the_minute_allowance() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    provider = PacedProvider(
        ScriptedProvider([_result(6000), _result(6000)]),
        TokenWindow(8000),
        clock=lambda: now[0],
        sleep=sleep,
        log=lambda _: None,
    )

    provider.generate(REQUEST)
    now[0] = 5
    provider.generate(REQUEST)

    assert sleeps == [55], "the first call's 6K tokens leave the window at 60 s"
