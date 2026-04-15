# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Yasashii Nihongo News (やさしい日本語ニュース) is a Streamlit web app that simplifies Japanese news articles for JLPT learners (N1–N5). It uses the Claude API to rewrite text at the appropriate level, optionally adding furigana and vocabulary lists. The app is deployed on Streamlit Cloud.

## Development Commands

```bash
# Setup
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run locally
streamlit run app.py
# App served at http://localhost:8501

# Utility: generate bcrypt-hashed credentials for settings.yaml
python create-credentials.py
```

There are no automated tests or linting configurations.

## Architecture

The entire application is in `app.py` (single file, ~430 lines). The flow:

1. **Auth** — `streamlit-authenticator` gates access using bcrypt-hashed credentials from `.streamlit/secrets.toml`
2. **Settings** — loaded from GitHub via the GitHub Contents API (PUT/GET on `settings.yaml`), cached 60s with `@st.cache_data`. Settings include a custom system prompt and per-level furigana instructions.
3. **UI** — user inputs article title, Japanese text, JLPT level (N1–N5), and furigana style
4. **Claude API call** — `claude-sonnet-4-6`, max 4096 tokens; the system prompt uses `{level}` and `{furigana_instruction}` placeholders
5. **Output** — Markdown → HTML conversion, rendered via `st.components.v1.html()` (not `st.markdown`) to avoid scroll traps; a download button provides the HTML file

## Configuration & Secrets

Secrets live in `.streamlit/secrets.toml` (gitignored). Required keys:

- `[cookie]` — `name`, `key`, `expiry_days` for session cookies
- `[credentials.usernames.<user>]` — `name`, `password` (bcrypt hash)
- `[github]` — `token` (PAT with `repo` scope), `repo` (`owner/repo`), `settings_path`

`settings.yaml` is the persisted config file stored in GitHub. It is also gitignored locally.

## Key Design Decisions

- **GitHub as backend**: No database — settings persist via GitHub API. The PUT request requires the file's current SHA for updates (fetched on each load).
- **components.html for output**: Output HTML is rendered with `st.components.v1.html()` instead of `st.markdown` to prevent Streamlit's scroll-trap behavior.
- **Print-ready HTML**: Output includes `@media print` CSS for paper output.
