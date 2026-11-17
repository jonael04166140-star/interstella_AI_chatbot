import streamlit as st
import streamlit.components.v1 as components
import requests
import spacy
import time
import re
import json
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

st.set_page_config(page_title="산청고 AI 챗봇 밀키웨이", page_icon="🌌", layout="centered")

# ==========================================
# 💡 [디자인] 챗봇 스타일 CSS
# ==========================================
CUSTOM_CSS = """
<style>
/* 기본 Streamlit 장식 숨기기 */
#MainMenu, footer {visibility: hidden;}
header[data-testid="stHeader"] {background: transparent;}
.block-container {max-width: 780px; padding-top: 1.2rem; padding-bottom: 8rem;}

/* 헤더 */
.mw-header {text-align: center; padding: 0.4rem 0 1.1rem;}
.mw-title {
    font-size: 1.9rem; font-weight: 800; letter-spacing: -0.5px;
    background: linear-gradient(90deg, #6366f1, #a855f7, #ec4899);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.mw-sub {opacity: 0.6; font-size: 0.88rem; margin-top: 0.15rem;}

/* 환영 화면 */
.mw-hero {text-align: center; padding: 2.2rem 0 1.2rem;}
.mw-hero .orb {
    width: 76px; height: 76px; margin: 0 auto 1rem; border-radius: 50%;
    background: radial-gradient(circle at 30% 30%, #c4b5fd, #6366f1 55%, #312e81);
    box-shadow: 0 0 40px rgba(139, 92, 246, 0.55);
    display: flex; align-items: center; justify-content: center; font-size: 2.1rem;
}
.mw-hero h3 {margin: 0.2rem 0 0.3rem; font-weight: 700;}
.mw-hero p {opacity: 0.6; margin: 0;}

/* 채팅 메시지 공통 */
[data-testid="stChatMessage"] {background: transparent; border: none; padding: 0.35rem 0;}
[data-testid="stChatMessage"] [data-testid="stChatMessageContent"] {
    border-radius: 18px; padding: 0.7rem 1rem; width: fit-content; max-width: 86%;
}

/* 챗봇(왼쪽) 말풍선 */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stChatMessageContent"] {
    background: rgba(128, 128, 128, 0.10);
    border: 1px solid rgba(128, 128, 128, 0.18);
    border-top-left-radius: 4px;
}

/* 사용자(오른쪽) 말풍선 */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {flex-direction: row-reverse;}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    color: #fff; border-top-right-radius: 4px; margin-left: auto; text-align: left;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] * {color: #fff;}

/* 입력창 */
[data-testid="stChatInput"] {
    border-radius: 26px; border: 1px solid rgba(129, 140, 248, 0.5);
    box-shadow: 0 4px 24px rgba(99, 102, 241, 0.12);
}
[data-testid="stChatInput"] textarea {font-size: 0.98rem;}

/* 답변 아래 작은 평가 아이콘 줄 (좋아요/싫어요/자세한 대답) */
[class*="st-key-fb_"] button {
    background: transparent !important; border: none !important; box-shadow: none !important;
    padding: 0.05rem 0.4rem !important; min-height: 0 !important;
    font-size: 1rem; opacity: 0.5; transition: opacity .15s, background .15s;
}
[class*="st-key-fb_"] button:hover {opacity: 1; background: rgba(128, 128, 128, 0.16) !important; border-radius: 8px;}
.mw-fb-note {font-size: 0.78rem; opacity: 0.55; padding-top: 0.3rem;}

/* 추천 질문 칩 */
[class*="st-key-chip_"] button {
    border-radius: 999px; border: 1px solid rgba(129, 140, 248, 0.45);
    background: rgba(99, 102, 241, 0.07); font-size: 0.9rem; padding: 0.45rem 0.9rem;
}
[class*="st-key-chip_"] button:hover {background: rgba(99, 102, 241, 0.18); border-color: #818cf8;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

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
# 4. UI 구성
# ==========================================
st.markdown(
    """
    <div class="mw-header">
        <div class="mw-title">🌌 밀키웨이</div>
        <div class="mw-sub">산청고등학교 AI 챗봇 · 인터스텔라</div>
    </div>
    """,
    unsafe_allow_html=True,
)


def render_feedback_row(i: int, msg: dict):
    """답변 말풍선 바로 아래에 붙는 작은 아이콘 줄. 입력창은 가리지 않습니다."""
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
                st.session_state.pending_detail = i
                st.rerun()

    if voted:
        with c_note:
            note = "도움이 됐다고 기록했어요" if voted == "up" else "더 나아지도록 반영할게요"
            st.markdown(f'<div class="mw-fb-note">{note}</div>', unsafe_allow_html=True)


def render_messages():
    for i, msg in enumerate(st.session_state.messages):
        avatar = BOT_AVATAR if msg["role"] == "assistant" else USER_AVATAR
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("feedback"):
                render_feedback_row(i, msg)


def render_welcome():
    st.markdown(
        """
        <div class="mw-hero">
            <div class="orb">🌌</div>
            <h3>안녕하세요, 밀키웨이예요!</h3>
            <p>급식, 날씨, 시간표, 학사일정부터 과학 질문까지 물어보세요.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    examples = ["오늘 급식 뭐야?", "내일 날씨 알려줘", "3학년 2반 시간표 알려줘", "수학여행 언제야?"]
    cols = st.columns(2)
    for n, text in enumerate(examples):
        with cols[n % 2]:
            if st.button(text, key=f"chip_{n}", use_container_width=True):
                st.session_state.queued_prompt = text
                st.rerun()


if not st.session_state.messages:
    render_welcome()
else:
    render_messages()

# 💡 '자세한 대답' 요청 처리: 새 답변을 새 말풍선으로 이어서 붙입니다.
if st.session_state.pending_detail is not None:
    idx = st.session_state.pending_detail
    st.session_state.pending_detail = None
    target = st.session_state.messages[idx]
    fb = target.get("feedback")
    if fb:
        target["detail_done"] = True
        st.session_state.latest_feedback = None
        with st.chat_message("assistant", avatar=BOT_AVATAR):
            detail_text = st.write_stream(stream_detail_answer(fb))
        st.session_state.messages.append({
            "role": "assistant",
            "content": detail_text,
            "feedback": st.session_state.latest_feedback,
            "voted": None,
            "detail_done": False,
        })
        st.session_state.latest_feedback = None
        st.rerun()

# 💡 입력창은 항상 열려 있습니다. (평가는 선택 사항)
user_input = st.chat_input("무엇이든 물어보세요...")
if st.session_state.queued_prompt:
    user_input = st.session_state.queued_prompt
    st.session_state.queued_prompt = None

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(user_input)

    st.session_state.latest_feedback = None

    with st.chat_message("assistant", avatar=BOT_AVATAR):
        if user_input == "종료":
            st.markdown("챗봇이 종료되었습니다.")
            st.stop()

        processed_input = rewrite_question(user_input)
        update_topic(processed_input)

        if len(knowledge_base) == 0:
            full_response = st.write_stream(stream_text("지식 베이스가 비어있습니다. DB를 확인해주세요."))
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
                full_response = st.write_stream(stream_text(matched_answer))
            else:
                full_response = st.write_stream(stream_edge_function(processed_input, current_lat, current_lon))

    st.session_state.messages.append({
        "role": "assistant",
        "content": full_response,
        "feedback": st.session_state.latest_feedback,
        "voted": None,
        "detail_done": False,
    })
    st.session_state.latest_feedback = None

    # 💡 다시 그려서 방금 답변 밑에 평가 아이콘 줄이 붙게 합니다.
    st.rerun()

scroll_to_bottom()
