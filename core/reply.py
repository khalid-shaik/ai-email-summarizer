"""Offline reply templates."""
INTENTS = ["Acknowledge and say I'll follow up", "Confirm / accept", "Decline politely", "Ask for more time", "Ask a clarifying question", "Say thank you"]
TONES = {
    "Friendly": {"hi": "Hi {n},", "close": "Thanks again!", "sign": "Cheers,"},
    "Professional": {"hi": "Hello {n},", "close": "Thank you for your time.", "sign": "Best regards,"},
    "Formal": {"hi": "Dear {n},", "close": "I appreciate your understanding.", "sign": "Sincerely,"},
}
CORE = {
    INTENTS[0]: "Thank you for your email. I have received it and will get back to you {when}.",
    INTENTS[1]: "Thank you for the message. I'm happy to confirm and will proceed as described.",
    INTENTS[2]: "Thank you for thinking of me. Unfortunately I won't be able to take this on at the moment.",
    INTENTS[3]: "Thank you for reaching out. I need a little more time to give this proper attention. Could I get back to you {when}?",
    INTENTS[4]: "Thank you for the details. Before I proceed, could you clarify a few points?",
    INTENTS[5]: "Thank you very much for your message. I really appreciate it.",
}


def draft(email: dict, intent: str, tone: str = "Professional", points=(), my_name: str = "", when: str = "by the end of the week") -> dict:
    t = TONES.get(tone, TONES["Professional"])
    first = (email.get("from_name") or "there").split()[0] if email.get("from_name") else "there"
    body = [t["hi"].format(n=first), "", CORE.get(intent, CORE[INTENTS[0]]).format(when=when)]
    pts = [p.strip() for p in points if p.strip()]
    if pts:
        label = "A few questions:" if intent == INTENTS[4] else "Specifically:"
        body += ["", label] + [f"- {p}" for p in pts]
    body += ["", t["close"], "", t["sign"], my_name or "[Your name]"]
    subj = email.get("subject", "")
    return {"subject": subj if subj.lower().startswith("re:") else f"Re: {subj}", "body": "\n".join(body)}
