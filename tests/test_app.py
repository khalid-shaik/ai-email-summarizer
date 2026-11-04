from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from core import llm, sample

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def at(monkeypatch):
    monkeypatch.setattr(llm, "list_models", lambda host=None: [])
    return AppTest.from_file(APP, default_timeout=60).run()


def _load(app):
    [b for b in app.sidebar.button if b.label == "Load sample inbox"][0].click().run()
    return app


def _click(app, label):
    [b for b in app.button if label in b.label][0].click().run()


def test_empty_state(at):
    assert not at.exception and any("Add some emails" in i.value for i in at.info)


def test_sample_triage_metrics(at):
    _load(at)
    assert not at.exception
    m = {x.label: x.value for x in at.metric if x.label in ("Emails", "High priority", "Need a reply")}
    assert m["Emails"] == "9" and int(m["High priority"]) >= 1 and int(m["Need a reply"]) >= 3
    assert len(at.dataframe) >= 1


def test_paste_adds_email(at):
    at.text_area(key="paste").set_value("From: Bob <bob@x.com>\nSubject: Hello there\n\nCould you send the slides by Friday?").run()
    _click(at, "Add pasted")
    assert not at.exception and len(at.session_state["emails"]) == 1 and at.text_area(key="paste").value == ""
    assert at.session_state["emails"][0]["subject"] == "Hello there"


def test_reply_draft_and_clear(at):
    _load(at)
    at.text_area(key="points").set_value("Thursday works for me").run()
    _click(at, "Draft reply")
    assert not at.exception and "Thursday works for me" in at.session_state["draft_body"] and at.session_state["draft_subject"].startswith("Re:")
    [b for b in at.sidebar.button if b.label == "Clear all emails"][0].click().run()
    assert at.session_state["emails"] == [] and not at.exception


def test_ai_failure_falls_back(monkeypatch):
    monkeypatch.setattr(llm, "list_models", lambda host=None: ["m:latest"])

    def boom(*a, **k):
        raise ConnectionError("down")
    monkeypatch.setattr(llm, "summarize_email", boom)
    monkeypatch.setattr(llm, "draft_reply", boom)
    app = AppTest.from_file(APP, default_timeout=60).run()
    _load(app)
    _click(app, "Summarize with AI")
    assert not app.exception and app.session_state["ai"] == {}  # nothing stored when AI fails
    _click(app, "Draft reply")
    assert not app.exception and app.session_state["draft_body"]


def test_ai_success_and_redaction(monkeypatch):
    monkeypatch.setattr(llm, "list_models", lambda host=None: ["m:latest"])
    seen = {}

    def fake(subject, sender, sent, body, model, host, **k):
        seen["sender"], seen["body"] = sender, body
        return llm.normalize_summary({"summary": "AI says hi", "key_points": ["k1"], "priority": "High", "reply_needed": True})
    monkeypatch.setattr(llm, "summarize_email", fake)
    app = AppTest.from_file(APP, default_timeout=60).run()
    _load(app)
    _click(app, "Summarize with AI")
    assert not app.exception and any("AI says hi" in s.value for s in app.success)
    assert "[EMAIL]" in seen["sender"] and "@" not in seen["sender"]  # address redacted before reaching the model
