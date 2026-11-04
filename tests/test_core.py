from datetime import date, datetime
from email.message import EmailMessage

import pytest

from core import analyze, clean, dates, digest, llm, parse, reply, sample, threads

TODAY = date(2026, 11, 4)  # Wednesday


# ---------- clean ----------
def test_strip_quoted_variants():
    assert clean.strip_quoted("Thanks!\n\nOn Mon, 3 Nov 2026 at 10:00, Bob <b@x.com> wrote:\n> old text\n> more") == "Thanks!"
    assert clean.strip_quoted("Yes\n> quoted line\nNo") == "Yes\nNo"
    assert clean.strip_quoted("OK\n-----Original Message-----\nFrom: a\nold") == "OK"
    assert clean.strip_quoted("Sure\n\nFrom: Bob\nSent: Monday\nTo: me\nold") == "Sure"
    assert clean.strip_quoted("Hi\nOn Mon, 3 Nov 2026 at 10:00, Bob\n<b@x.com> wrote:\n> old") == "Hi"
    assert clean.strip_quoted("") == ""


def test_strip_signature_and_disclaimer():
    assert clean.strip_signature("See you\n-- \nAlex\nCEO") == "See you"
    assert clean.strip_signature("Hi\nSent from my iPhone") == "Hi"
    assert clean.strip_signature("Hello\nCONFIDENTIALITY NOTICE: this is private") == "Hello"


@pytest.mark.parametrize("raw,expected", [("Re: Re: FWD: Plan  A", "plan a"), ("RE[2]: Hello", "hello"), ("Fw: x", "x"), ("Regarding: x", "regarding: x"), ("", "")])
def test_normalize_subject(raw, expected):
    assert clean.normalize_subject(raw) == expected


def test_redact():
    out = clean.redact("Mail me at a.b@x.co.in or call +91 98765 43210. Account 123456789012. Order 12345 on 2026-11-04.")
    assert "[EMAIL]" in out and "[PHONE]" in out and "[NUMBER]" in out
    assert "12345" in out and "2026-11-04" in out and "a.b@x.co.in" not in out


# ---------- dates ----------
@pytest.mark.parametrize("text,expected", [
    ("by Friday", date(2026, 11, 6)), ("by EOD tomorrow", date(2026, 11, 5)), ("tomorrow", date(2026, 11, 5)), ("due 12 November", date(2026, 11, 12)),
    ("Nov 20, 2026", date(2026, 11, 20)), ("on 2026-12-01", date(2026, 12, 1)), ("end of week", date(2026, 11, 6)), ("by end of month", date(2026, 11, 30)),
    ("next week", date(2026, 11, 9)), ("in 2 weeks", date(2026, 11, 18)), ("15/11/2026", date(2026, 11, 15)), ("today", TODAY),
    ("next Wednesday", date(2026, 11, 11)), ("Wednesday", TODAY), ("5 jan", date(2027, 1, 5)),
])
def test_find_date(text, expected):
    assert dates.find_date(text, TODAY)[0] == expected


def test_find_date_none_and_invalid():
    assert dates.find_date("no dates here", TODAY)[0] is None
    assert dates.find_date("31 feb", TODAY)[0] is None


# ---------- parse ----------
def _eml(**kw) -> bytes:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"], m["Date"] = kw.get("from_", "Ann Lee <ann@x.com>"), "me@x.com", kw.get("subject", "Hello"), kw.get("date", "Tue, 03 Nov 2026 10:00:00 +0530")
    if "cc" in kw:
        m["Cc"] = kw["cc"]
    m.set_content(kw.get("text", "Hi,\n\nPlease send the file by Friday.\n\nAnn"))
    if kw.get("html"):
        m.add_alternative(kw["html"], subtype="html")
    for name in kw.get("attach", []):
        m.add_attachment(b"data", maintype="application", subtype="pdf", filename=name)
    return m.as_bytes()


def test_parse_eml_basic_and_attachments():
    e = parse.parse_eml(_eml(attach=["a.pdf", "b.pdf"], cc="c@x.com"))
    assert e["from_name"] == "Ann Lee" and e["from_addr"] == "ann@x.com" and e["to"] == ["me@x.com"] and e["cc"] == ["c@x.com"]
    assert e["date"] == "2026-11-03T10:00" and e["attachments"] == ["a.pdf", "b.pdf"] and "Please send" in e["body"]


def test_parse_html_only_and_encoded_subject_and_bad_date():
    m = EmailMessage()
    m["From"], m["To"], m["Date"] = "x@y.com", "me@x.com", "not a date"
    m["Subject"] = "Café meeting ☕"
    m.set_content("<html><head><style>p{}</style></head><body><p>Hello <b>there</b></p><ul><li>one</li><li>two</li></ul><script>bad()</script></body></html>", subtype="html")
    e = parse.parse_eml(m.as_bytes())
    assert e["subject"] == "Café meeting ☕" and e["date"] == ""
    assert "Hello there" in e["body"] and "one" in e["body"] and "bad()" not in e["body"] and "p{}" not in e["body"]
    assert parse.parse_eml(b"garbage with no headers")["subject"] == "(no subject)"


def test_parse_mbox_roundtrip_and_limit():
    box = b"".join(b"From a@x.com Tue Nov  3 10:00:00 2026\n" + _eml(subject=f"S{i}").replace(b"\r\n", b"\n") + b"\n" for i in range(3))
    got = parse.parse_mbox(box)
    assert [e["subject"] for e in got] == ["S0", "S1", "S2"]
    assert len(parse.parse_mbox(box, limit=2)) == 2


def test_parse_pasted():
    one = parse.parse_pasted("From: Bob <bob@x.com>\nSubject: Lunch?\nDate: Tue, 03 Nov 2026 10:00:00 +0530\n\nAre you free today?")[0]
    assert one["subject"] == "Lunch?" and one["from_addr"] == "bob@x.com" and one["body"] == "Are you free today?"
    plain = parse.parse_pasted("Just some text\nwith lines")[0]
    assert plain["subject"] == "(pasted email)" and "some text" in plain["body"]
    assert len(parse.parse_pasted("A body\n-----\nSecond body\n=====\nThird")) == 3
    assert parse.parse_pasted("   \n ") == []


def test_parse_file_dispatch():
    assert parse.parse_file("x.EML", _eml())[0]["subject"] == "Hello"
    assert len(parse.parse_file("x.txt", b"hello")) == 1
    with pytest.raises(ValueError):
        parse.parse_file("x.pdf", b"")


# ---------- analyze ----------
def _e(subject="Hi", body="", sender="bob@x.com", to=("me@x.com",), date_="2026-11-04T09:00", **kw):
    return parse.build_email(subject, "Bob", sender, to, kw.get("cc", ()), date_, body, importance=kw.get("importance", ""))


def test_summary_keeps_order_and_length():
    text = "We are launching the new dashboard on Monday. The team worked hard on it. Lots of chart types were added. Please review the dashboard before Monday. Coffee is in the kitchen."
    s = analyze.extractive_summary(text, 2)
    assert 0 < len(s.split(". ")) <= 3 and "dashboard" in s
    assert analyze.extractive_summary("Short one.", 3) == "Short one." and analyze.extractive_summary("", 3) == ""
    assert analyze.extractive_summary("Hi Bob,\nThanks,\nAlex", 2) == ""
    assert analyze.extractive_summary("Hi Bob,\nThe build is ready.\nBest regards,\nPriya Nair\nTalent Partner", 3) == "The build is ready."
    assert "Confirmed." in analyze.split_sentences("Thanks for the update. Confirmed.")


def test_actions_requests_commitments_and_dates():
    acts = analyze.find_actions("Please send the report by Friday. I will share the data tomorrow. The sky is blue. Can you review this?", TODAY)
    assert [a["kind"] for a in acts] == ["request", "commitment", "request"]
    assert acts[0]["due"] == date(2026, 11, 6) and acts[1]["due"] == date(2026, 11, 5) and acts[2]["due"] is None
    assert analyze.find_actions("Nothing to do here.", TODAY) == []
    assert len(analyze.find_actions("Please send it. Please send it.", TODAY)) == 1


def test_relative_dates_use_email_sent_date():
    e = _e(body="Please send it by tomorrow.", date_="2026-10-20T09:00")
    a = analyze.analyze_email(e, TODAY)
    assert a["actions"][0]["due"] == date(2026, 10, 21)
    assert any(r.startswith("Deadline passed") for r in a["urgency"]["reasons"])


def test_urgency_levels():
    hi = analyze.analyze_email(_e("URGENT: report", "Please send the report by EOD today. This is urgent!", importance="high"), TODAY, ["me@x.com"])
    lo = analyze.analyze_email(_e("Weekly newsletter", "Our newsletter: 40% off sale! Unsubscribe anytime. View in browser.", sender="newsletter@shop.com"), TODAY)
    mid = analyze.analyze_email(_e("Question", "Could you tell me what time the meeting starts?"), TODAY, ["me@x.com"])
    assert hi["urgency"]["level"] == "High" and lo["urgency"]["level"] == "Low" and lo["category"] == "Newsletter / Promo"
    assert hi["urgency"]["score"] > mid["urgency"]["score"] > lo["urgency"]["score"]


def test_needs_reply_rules():
    q = _e("Lunch", "Are you free for lunch?")
    assert analyze.analyze_email(q, TODAY, ["me@x.com"])["needs_reply"]
    assert not analyze.analyze_email(_e("FYI", "Report attached. Nothing needed."), TODAY, ["me@x.com"])["needs_reply"]
    assert not analyze.analyze_email(_e("Alert", "Are you sure? Please verify your account.", sender="no-reply@bank.com"), TODAY)["needs_reply"]
    assert not analyze.analyze_email(_e("Lunch", "Are you free?", sender="me@x.com"), TODAY, ["me@x.com"])["needs_reply"]
    cc_only = _e("Lunch", "Are you free?", to=("other@x.com",), cc=("me@x.com",))
    assert not analyze.analyze_email(cc_only, TODAY, ["me@x.com"])["needs_reply"]


def test_categories():
    cat = lambda s, b, f="a@x.com": analyze.analyze_email(_e(s, b, sender=f), TODAY)["category"]
    assert cat("Interview invitation", "We would like to schedule your interview for the position.") == "Job / Recruiting"
    assert cat("Invoice 12", "Your invoice payment of 500 is due.") == "Finance"
    assert cat("Meeting tomorrow", "Zoom invite and agenda attached.") == "Meetings"
    assert cat("Security alert", "New sign-in to your account", "no-reply@x.com") == "Notification"
    assert cat("zzz", "nothing special at all") == "Other"


# ---------- sample pipeline & threads ----------
def test_sample_inbox_end_to_end():
    emails = [parse.parse_eml(b) for b in sample.sample_raw(TODAY)]
    assert len(emails) == 9 and len({e["id"] for e in emails}) == 9
    an = {e["subject"]: analyze.analyze_email(e, TODAY, [sample.SAMPLE_USER]) for e in emails}
    assert an["Weekly report and dashboard review"]["urgency"]["level"] == "High"
    assert an["Interview invitation: Data Analyst at Northwind"]["category"] == "Job / Recruiting"
    assert an["Interview invitation: Data Analyst at Northwind"]["actions"][0]["due"] == date(2026, 11, 6)
    assert an["This week in data: 10 SQL tricks + 40% off courses"]["urgency"]["level"] == "Low"
    assert not an["Security alert: new sign-in to your account"]["needs_reply"]
    assert "Re: Project Alpha sync" in an
    ths = threads.group_threads(emails)
    big = max(ths, key=lambda t: len(t["emails"]))
    assert len(big["emails"]) == 3 and big["emails"][0]["subject"] == "Project Alpha sync" and len(ths) == 7
    assert "On Sun" not in big["emails"][1]["body"] and ">" not in big["emails"][1]["body"]


def test_threads_group_by_subject_when_no_ids():
    a, b, c = _e("Plan", "x", date_="2026-11-01T10:00"), _e("RE: Plan", "y", date_="2026-11-02T10:00"), _e("Other", "z")
    t = threads.group_threads([b, c, a])
    assert [len(x["emails"]) for x in t] == [1, 2] or [len(x["emails"]) for x in t] == [2, 1]
    assert [m["body"] for m in max(t, key=lambda x: len(x["emails"]))["emails"]] == ["x", "y"]


# ---------- reply & digest ----------
def test_reply_templates():
    e = _e("Project Alpha sync", "x")
    for intent in reply.INTENTS:
        for tone in reply.TONES:
            d = reply.draft(e, intent, tone, ["Thursday works"], "Alex")
            assert d["subject"] == "Re: Project Alpha sync" and "Bob" in d["body"] and "Alex" in d["body"] and "{" not in d["body"]
    assert reply.draft({"subject": "Re: X", "from_name": ""}, reply.INTENTS[0])["subject"] == "Re: X"
    assert "[Your name]" in reply.draft(e, reply.INTENTS[0])["body"]


def test_digest_csv_and_quickadd():
    emails = [parse.parse_eml(b) for b in sample.sample_raw(TODAY)]
    items = [{"email": e, "a": analyze.analyze_email(e, TODAY, [sample.SAMPLE_USER])} for e in emails]
    md = digest.build_digest(items, TODAY)
    assert md.startswith("# Email digest") and "[High] Weekly report" in md and md.index("[High]") < md.index("[Low]")
    csv_text = digest.actions_csv(items)
    assert csv_text.splitlines()[0].startswith("email_subject,from,task") and "2026-11-06" in csv_text
    lines = digest.quickadd_lines(items)
    assert lines and all(l.endswith(("p1", "p2", "p3")) and "#email" in l for l in lines)
    assert any("by 2026-11-05" in l for l in lines) and not any("I will share" in l for l in lines)


# ---------- llm ----------
def test_llm_normalizers():
    assert llm.parse_json('x {"a": 1} y') == {"a": 1}
    with pytest.raises(ValueError):
        llm.parse_json("none")
    s = llm.normalize_summary({"summary": " hi ", "action_items": [{"task": "A", "due": "2026-11-05"}, {"task": "B", "due": "soon"}, "C", {"task": ""}], "priority": "high", "reply_needed": 1, "key_points": "x"})
    assert s["summary"] == "hi" and s["priority"] == "High" and s["reply_needed"] is True and s["key_points"] == []
    assert [a["due"] for a in s["action_items"]] == ["2026-11-05", "", ""]
    assert llm.normalize_summary({"priority": "urgent"})["priority"] == ""
    fb = {"subject": "S", "body": "B"}
    assert llm.normalize_draft({}, fb) == fb and llm.normalize_draft({"body": " x "}, fb)["body"] == "x"
    assert llm.normalize_thread({"timeline": ["a"], "summary": "s"})["timeline"] == ["a"]
