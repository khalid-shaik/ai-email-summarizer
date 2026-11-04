"""Optional local AI (Ollama): structured email summaries, thread summaries and reply drafts."""
import json
import re

import ollama

MAX_CHARS = 6000
SYSTEM = ("You are a precise executive assistant. Use ONLY information in the email text; never invent names, dates, amounts or commitments. "
          "Reply with a single valid JSON object only.")


def parse_json(raw: str) -> dict:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            raise ValueError("Model did not return JSON.")
        return json.loads(m.group(0))


def list_models(host: str | None = None) -> list[str]:
    try:
        client = ollama.Client(host=host) if host else ollama.Client()
        resp = client.list()
        models = resp["models"] if isinstance(resp, dict) else resp.models
        return sorted((m["model"] if isinstance(m, dict) else m.model) for m in models)
    except Exception:
        return []


def _chat(prompt, model, host, temperature) -> dict:
    client = ollama.Client(host=host) if host else ollama.Client()
    resp = client.chat(model=model, messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                       format="json", options={"temperature": temperature})
    content = resp["message"]["content"] if isinstance(resp, dict) else resp.message.content
    return parse_json(content)


def _list(v):
    return [str(x).strip() for x in v if str(x).strip()] if isinstance(v, list) else []


def _actions(v):
    out = []
    for a in v if isinstance(v, list) else []:
        if isinstance(a, dict) and str(a.get("task", "")).strip():
            due = str(a.get("due", "")).strip()
            out.append({"task": str(a["task"]).strip(), "owner": str(a.get("owner", "")).strip() or "me",
                        "due": due if re.match(r"^\d{4}-\d{2}-\d{2}$", due) else ""})
        elif isinstance(a, str) and a.strip():
            out.append({"task": a.strip(), "owner": "me", "due": ""})
    return out


def normalize_summary(d: dict) -> dict:
    pr = str(d.get("priority", "")).strip().capitalize()
    return {"summary": str(d.get("summary", "")).strip(), "key_points": _list(d.get("key_points")), "action_items": _actions(d.get("action_items")),
            "questions": _list(d.get("questions")), "decisions": _list(d.get("decisions")), "tone": str(d.get("tone", "")).strip().lower(),
            "reply_needed": bool(d.get("reply_needed")), "priority": pr if pr in ("High", "Medium", "Low") else ""}


def normalize_thread(d: dict) -> dict:
    return {"summary": str(d.get("summary", "")).strip(), "timeline": _list(d.get("timeline")), "decisions": _list(d.get("decisions")),
            "open_questions": _list(d.get("open_questions")), "action_items": _actions(d.get("action_items"))}


def normalize_draft(d: dict, fallback: dict) -> dict:
    body = str(d.get("body", "")).strip()
    return {"subject": str(d.get("subject", "")).strip() or fallback["subject"], "body": body or fallback["body"]}


def summarize_email(subject, sender, sent, body, model="llama3.2", host=None, temperature=0.2) -> dict:
    prompt = (f"EMAIL\nFrom: {sender}\nDate: {sent}\nSubject: {subject}\n\n{body[:MAX_CHARS]}\n\n"
              'Return JSON: {"summary": "2-3 sentences", "key_points": ["..."], "action_items": [{"task": "...", "owner": "me|sender|other", "due": "YYYY-MM-DD or empty"}], '
              '"questions": ["questions asked"], "decisions": ["decisions made"], "tone": "neutral|friendly|urgent|formal|negative", '
              '"reply_needed": true, "priority": "High|Medium|Low"}')
    return normalize_summary(_chat(prompt, model, host, temperature))


def summarize_thread(subject, messages_text, model="llama3.2", host=None, temperature=0.2) -> dict:
    prompt = (f"EMAIL THREAD about: {subject}\n\n{messages_text[:MAX_CHARS * 2]}\n\n"
              'Return JSON: {"summary": "3 sentences on where things stand", "timeline": ["who said/did what, in order"], "decisions": ["..."], '
              '"open_questions": ["..."], "action_items": [{"task": "...", "owner": "...", "due": "YYYY-MM-DD or empty"}]}')
    return normalize_thread(_chat(prompt, model, host, temperature))


def draft_reply(subject, sender, body, intent, tone, points, my_name, fallback, model="llama3.2", host=None, temperature=0.5) -> dict:
    prompt = (f"Write a reply to this email.\nFrom: {sender}\nSubject: {subject}\n\n{body[:MAX_CHARS]}\n\n"
              f"Intent: {intent}. Tone: {tone}. Points to include: {'; '.join(points) or 'none'}. Sign off as: {my_name or '[Your name]'}. "
              "Keep it under 150 words. Do not invent facts or commitments beyond the points given.\n"
              'Return JSON: {"subject": "...", "body": "..."}')
    return normalize_draft(_chat(prompt, model, host, temperature), fallback)
