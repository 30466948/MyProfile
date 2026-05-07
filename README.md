# 🏡 Family Chores

A lightweight, mobile-friendly family chore tracker. Single-page web app — no
backend, no signup, just open the link.

## Try it locally

```bash
open index.html      # macOS
xdg-open index.html  # linux
start index.html     # windows
```

That's it. State is saved in your browser's `localStorage`.

## Get it on your phone (deploy with GitHub Pages)

A workflow is included that publishes the site automatically.

1. Push to GitHub (this branch is already pushed).
2. Go to **Settings → Pages** in the repo.
3. Under **Build and deployment → Source**, pick **GitHub Actions**.
4. Open the **Actions** tab and re-run the latest **Deploy to GitHub Pages**
   workflow if it didn't run automatically.
5. The job will print a URL like `https://<user>.github.io/<repo>/` —
   share that with the family.

## Features

- **4 family members** — tap a face to filter
- **Add chores** with assignee, due date, points, and recurrence (one-time / daily / weekly)
- **Recurring chores** roll their due date forward when checked off, and credit points to the weekly leaderboard
- **Inline editing** — click any chore title (or the ✎ icon) to rename
- **Sections** — Overdue / Today / This Week / Completed
- **Weekly leaderboard** with a 👑 for the top scorer

Edit the `FAMILY` array at the top of the `<script>` block in `index.html` to
use your real names, colors, and emojis.

## Roadmap (when you're ready for "real app" mode)

- Real-time sync across devices (Firebase / Supabase)
- Per-member sign-in (so kids can only check off their own chores, parents see all)
- Push notifications when a chore goes overdue
- Photo proof on completion
- Reward catalog ("100 pts → movie night")

## Files

- [`index.html`](index.html) — the whole app
- [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) — auto-deploy to GitHub Pages
