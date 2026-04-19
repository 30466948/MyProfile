# MES Qatar Admission Monitor

Cloud-scheduled check of [MES Qatar admission portal](https://portal.mesqatar.org/user/admission/home).
Runs daily at **09:00 Qatar time (06:00 UTC)** on GitHub Actions, logs into
the portal with Playwright, and emails as soon as **KG-2** or **Grade 5
Morning Shift** at **MES Main Branch** moves off `On Hold`.

## How it works

1. GitHub Actions (`.github/workflows/check-admission.yml`) fires on cron
   `0 6 * * *` and on manual `workflow_dispatch`.
2. `check_admission.py` logs into the portal with headless Chromium,
   navigates to the admission page, and parses each card.
3. If the status badge for a target card is anything other than `On Hold`
   (e.g. `Apply Now`, `Open`, `Accepting Applications`), it emails you via
   Gmail SMTP.
4. On failure the job uploads `debug_screenshot.png` and `debug_page.html`
   as a workflow artifact for 7 days.

## GitHub Secrets to add

Go to **Settings → Secrets and variables → Actions → New repository secret**
and add all five:

| Secret | Value |
| --- | --- |
| `PORTAL_USERNAME` | Your MES portal login (email or username) |
| `PORTAL_PASSWORD` | Your MES portal password |
| `GMAIL_USER` | Gmail address that will send the alert |
| `GMAIL_APP_PASSWORD` | 16-char Gmail [App Password](https://myaccount.google.com/apppasswords) (not your real password; 2FA required) |
| `NOTIFY_EMAIL` | Where you want to receive the alert |

> **Gmail App Password**: enable 2-Step Verification on the Gmail account,
> then create an App Password at <https://myaccount.google.com/apppasswords>.
> Paste the 16-character password (spaces optional) into
> `GMAIL_APP_PASSWORD`.

## Testing

1. Add all five secrets above.
2. Open the **Actions** tab → **MES Admission Check** workflow.
3. Click **Run workflow** → branch `claude/mesqatar-admission-access-PIB3H`
   → **Run workflow**.
4. Watch the job logs. If it fails, download the
   `admission-debug-<run-id>` artifact to inspect the screenshot/HTML.

Manual trigger URL:
<https://github.com/30466948/myprofile/actions/workflows/check-admission.yml>

## Assumptions (adjust if wrong)

- The portal's login page exposes a username/email input, a password input,
  and a submit button. The script probes a handful of common selectors
  (`input[type=email]`, `input[type=password]`, `button[type=submit]`,
  and text-based matches like *Login* / *Sign in*). If those all fail it
  falls back to the first two visible `input` elements and dumps the page
  HTML.
- Admission cards on `/user/admission/home` contain the labels *Grade*,
  *Branch*, and a status badge. Grade detection is regex-based and
  tolerates `KG-2`, `KG 2`, `K.G.2`, `Grade 5`, `Grade-5`, etc. Morning
  shift is matched by the word *morning* appearing in the card.
- Status text is read from small elements that contain one of `on hold`,
  `apply now`, `open`, `accepting`, `closed`, `coming soon`, `register`.
- "On Hold" (case-insensitive) is treated as closed; **anything else** is
  treated as open and triggers an email.
- Academic year / start date / close date are best-effort — the email
  still goes out even if those fields are blank.
- If a target card is missing entirely (e.g. the portal hasn't published
  that grade yet), the script logs it and moves on — it does **not**
  send an email.

## Files

- [`check_admission.py`](check_admission.py) — the scraper + mailer
- [`requirements.txt`](requirements.txt) — Playwright + BeautifulSoup
- [`.github/workflows/check-admission.yml`](.github/workflows/check-admission.yml) — daily cron + manual trigger

## Running locally (optional)

```bash
pip install -r requirements.txt
python -m playwright install chromium
export PORTAL_USERNAME=...
export PORTAL_PASSWORD=...
export GMAIL_USER=...
export GMAIL_APP_PASSWORD=...
export NOTIFY_EMAIL=...
python check_admission.py
```
