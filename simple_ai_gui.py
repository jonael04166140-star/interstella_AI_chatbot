import streamlit as st
import streamlit.components.v1 as components
import requests
import spacy
import time
import re
import json
from itertools import chain
from datetime import datetime, timezone, timedelta
from sentence_transformers import SentenceTransformer

# ==========================================
# 1. 환경 설정 및 변수
# ==========================================
SUPABASE_URL = "https://hxpbryalkbdbusrepsne.supabase.co"
ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh4cGJyeWFsa2JkYnVzcmVwc25lIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODMyNzU2MDgsImV4cCI6MjA5ODg1MTYwOH0.vwL_b5eB9PjmXGKnOghV5ahR4Gmcjzr7Jjc9R_of9Jg"
headers = {"apikey": ANON_KEY, "Authorization": f"Bearer {ANON_KEY}", "Content-Type": "application/json"}

EDGE_URL = f"{SUPABASE_URL}/functions/v1/functional_answer"
BOT_AVATAR = "🌌"
USER_AVATAR = "🙂"
TYPING_DELAY = 0.02
KST = timezone(timedelta(hours=9))

st.set_page_config(page_title="산청고 AI 챗봇 밀키웨이", page_icon="💬", layout="centered")

# ==========================================
# 💡 [디자인] 아이폰 메시지(iMessage) 스타일 CSS
# ==========================================
CUSTOM_CSS = """
<style>
/* ===== 색상 · 폰트 변수 (라이트/다크 자동) · 따뜻한 크림 + 테라코타 톤 ===== */
:root {
    --mw-bg: #faf9f5;
    --mw-text: #1f1e1d;
    --mw-recv: #f0eee6;
    --mw-sent: #c0603f;
    --mw-link: #b4502e;
    --mw-muted: #8a867c;
    --mw-bar: rgba(250, 249, 245, 0.82);
    --mw-line: rgba(31, 30, 29, 0.12);
    --mw-line-strong: #dad7cb;
    --mw-dot: #c0603f;
    --mw-shadow: 0 1px 2px rgba(31, 30, 29, 0.06);
    --mw-input-shadow: 0 2px 12px rgba(31, 30, 29, 0.06);
    --mw-font: "Pretendard", "Apple SD Gothic Neo", "Noto Sans KR", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    --mw-serif: "Noto Serif KR", "Nanum Myeongjo", "Apple SD Gothic Neo", Georgia, "Times New Roman", serif;

    /* 말풍선 셀렉터에서 공통으로 쓰는 값 */
    --mw-radius: 1.2rem;
}
@media (prefers-color-scheme: dark) {
    :root {
        --mw-bg: #262624;
        --mw-text: #f0eee6;
        --mw-recv: #33322f;
        --mw-sent: #c4623f;
        --mw-link: #e8a07f;
        --mw-muted: #9a968c;
        --mw-bar: rgba(38, 38, 36, 0.82);
        --mw-line: rgba(240, 238, 230, 0.14);
        --mw-line-strong: #4a4945;
        --mw-dot: #d97757;
        --mw-shadow: none;
        --mw-input-shadow: 0 2px 12px rgba(0, 0, 0, 0.25);
    }
}

/* ===== 기본 장식 정리 ===== */
#MainMenu, footer, [data-testid="stDecoration"],
[data-testid="stToolbar"], [data-testid="stAppDeployButton"], [data-testid="stMainMenu"] {display: none !important;}
header[data-testid="stHeader"] {background: transparent; height: 0;}
.stApp, [data-testid="stAppViewContainer"] {background: var(--mw-bg) !important; color: var(--mw-text);}
.stApp, .stApp button, .stApp textarea {font-family: var(--mw-font) !important;}
.block-container {max-width: 720px; padding: 6.2rem 1rem 7rem;}
.block-container [data-testid="stVerticalBlock"] {gap: 0.28rem;}
* {scrollbar-width: thin; scrollbar-color: rgba(138, 134, 124, 0.4) transparent;}

/* 답변이 오는 동안 이전 말풍선이 흐려졌다 돌아오는 깜빡임 방지 */
[data-stale="true"] {opacity: 1 !important; transition: none !important;}

/* ===== 애니메이션 ===== */
@keyframes mw-pop {
    0%   {opacity: 0; transform: scale(0.6) translateY(6px);}
    60%  {opacity: 1; transform: scale(1.03);}
    100% {opacity: 1; transform: scale(1);}
}
@keyframes mw-fade {from {opacity: 0;} to {opacity: 1;}}
@keyframes mw-fade-down {from {opacity: 0; transform: translateY(-10px);} to {opacity: 1; transform: translateY(0);}}
@keyframes mw-rise {from {opacity: 0; transform: translateY(12px);} to {opacity: 1; transform: translateY(0);}}
@keyframes mw-dot {
    0%, 60%, 100% {opacity: 0.35; transform: translateY(0);}
    30%           {opacity: 1;    transform: translateY(-4px);}
}
@keyframes mw-pulse {
    0%   {box-shadow: 0 0 0 0 rgba(91, 154, 106, 0.5);}
    70%  {box-shadow: 0 0 0 6px rgba(91, 154, 106, 0);}
    100% {box-shadow: 0 0 0 0 rgba(91, 154, 106, 0);}
}

/* ===== 상단 연락처 바 (블러) ===== */
.mw-bar {
    position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
    display: flex; justify-content: center; padding: 0.55rem 0 0.45rem;
    padding-top: calc(0.55rem + env(safe-area-inset-top, 0px));
    background: var(--mw-bar);
    backdrop-filter: blur(24px) saturate(180%); -webkit-backdrop-filter: blur(24px) saturate(180%);
    border-bottom: 0.5px solid var(--mw-line);
    animation: mw-fade-down 0.45s ease-out;
}
.mw-contact {display: flex; flex-direction: column; align-items: center; gap: 0.1rem;}
.mw-avatar-wrap {position: relative;}
.mw-avatar {
    width: 46px; height: 46px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(160deg, #e39574, #c0603f 65%, #a84e30);
    font-family: var(--mw-serif);
    color: #fff; font-weight: 700; font-size: 1.15rem;
    box-shadow: 0 2px 8px rgba(192, 96, 63, 0.32);
}
.mw-online {
    position: absolute; right: 0; bottom: 1px; width: 12px; height: 12px; border-radius: 50%;
    background: #5b9a6a; border: 2px solid var(--mw-bg); animation: mw-pulse 2.4s infinite;
}
.mw-name {font-family: var(--mw-serif); font-size: 0.82rem; font-weight: 700; color: var(--mw-text);}
.mw-name span {color: var(--mw-muted); margin-left: 2px; font-weight: 400;}
.mw-sub {font-size: 0.62rem; color: var(--mw-muted); margin-top: -0.1rem;}

/* ===== 시간 라벨 / 읽음 표시 ===== */
.mw-time {text-align: center; font-size: 0.72rem; color: var(--mw-muted); margin: 0.2rem 0 0.6rem; animation: mw-fade 0.5s ease-out;}
.mw-time b {font-weight: 600;}
.mw-receipt {text-align: right; font-size: 0.7rem; font-weight: 600; color: var(--mw-muted); padding-right: 0.4rem; animation: mw-fade 0.4s ease-out;}

/* =====================================================================
   말풍선
   ※ 이모지 아바타(🌌 🙂)를 쓰면 Streamlit이 stChatMessageAvatarUser/Assistant 속성을
     붙이지 않으므로, 항상 존재하는 aria-label("Chat message from user/assistant")로
     보낸 사람을 구분합니다.
   ===================================================================== */

/* 아바타 숨김 (본문을 제외한 나머지 자식) */
[data-testid="stChatMessage"] > *:not([data-testid="stChatMessageContent"]) {display: none !important;}

/* 한 줄(행) 전체 */
[data-testid="stChatMessage"] {
    display: flex !important; width: 100%;
    background: transparent !important; border: none !important;
    padding: 0.06rem 0 !important; gap: 0 !important; overflow: visible;
}
[data-testid="stChatMessage"]:has(> [aria-label="Chat message from assistant"]) {justify-content: flex-start;}
[data-testid="stChatMessage"]:has(> [aria-label="Chat message from user"])      {justify-content: flex-end;}

/* 말풍선 공통 */
[data-testid="stChatMessageContent"] {
    position: relative; isolation: isolate;
    flex: 0 1 auto !important; width: fit-content !important; min-width: 0; max-width: 78%;
    margin: 0 !important; /* Streamlit 기본값 margin:auto 가 말풍선을 가운데로 밀어내므로 제거 */
    padding: 0.55rem 0.95rem; border-radius: var(--mw-radius);
    font-size: 1rem; line-height: 1.42; box-shadow: var(--mw-shadow);
    word-break: keep-all; overflow-wrap: anywhere;
}
/* Streamlit 마크다운 컨테이너는 margin-bottom:-1rem 으로 마지막 문단 여백을 상쇄합니다.
   여백을 직접 관리하므로 상쇄값을 0으로 맞춰야 말풍선 아래가 잘리지 않습니다. */
[data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"] {margin-bottom: 0 !important;}
[data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"] > :last-child {margin-bottom: 0 !important;}
[data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"],
[data-testid="stChatMessageContent"] p, [data-testid="stChatMessageContent"] li {
    word-break: keep-all !important; overflow-wrap: anywhere !important; /* 한글은 단어(띄어쓰기) 단위로 줄바꿈 */
}
[data-testid="stChatMessageContent"] p {margin: 0 0 0.4rem;}
[data-testid="stChatMessageContent"] ul, [data-testid="stChatMessageContent"] ol {margin: 0.15rem 0 0.4rem; padding-left: 1.15rem;}
[data-testid="stChatMessageContent"] li {margin: 0.1rem 0; padding-left: 0.1rem;}
[data-testid="stChatMessageContent"] li p {margin: 0;}
[data-testid="stChatMessageContent"] h1, [data-testid="stChatMessageContent"] h2,
[data-testid="stChatMessageContent"] h3, [data-testid="stChatMessageContent"] h4 {
    font-size: 1.04rem; font-weight: 700; margin: 0.15rem 0 0.3rem; padding: 0;
}
[data-testid="stChatMessageContent"] code {
    font-size: 0.88em; padding: 0.1em 0.38em; border-radius: 6px; background: rgba(120, 120, 128, 0.18);
}
[data-testid="stChatMessageContent"] a {text-decoration: underline; text-underline-offset: 2px;}

/* ----- 받은 메시지 (왼쪽 · 크림) ----- */
[data-testid="stChatMessageContent"][aria-label="Chat message from assistant"] {
    background: var(--mw-recv); color: var(--mw-text); margin-right: auto !important;
    border: 1px solid var(--mw-line); border-bottom-left-radius: 0.4rem;
    animation: mw-rise 0.35s ease-out;
}
[data-testid="stChatMessageContent"][aria-label="Chat message from assistant"] a {color: var(--mw-link);}

/* ----- 보낸 메시지 (오른쪽 · 테라코타) ----- */
[data-testid="stChatMessageContent"][aria-label="Chat message from user"] {
    background: var(--mw-sent); color: #fff; margin-left: auto !important;
    border: 1px solid transparent; border-bottom-right-radius: 0.4rem;
    animation: mw-rise 0.35s ease-out;
}
[data-testid="stChatMessageContent"][aria-label="Chat message from user"] * {color: #fff !important;}
[data-testid="stChatMessageContent"][aria-label="Chat message from user"] code {background: rgba(255, 255, 255, 0.22);}

/* ----- 같은 사람이 연속으로 보낸 말풍선: 모서리를 모두 둥글게 ----- */
:is([data-testid="stLayoutWrapper"], [data-testid="stElementContainer"]):has(> [data-testid="stChatMessage"] [aria-label="Chat message from user"]):has(+ :is([data-testid="stLayoutWrapper"], [data-testid="stElementContainer"]) > [data-testid="stChatMessage"] [aria-label="Chat message from user"]) [data-testid="stChatMessageContent"] {
    border-bottom-right-radius: var(--mw-radius);
}
:is([data-testid="stLayoutWrapper"], [data-testid="stElementContainer"]):has(> [data-testid="stChatMessage"] [aria-label="Chat message from assistant"]):has(+ :is([data-testid="stLayoutWrapper"], [data-testid="stElementContainer"]) > [data-testid="stChatMessage"] [aria-label="Chat message from assistant"]) [data-testid="stChatMessageContent"] {
    border-bottom-left-radius: var(--mw-radius);
}
/* 말하는 사람이 바뀌면 간격을 조금 더 벌려 대화 흐름이 보이게 */
:is([data-testid="stLayoutWrapper"], [data-testid="stElementContainer"]):has(> [data-testid="stChatMessage"] [aria-label="Chat message from user"]) + :is([data-testid="stLayoutWrapper"], [data-testid="stElementContainer"]):has(> [data-testid="stChatMessage"] [aria-label="Chat message from assistant"]),
:is([data-testid="stLayoutWrapper"], [data-testid="stElementContainer"]):has(> [data-testid="stChatMessage"] [aria-label="Chat message from assistant"]) + :is([data-testid="stLayoutWrapper"], [data-testid="stElementContainer"]):has(> [data-testid="stChatMessage"] [aria-label="Chat message from user"]) {
    margin-top: 0.4rem;
}

/* ===== '입력 중...' 점 세 개 ===== */
.mw-typing {display: inline-flex; align-items: center; gap: 5px; height: 1.4rem; padding: 0 0.2rem;}
.mw-typing span {
    width: 8px; height: 8px; border-radius: 50%; background: var(--mw-dot);
    animation: mw-dot 1.3s infinite ease-in-out;
}
.mw-typing span:nth-child(2) {animation-delay: 0.18s;}
.mw-typing span:nth-child(3) {animation-delay: 0.36s;}

/* ===== 입력창 ===== */
[data-testid="stBottom"] > div {
    background: var(--mw-bar) !important;
    backdrop-filter: blur(24px) saturate(180%); -webkit-backdrop-filter: blur(24px) saturate(180%);
    border-top: 0.5px solid var(--mw-line);
    padding-bottom: env(safe-area-inset-bottom, 0px);
}
[data-testid="stChatInput"] {background: transparent !important; border: none !important; box-shadow: none !important;}
[data-testid="stChatInput"] > div {
    border-radius: 20px !important; border: 1px solid var(--mw-line-strong) !important;
    background: var(--mw-bg) !important; box-shadow: var(--mw-input-shadow); overflow: hidden;
    transition: border-color 0.2s, box-shadow 0.2s;
}
[data-testid="stChatInput"] > div:focus-within {
    border-color: var(--mw-sent) !important; box-shadow: 0 0 0 3px rgba(192, 96, 63, 0.16);
}
[data-testid="stChatInput"] > div div, [data-testid="stChatInput"] textarea {
    background: transparent !important; border-radius: 0 !important; box-shadow: none !important;
}
[data-testid="stChatInput"] textarea {font-size: 1rem; padding-left: 1.1rem !important; color: var(--mw-text);}
[data-testid="stChatInput"] textarea::placeholder {color: var(--mw-muted); opacity: 1;}
[data-testid="stChatInput"] button {
    border-radius: 12px !important; background: var(--mw-sent) !important; color: #fff !important;
    transition: transform 0.15s, opacity 0.2s;
}
[data-testid="stChatInput"] button:hover {transform: scale(1.08);}
[data-testid="stChatInput"] button:active {transform: scale(0.9);}
[data-testid="stChatInput"] button:disabled {background: var(--mw-muted) !important; opacity: 0.3;}
[data-testid="stChatInput"] button svg {fill: #fff !important; color: #fff !important;}

/* ===== 답변 아래 평가 아이콘 줄 (좁은 화면에서도 가로로 유지) ===== */
[data-testid="stHorizontalBlock"]:has([class*="st-key-fb_"]) {
    flex-wrap: nowrap !important; gap: 0.1rem !important; align-items: center; padding-left: 0.15rem;
}
[data-testid="stHorizontalBlock"]:has([class*="st-key-fb_"]) > [data-testid="stColumn"] {
    flex: 0 0 auto !important; width: auto !important; min-width: 0 !important;
}
[class*="st-key-fb_"] {animation: mw-rise 0.3s ease-out;}
[class*="st-key-fb_"] button {
    background: transparent !important; border: none !important; box-shadow: none !important;
    padding: 0.05rem 0.4rem !important; min-height: 0 !important;
    font-size: 0.95rem; opacity: 0.55; transition: opacity 0.15s, transform 0.15s, background 0.15s;
}
[class*="st-key-fb_"] button:hover {opacity: 1; transform: scale(1.15); background: rgba(142, 142, 147, 0.16) !important; border-radius: 10px;}
[class*="st-key-fb_"] button:active {transform: scale(0.9);}
.mw-fb-note {font-size: 0.72rem; font-weight: 600; color: var(--mw-muted); white-space: nowrap; padding-left: 0.2rem; animation: mw-fade 0.4s ease-out;}

/* ===== 추천 질문 (iOS 스마트 답장 느낌 · 모바일에서도 2열) ===== */
[data-testid="stHorizontalBlock"]:has([class*="st-key-chip_"]) {
    flex-wrap: wrap !important; gap: 0.5rem !important; margin-top: 0.5rem;
}
[data-testid="stHorizontalBlock"]:has([class*="st-key-chip_"]) > [data-testid="stColumn"] {
    flex: 1 1 calc(50% - 0.5rem) !important; width: auto !important; min-width: 0 !important;
}
[class*="st-key-chip_"] {animation: mw-rise 0.5s ease-out both;}
.st-key-chip_1 {animation-delay: 0.08s;}
.st-key-chip_2 {animation-delay: 0.16s;}
.st-key-chip_3 {animation-delay: 0.24s;}
[class*="st-key-chip_"] button {
    border-radius: 14px; border: 1px solid var(--mw-line-strong); background: var(--mw-bg);
    padding: 0.5rem 0.8rem; transition: transform 0.15s, background 0.15s, border-color 0.15s;
}
[class*="st-key-chip_"] button p {
    color: var(--mw-sent) !important; font-size: 0.9rem; font-weight: 500; line-height: 1.25;
    white-space: normal; word-break: keep-all; overflow: visible; text-overflow: clip;
}
[class*="st-key-chip_"] button:hover {background: rgba(192, 96, 63, 0.09); border-color: var(--mw-sent); transform: translateY(-1px);}
[class*="st-key-chip_"] button:active {transform: scale(0.96);}

/* ===== 작은 화면 ===== */
@media (max-width: 480px) {
    .block-container {padding-left: 0.7rem; padding-right: 0.7rem;}
    [data-testid="stChatMessageContent"] {max-width: 85%; font-size: 0.98rem;}
}

/* ===== 모션 줄이기 설정 존중 ===== */
@media (prefers-reduced-motion: reduce) {
    * {animation: none !important; transition: none !important;}
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

TYPING_HTML = '<div class="mw-typing"><span></span><span></span><span></span></div>'


def time_label():
    n = datetime.now(KST)
    ampm = "오전" if n.hour < 12 else "오후"
    return f"<b>오늘</b> {ampm} {n.hour % 12 or 12}:{n.minute:02d}"


# ==========================================
# 세션 상태
# ==========================================
# messages 항목: {"role", "content", "feedback"(dict|None), "voted"(None|"up"|"down"), "detail_done"(bool)}
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_topic" not in st.session_state:
    st.session_state.last_topic = None
if "last_suggestion" not in st.session_state:
    st.session_state.last_suggestion = None
if "last_intent" not in st.session_state:
    st.session_state.last_intent = None
if "last_class" not in st.session_state:
    st.session_state.last_class = None
if "latest_feedback" not in st.session_state:
    # 💡 스트리밍 중 서버가 돌려준 평가 정보. 답변이 끝나면 그 메시지에 붙입니다.
    st.session_state.latest_feedback = None
if "queued_prompt" not in st.session_state:
    st.session_state.queued_prompt = None
if "pending_detail" not in st.session_state:
    st.session_state.pending_detail = None
if "started_label" not in st.session_state:
    st.session_state.started_label = time_label()


# ==========================================
# 💡 [자동 스크롤]
# ==========================================
def scroll_to_bottom():
    components.html(
        """
        <script>
        (function() {
            function getMainContainer() {
                const doc = window.parent.document;
                return (
                    doc.querySelector('[data-testid="stMain"]') ||
                    doc.querySelector('section[data-testid="stMain"]') ||
                    doc.querySelector('[data-testid="stAppViewContainer"] section.main') ||
                    doc.querySelector('section.main') ||
                    doc.querySelector('[data-testid="stAppViewContainer"]')
                );
            }
            function scrollToBottom() {
                const el = getMainContainer();
                if (el) { el.scrollTop = el.scrollHeight; }
            }
            [0, 50, 150, 300, 600].forEach(function(delay) { setTimeout(scrollToBottom, delay); });
        })();
        </script>
        """,
        height=0,
    )


# ==========================================
# 2. 핵심 로직 함수들 (Streamlit 캐싱 적용)
# ==========================================
@st.cache_resource(show_spinner="AI 엔진을 불러오는 중입니다...")
def load_ai_model():
    model = SentenceTransformer('snunlp/KR-SBERT-V40K-klueNLI-augSTS')
    try:
        nlp = spacy.load("ko_core_news_sm")
    except Exception:
        nlp = None
    return model, nlp


@st.cache_data(ttl=60, show_spinner="데이터베이스를 동기화하는 중입니다...")
def load_database_st():
    url = f"{SUPABASE_URL}/rest/v1/knowledge_qa?select=question,answer,category,keywords"
    topic_keywords = {}
    knowledge_base = []
    combined_sentences = []

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            for row in data:
                cat = row.get('category', '')
                keys_list = []

                if 'keywords' in row and row['keywords']:
                    keys_list = [k.strip() for k in row['keywords'].split(',')]
                    keys_list.append(cat)
                    if cat not in topic_keywords:
                        topic_keywords[cat] = keys_list.copy()
                    else:
                        topic_keywords[cat].extend(keys_list)

                if 'answer' in row and 'question' in row:
                    knowledge_base.append(row)
                    keyword_string = " ".join(keys_list)
                    combined_sentence = f"{row['question']} {keyword_string}"
                    combined_sentences.append(combined_sentence)
            return knowledge_base, combined_sentences, topic_keywords
    except Exception as e:
        st.error(f"DB 로드 실패: {e}")
    return [], [], {}


def semantic_search_db(query_text, top_k=2, threshold=0.65):
    """사용자 질문 하나만 인코딩하고, 유사도 검색은 pgvector RPC(match_knowledge_qa)에 맡깁니다."""
    query_vector = model.encode(query_text).tolist()
    rpc_url = f"{SUPABASE_URL}/rest/v1/rpc/match_knowledge_qa"
    payload = {
        "query_embedding": query_vector,
        "match_threshold": threshold,
        "match_count": top_k,
    }
    try:
        res = requests.post(rpc_url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            return res.json()
        else:
            st.error(f"의미 기반 검색 실패 (HTTP {res.status_code}): {res.text}")
            return []
    except Exception as e:
        st.error(f"의미 기반 검색 통신 오류: {e}")
        return []


def get_current_location():
    try:
        res = requests.get("http://ip-api.com/json/", timeout=5)
        return res.json().get('lat', 35.415), res.json().get('lon', 127.873)
    except Exception:
        return 35.415, 127.873


# 사이트 접속/새로고침 시 캐시를 비워 최신 DB를 불러옵니다.
if "app_initialized" not in st.session_state:
    load_database_st.clear()
    st.session_state.app_initialized = True

model, nlp = load_ai_model()
knowledge_base, combined_sentences, TOPIC_KEYWORDS = load_database_st()
current_lat, current_lon = get_current_location()


def rewrite_question(user_input):
    if nlp is None:
        return user_input
    all_known_keywords = [k for sublist in TOPIC_KEYWORDS.values() for k in sublist]

    if st.session_state.last_topic and not any(kw in user_input for kw in all_known_keywords):
        if user_input.endswith("은") or user_input.endswith("는") or user_input.endswith("은?") or user_input.endswith("는?"):
            clean = user_input.replace("은?", "").replace("는?", "").replace("은", "").replace("는", "").strip()
            return f"{clean} {st.session_state.last_topic}"

        date_pattern = r"어제|그저께|엊그제|내일|모레|글피|그글피|오늘|이번주|저번주|지난주|다음주|다다음주|저저번주|지지난주|요일|하루|이틀|사흘|나흘|닷새|엿새|이레|여드레|아흐레|열흘|보름|\d+일|\d+월|\d+주|\d+주일"
        if re.search(date_pattern, user_input):
            return f"{user_input} {st.session_state.last_topic}"
    return user_input


def update_topic(user_input):
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in user_input for kw in keywords):
            st.session_state.last_topic = topic
            break


def get_word_candidates(user_input):
    """사용자 입력을 '완전한 단어(토큰)' 단위 후보 집합으로 변환합니다."""
    if nlp is None:
        return set(user_input.split())

    tokens = [tok.text for tok in nlp(user_input) if tok.text.strip()]
    candidates = set(tokens)
    candidates.update(a + b for a, b in zip(tokens, tokens[1:]))
    return candidates


def get_content_tokens(user_input):
    """질문에서 내용어(명사/고유명사)만 추출합니다."""
    if nlp is None:
        return set(user_input.split())
    return {tok.text for tok in nlp(user_input) if tok.pos_ in ("NOUN", "PROPN") and len(tok.text) > 1}


def keyword_match(user_input, coverage_threshold=0.6):
    """키워드 AND 조건 매칭 + 명사 커버리지 검사."""
    word_candidates = get_word_candidates(user_input)
    content_tokens = get_content_tokens(user_input)
    candidates = []

    for idx, row in enumerate(knowledge_base):
        keywords_field = row.get('keywords', '') or ''
        for kw_group in keywords_field.split(','):
            conditions = [c.strip() for c in kw_group.split('+') if c.strip()]
            if not conditions:
                continue
            if not all(cond in word_candidates for cond in conditions):
                continue

            if content_tokens:
                covered = sum(
                    1 for t in content_tokens
                    if any(cond in t or t in cond for cond in conditions)
                )
                coverage_score = covered / len(content_tokens)
            else:
                coverage_score = 1.0

            if coverage_score >= coverage_threshold:
                candidates.append((idx, len(conditions), coverage_score))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (-x[1], -x[2]))
    return candidates[0][0]


# ==========================================
# 3. 출력 제너레이터 (스트리밍 타이핑 효과)
# ==========================================
def stream_text(text):
    for char in text:
        yield char
        time.sleep(TYPING_DELAY)


def _stream_error(msg):
    for char in msg:
        yield char
        time.sleep(TYPING_DELAY)


def _consume_edge_stream(response):
    """엣지 펑션 NDJSON 응답을 읽어 글자 단위로 yield. 평가 정보는 latest_feedback에 저장."""
    for line in response.iter_lines():
        if not line:
            continue
        res_json = json.loads(line.decode('utf-8'))

        if 'loading_msg' in res_json:
            yield f"_{res_json['loading_msg']}_\n\n"
        elif 'error' in res_json:
            yield from _stream_error(f"오류가 발생했습니다: {res_json['error']}")
        elif 'reply' in res_json:
            st.session_state.last_suggestion = res_json.get("suggestion")

            context = res_json.get("context")
            if context is not None:
                st.session_state.last_intent = context.get("last_intent")
                st.session_state.last_class = context.get("last_class")
                feedback = context.get("feedback")
                st.session_state.latest_feedback = feedback if feedback and feedback.get("enabled") else None

            for char in res_json.get('reply', ''):
                yield char
                time.sleep(TYPING_DELAY)


def stream_edge_function(original_input, lat, lon):
    data = {
        "user_message": original_input,
        "lat": lat,
        "lon": lon,
        "last_suggestion": st.session_state.last_suggestion,
        "last_intent": st.session_state.last_intent,
        "last_class": st.session_state.last_class,
    }
    try:
        response = requests.post(EDGE_URL, json=data, headers=headers, stream=True)
        if response.status_code == 200:
            yield from _consume_edge_stream(response)
        else:
            yield from _stream_error(f"엣지 펑션 연결 실패. (HTTP {response.status_code})")
    except Exception as e:
        yield from _stream_error(f"서버 통신 오류: {e}")


def stream_detail_answer(fb: dict):
    """'자세한 대답' 요청. 서버가 DB 답변을 참고자료 삼아 LLM으로 새 답을 만들어 돌려줍니다."""
    data = {
        "action": "detail",
        "qa_id": fb.get("qa_id"),
        "question": fb.get("question"),
        "raw_answer": fb.get("raw_answer"),
        "last_intent": st.session_state.last_intent,
        "last_class": st.session_state.last_class,
    }
    try:
        response = requests.post(EDGE_URL, json=data, headers=headers, stream=True)
        if response.status_code == 200:
            yield from _consume_edge_stream(response)
        else:
            yield from _stream_error(f"엣지 펑션 연결 실패. (HTTP {response.status_code})")
    except Exception as e:
        yield from _stream_error(f"서버 통신 오류: {e}")


def send_feedback(fb: dict, vote: str):
    """vote: 'up' 또는 'down'. 서버가 해당 항목의 reliability를 조정합니다."""
    try:
        requests.post(
            EDGE_URL,
            json={"action": "feedback", "qa_id": fb.get("qa_id"), "vote": vote},
            headers=headers,
            timeout=10,
        )
    except Exception as e:
        st.error(f"피드백 전송 실패: {e}")


# ==========================================
# 💬 '입력 중...' 말풍선 + 답변 스트리밍
# ==========================================
def show_typing():
    """회색 말풍선 안에서 점 세 개가 통통 튀는 '입력 중' 표시를 띄웁니다."""
    ph = st.empty()
    with ph.container():
        with st.chat_message("assistant", avatar=BOT_AVATAR):
            st.markdown(TYPING_HTML, unsafe_allow_html=True)
    return ph


def stream_reply(ph, gen, started_at, min_delay=0.0):
    """첫 글자가 올 때까지 '입력 중' 말풍선을 보여주고, 도착하면 실제 답변 말풍선으로 바꿔 스트리밍합니다."""
    gen = iter(gen)
    try:
        first = next(gen)
        chunks = chain([first], gen)
    except StopIteration:
        chunks = iter(())

    wait = min_delay - (time.time() - started_at)
    if wait > 0:
        time.sleep(wait)

    ph.empty()
    with st.chat_message("assistant", avatar=BOT_AVATAR):
        return st.write_stream(chunks)


def add_assistant_message(text):
    """답변을 대화 기록에 저장하고, 평가 아이콘 줄이 필요하면 바로 아래에 붙입니다."""
    st.session_state.messages.append({
        "role": "assistant",
        "content": text,
        "feedback": st.session_state.latest_feedback,
        "voted": None,
        "detail_done": False,
    })
    st.session_state.latest_feedback = None
    idx = len(st.session_state.messages) - 1
    msg = st.session_state.messages[idx]
    if msg["feedback"]:
        render_feedback_row(idx, msg)


# ==========================================
# 4. UI 구성
# ==========================================
st.markdown(
    """
    <div class="mw-bar">
        <div class="mw-contact">
            <div class="mw-avatar-wrap"><div class="mw-avatar">밀</div><span class="mw-online"></span></div>
            <div class="mw-name">밀키웨이<span>›</span></div>
            <div class="mw-sub">산청고등학교 AI 챗봇 · 인터스텔라</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


def render_feedback_row(i: int, msg: dict):
    """받은 메시지 바로 아래에 붙는 작은 아이콘 줄. 입력창은 가리지 않습니다."""
    voted = msg.get("voted")
    detail_done = msg.get("detail_done", False)

    c_up, c_down, c_detail, c_note = st.columns([1, 1, 1, 9], gap="small", vertical_alignment="center")

    if not voted:
        with c_up:
            if st.button("👍", key=f"fb_up_{i}", help="도움이 됐어요"):
                send_feedback(msg["feedback"], "up")
                st.session_state.messages[i]["voted"] = "up"
                st.rerun()
        with c_down:
            if st.button("👎", key=f"fb_down_{i}", help="별로예요"):
                send_feedback(msg["feedback"], "down")
                st.session_state.messages[i]["voted"] = "down"
                st.rerun()

    if not detail_done:
        with c_detail:
            if st.button("🔍", key=f"fb_detail_{i}", help="자세한 대답 보기"):
                st.session_state.messages[i]["detail_done"] = True
                st.session_state.pending_detail = i
                st.rerun()

    if voted:
        with c_note:
            note = "도움이 됐다고 기록했어요" if voted == "up" else "더 나아지도록 반영할게요"
            st.markdown(f'<div class="mw-fb-note">{note}</div>', unsafe_allow_html=True)


def render_messages():
    msgs = st.session_state.messages
    last_user = max((i for i, m in enumerate(msgs) if m["role"] == "user"), default=None)

    for i, msg in enumerate(msgs):
        avatar = BOT_AVATAR if msg["role"] == "assistant" else USER_AVATAR
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

        # 마지막으로 보낸 메시지 아래에 아이폰처럼 '전송됨/읽음' 표시
        if msg["role"] == "user" and i == last_user:
            status = "읽음" if i < len(msgs) - 1 else "전송됨"
            st.markdown(f'<div class="mw-receipt">{status}</div>', unsafe_allow_html=True)

        if msg["role"] == "assistant" and msg.get("feedback"):
            render_feedback_row(i, msg)


def render_welcome():
    with st.chat_message("assistant", avatar=BOT_AVATAR):
        st.markdown("안녕하세요, 밀키웨이예요! 👋\n\n급식, 날씨, 시간표, 학사일정부터 과학 질문까지 편하게 물어보세요.")

    examples = [
        ("🍚", "오늘 급식 뭐야?"),
        ("🌤️", "내일 날씨 알려줘"),
        ("📚", "3학년 2반 시간표 알려줘"),
        ("🚌", "수학여행 언제야?"),
    ]
    cols = st.columns(2)
    for n, (icon, text) in enumerate(examples):
        with cols[n % 2]:
            if st.button(f"{icon}  {text}", key=f"chip_{n}", use_container_width=True):
                st.session_state.queued_prompt = text
                st.rerun()


st.markdown(f'<div class="mw-time">{st.session_state.started_label}</div>', unsafe_allow_html=True)

welcome_ph = st.empty()  # 첫 메시지를 보내면 비웁니다
if not st.session_state.messages:
    with welcome_ph.container():
        render_welcome()
else:
    render_messages()

# 💡 '자세한 대답' 요청 처리: 새 답변을 새 말풍선으로 이어서 붙입니다.
if st.session_state.pending_detail is not None:
    idx = st.session_state.pending_detail
    st.session_state.pending_detail = None
    fb = st.session_state.messages[idx].get("feedback")
    if fb:
        st.session_state.latest_feedback = None
        typing_ph = show_typing()
        detail_text = stream_reply(typing_ph, stream_detail_answer(fb), time.time(), 0.4)
        add_assistant_message(detail_text)

# 💡 입력창은 항상 열려 있습니다. (평가는 선택 사항)
user_input = st.chat_input("메시지 입력")
if st.session_state.queued_prompt:
    user_input = st.session_state.queued_prompt
    st.session_state.queued_prompt = None

if user_input:
    welcome_ph.empty()  # 환영 말풍선 + 추천 질문 제거
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(user_input)
    st.markdown('<div class="mw-receipt">읽음</div>', unsafe_allow_html=True)

    st.session_state.latest_feedback = None

    if user_input == "종료":
        with st.chat_message("assistant", avatar=BOT_AVATAR):
            st.markdown("챗봇이 종료되었습니다.")
        st.stop()

    typing_ph = show_typing()
    t0 = time.time()

    processed_input = rewrite_question(user_input)
    update_topic(processed_input)

    if len(knowledge_base) == 0:
        full_response = stream_reply(typing_ph, stream_text("지식 베이스가 비어있습니다. DB를 확인해주세요."), t0, 0.6)
    else:
        # [1차: 키워드 AND 매칭]
        matched_idx = keyword_match(processed_input)

        if matched_idx is not None:
            matched_answer = knowledge_base[matched_idx]["answer"]
        else:
            # [2차: 임베딩 유사도 폴백] 1·2등 점수 차이가 작으면 애매한 매칭으로 보고 AI 폴백으로 넘깁니다.
            matches = semantic_search_db(processed_input, top_k=2, threshold=0.65)

            if matches:
                best = matches[0]
                best_score = best.get("similarity", 0.0)
                second_score = matches[1].get("similarity", 0.0) if len(matches) > 1 else 0.0
                margin = best_score - second_score

                if best_score >= 0.65 and margin >= 0.05:
                    matched_answer = best.get("answer")
                else:
                    matched_answer = None
            else:
                matched_answer = None

        if matched_answer is not None and "!edgefunction@" not in matched_answer:
            full_response = stream_reply(typing_ph, stream_text(matched_answer), t0, 0.7)
        else:
            full_response = stream_reply(typing_ph, stream_edge_function(processed_input, current_lat, current_lon), t0)

    add_assistant_message(full_response)

scroll_to_bottom()