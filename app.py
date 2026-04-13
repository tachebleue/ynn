import anthropic
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from anthropic.types.text_block import TextBlock
from yaml.loader import SafeLoader

# ── Auth ──────────────────────────────────────────────────────────────────────
with open("credentials.yaml") as f:
    config = yaml.load(f, Loader=SafeLoader)

auth = stauth.Authenticate(
    config["credentials"],
    config["cookie"]["name"],
    config["cookie"]["key"],
    config["cookie"]["expiry_days"],
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

# ── Default prompt ─────────────────────────────────────────────────────────────
DEFAULT_SYSTEM = """\
あなたは日本語教育の専門家です。
日本語能力試験N4・N3レベルの学習者が読める「やさしい日本語」に変換してください。マークダウンや余計な文字は不要です。

変換ルール:
1. {level}レベルの文法・語彙のみを使う（難しい語は簡単な語に置き換える）
2. 一文を短くする（20〜30字程度）
3. 敬体（です・ます調）に統一する
4. 難しい語句には意味の説明を添える
5. {furigana_instruction}
6. 重要な語句リストも出力する（元の語と簡単な意味）
"""

FURIGANA_INSTRUCTIONS = {
    "All kanji": "漢字にはふりがなをつける（HTMLのrubyタグを使う、例えば：<ruby>漢字<rt>かなよみ</rt></ruby>）\
       - 普通の数字（算用数字）にはふりがなをつけない \
       - ただし日付として読む漢字（月・日など）は正しく読む \
         ・「月」→「がつ」（例：1<ruby>月<rt>がつ</rt></ruby>） \
         ・「日」が日付の場合は日本語の日付読みに従う（ついたち・ふつか…） \
         ・年（ねん）も同様: 2024<ruby>年<rt>ねん</rt></ruby> \
       - 日付以外の「日」は文脈で判断（「今日」→<ruby>今日<rt>きょう</rt></ruby>）\
       - 固有名詞（人名・地名など）にもふりがなをつける",
    "N2+ only": "Add furigana only to N2-level kanji or harder. Leave common kanji without furigana.",
    "None": "Do not add any furigana.",
}

# ── UI ────────────────────────────────────────────────────────────────────────
st.title("Japanese article simplifier")

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
    system_template = st.text_area(
        "System prompt", value=DEFAULT_SYSTEM, height=220, label_visibility="collapsed"
    )
    if st.button("Reset to default"):
        system_template = DEFAULT_SYSTEM
        st.rerun()

# ── Run ───────────────────────────────────────────────────────────────────────
if st.button("Simplify →", type="primary"):
    if not text.strip():
        st.warning("Please paste some Japanese text first.")
    else:
        try:
            system = system_template.format(
                level=level,
                furigana_instruction=FURIGANA_INSTRUCTIONS[furi],
            )
        except KeyError as e:
            st.error(
                f"Unknown placeholder in prompt: {e}. Use only {{level}} and {{furigana_instruction}}."
            )
            st.stop()

        client = anthropic.Anthropic()
        with st.spinner("Simplifying…"):
            msg = client.messages.create(
                model="claude-opus-4-5",
                max_tokens=2048,
                system=system,
                messages=[{"role": "user", "content": text}],
            )

        text_blocks = [block for block in msg.content if isinstance(block, TextBlock)]
        if not text_blocks:
            st.error("No text response received from the model.")
            st.stop()
        result = text_blocks[0].text.strip()
        st.divider()
        st.markdown(result, unsafe_allow_html=True)
