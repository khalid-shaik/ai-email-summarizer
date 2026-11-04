"""Exports: Markdown digest, action-item CSV and quick-add lines."""
import csv
import io
import re
from datetime import date

PRI = {"High": 1, "Medium": 2, "Low": 3}


def build_digest(items: list[dict], today: date) -> str:
    """items: [{'email': e, 'a': analysis, 'ai': optional AI result}]"""
    order = sorted(items, key=lambda x: -x["a"]["urgency"]["score"])
    out = [f"# Email digest, {today:%d %b %Y}", "",
           f"{len(items)} emails · {sum(1 for x in items if x['a']['urgency']['level'] == 'High')} high priority · "
           f"{sum(1 for x in items if x['a']['needs_reply'])} need a reply", ""]
    for x in order:
        e, a = x["email"], x["a"]
        summary = (x.get("ai") or {}).get("summary") or a["summary"] or "(no text)"
        out += [f"## [{a['urgency']['level']}] {e['subject']}", f"*From {e['from_name']} · {a['category']}" + (" · reply needed" if a["needs_reply"] else "") + "*", "", summary, ""]
        for act in a["actions"]:
            out.append(f"- [ ] ({act['kind']}) {act['text']}" + (f" (due {act['due']:%d %b})" if act["due"] else ""))
        out.append("")
    return "\n".join(out)


def actions_csv(items: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email_subject", "from", "task", "kind", "due", "priority", "category"])
    for x in items:
        for act in x["a"]["actions"]:
            w.writerow([x["email"]["subject"], x["email"]["from_name"], act["text"], act["kind"], act["due"] or "", x["a"]["urgency"]["level"], x["a"]["category"]])
    return buf.getvalue()


def quickadd_lines(items: list[dict]) -> list[str]:
    """Lines you can paste into the AI Productivity Manager quick-add box."""
    lines = []
    for x in items:
        for act in x["a"]["actions"]:
            if act["kind"] != "request":
                continue
            task = re.sub(r"\s+", " ", re.sub(r"[^\w\s,.'&/()-]", "", act["text"])).strip(" .,")
            task = task[:90].rsplit(" ", 1)[0] if len(task) > 90 else task
            lines.append(f"{task}" + (f" by {act['due'].isoformat()}" if act["due"] else "") + f" #email p{PRI[x['a']['urgency']['level']]}")
    return lines
