"""Parse emails from .eml, .mbox and pasted text into plain dicts."""
import hashlib
import mailbox
import re
import tempfile
from datetime import datetime
from email import message_from_bytes, policy
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

from .clean import clean_body

MAX_BODY = 20000


class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "table"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    p.feed(html or "")
    text = re.sub(r"[ \t\xa0]+", " ", "".join(p.parts))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _addr_list(value) -> list[str]:
    return [a.lower() for _, a in getaddresses([str(value or "")]) if a]


def _iso(value) -> str:
    try:
        return parsedate_to_datetime(str(value)).replace(tzinfo=None).isoformat(timespec="minutes")
    except (TypeError, ValueError, IndexError):
        return ""


def make_id(subject, sender, date, body) -> str:
    return hashlib.sha1(f"{subject}|{sender}|{date}|{body[:200]}".encode("utf-8", "ignore")).hexdigest()[:10]


def build_email(subject="", from_name="", from_addr="", to=(), cc=(), date="", raw_body="", attachments=(),
                message_id="", in_reply_to="", references=(), importance="") -> dict:
    raw_body = (raw_body or "")[:MAX_BODY]
    subject = re.sub(r"\s+", " ", subject or "").strip() or "(no subject)"
    return {"id": make_id(subject, from_addr, date, raw_body), "subject": subject, "from_name": from_name or from_addr.split("@")[0],
            "from_addr": from_addr.lower(), "to": list(to), "cc": list(cc), "date": date, "raw_body": raw_body,
            "body": clean_body(raw_body) or raw_body.strip(), "attachments": list(attachments), "message_id": message_id,
            "in_reply_to": in_reply_to, "references": list(references), "importance": importance.lower()}


def from_message(msg) -> dict:
    part = msg.get_body(preferencelist=("plain", "html"))
    body = ""
    if part is not None:
        try:
            content = part.get_content()
        except (LookupError, UnicodeDecodeError):
            content = part.get_payload(decode=True).decode("utf-8", "ignore") if part.get_payload(decode=True) else ""
        body = html_to_text(content) if part.get_content_type() == "text/html" else content
    name, addr = ("", "")
    senders = getaddresses([str(msg.get("From", ""))])
    if senders:
        name, addr = senders[0]
    atts = [a.get_filename() or "attachment" for a in msg.iter_attachments()]
    imp = f"{msg.get('Importance', '')} {msg.get('X-Priority', '')} {msg.get('Priority', '')}".strip()
    return build_email(str(msg.get("Subject", "")), name, addr, _addr_list(msg.get("To")), _addr_list(msg.get("Cc")), _iso(msg.get("Date")),
                       body, atts, str(msg.get("Message-ID", "")).strip(), str(msg.get("In-Reply-To", "")).strip(),
                       re.findall(r"<[^>]+>", str(msg.get("References", ""))), imp)


def parse_eml(data: bytes) -> dict:
    return from_message(message_from_bytes(data, policy=policy.default))


def parse_mbox(data: bytes, limit: int = 300) -> list[dict]:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "in.mbox"
        path.write_bytes(data)
        box = mailbox.mbox(str(path))
        out = []
        for i, m in enumerate(box):
            if i >= limit:
                break
            out.append(from_message(message_from_bytes(m.as_bytes(), policy=policy.default)))
        box.close()
    return out


_HDR = re.compile(r"^(from|to|cc|subject|date|sent)\s*:\s*(.*)$", re.I)


def parse_pasted(text: str) -> list[dict]:
    """Paste one email or several separated by a line of 5+ dashes or equals signs. Optional header lines are understood."""
    chunks = [c.strip() for c in re.split(r"\n\s*(?:-{5,}|={5,})\s*\n", (text or "").replace("\r\n", "\n")) if c.strip()]
    emails = []
    for chunk in chunks:
        headers, lines, i = {}, chunk.split("\n"), 0
        while i < len(lines):
            m = _HDR.match(lines[i].strip())
            if not m:
                break
            headers[m[1].lower()] = m[2].strip()
            i += 1
        body = "\n".join(lines[i:]).strip() if headers else chunk
        senders = getaddresses([headers.get("from", "")])
        name, addr = senders[0] if senders else ("", "")
        date = _iso(headers.get("date") or headers.get("sent"))
        emails.append(build_email(headers.get("subject", "") or "(pasted email)", name, addr, _addr_list(headers.get("to")),
                                  _addr_list(headers.get("cc")), date, body or chunk))
    return emails


def parse_file(name: str, data: bytes) -> list[dict]:
    n = name.lower()
    if n.endswith(".eml"):
        return [parse_eml(data)]
    if n.endswith(".mbox"):
        return parse_mbox(data)
    if n.endswith((".txt", ".md")):
        return parse_pasted(data.decode("utf-8", "ignore"))
    raise ValueError(f"Unsupported file type: {name}. Use .eml, .mbox or .txt")


def email_date(e: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(e["date"]) if e.get("date") else None
    except ValueError:
        return None
