"""Text cleaning: quoted replies, signatures, subject normalisation and PII redaction."""
import re

_QUOTE_START = [
    re.compile(r"^\s*On\s.{5,250}\swrote:\s*$", re.I),
    re.compile(r"^\s*-{2,}\s*Original Message\s*-{2,}\s*$", re.I),
    re.compile(r"^\s*-{3,}\s*Forwarded message\s*-{3,}\s*$", re.I),
    re.compile(r"^\s*_{10,}\s*$"),
    re.compile(r"^\s*Begin forwarded message:\s*$", re.I),
]
_SIG_BREAK = [re.compile(r"^--\s*$"), re.compile(r"^(CONFIDENTIALITY NOTICE|DISCLAIMER|This (e-?mail|message) (and any attachments )?(is|are) (confidential|intended))", re.I)]
_SIG_SKIP = [re.compile(r"^Sent from my .{2,40}$", re.I), re.compile(r"^Get Outlook for .{2,20}$", re.I)]


def strip_quoted(body: str) -> str:
    lines = (body or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    for i, line in enumerate(lines):
        if any(p.match(line) for p in _QUOTE_START):
            break
        if re.match(r"^\s*On\s.{3,120}$", line) and i + 1 < len(lines) and re.search(r"wrote:\s*$", lines[i + 1], re.I):
            break  # "On ... " wrapped over two lines
        if re.match(r"^\s*From:\s.+", line) and i + 1 < len(lines) and re.match(r"^\s*(Sent|Date):", lines[i + 1], re.I) and out:
            break  # Outlook-style header block
        if line.lstrip().startswith(">"):
            continue
        out.append(line)
    return "\n".join(out).strip()


def strip_signature(body: str) -> str:
    out = []
    for line in (body or "").split("\n"):
        t = line.strip()
        if any(p.match(t) for p in _SIG_BREAK):
            break
        if any(p.match(t) for p in _SIG_SKIP):
            continue
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def clean_body(body: str) -> str:
    return strip_signature(strip_quoted(body))


def normalize_subject(subject: str) -> str:
    s = (subject or "").strip()
    while True:
        n = re.sub(r"^\s*(re|fwd?|aw|sv)\s*(\[\d+\])?\s*:\s*", "", s, flags=re.I)
        if n == s:
            break
        s = n
    return re.sub(r"\s+", " ", s).strip().lower()


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?<![\w])\+?\d[\d\s().-]{7,}\d(?![\w])")
NUMBER_RE = re.compile(r"(?<![\w.])\d{9,}(?![\w])")


def redact(text: str) -> str:
    """Replace emails, phone numbers and long digit strings (account numbers) with placeholders."""
    text = EMAIL_RE.sub("[EMAIL]", text or "")
    def _phone(m):
        g = m.group()
        if sum(c.isdigit() for c in g) < 9:
            return g  # e.g. a date like 2026-11-04
        return "[NUMBER]" if g.isdigit() else "[PHONE]"  # plain digit strings are account/ID numbers

    text = PHONE_RE.sub(_phone, text)
    return NUMBER_RE.sub("[NUMBER]", text)
