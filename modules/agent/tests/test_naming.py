import pytest

from scopesteps.agent.application.naming import name_labels, name_labels_in

NAMES = {"B12": "brief paragraph 12", "A1": "reviewer answer", "S3": '"Cancel a booking"'}


@pytest.mark.parametrize(
    ("text", "named"),
    [
        ("The brief left it open (B12).", "The brief left it open (brief paragraph 12)."),
        ("Cancellations under S3 change.", 'Cancellations under "Cancel a booking" change.'),
        ("B120 and AB12 are not labels here.", "B120 and AB12 are not labels here."),
        ("Unknown B99 stays.", "Unknown B99 stays."),
    ],
)
def test_known_labels_in_prose_get_their_names(text: str, named: str) -> None:
    assert name_labels(text, NAMES) == named


def test_ids_citations_and_quotes_keep_their_labels() -> None:
    output = {
        "summary": "Settled by A1.",
        "citations": [{"block_id": "B12", "quote": "see B12"}],
        "statements": [{"id": "T1", "kind": "decision", "summary": "As B12 says."}],
        "affects": ["S3"],
    }

    assert name_labels_in(output, NAMES) == {
        "summary": "Settled by reviewer answer.",
        "citations": [{"block_id": "B12", "quote": "see B12"}],
        "statements": [{"id": "T1", "kind": "decision", "summary": "As brief paragraph 12 says."}],
        "affects": ["S3"],
    }
