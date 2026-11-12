"""The alert rules' metadata: what promtool cannot check (ADR 0023). Whether each rule fires is
tested by ops/monitoring/alerts.test.yaml (`just alerts-check`)."""

import re
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from scopesteps.agent.client import FINISH_REASON_LABEL

ROOT = Path(__file__).resolve().parents[2]
MONITORING = ROOT / "ops" / "monitoring"
RUNBOOK = ROOT / "docs" / "runbooks" / "agent-alerts.md"
RUNBOOK_URL = "https://github.com/ScopeSteps/scopesteps/blob/main/docs/runbooks/agent-alerts.md#"
STAMP = re.compile(r"\b\d{8}T\d{6}Z\b")


def _rules(group_name: str) -> list[dict[str, Any]]:
    document = cast(dict[str, Any], yaml.safe_load((MONITORING / "alerts.yaml").read_text()))
    return [
        rule
        for group in document["groups"]
        if group["name"] == group_name
        for rule in group["rules"]
    ]


# The agent's rules come from evaluations; Jira publishing's (ADR 0029) from the sender's limits.
RULES = _rules("scopesteps-agent")
JIRA_RULES = _rules("scopesteps-jira")
JIRA_RUNBOOK = ROOT / "docs" / "runbooks" / "jira-alerts.md"
JIRA_RUNBOOK_URL = (
    "https://github.com/ScopeSteps/scopesteps/blob/main/docs/runbooks/jira-alerts.md#"
)


def test_jira_publishing_has_its_stuck_rule_with_a_runbook_section() -> None:
    headings = {
        line.removeprefix("## ").strip().lower()
        for line in JIRA_RUNBOOK.read_text().splitlines()
        if line.startswith("## ")
    }

    assert [rule["alert"] for rule in JIRA_RULES] == ["JiraPublishStuck"]
    for rule in JIRA_RULES:
        annotations = rule["annotations"]
        assert rule["labels"]["severity"] in {"critical", "warning"}
        for key in ("summary", "threshold", "window", "min_runs", "source", "runbook_url"):
            assert annotations.get(key), f"{rule['alert']} has no {key}"
        assert annotations["runbook_url"].startswith(JIRA_RUNBOOK_URL)
        assert annotations["runbook_url"].removeprefix(JIRA_RUNBOOK_URL) in headings


def _id(rule: dict[str, Any]) -> str:
    kind = rule["labels"].get("scopesteps_run_kind")
    return rule["alert"] if kind is None else f"{rule['alert']}-{kind}"


def _thresholds_section() -> str:
    text = (ROOT / "evals" / "README.md").read_text()
    start = text.index("## Alert thresholds")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else None]


def test_every_signal_the_ticket_names_has_a_rule() -> None:
    assert {rule["alert"] for rule in RULES} == {
        "AgentRunFailureRateHigh",
        "ModelCallLatencyHigh",
        "ModelCallsCutOff",
        "AgentRunCostHigh",
        "AgentRunProblemsHigh",
        "BackupCircuitOpened",
    }


@pytest.mark.parametrize("rule", RULES, ids=_id)
def test_each_rule_states_its_threshold_window_minimum_severity_and_runbook(
    rule: dict[str, Any],
) -> None:
    annotations = rule["annotations"]

    assert rule["labels"]["severity"] in {"critical", "warning"}
    for key in ("summary", "threshold", "window", "min_runs", "source", "runbook_url"):
        assert annotations.get(key), f"{_id(rule)} has no {key}"
    assert annotations["runbook_url"].startswith(RUNBOOK_URL)


@pytest.mark.parametrize("rule", RULES, ids=_id)
def test_each_rule_evaluates_the_window_it_states(rule: dict[str, Any]) -> None:
    assert f"[{rule['annotations']['window']}]" in rule["expr"]


@pytest.mark.parametrize("rule", RULES, ids=_id)
def test_each_rule_needs_its_minimum_number_of_runs(rule: dict[str, Any]) -> None:
    minimum = re.match(r"(\d+) finished", rule["annotations"]["min_runs"])
    if rule["alert"] == "BackupCircuitOpened":
        # The breaker has its own minimum (3 failures in 2 minutes) before it can open at all.
        assert minimum is None
        return

    assert minimum is not None
    assert f">= {minimum.group(1)}" in rule["expr"]


@pytest.mark.parametrize(
    "rule", [rule for rule in RULES if rule["alert"] != "BackupCircuitOpened"], ids=_id
)
def test_each_threshold_cites_a_report_recorded_in_the_evals_readme(rule: dict[str, Any]) -> None:
    source = rule["annotations"]["source"]
    stamps = STAMP.findall(source)

    assert source.startswith('evals/README.md, "Alert thresholds"')
    assert stamps, f"{_id(rule)} cites no report stamp"
    section = _thresholds_section()
    for stamp in stamps:
        assert stamp in section, f"{stamp} is not in the Alert thresholds section"


@pytest.mark.parametrize("rule", RULES, ids=_id)
def test_each_rule_leaves_replays_out(rule: dict[str, Any]) -> None:
    if rule["alert"] == "BackupCircuitOpened":
        return  # a replay never calls a provider, so it cannot open the circuit
    for selector in re.findall(r"\{[^}]*\}", rule["expr"]):
        assert (
            'scopesteps_replay="false"' in selector or 'gen_ai_provider_name!="replay"' in selector
        )


def test_every_alert_has_a_runbook_section() -> None:
    headings = {
        line.removeprefix("## ").strip().lower()
        for line in RUNBOOK.read_text().splitlines()
        if line.startswith("## ")
    }

    for rule in RULES:
        assert rule["annotations"]["runbook_url"].removeprefix(RUNBOOK_URL) in headings


def test_every_alert_is_shown_firing_in_the_promtool_tests() -> None:
    tests = cast(dict[str, Any], yaml.safe_load((MONITORING / "alerts.test.yaml").read_text()))
    checks = [check for test in tests["tests"] for check in test["alert_rule_test"]]
    fired = {
        (
            str(check["alertname"]),
            cast(dict[str, str], alert["exp_labels"]).get("scopesteps_run_kind"),
        )
        for check in cast(list[dict[str, Any]], checks)
        for alert in cast(list[dict[str, Any]], check.get("exp_alerts") or [])
    }

    assert fired == {
        (rule["alert"], rule["labels"].get("scopesteps_run_kind")) for rule in RULES + JIRA_RULES
    }


def test_the_cut_off_rule_uses_the_label_the_api_exports() -> None:
    (rule,) = [rule for rule in RULES if rule["alert"] == "ModelCallsCutOff"]

    assert f'{FINISH_REASON_LABEL.replace(".", "_")}="max_tokens"' in rule["expr"]
