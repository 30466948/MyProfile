"""
MES Qatar admission portal monitor.

Checks https://portal.mesqatar.org/user/admission/home daily to see whether
KG-2 and Grade 5 Morning Shift at MES Main Branch are open. Sends an email
when either moves from "On Hold" to any other status.

Environment variables (GitHub Secrets):
    PORTAL_USERNAME, PORTAL_PASSWORD
    GMAIL_USER, GMAIL_APP_PASSWORD, NOTIFY_EMAIL
"""

from __future__ import annotations

import os
import re
import smtplib
import sys
import time
import traceback
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from bs4 import BeautifulSoup
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright


PORTAL_URL = "https://portal.mesqatar.org"
LOGIN_URL = f"{PORTAL_URL}/user/login"
ADMISSION_URL = f"{PORTAL_URL}/user/admission/home"

TARGET_BRANCH = "MES Main Branch"
TARGETS = [
    {"grade_patterns": [r"\bKG\s*-?\s*2\b", r"\bK\.?G\.?\s*2\b"], "label": "KG-2", "shift": None},
    {"grade_patterns": [r"\bGrade\s*-?\s*5\b"], "label": "Grade 5 Morning Shift", "shift": "morning"},
]

CLOSED_STATUS = "on hold"
DEFAULT_TIMEOUT_MS = 30_000
MAX_ATTEMPTS = 3
SCREENSHOT_PATH = "debug_screenshot.png"
HTML_DUMP_PATH = "debug_page.html"


@dataclass
class CardInfo:
    grade: str
    branch: str
    status: str
    academic_year: str
    start_date: str
    close_date: str
    raw_text: str


def log(msg: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def login(page: Page, username: str, password: str) -> None:
    log(f"Navigating to {LOGIN_URL}")
    page.goto(LOGIN_URL, timeout=DEFAULT_TIMEOUT_MS, wait_until="domcontentloaded")

    user_selectors = [
        "input[type=email]",
        "input[name*=user i]",
        "input[name*=email i]",
        "input[id*=user i]",
        "input[id*=email i]",
        "input[placeholder*=user i]",
        "input[placeholder*=email i]",
    ]
    pass_selectors = [
        "input[type=password]",
        "input[name*=pass i]",
        "input[id*=pass i]",
    ]
    submit_selectors = [
        "button[type=submit]",
        "input[type=submit]",
        "button:has-text('Login')",
        "button:has-text('Sign in')",
        "button:has-text('Log in')",
    ]

    def first_visible(selectors: list[str]):
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=1500):
                    return loc
            except Exception:
                continue
        return None

    user_field = first_visible(user_selectors)
    pass_field = first_visible(pass_selectors)

    if not user_field or not pass_field:
        log("Standard selectors failed; falling back to any visible input.")
        log("Dumping page HTML for debugging.")
        try:
            with open(HTML_DUMP_PATH, "w", encoding="utf-8") as f:
                f.write(page.content())
        except Exception as exc:
            log(f"Could not dump HTML: {exc}")
        inputs = page.locator("input:visible")
        count = inputs.count()
        if count < 2:
            raise RuntimeError(f"Login inputs not found (visible inputs: {count}).")
        user_field = user_field or inputs.nth(0)
        pass_field = pass_field or inputs.nth(1)

    user_field.fill(username)
    pass_field.fill(password)

    submit = first_visible(submit_selectors)
    if submit:
        submit.click()
    else:
        pass_field.press("Enter")

    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT_MS)
    log(f"Post-login URL: {page.url}")
    if "login" in page.url.lower():
        raise RuntimeError("Still on login URL after submit — credentials may be wrong.")


def fetch_admission_html(username: str, password: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT_MS)

        try:
            login(page, username, password)
            log(f"Navigating to {ADMISSION_URL}")
            page.goto(ADMISSION_URL, timeout=DEFAULT_TIMEOUT_MS, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT_MS)
            except PlaywrightTimeout:
                log("networkidle timeout — continuing with current DOM.")
            try:
                page.wait_for_selector("text=/admission|grade|branch/i", timeout=5000)
            except PlaywrightTimeout:
                pass
            html = page.content()
            return html
        except Exception:
            log("Failure during fetch — capturing screenshot and HTML.")
            try:
                page.screenshot(path=SCREENSHOT_PATH, full_page=True)
            except Exception as exc:
                log(f"Screenshot failed: {exc}")
            try:
                with open(HTML_DUMP_PATH, "w", encoding="utf-8") as f:
                    f.write(page.content())
            except Exception as exc:
                log(f"HTML dump failed: {exc}")
            raise
        finally:
            context.close()
            browser.close()


def _text(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)) if node else ""


def _extract_field(text: str, label: str) -> str:
    m = re.search(rf"{re.escape(label)}\s*[:\-]?\s*([^\n|]+?)(?:\s{{2,}}|$|\||  )", text, re.IGNORECASE)
    if m:
        return m.group(1).strip(" .,-")
    m = re.search(rf"{re.escape(label)}\s*[:\-]?\s*(\S[^\n]*)", text, re.IGNORECASE)
    return m.group(1).strip(" .,-") if m else ""


def parse_cards(html: str) -> list[CardInfo]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for sel in ["div.card", ".admission-card", "[class*=card]", "article", "li"]:
        for el in soup.select(sel):
            txt = _text(el)
            if not txt or len(txt) < 20:
                continue
            if "branch" in txt.lower() or "grade" in txt.lower() or "kg" in txt.lower():
                candidates.append(el)

    seen = set()
    cards: list[CardInfo] = []
    for el in candidates:
        key = id(el)
        if key in seen:
            continue
        seen.add(key)
        txt = _text(el)

        status = ""
        for badge in el.select("[class*=badge], [class*=status], span, small, label, button"):
            btxt = _text(badge)
            if btxt and len(btxt) < 40 and re.search(
                r"on hold|apply now|open|accepting|closed|coming soon|register",
                btxt,
                re.IGNORECASE,
            ):
                status = btxt
                break

        grade = _extract_field(txt, "Grade") or _extract_field(txt, "Class")
        branch = _extract_field(txt, "Branch") or _extract_field(txt, "School")
        academic_year = (
            _extract_field(txt, "Academic Year")
            or _extract_field(txt, "Year")
            or (re.search(r"\b20\d{2}\s*[-/]\s*20\d{2}\b", txt).group(0) if re.search(r"\b20\d{2}\s*[-/]\s*20\d{2}\b", txt) else "")
        )
        start_date = _extract_field(txt, "Start Date") or _extract_field(txt, "Opens")
        close_date = _extract_field(txt, "Close Date") or _extract_field(txt, "Closes") or _extract_field(txt, "End Date")

        cards.append(
            CardInfo(
                grade=grade,
                branch=branch,
                status=status,
                academic_year=academic_year,
                start_date=start_date,
                close_date=close_date,
                raw_text=txt[:1000],
            )
        )
    return cards


def match_target(card: CardInfo, target: dict) -> bool:
    hay = f"{card.grade} {card.raw_text}"
    if not any(re.search(pat, hay, re.IGNORECASE) for pat in target["grade_patterns"]):
        return False
    if TARGET_BRANCH.lower() not in (card.branch + " " + card.raw_text).lower():
        return False
    if target["shift"] == "morning":
        if not re.search(r"morning", card.raw_text, re.IGNORECASE):
            return False
    return True


def is_open(status: str) -> bool:
    if not status:
        return False
    return status.strip().lower() != CLOSED_STATUS


def send_email(grade_label: str, card: CardInfo) -> None:
    gmail_user = os.environ["GMAIL_USER"]
    gmail_pass = os.environ["GMAIL_APP_PASSWORD"]
    to_addr = os.environ["NOTIFY_EMAIL"]

    subject = f"MES Admission OPEN - {grade_label}"
    body = f"""Admissions appear to be OPEN.

Grade          : {grade_label}
Branch         : {card.branch or TARGET_BRANCH}
Status         : {card.status or '(unknown, not "On Hold")'}
Academic Year  : {card.academic_year or 'n/a'}
Start Date     : {card.start_date or 'n/a'}
Close Date     : {card.close_date or 'n/a'}

Open the portal to apply:
{ADMISSION_URL}

-- automated check from GitHub Actions
"""
    msg = MIMEMultipart()
    msg["From"] = gmail_user
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    log(f"Sending email to {to_addr} — {subject}")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(gmail_user, gmail_pass)
        s.sendmail(gmail_user, [to_addr], msg.as_string())
    log("Email sent.")


def run_once() -> int:
    username = os.environ["PORTAL_USERNAME"]
    password = os.environ["PORTAL_PASSWORD"]

    html = fetch_admission_html(username, password)
    cards = parse_cards(html)
    log(f"Parsed {len(cards)} candidate cards.")

    notified = 0
    for target in TARGETS:
        matches = [c for c in cards if match_target(c, target)]
        if not matches:
            log(f"No card matched target: {target['label']}")
            continue
        card = matches[0]
        log(f"{target['label']}: status={card.status!r} branch={card.branch!r}")
        if is_open(card.status):
            send_email(target["label"], card)
            notified += 1
        else:
            log(f"{target['label']} is still closed ('On Hold'). No email.")
    log(f"Run complete. Emails sent: {notified}")
    return 0


def main() -> int:
    last_exc: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        log(f"Attempt {attempt}/{MAX_ATTEMPTS}")
        try:
            return run_once()
        except Exception as exc:
            last_exc = exc
            log(f"Attempt {attempt} failed: {exc}")
            traceback.print_exc()
            if attempt < MAX_ATTEMPTS:
                time.sleep(5 * attempt)
    log(f"All {MAX_ATTEMPTS} attempts failed. Last error: {last_exc}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
