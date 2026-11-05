# 📧 AI Email SummarizeR
AI agents, Drop in emails and get a prioritised inbox, plain-English summaries, action items with deadlines, conversation summaries and reply drafts. It runs locally: **all analysis works offline**, and Ollama only adds richer summaries and replies. Emails are processed in memory and never saved to disk.

## Features
- **Inputs:** upload `.eml`, `.mbox` (Gmail Takeout) or `.txt`, or paste emails (with or without From/Subject/Date lines)
- **Cleaning:** strips quoted replies, signatures, disclaimers and HTML so only the new message is analysed
- **Triage:** priority (High / Medium / Low with reasons), category (Job, Meetings, Finance, Work, Personal, Newsletter, Notification), "needs a reply" detection, filters and a category chart
- **Read & summarize:** offline extractive summary, action items split into *to do (you)* and *waiting on sender*, questions asked, and deadlines. Relative dates like "by Friday" are resolved against **the date the email was sent**
- **Threads:** conversations grouped by Message-ID/References and subject, with a per-message timeline and open action items
- **Reply:** six intents × three tones as offline templates, or AI drafts. Edit, download or open in your mail app. It never sends anything
- **Export:** Markdown digest, action-item CSV, and quick-add lines for the AI Productivity Manager (Project 5)
- **Privacy:** optional redaction of emails, phone numbers and account numbers before anything reaches the model

## Tech stack
Python · Streamlit · stdlib `email` / `mailbox` · pandas · Ollama (optional) · pytest · GitHub Actions

## Quick start
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```
Click **Load sample inbox** in the sidebar, or upload the files in `samples/`. For AI features install Ollama and run `ollama pull llama3.2`.

## Getting your emails in
- **Gmail:** open an email → ⋮ → *Download message* (.eml). For many emails use Google Takeout (.mbox).
- **Outlook:** drag a message to the desktop to save it as .msg, then open it and *Save as* text, or copy and paste the text.
- **Anywhere:** copy the text and paste it into the box.

## Project structure
```
app.py            Streamlit UI (5 tabs)
core/parse.py     .eml / .mbox / pasted text -> dicts
core/clean.py     quoted-reply and signature stripping, subject normalisation, redaction
core/dates.py     deadline detection relative to the sent date
core/analyze.py   summary, actions, questions, urgency, category, reply-needed
core/threads.py   conversation grouping
core/reply.py     offline reply templates
core/digest.py    Markdown / CSV / quick-add exports
core/llm.py       optional Ollama helpers (validated JSON)
core/sample.py    sample inbox
tests/            pytest unit and UI tests (46)
samples/          .eml files and a .mbox to try uploads
```

## Limits
- Offline summaries are extractive (they pick the most important sentences), so they are less fluent than AI summaries.
- Action-item and urgency detection is rule-based and tuned for English emails. Treat it as a first pass.
- The sample files in `samples/` are dated 4 Nov 2026, so "overdue" flags will appear as time passes.

## Tests
```bash
pytest -q
```

## Roadmap
- [ ] Live inbox via IMAP (app password)
- [ ] Attachment text extraction (PDF, DOCX)
- [ ] Follow-up reminders for "waiting on sender" items
