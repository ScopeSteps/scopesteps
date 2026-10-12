from scopesteps.kernel import DomainError, DomainEvent, new_id


def test_new_id_is_unique_and_time_ordered() -> None:
    first, second = new_id(), new_id()

    assert first != second
    assert first.version == 7
    assert first < second


def test_domain_error_defaults_details_to_empty() -> None:
    error = DomainError("Something went wrong")

    assert error.message == "Something went wrong"
    assert error.details == {}
    assert error.retryable is False


def test_domain_event_has_identity_and_timestamp() -> None:
    event = DomainEvent()

    assert event.event_id.version == 7
    assert event.occurred_at.tzinfo is not None
