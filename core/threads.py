"""Group emails into conversations (Message-ID links plus normalised subject)."""
from .clean import normalize_subject
from .parse import email_date


def group_threads(emails: list[dict]) -> list[dict]:
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    for e in emails:
        node = f"e:{e['id']}"
        find(node)
        for ref in [e.get("message_id"), e.get("in_reply_to"), *e.get("references", [])]:
            if ref:
                union(node, f"m:{ref}")
        subj = normalize_subject(e["subject"])
        if subj and subj != "(no subject)":
            union(node, f"s:{subj}")
    groups: dict[str, list[dict]] = {}
    for e in emails:
        groups.setdefault(find(f"e:{e['id']}"), []).append(e)
    threads = []
    for members in groups.values():
        members.sort(key=lambda m: (email_date(m) or __import__("datetime").datetime.min, m["id"]))
        threads.append({"subject": members[0]["subject"], "emails": members,
                        "participants": sorted({m["from_name"] or m["from_addr"] for m in members}),
                        "last": members[-1].get("date", "")})
    return sorted(threads, key=lambda t: t["last"], reverse=True)
