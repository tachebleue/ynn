import base64
import json
import urllib.error
import urllib.request

import anthropic
import markdown
import streamlit as st
import streamlit.components.v1 as components
import streamlit_authenticator as stauth
import yaml
from anthropic.types.text_block import TextBlock

# ── Settings persistence via GitHub API ───────────────────────────────────────
_GH_TOKEN = st.secrets.get("github", {}).get("token", "")
_GH_REPO = st.secrets.get("github", {}).get("repo", "")  # e.g. "tachebleue/ynn"
_GH_PATH = st.secrets.get("github", {}).get("settings_path", "settings.yaml")
_GH_API = f"https://api.github.com/repos/{_GH_REPO}/contents/{_GH_PATH}"


def _gh_request(method: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        _GH_API,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_GH_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def load_settings() -> dict:
    """Fetch settings.yaml from the GitHub repo; return {} if it doesn't exist yet."""
    if not _GH_TOKEN or not _GH_REPO:
        return {}
    try:
        data = _gh_request("GET")
        content = base64.b64decode(data["content"]).decode()
        return yaml.safe_load(content) or {}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        raise


def save_settings(settings: dict) -> None:
    """Write settings.yaml back to the GitHub repo (create or update)."""
    if not _GH_TOKEN or not _GH_REPO:
        st.warning(
            "GitHub settings not configured — changes won't persist across sessions."
        )
        return
    content = base64.b64encode(
        yaml.dump(settings, allow_unicode=True, default_flow_style=False).encode()
    ).decode()
    # Fetch current SHA so GitHub accepts the update (required for existing files)
    sha: str | None = None
    try:
        existing = _gh_request("GET")
        sha = existing.get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    body: dict = {
        "message": "chore: update settings.yaml",
        "content": content,
    }
    if sha:
        body["sha"] = sha
    _gh_request("PUT", body)


@st.cache_data(ttl=60)
def _load_settings_cached() -> dict:
    return load_settings()


_settings = _load_settings_cached()

# ── Auth ──────────────────────────────────────────────────────────────────────
# st.secrets returns immutable AttrDicts; streamlit-authenticator mutates the
# credentials dict (e.g. to record failed login attempts), so we must convert
# everything into plain Python dicts first.
_secrets_dict = st.secrets.to_dict()
_credentials = _secrets_dict["credentials"]

auth = stauth.Authenticate(
    _credentials,
    str(st.secrets["cookie"]["name"]),
    str(st.secrets["cookie"]["key"]),
    int(st.secrets["cookie"]["expiry_days"]),
)

auth.login()

if st.session_state["authentication_status"] is False:
    st.error("Incorrect username or password.")
    st.stop()
elif st.session_state["authentication_status"] is None:
    st.info("Please log in.")
    st.stop()

# ── Authenticated ─────────────────────────────────────────────────────────────
auth.logout(location="sidebar")
st.sidebar.write(f"Logged in as **{st.session_state['name']}**")

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_SYSTEM = """\
あなたは日本語教育の専門家です。
日本語能力試験N4・N3レベルの学習者が読める「やさしい日本語」に変換してください。

出力は必ず以下の構造にしてください。他の見出しや装飾は使わないでください。

TITLE: （簡単にしたタイトルをここに1行で書く）

（簡単にした本文をここに書く）

## Vocabulary List

| Word | Meaning |
|------|---------|
| （語句） | （簡単な意味） |

変換ルール:
1. {level}レベルの文法・語彙のみを使う（難しい語は簡単な語に置き換える）
2. 一文を短くする（20〜30字程度）
3. 敬体（です・ます調）に統一する
4. 難しい語句には意味の説明を添える
5. {furigana_instruction}
6. 語句リストには重要な語句を8〜12語入れる。しかし実際優しくした文章に出てくる語句のみ。語句リストでも、漢字にはすべてふりがなをつける（rubyタグを使う）。
"""

DEFAULT_FURIGANA_INSTRUCTIONS = {
    "All kanji": "漢字にはふりがなをつける（HTMLのrubyタグを使う、例えば：<ruby>漢字<rt>かなよみ</rt></ruby>）\
       - 普通の数字（算用数字）にはふりがなをつけない \
       - ただし日付として読む漢字（月・日など）は正しく読む \
         ・「月」→「がつ」（例：1<ruby>月<rt>がつ</rt></ruby>） \
         ・「日」が日付の場合は日本語の日付読みに従う（ついたち・ふつか…） \
         ・年（ねん）も同様: 2024<ruby>年<rt>ねん</rt></ruby> \
       - 日付以外の「日」は文脈で判断（「今日」→<ruby>今日<rt>きょう</rt></ruby>）\
       - 固有名詞（人名・地名など）にもふりがなをつける \
       - カタカナにはふりがなをつけない",
    "N2+ only": "Add furigana only to N2-level kanji or harder. Leave common kanji without furigana.",
    "None": "Do not add any furigana.",
}

# Merge saved overrides on top of the hardcoded defaults
FURIGANA_INSTRUCTIONS = {
    **DEFAULT_FURIGANA_INSTRUCTIONS,
    **_settings.get("furigana_instructions", {}),
}

HTML_CSS = """\
body {
  font-family: "Hiragino Sans", "Yu Gothic", "Meiryo", sans-serif;
  font-size: 13pt;
  line-height: 2.8;
  color: #1a1a1a;
  max-width: 720px;
  margin: 2cm auto;
  padding: 0 1cm;
}
ruby {
  ruby-align: center;
}
rt {
  font-size: 0.5em;
  color: #555;
}
h1 {
  font-size: 1.5em;
  font-weight: bold;
  margin: 0 0 0.6em;
  line-height: 1.8;
  border-bottom: 2px solid #1a1a1a;
  padding-bottom: 0.2em;
}
h2 {
  font-size: 1.15em;
  font-weight: bold;
  margin: 1.6em 0 0.4em;
  line-height: 1.6;
  color: #333;
  border-bottom: 1px solid #ccc;
  padding-bottom: 0.15em;
}
p {
  margin: 0.4em 0 1em;
}
table {
  border-collapse: collapse;
  width: 100%;
  margin: 0.6em 0 1.4em;
  font-size: 11pt;
  line-height: 2.2;
}
th {
  background: #2c2c2c;
  color: #fff;
  font-weight: bold;
  padding: 8px 14px;
  text-align: left;
  letter-spacing: 0.03em;
}
td {
  padding: 6px 14px;
  text-align: left;
  border-bottom: 1px solid #ddd;
  vertical-align: middle;
}
tr:nth-child(even) td {
  background: #f7f7f7;
}
tr:last-child td {
  border-bottom: none;
}
hr {
  border: none;
  border-top: 1px solid #ccc;
  margin: 1.2em 0;
}
strong { font-weight: bold; }
em     { font-style: italic; }
@media print {
  body { margin: 0; padding: 0; max-width: 100%; }
}
"""

VOCAB_SECTION_MARKER = "## Vocabulary List"


def parse_result(raw: str) -> tuple[str, str, str]:
    """Return (simplified_title, body, vocab_markdown).

    Expects the model to emit:
        TITLE: <one-line simplified title>
        <blank line>
        <body paragraphs>
        ## Vocabulary List
        <markdown table>
    """
    # Extract title line
    title = ""
    rest = raw
    for line in raw.splitlines():
        if line.startswith("TITLE:"):
            title = line[len("TITLE:") :].strip()
            # Remove the title line (and any immediately following blank line) from rest
            rest = raw[raw.index(line) + len(line) :].lstrip("\n")
            break

    # Split body from vocab section
    if VOCAB_SECTION_MARKER in rest:
        body_part, vocab_part = rest.split(VOCAB_SECTION_MARKER, 1)
    else:
        body_part = rest
        vocab_part = ""

    return title, body_part.strip(), vocab_part.strip()


def result_to_html(title: str, body_md: str, vocab_md: str) -> bytes:
    """Wrap the parsed model output in a self-contained HTML file."""
    body_html = markdown.markdown(body_md, extensions=["tables"], output_format="html")

    title_html = ""
    if title:
        title_html = f"<h1>{title}</h1>\n"

    vocab_html = ""
    if vocab_md:
        vocab_html = "<h2>Vocabulary List</h2>\n" + markdown.markdown(
            vocab_md, extensions=["tables"], output_format="html"
        )

    full_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title or "やさしい日本語"}</title>
  <style>
{HTML_CSS}
  </style>
</head>
<body>
{title_html}{body_html}
{vocab_html}
</body>
</html>"""
    return full_html.encode("utf-8")


# ── UI ────────────────────────────────────────────────────────────────────────
st.title("Japanese article simplifier")

title_input = st.text_input(
    "Article title",
    placeholder="記事のタイトルを入力してください…",
)
text = st.text_area(
    "Paste Japanese text here",
    height=220,
    placeholder="ここに日本語の文章を貼り付けてください…",
)
col1, col2 = st.columns(2)
level = col1.selectbox("Target JLPT level", ["N5", "N4", "N3", "N2", "N1"], index=2)
furi = col2.selectbox("Furigana", list(FURIGANA_INSTRUCTIONS), index=0)

with st.expander("Edit system prompt"):
    st.caption(
        "Use `{level}` and `{furigana_instruction}` as placeholders — "
        "they are filled in automatically from the dropdowns above."
    )
    system_template = (
        st.text_area(
            "System prompt",
            value=_settings.get("system_prompt") or DEFAULT_SYSTEM,
            height=280,
            label_visibility="collapsed",
        )
        or DEFAULT_SYSTEM
    )
    col_save_sys, col_reset_sys = st.columns([1, 1])
    if col_save_sys.button("💾 Save as default", key="save_system"):
        _settings["system_prompt"] = system_template
        save_settings(_settings)
        _load_settings_cached.clear()
        st.success("System prompt saved.")
    if col_reset_sys.button("Reset to default", key="reset_system"):
        _settings.pop("system_prompt", None)
        save_settings(_settings)
        _load_settings_cached.clear()
        st.rerun()

with st.expander("Edit furigana instructions"):
    st.caption(
        "These are the texts substituted for `{furigana_instruction}` depending on the Furigana dropdown selection above."
    )
    edited_furigana: dict[str, str] = {}
    saved_furi: dict[str, str] = _settings.get("furigana_instructions") or {}
    for key, default_value in DEFAULT_FURIGANA_INSTRUCTIONS.items():
        col_label, col_reset = st.columns([6, 1])
        col_label.markdown(f"**{key}**")
        if col_reset.button("Reset", key=f"reset_furi_{key}"):
            saved_furi.pop(key, None)
            _settings["furigana_instructions"] = saved_furi
            save_settings(_settings)
            _load_settings_cached.clear()
            st.rerun()
        edited_furigana[key] = (
            st.text_area(
                key,
                value=saved_furi.get(key) or default_value,
                height=120,
                label_visibility="collapsed",
                key=f"furi_{key}",
            )
            or default_value
        )
    if st.button("💾 Save as default", key="save_furi"):
        _settings["furigana_instructions"] = edited_furigana
        save_settings(_settings)
        _load_settings_cached.clear()
        st.success("Furigana instructions saved.")

# ── Run ───────────────────────────────────────────────────────────────────────
if st.button("Simplify →", type="primary"):
    if not text.strip():
        st.warning("Please paste some Japanese text first.")
    else:
        try:
            system = system_template.format(
                level=level,
                furigana_instruction=edited_furigana[furi or "None"],
            )
        except KeyError as e:
            st.error(
                f"Unknown placeholder in prompt: {e}. Use only {{level}} and {{furigana_instruction}}."
            )
            st.stop()

        user_message = text.strip()
        if title_input.strip():
            user_message = f"タイトル：{title_input.strip()}\n\n{user_message}"

        client = anthropic.Anthropic(api_key=st.secrets["anthropic"]["api_key"])
        with st.spinner("Simplifying…"):
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )

        text_blocks = [block for block in msg.content if isinstance(block, TextBlock)]
        if not text_blocks:
            st.error("No text response received from the model.")
            st.stop()
        raw = text_blocks[0].text.strip()

        simplified_title, body_md, vocab_md = parse_result(raw)

        st.divider()
        html_bytes = result_to_html(simplified_title, body_md, vocab_md)
        # Render via components.html so the output is part of the normal page
        # flow and never creates a competing scroll container.
        # Height is estimated from content length; 1px = ~2 chars is conservative.
        estimated_height = max(400, len(html_bytes) // 2)
        components.html(
            html_bytes.decode("utf-8"), height=estimated_height, scrolling=False
        )

        st.download_button(
            label="🖨️ Download for printing",
            data=result_to_html(simplified_title, body_md, vocab_md),
            file_name="yasashii_nihongo.html",
            mime="text/html",
        )
