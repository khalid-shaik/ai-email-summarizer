from datetime import date
from urllib.parse import quote

import pandas as pd
import streamlit as st

from core import analyze, clean, digest, llm, parse, reply, sample, threads

st.set_page_config(page_title="AI Email Summarizer", page_icon="📧", layout="wide")
TODAY = date.today()
ss = st.session_state
MAX_EMAILS = 300
for k, v in {"emails": [], "ai": {}, "thread_ai": {}, "seen_files": [], "flash": "", "my_addrs": "", "my_name": "", "paste": "",
             "draft_subject": "", "draft_body": "", "points": ""}.items():
    ss.setdefault(k, v)


# ---------- helpers ----------
def my_addrs() -> list[str]:
    return [a.strip().lower() for a in ss.my_addrs.replace(";", ",").split(",") if a.strip()]


def add_emails(new: list[dict]):
    known = {e["id"] for e in ss.emails}
    fresh = [e for e in new if e["id"] not in known]
    ss.emails = (ss.emails + fresh)[:MAX_EMAILS]
    ss.flash = f"Added {len(fresh)} email(s)." + (f" Only the first {MAX_EMAILS} are kept." if len(ss.emails) >= MAX_EMAILS else "")


def ai_text(e: dict) -> str:
    return clean.redact(e["body"]) if ss.get("redact") else e["body"]


def ai_cfg():
    return ss.get("model", "llama3.2"), ss.get("host")


def load_sample_cb():
    ss.emails, ss.ai, ss.thread_ai = [], {}, {}
    ss.my_addrs = sample.SAMPLE_USER
    add_emails([parse.parse_eml(b) for b in sample.sample_raw(TODAY)])


def clear_cb():
    ss.emails, ss.ai, ss.thread_ai, ss.seen_files = [], {}, {}, []
    ss.flash = "Cleared."


def add_pasted_cb():
    found = parse.parse_pasted(ss.paste)
    add_emails(found)
    ss.paste = ""


def ai_summarize_cb(e: dict):
    ss.flash = ""
    try:
        model, host = ai_cfg()
        sender = clean.redact(f"{e['from_name']} <{e['from_addr']}>") if ss.get("redact") else f"{e['from_name']} <{e['from_addr']}>"
        ss.ai[e["id"]] = llm.summarize_email(e["subject"], sender, e["date"], ai_text(e), model, host)
    except Exception as ex:
        ss.flash = f"AI unavailable ({ex}). Showing the offline analysis."


def ai_thread_cb(key: str, subject: str, text: str):
    ss.flash = ""
    try:
        model, host = ai_cfg()
        ss.thread_ai[key] = llm.summarize_thread(subject, clean.redact(text) if ss.get("redact") else text, model, host)
    except Exception as ex:
        ss.flash = f"AI unavailable ({ex}). Showing the offline analysis."


def make_draft_cb(e: dict):
    ss.flash = ""
    points = [p for p in ss.points.splitlines() if p.strip()]
    fb = reply.draft(e, ss.intent, ss.tone, points, ss.my_name)
    out = fb
    if ss.get("use_ai"):
        try:
            model, host = ai_cfg()
            out = llm.draft_reply(e["subject"], e["from_name"], ai_text(e), ss.intent, ss.tone, points, ss.my_name, fb, model, host)
        except Exception as ex:
            ss.flash = f"AI unavailable ({ex}). Used the template."
    ss.draft_subject, ss.draft_body = out["subject"], out["body"]


# ---------- sidebar ----------
with st.sidebar:
    st.header("⚙️ Settings")
    st.text_input("Your email address(es)", key="my_addrs", placeholder="you@example.com, alt@example.com",
                  help="Used to tell which emails are addressed to you and which you sent.")
    st.text_input("Your name (for replies)", key="my_name")
    host = st.text_input("Ollama host", value="http://localhost:11434", key="host")
    installed = llm.list_models(host)
    if installed:
        st.selectbox("Model", installed, key="model")
        st.checkbox("Use AI features", value=True, key="use_ai")
        st.checkbox("Redact emails, phones and account numbers before AI", value=True, key="redact")
        if not host.startswith(("http://localhost", "http://127.0.0.1")):
            st.warning("Your Ollama host is not local. Keep redaction on.")
    else:
        ss["use_ai"] = False
        st.caption("Ollama not detected. Everything works offline; AI adds richer summaries and replies.")
    st.divider()
    st.button("Load sample inbox", on_click=load_sample_cb, use_container_width=True)
    st.button("Clear all emails", on_click=clear_cb, use_container_width=True)
    st.caption("Emails are processed in memory only and never saved to disk.")

st.title("📧 AI Email Summarizer")
if ss.flash:
    st.toast(ss.flash)
    ss.flash = ""

# ---------- input ----------
with st.expander("➕ Add emails", expanded=not ss.emails):
    up = st.file_uploader("Upload .eml, .mbox or .txt files", type=["eml", "mbox", "txt"], accept_multiple_files=True)
    sig = sorted((f.name, f.size) for f in up or [])
    if up and sig != ss.seen_files:
        errors = []
        for f in up:
            try:
                add_emails(parse.parse_file(f.name, f.getvalue()))
            except Exception as ex:
                errors.append(f"{f.name}: {ex}")
        ss.seen_files = sig
        for er in errors:
            st.error(er)
        st.rerun()
    st.text_area("...or paste an email (with or without From/Subject/Date lines). Separate several with a line of -----", key="paste", height=150)
    st.button("Add pasted email(s)", on_click=add_pasted_cb, disabled=not ss.paste.strip())
    st.caption("Tip: in Gmail open an email → ⋮ → Download message to get an .eml file. Google Takeout gives .mbox.")

emails = ss.emails
if not emails:
    st.info("Add some emails above, or click **Load sample inbox** in the sidebar.")
    st.stop()

# ---------- analysis ----------
mine = my_addrs()
cache_key = (tuple(mine), TODAY)
if ss.get("_ck") != cache_key:
    ss._ck, ss._an = cache_key, {}
for e in emails:
    if e["id"] not in ss._an:
        ss._an[e["id"]] = analyze.analyze_email(e, TODAY, mine)
A = ss._an
items = [{"email": e, "a": A[e["id"]], "ai": ss.ai.get(e["id"])} for e in emails]
by_id = {e["id"]: e for e in emails}

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📥 Inbox triage", "🔍 Read & summarize", "🧵 Threads", "✍️ Reply", "📤 Export"])

# ---------- triage ----------
with tab1:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Emails", len(items))
    m2.metric("High priority", sum(1 for x in items if x["a"]["urgency"]["level"] == "High"))
    m3.metric("Need a reply", sum(1 for x in items if x["a"]["needs_reply"]))
    m4.metric("Action items", sum(len([a for a in x["a"]["actions"] if a["kind"] == "request"]) for x in items))
    f1, f2, f3 = st.columns(3)
    pri_f = f1.multiselect("Priority", ["High", "Medium", "Low"], default=["High", "Medium", "Low"])
    cats = sorted({x["a"]["category"] for x in items})
    cat_f = f2.multiselect("Category", cats, default=cats)
    reply_only = f3.checkbox("Only emails that need a reply")
    rows = [{"Priority": x["a"]["urgency"]["level"], "Score": x["a"]["urgency"]["score"], "Category": x["a"]["category"], "From": x["email"]["from_name"],
             "Subject": x["email"]["subject"], "Date": x["email"]["date"][:10], "Reply?": "✉️" if x["a"]["needs_reply"] else "",
             "Actions": len([a for a in x["a"]["actions"] if a["kind"] == "request"]), "Why": "; ".join(x["a"]["urgency"]["reasons"][:2])}
            for x in items if x["a"]["urgency"]["level"] in pri_f and x["a"]["category"] in cat_f and (x["a"]["needs_reply"] or not reply_only)]
    if rows:
        df = pd.DataFrame(rows).sort_values("Score", ascending=False)
        st.dataframe(df.drop(columns="Score"), use_container_width=True, hide_index=True)
    else:
        st.info("No emails match these filters.")
    st.bar_chart(pd.Series([x["a"]["category"] for x in items]).value_counts().rename("emails"))

# ---------- read ----------
with tab2:
    order = sorted(emails, key=lambda e: -A[e["id"]]["urgency"]["score"])
    pick = st.selectbox("Email", [e["id"] for e in order], format_func=lambda i: f"[{A[i]['urgency']['level']}] {by_id[i]['subject']}  ·  {by_id[i]['from_name']}")
    e, a = by_id[pick], A[pick]
    st.markdown(f"**{e['subject']}**  \nFrom **{e['from_name']}** <{e['from_addr']}> · {e['date'].replace('T', ' ') or 'no date'} · {a['category']}")
    if e["attachments"]:
        st.caption("📎 " + ", ".join(e["attachments"]))
    c1, c2, c3 = st.columns(3)
    c1.metric("Priority", f"{a['urgency']['level']} ({a['urgency']['score']})")
    c2.metric("Needs reply", "Yes" if a["needs_reply"] else "No")
    c3.metric("Action items", len([x for x in a["actions"] if x["kind"] == "request"]))
    if a["urgency"]["reasons"]:
        st.caption("Why: " + " · ".join(a["urgency"]["reasons"]))

    n_sent = st.slider("Offline summary length (sentences)", 1, 6, 3, key="n_sent")
    st.markdown("**Summary**")
    st.write(analyze.extractive_summary(e["body"], n_sent) or "(empty email)")
    ai = ss.ai.get(pick)
    if ss.get("use_ai"):
        st.button("✨ Summarize with AI", on_click=ai_summarize_cb, args=(e,), key=f"ai_{pick}")
    if ai and ai["summary"]:
        st.success(ai["summary"])
        l, r = st.columns(2)
        l.markdown("**Key points**")
        for x in ai["key_points"]:
            l.write(f"- {x}")
        r.markdown("**Decisions**")
        for x in ai["decisions"] or ["None noted"]:
            r.write(f"- {x}")
        st.caption(f"Tone: {ai['tone'] or 'n/a'} · AI priority: {ai['priority'] or 'n/a'} · Reply needed: {'yes' if ai['reply_needed'] else 'no'}")
    st.markdown("**Action items**")
    acts = [x for x in a["actions"]]
    if acts:
        st.dataframe(pd.DataFrame([{"Type": "To do (you)" if x["kind"] == "request" else "Waiting on sender", "Item": x["text"], "Due": x["due"] or ""} for x in acts]),
                     use_container_width=True, hide_index=True)
    else:
        st.write("None detected.")
    if ai and ai["action_items"]:
        st.markdown("AI-detected:")
        for x in ai["action_items"]:
            st.write(f"- {x['task']} ({x['owner']}{', due ' + x['due'] if x['due'] else ''})")
    if a["questions"]:
        st.markdown("**Questions asked**")
        for q in a["questions"]:
            st.write(f"- {q}")
    if a["deadlines"]:
        st.markdown("**Dates mentioned**")
        for d in a["deadlines"]:
            st.write(f"- {d['date']:%a %d %b}: {d['text']}")
    with st.expander("Cleaned email text"):
        st.text(e["body"])
    with st.expander("Original text"):
        st.text(e["raw_body"])

# ---------- threads ----------
with tab3:
    ths = threads.group_threads(emails)
    multi = [t for t in ths if len(t["emails"]) > 1]
    st.caption(f"{len(ths)} conversations, {len(multi)} with more than one message.")
    if not ths:
        st.info("No conversations yet.")
    else:
        labels = {i: f"{t['subject']} ({len(t['emails'])} msg)" for i, t in enumerate(ths)}
        i = st.selectbox("Conversation", list(labels), format_func=labels.get, index=ths.index(multi[0]) if multi else 0)
        t = ths[i]
        st.write("Participants: " + ", ".join(t["participants"]))
        text = ""
        for m in t["emails"]:
            st.markdown(f"**{m['date'][:16].replace('T', ' ')} · {m['from_name']}**")
            st.write(analyze.extractive_summary(m["body"], 2) or "(empty)")
            text += f"From {m['from_name']} ({m['date']}):\n{m['body']}\n\n"
        pending = [(x, m["from_name"]) for m in t["emails"] for x in A[m["id"]]["actions"] if x["kind"] == "request"]
        if pending:
            st.markdown("**Open action items in this conversation**")
            for x, who in pending:
                st.write(f"- {x['text']} ({who}{', due ' + str(x['due']) if x['due'] else ''})")
        key = t["emails"][0]["id"]
        if ss.get("use_ai") and len(t["emails"]) > 1:
            st.button("✨ Summarize conversation with AI", on_click=ai_thread_cb, args=(key, t["subject"], text), key=f"tai_{key}")
        tai = ss.thread_ai.get(key)
        if tai and tai["summary"]:
            st.success(tai["summary"])
            for label, vals in (("Timeline", tai["timeline"]), ("Decisions", tai["decisions"]), ("Open questions", tai["open_questions"])):
                if vals:
                    st.markdown(f"**{label}**")
                    for v in vals:
                        st.write(f"- {v}")

# ---------- reply ----------
with tab4:
    pick_r = st.selectbox("Reply to", [e["id"] for e in order], format_func=lambda i: by_id[i]["subject"], key="reply_pick")
    er = by_id[pick_r]
    a1, b1 = st.columns(2)
    a1.selectbox("What do you want to say?", reply.INTENTS, key="intent")
    b1.selectbox("Tone", list(reply.TONES), key="tone")
    st.text_area("Points to include (one per line, optional)", key="points", height=90)
    st.button("✍️ Draft reply" + (" (AI)" if ss.get("use_ai") else ""), on_click=make_draft_cb, args=(er,), type="primary")
    if ss.draft_body:
        st.text_input("Subject", key="draft_subject")
        st.text_area("Draft (edit freely)", key="draft_body", height=260)
        d1, d2 = st.columns(2)
        d1.download_button("⬇️ Download (.txt)", f"Subject: {ss.draft_subject}\n\n{ss.draft_body}", "reply.txt", use_container_width=True)
        if er["from_addr"]:
            d2.link_button("📨 Open in mail app", f"mailto:{er['from_addr']}?subject={quote(ss.draft_subject)}&body={quote(ss.draft_body[:1500])}", use_container_width=True)
        st.caption("Always review the draft before sending. It never sends anything by itself.")

# ---------- export ----------
with tab5:
    st.write("Export what the app found.")
    e1, e2 = st.columns(2)
    e1.download_button("📝 Daily digest (.md)", digest.build_digest(items, TODAY), f"email_digest_{TODAY}.md", "text/markdown", use_container_width=True)
    e2.download_button("📊 Action items (.csv)", digest.actions_csv(items), "email_actions.csv", "text/csv", use_container_width=True)
    lines = digest.quickadd_lines(items)
    st.markdown("**Send action items to your task manager**")
    st.caption("Paste these into the quick-add box of the AI Productivity Manager (Project 5), one per line.")
    st.code("\n".join(lines) or "No action items found.", language=None)
