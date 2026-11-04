"""Sample inbox (raw RFC822) so the app can be explored immediately. Dates are relative to 'today'."""
from datetime import date, datetime, timedelta
from email.utils import format_datetime

SAMPLE_USER = "alex@example.com"


def _msg(sender, subject, body, when, to=SAMPLE_USER, mid="", reply_to="", refs="", extra=""):
    hdr = [f"From: {sender}", f"To: {to}", f"Subject: {subject}", f"Date: {format_datetime(when)}"]
    if mid:
        hdr.append(f"Message-ID: <{mid}>")
    if reply_to:
        hdr.append(f"In-Reply-To: <{reply_to}>")
    if refs:
        hdr.append(f"References: {refs}")
    if extra:
        hdr.append(extra)
    return "\r\n".join(hdr) + "\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n" + body.strip().replace("\n", "\r\n") + "\r\n"


def sample_emails(today: date) -> list[tuple[str, str]]:
    at = lambda days, h=9, m=30: datetime(today.year, today.month, today.day, h, m) - timedelta(days=days)
    return [
        ("recruiter.eml", _msg("Priya Nair <priya@talentbridge.example>", "Interview invitation: Data Analyst at Northwind",
         "Hi Alex,\n\nThank you for applying. We would like to invite you for a 45 minute interview for the Data Analyst position.\n"
         "Please confirm your availability by Friday. Can you also send an updated resume before the call?\nThe interview will be on Zoom.\n\nBest regards,\nPriya Nair\nTalent Partner", at(0, 8, 15))),
        ("manager.eml", _msg("Rahul Mehta <rahul@example.com>", "Weekly report and dashboard review",
         "Hi Alex,\n\nCan you send the weekly sales report by EOD tomorrow? Also please review the new Power BI dashboard and share feedback.\n"
         "The numbers look off for the south region, so this is urgent. I will share the raw data file shortly.\n\nThanks,\nRahul", at(0, 9, 5), extra="Importance: High")),
        ("invoice.eml", _msg("Billing <billing@cloudhost.example>", "Invoice INV-2041 payment due",
         "Hello,\n\nYour invoice INV-2041 for hosting is pending. The amount due is 4500 INR and payment is due by 12 November.\n"
         "Please pay using the link in your account. Account reference 123456789012.\n\nRegards,\nCloudHost Billing", at(1))),
        ("newsletter.eml", _msg("Data Weekly <newsletter@dataweekly.example>", "This week in data: 10 SQL tricks + 40% off courses",
         "Welcome to this week's newsletter! This week we cover 10 SQL tricks, a new dashboard gallery and a limited time sale: 40% off all courses.\n"
         "View in browser. Unsubscribe at any time.", at(1, 7, 0))),
        ("security.eml", _msg("Accounts <no-reply@accounts.example>", "Security alert: new sign-in to your account",
         "We noticed a new sign-in to your account from a new device. If this was you, no action is needed. If not, please secure your account.\nThis is an automated message, do not reply.", at(2, 22, 10))),
        ("thread1.eml", _msg("Meera Iyer <meera@example.com>", "Project Alpha sync",
         "Hi team,\n\nLet's sync on Project Alpha this week. Which day works for everyone? I'm free Tuesday or Thursday afternoon.\n\nMeera", at(3), to=f"{SAMPLE_USER}, rahul@example.com", mid="alpha-1@example.com")),
        ("thread2.eml", _msg("Rahul Mehta <rahul@example.com>", "Re: Project Alpha sync",
         "Thursday works for me. Let's also decide on the data source, I suggest we use the warehouse export.\n\nOn Sun, Meera Iyer wrote:\n> Let's sync on Project Alpha this week. Which day works?\n> Meera", at(2), to=f"meera@example.com, {SAMPLE_USER}", mid="alpha-2@example.com", reply_to="alpha-1@example.com", refs="<alpha-1@example.com>")),
        ("thread3.eml", _msg("Meera Iyer <meera@example.com>", "Re: Project Alpha sync",
         "Great, Thursday 3 PM it is. We will go with the warehouse export. Alex, could you prepare a short data quality summary before the meeting? I'll send the invite today.\n\n"
         "On Mon, Rahul Mehta wrote:\n> Thursday works for me.\n", at(1, 16, 0), to=f"{SAMPLE_USER}, rahul@example.com", mid="alpha-3@example.com", reply_to="alpha-2@example.com", refs="<alpha-1@example.com> <alpha-2@example.com>")),
        ("friend.eml", _msg("Sam <sam@example.com>", "Dinner on Saturday?",
         "Hey Alex! Are you free for dinner this Saturday? Thinking of that new place near the lake. Let me know!\n\nSam\n\nSent from my iPhone", at(0, 7, 40))),
    ]


def sample_raw(today: date) -> list[bytes]:
    return [m.encode("utf-8") for _, m in sample_emails(today)]
