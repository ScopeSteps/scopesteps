from scopesteps.agent.domain.rate import TokenWindow


def test_a_call_that_fits_does_not_wait() -> None:
    window = TokenWindow(8000)
    window.record(0, 3000)

    assert window.wait_seconds(10, 4000) == 0


def test_a_call_that_does_not_fit_waits_for_enough_tokens_to_expire() -> None:
    window = TokenWindow(8000)
    window.record(0, 3000)
    window.record(20, 3000)

    assert window.wait_seconds(30, 4000) == 30, "the first call expires at 60 s"


def test_a_call_larger_than_the_allowance_waits_for_an_empty_window() -> None:
    window = TokenWindow(8000)
    window.record(0, 2000)
    window.record(30, 2000)

    assert window.wait_seconds(40, 9000) == 50


def test_old_usage_is_forgotten() -> None:
    window = TokenWindow(8000)
    window.record(0, 8000)

    assert window.wait_seconds(61, 8000) == 0
