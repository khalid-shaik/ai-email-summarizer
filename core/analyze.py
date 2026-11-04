"""Offline email analysis: summary, action items, questions, urgency, category. No LLM needed."""
import re
from collections import Counter
from datetime import date, timedelta

from .dates import find_date
from .parse import email_date

STOP = set("""a an the and or but if then so to of in on at for with from by as is are was were be been it its this that these those
i you he she we they me my your our their him her them us not no yes do does did have has had will would can could should may might
just also very more most some any all about into over under again there here what which who whom when where why how than too out up
down off only own same can't won't don't i'm i'll we'll you'll thanks thank please hi hello dear regards best""".split())
GREETING = re.compile(r"^(hi|hello|hey|dear|good (morning|afternoon|evening))\b[^.?!]{0,40}[,!:]?$", re.I)
CLOSING = re.compile(r"^(thanks|thank you|many thanks|regards|best|cheers|sincerely|warm regards|kind regards|best regards|yours)\b[^.?!]{0,30}[,.!]?$", re.I)

REQUEST_PATTERNS = [
    r"\b(please|kindly|pls)\b.{0,80}\b(send|share|review|confirm|submit|update|provide|complete|fill|sign|reply|respond|check|prepare|schedule|book|attend|join|approve|forward|arrange|let me know|revert)\b",
    r"\b(can|could|would|will) you\b", r"\b(need|needs|required|requires|must) (you )?to\b", r"\bplease\b.{0,20}\b(find|see|note)\b",
    r"\baction (required|needed|item)\b", r"\bdon'?t forget\b", r"\bmake sure\b", r"\blet me know\b", r"\b(rsvp|confirm your)\b",
    r"\byou (should|need|have to)\b", r"\b(deadline|due (on|by|date))\b",
]
COMMIT_PATTERNS = [r"\b(i|we)\s*(will|'ll|am going to|shall)\s+(send|share|get|follow|update|provide|prepare|check|review|schedule|book|arrange|reach|revert|work)\b"]
URGENT_WORDS = [r"\burgent(ly)?\b", r"\basap\b", r"\bimmediately\b", r"\bcritical\b", r"\btime[- ]sensitive\b", r"\baction required\b",
                r"\bfinal (notice|reminder)\b", r"\boverdue\b", r"\bby (eod|end of day|today|tomorrow)\b", r"\bdeadline\b", r"\bexpires? (today|tomorrow|soon)\b"]

CATEGORIES = {
    "Job / Recruiting": ["interview", "recruiter", "hiring", "application", "candidate", "job", "position", "offer letter", "resume", "shortlisted", "hr round"],
    "Meetings": ["meeting", "invite", "invitation", "calendar", "zoom", "teams", "google meet", "reschedule", "agenda", "sync", "call at", "webinar"],
    "Finance": ["invoice", "payment", "receipt", "statement", "bill", "amount due", "transaction", "refund", "subscription", "emi", "tax"],
    "Newsletter / Promo": ["unsubscribe", "newsletter", "view in browser", "% off", "sale", "limited time", "deal", "discount", "coupon", "weekly digest", "promo"],
    "Notification": ["security alert", "verify your", "password", "sign-in", "login", "otp", "your account", "notification", "do not reply", "automated message"],
    "Work": ["project", "report", "deadline", "review", "sprint", "client", "deliverable", "dashboard", "task", "ticket", "release"],
    "Personal": ["dinner", "weekend", "birthday", "party", "lunch", "family", "trip", "see you", "catch up"],
}
NOREPLY = re.compile(r"(no-?reply|do-?not-?reply|notifications?@|alerts?@|mailer-daemon|newsletter@|updates?@)", re.I)


def split_sentences(text: str) -> list[str]:
    out, after_closing = [], False
    for line in (text or "").split("\n"):
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", line.strip())
        if not line:
            continue
        if CLOSING.match(line) and (line.endswith(",") or len(line.split()) <= 3):
            after_closing = True  # sign-off: the short lines that follow are the signature block
            continue
        if after_closing and len(line.split()) <= 4:
            continue
        after_closing = False
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])", line):
            s = s.strip()
            if s and not GREETING.match(s) and not CLOSING.match(s):
                out.append(s)
    return out


def _words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z][a-z'-]+", s.lower()) if w not in STOP and len(w) > 2]


def extractive_summary(text: str, n: int = 3) -> str:
    sents = split_sentences(text)
    if len(sents) <= n:
        return " ".join(sents)
    freq = Counter(w for s in sents for w in _words(s))
    top = max(freq.values()) if freq else 1
    scored = []
    for i, s in enumerate(sents):
        ws = _words(s)
        if len(s.split()) < 4:
            continue
        score = sum(freq[w] / top for w in ws) / (len(ws) ** 0.6 or 1)
        score += 0.4 if i == 0 else 0.15 if i == 1 else 0
        if any(re.search(p, s, re.I) for p in REQUEST_PATTERNS[:3] + [r"\bdeadline\b", r"\bby \w+day\b"]):
            score += 0.25
        scored.append((score, i, s))
    chosen = sorted(sorted(scored, reverse=True)[:n], key=lambda x: x[1])
    return " ".join((s if len(s.split()) <= 45 else " ".join(s.split()[:45]) + "…") for _, _, s in chosen)


def find_actions(text: str, base: date) -> list[dict]:
    out, seen = [], set()
    for s in split_sentences(text):
        kind = "request" if any(re.search(p, s, re.I) for p in REQUEST_PATTERNS) else "commitment" if any(re.search(p, s, re.I) for p in COMMIT_PATTERNS) else None
        if not kind or s.endswith("?") and kind == "request" and not re.search(r"\b(can|could|would|will) you\b|\bplease\b", s, re.I):
            continue
        key = s.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        due, due_text = find_date(s, base)
        out.append({"text": s if len(s) <= 220 else s[:217] + "…", "kind": kind, "due": due, "due_text": due_text})
    return out


def find_questions(text: str) -> list[str]:
    return [s for s in split_sentences(text) if s.endswith("?")][:6]


def find_deadlines(text: str, base: date) -> list[dict]:
    out = []
    for s in split_sentences(text):
        if re.search(r"\b(by|before|due|deadline|until|on|expires?|ends?|last date)\b", s, re.I):
            d, t = find_date(s, base)
            if d:
                out.append({"date": d, "text": s if len(s) <= 160 else s[:157] + "…"})
    return out


def categorize(e: dict, text: str) -> str:
    subj, body, sender = e["subject"].lower(), text.lower(), e["from_addr"]
    scores = {}
    for cat, kws in CATEGORIES.items():
        scores[cat] = sum(3 * (k in subj) + min(2, body.count(k)) for k in kws)
    if NOREPLY.search(sender):
        scores["Notification"] += 4
        scores["Newsletter / Promo"] += 1
    best, val = max(scores.items(), key=lambda x: x[1])
    return best if val >= 2 else "Other"


def urgency(e: dict, text: str, category: str, deadlines: list[dict], today: date, direct: bool) -> dict:
    score, reasons = 0, []
    if re.search(r"high|^1\b|urgent", e.get("importance", "")):
        score += 35
        reasons.append("Marked high importance")
    hits = sum(1 for p in URGENT_WORDS if re.search(p, f"{e['subject']} {text}", re.I))
    if hits:
        score += min(40, 20 * hits)
        reasons.append("Urgent wording")
    soonest = min((d["date"] for d in deadlines), default=None)
    if soonest is not None:
        days = (soonest - today).days
        if days < 0:
            score += 30
            reasons.append(f"Deadline passed ({soonest:%d %b})")
        elif days <= 2:
            score += 25
            reasons.append(f"Deadline {soonest:%d %b}")
        elif days <= 7:
            score += 10
            reasons.append(f"Deadline {soonest:%d %b}")
    if "?" in text:
        score += 8
        reasons.append("Asks a question")
    if category in ("Job / Recruiting",):
        score += 12
        reasons.append("Career related")
    if category == "Finance" and re.search(r"due|overdue|pending|failed", text, re.I):
        score += 12
        reasons.append("Payment related")
    if category == "Newsletter / Promo":
        score -= 35
    elif category == "Notification":
        score -= 15
    if direct:
        score += 6
    elif e.get("cc"):
        score -= 6
        reasons.append("You are on CC")
    score = max(0, score)
    return {"score": score, "level": "High" if score >= 55 else "Medium" if score >= 25 else "Low", "reasons": reasons}


def analyze_email(e: dict, today: date, my_addrs=(), summary_sentences: int = 3) -> dict:
    my = {a.strip().lower() for a in my_addrs if a.strip()}
    sent = email_date(e)
    base = sent.date() if sent else today
    text = e["body"]
    category = categorize(e, text)
    actions = find_actions(text, base)
    questions = find_questions(text)
    deadlines = find_deadlines(text, base)
    direct = (not my) or bool(my & set(e["to"]))
    from_me = e["from_addr"] in my
    urg = urgency(e, text, category, deadlines, today, direct)
    needs_reply = (not from_me and category not in ("Newsletter / Promo", "Notification") and not NOREPLY.search(e["from_addr"])
                   and direct and (bool(questions) or any(a["kind"] == "request" for a in actions)))
    return {"id": e["id"], "summary": extractive_summary(text, summary_sentences), "actions": actions, "questions": questions,
            "deadlines": deadlines, "category": category, "urgency": urg, "needs_reply": needs_reply, "from_me": from_me}
