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

# 💡 [자동 백필용] service_role 키는 코드에 직접 넣지 않고 Streamlit secrets에서 읽습니다.
# 로컬: .streamlit/secrets.toml에 SUPABASE_SERVICE_ROLE_KEY = "..." 추가
# 배포(Streamlit Cloud): 앱 설정 > Secrets에 동일하게 등록
SERVICE_ROLE_KEY = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "")
service_headers = {
    "apikey": SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}

st.set_page_config(page_title=" 산청고 AI 챗봇 밀키웨이", page_icon="🤖")

# messages 항목: {"role", "content", "feedback"(dict|None), "voted"(None|"up"|"down"), "detail_done"(bool)}
#   💡 [RLHF 변경] 평가 정보(feedback)는 이제 '답변 메시지마다' 따로 저장됩니다.
#   그래서 예전 답변에도 평가 줄이 그대로 남아 있고, 입력창은 절대 가려지지 않습니다.
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_topic" not in st.session_state:
    st.session_state.last_topic = None
if "last_suggestion" not in st.session_state:
    st.session_state.last_suggestion = None
if "last_intent" not in st.session_state:
    # 💡 [맥락 세션] 급식/날씨/요일처럼 "함수형 의도"를 이어가기 위한 상태.
    # last_topic(임베딩 기반 주제 추적)과는 별개로, edge function이 실행한
    # 구체적인 기능(rice/weather/dayofweek/subjects)을 기억해서 "그럼 모레는?" 같은
    # 후속 질문에 같은 기능을 재사용할 수 있게 해줍니다.
    st.session_state.last_intent = None
if "last_class" not in st.session_state:
    # 💡 [맥락 세션] 시간표(subjects) 조회 시 사용한 학년/반을 기억합니다.
    # 예: {"grade": "3", "classNm": "2"}
    st.session_state.last_class = None
if "latest_feedback" not in st.session_state:
    # 💡 [RLHF] 스트리밍 중 edge function이 돌려준 평가 정보
    # ({"qa_id":..., "delta":..., "enabled": true, "question":..., "raw_answer":...}).
    # 답변 출력이 끝나면 그 답변 메시지에 붙이고 None으로 비웁니다.
    st.session_state.latest_feedback = None
if "pending_detail" not in st.session_state:
    # 💡 '자세한 대답' 버튼을 누른 메시지의 인덱스. 다음 렌더링에서 처리합니다.
    st.session_state.pending_detail = None


# ==========================================
# 💡 [자동 스크롤] rerun 시 최상단으로 튀는 문제 방지
# 스크립트가 그려질 때마다(특히 rerun 직후) 맨 아래로 스크롤을 강제 이동시킵니다.
# ==========================================
def scroll_to_bottom():
    # 버전별로 달라질 수 있는 셀렉터 후보를 여러 개 시도하고,
    # 버튼/텍스트가 아주 살짝 늦게 그려지는 경우까지 잡기 위해 여러 번 재시도합니다.
    # (최신 Streamlit은 <main data-testid="stMain"> 이라 태그를 가리지 않는 셀렉터를 먼저 시도)
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
                if (el) {
                    el.scrollTop = el.scrollHeight;
                }
            }

            [0, 50, 150, 300, 600].forEach(function(delay) {
                setTimeout(scrollToBottom, delay);
            });
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


def sync_missing_embeddings(model):
    """
    💡 [비활성화] 임베딩 백필 기능을 완전히 껐습니다.
    knowledge_qa.embedding은 이제 항상 null로 유지되며, Edge Function은
    1단계 키워드 매칭만으로 동작합니다.
    """
    return


def semantic_search_db(query_text, top_k=2, threshold=0.65):
    """
    💡 [DB 스케일업] '사용자의 질문 하나'만 로컬 모델로 인코딩하고, 실제 유사도 계산은
    Postgres(pgvector)의 match_knowledge_qa RPC 함수에 맡깁니다.

    ⚠️ 주의: 여기서 만드는 쿼리 벡터와 knowledge_qa.embedding 컬럼에 저장된
    벡터는 반드시 '같은 모델(KR-SBERT)'로 만들어져야 코사인 유사도 비교가
    의미가 있습니다.
    """
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


# ==========================================
# 💡 [자동 캐시 갱신]
#   1) 사이트 접속/새로고침 시: session_state가 초기화되는 것을 감지해서 즉시 캐시를 비웁니다.
#   2) 대화 도중에도: 캐시에 ttl=60(초)을 걸어둬서, 60초가 지나면 다음 메시지를 보낼 때
#      자동으로 Supabase에서 최신 데이터를 다시 불러옵니다.
# ==========================================
if "app_initialized" not in st.session_state:
    load_database_st.clear()
    st.session_state.app_initialized = True

model, nlp = load_ai_model()
knowledge_base, combined_sentences, TOPIC_KEYWORDS = load_database_st()
current_lat, current_lon = get_current_location()

if "embeddings_synced" not in st.session_state:
    # 💡 embedding이 비어있는 새 데이터가 있으면 자동으로 채워둡니다 (현재는 비활성화됨)
    sync_missing_embeddings(model)
    st.session_state.embeddings_synced = True


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
    """
    💡 사용자 입력을 '완전한 단어(토큰)' 단위 후보 집합으로 변환합니다.
    """
    if nlp is None:
        # spaCy 모델이 없으면 최소한의 안전장치로 공백 기준 분리만 사용
        return set(user_input.split())

    tokens = [tok.text for tok in nlp(user_input) if tok.text.strip()]
    candidates = set(tokens)
    # "2" + "학년" 처럼 숫자와 명사가 분리되는 경우를 대비해 인접 토큰 2개를 붙인 것도 후보에 포함
    candidates.update(a + b for a, b in zip(tokens, tokens[1:]))
    return candidates


def get_content_tokens(user_input):
    """
    💡 질문에서 조사/어미/동사 등을 제외한 '내용어(명사류)'만 추출합니다.
    질문 안에 '학생회장'처럼 그 키워드 그룹이 다루지 않는 핵심 명사가 남아있는지를
    판단하기 위해, 명사(NOUN)/고유명사(PROPN)만 따로 뽑아둡니다.
    """
    if nlp is None:
        return set(user_input.split())
    return {tok.text for tok in nlp(user_input) if tok.pos_ in ("NOUN", "PROPN") and len(tok.text) > 1}


def keyword_match(user_input, coverage_threshold=0.6):
    """
    💡 [1차 검색 - 키워드 AND 조건 매칭 + 명사 커버리지 검사]
    knowledge_base 행의 keywords 컬럼에 "인터스텔라+가입,인터스텔라+지원" 처럼
    '+'로 AND 조건을, ','로 OR(여러 조합)을 표현해두면, 조건이 많은(=더 구체적인) 항목이
    단일 키워드 일반 항목보다 우선순위를 갖습니다.

    💡 [커버리지 검사 - 문맥 오매칭 방지] 조건이 다 포함돼도, 질문 속 핵심 명사 중
    이 키워드 그룹이 전혀 다루지 않는 명사가 많이 남아있다면(coverage_score가 낮다면)
    "의도가 다른 질문"일 가능성이 높다고 보고 매칭을 기각합니다.
    예: "산청고 학생회장이 누구야?" → 명사={산청고, 학생회장}, 키워드그룹=[산청고]
        → 커버리지 1/2=0.5 < 0.6 → 기각 → 임베딩/AI 폴백으로 넘어감
    """
    word_candidates = get_word_candidates(user_input)
    content_tokens = get_content_tokens(user_input)
    candidates = []  # (knowledge_base 인덱스, 조건 개수, 커버리지 점수)

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
                coverage_score = 1.0  # 명사 추출이 안 되면(예: nlp 없음) 기존 방식대로 통과

            if coverage_score >= coverage_threshold:
                candidates.append((idx, len(conditions), coverage_score))

    if not candidates:
        return None

    # 조건 개수가 많을수록(=더 구체적인 질문일수록) 우선, 그 다음 커버리지 점수 우선
    candidates.sort(key=lambda x: (-x[1], -x[2]))
    return candidates[0][0]


# ==========================================
# 3. 출력 제너레이터 (스트리밍 타이핑 효과)
# ==========================================
def stream_text(text):
    for char in text:
        yield char
        time.sleep(0.03)


def _stream_error(msg):
    for char in msg:
        yield char
        time.sleep(0.03)


def _consume_edge_stream(response):
    """엣지 펑션 NDJSON 응답을 글자 단위로 yield. 평가 정보는 latest_feedback에 저장합니다."""
    for line in response.iter_lines():
        if not line:
            continue
        res_json = json.loads(line.decode('utf-8'))

        if 'loading_msg' in res_json:
            # 로딩 메시지는 빠르게 한 번에 띄웁니다.
            yield f"_{res_json['loading_msg']}_\n\n"
        elif 'reply' in res_json:
            st.session_state.last_suggestion = res_json.get("suggestion")

            # 💡 서버가 이번 응답에서 어떤 의도/학년반을 사용했는지 알려주면 세션에 저장.
            # 다음 턴에 이 값을 다시 보내서 "그럼 모레는?" 같은 후속 질문에 이어붙입니다.
            context = res_json.get("context")
            if context is not None:
                st.session_state.last_intent = context.get("last_intent")
                st.session_state.last_class = context.get("last_class")

                # 💡 [RLHF] 이번 답변이 평가 대상이면(reliability < 9.0인 knowledge_qa 항목)
                # 일단 임시 보관해두고, 답변이 끝나면 그 메시지 바로 아래에 평가 줄을 붙입니다.
                feedback = context.get("feedback")
                st.session_state.latest_feedback = feedback if feedback and feedback.get("enabled") else None

            # 💡 엣지 펑션의 최종 응답을 한 글자씩 쪼개서 타이핑 효과 부여
            for char in res_json.get('reply', ''):
                yield char
                time.sleep(0.03)


def stream_edge_function(original_input, lat, lon):
    edge_url = f"{SUPABASE_URL}/functions/v1/functional_answer"
    data = {
        "user_message": original_input,
        "lat": lat,
        "lon": lon,
        "last_suggestion": st.session_state.last_suggestion,
        "last_intent": st.session_state.last_intent,  # 💡 직전 턴의 의도(rice/weather/dayofweek/subjects 등)
        "last_class": st.session_state.last_class      # 💡 시간표 조회 시 사용한 학년/반 맥락
    }

    try:
        response = requests.post(edge_url, json=data, headers=headers, stream=True)
        if response.status_code == 200:
            yield from _consume_edge_stream(response)
        else:
            yield from _stream_error(f"엣지 펑션 연결 실패. (HTTP {response.status_code})")
    except Exception as e:
        yield from _stream_error(f"서버 통신 오류: {e}")


# ==========================================
# 💡 [RLHF] "자세한 대답" 버튼 클릭 시 LLM(Gemini) 답변 스트리밍
# ==========================================
def stream_detail_answer(fb: dict):
    """
    fb: 해당 답변 메시지에 저장된 평가 정보 (qa_id, question, raw_answer 포함).
    edge function에 action="detail"로 요청하면, 그때 처음 Gemini를 호출해서
    DB 원본 답변(raw_answer)을 참고자료 삼아 새 답을 생성해 돌려줍니다.
    """
    edge_url = f"{SUPABASE_URL}/functions/v1/functional_answer"
    data = {
        "action": "detail",
        "qa_id": fb.get("qa_id"),
        "question": fb.get("question"),
        "raw_answer": fb.get("raw_answer"),
        "last_intent": st.session_state.last_intent,
        "last_class": st.session_state.last_class,
    }
    try:
        response = requests.post(edge_url, json=data, headers=headers, stream=True)
        if response.status_code == 200:
            yield from _consume_edge_stream(response)
        else:
            yield from _stream_error(f"엣지 펑션 연결 실패. (HTTP {response.status_code})")
    except Exception as e:
        yield from _stream_error(f"서버 통신 오류: {e}")


# ==========================================
# 💡 [RLHF] 좋아요/싫어요 피드백 전송
# ==========================================
def send_feedback(fb: dict, vote: str):
    """
    vote: "up" 또는 "down".
    edge function에 action="feedback"으로 요청을 보내면, 서버가 해당
    knowledge_qa 행의 reliability를 등급별 delta(0.2 / 0.5)만큼 조정합니다.
    """
    edge_url = f"{SUPABASE_URL}/functions/v1/functional_answer"
    try:
        requests.post(
            edge_url,
            json={"action": "feedback", "qa_id": fb.get("qa_id"), "vote": vote},
            headers=headers,
            timeout=10,
        )
    except Exception as e:
        st.error(f"피드백 전송 실패: {e}")


# ==========================================
# 4. Streamlit UI 구성
# ==========================================
# 평가 줄이 좁은 화면(모바일)에서도 세로로 쌓이지 않고 한 줄로 유지되도록 하는 최소한의 CSS
st.markdown(
    """
    <style>
    [data-testid="stHorizontalBlock"]:has([class*="st-key-fb_"]) {
        flex-wrap: nowrap !important; gap: 0.1rem !important; align-items: center;
    }
    [data-testid="stHorizontalBlock"]:has([class*="st-key-fb_"]) > [data-testid="stColumn"] {
        flex: 0 0 auto !important; width: auto !important; min-width: 0 !important;
    }
    [class*="st-key-fb_"] button {
        background: transparent !important; border: none !important; box-shadow: none !important;
        padding: 0.05rem 0.45rem !important; min-height: 0 !important; opacity: 0.6;
        transition: opacity 0.15s, transform 0.15s;
    }
    [class*="st-key-fb_"] button:hover {opacity: 1; transform: scale(1.15);}
    .fb-note {font-size: 0.8rem; opacity: 0.65; white-space: nowrap;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("AI 챗봇 밀키웨이")


def render_feedback_row(i: int, msg: dict):
    """
    💡 [RLHF] 답변 말풍선 바로 아래에 붙는 작은 평가 줄. 입력창은 가리지 않습니다.
    - 👍/👎: 한 번 누르면 사라지고 안내 문구로 바뀝니다.
    - 🔍: 자세한 대답을 새 말풍선으로 이어 붙입니다 (한 번만).
    """
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
            st.markdown(f'<div class="fb-note">{note}</div>', unsafe_allow_html=True)


def add_assistant_message(text):
    """답변을 대화 기록에 저장하고, 평가 대상이면 바로 아래에 평가 줄을 붙입니다."""
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


# 지난 대화 다시 그리기 (평가 대상 답변 아래에는 평가 줄을 함께)
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
    if msg["role"] == "assistant" and msg.get("feedback"):
        render_feedback_row(i, msg)

# 💡 '자세한 대답' 요청 처리: 새 답변을 새 말풍선으로 이어서 붙입니다.
if st.session_state.pending_detail is not None:
    idx = st.session_state.pending_detail
    st.session_state.pending_detail = None
    fb = st.session_state.messages[idx].get("feedback")
    if fb:
        st.session_state.latest_feedback = None
        with st.chat_message("assistant"):
            detail_text = st.write_stream(stream_detail_answer(fb))
        add_assistant_message(detail_text)

# 💡 입력창은 항상 열려 있습니다. (평가는 선택 사항이며 입력을 막지 않습니다)
user_input = st.chat_input("메시지를 입력하세요...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    st.session_state.latest_feedback = None  # 이전 질문의 평가 정보가 섞이지 않도록 초기화

    with st.chat_message("assistant"):
        if user_input == "종료":
            st.markdown("챗봇이 종료되었습니다.")
            st.stop()

        processed_input = rewrite_question(user_input)
        update_topic(processed_input)

        # 지식 베이스 검사
        if len(knowledge_base) == 0:
            full_response = st.write_stream(stream_text("지식 베이스가 비어있습니다. DB를 확인해주세요."))
        else:
            # 💡 [1차: 키워드 AND 매칭] 정의성 질문("~가 뭐야")과 절차성 질문("~하려면 어떻게")처럼
            # 핵심 개체명은 같지만 의도가 다른 질문을 구분하기 위해 키워드 매칭을 먼저 시도합니다.
            matched_idx = keyword_match(processed_input)

            if matched_idx is not None:
                best_match_index = matched_idx
                matched_answer = knowledge_base[best_match_index]["answer"]
            else:
                # 💡 [2차: 임베딩 유사도 폴백 - pgvector RPC]
                # 1등과 2등의 점수 차이(margin)가 너무 작으면 "애매한 매칭"으로 보고
                # edge function(AI 폴백)으로 넘겨 오답 확정을 피합니다.
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

            if matched_answer is not None:
                if "!edgefunction@" in matched_answer:
                    full_response = st.write_stream(stream_edge_function(processed_input, current_lat, current_lon))
                else:
                    full_response = st.write_stream(stream_text(matched_answer))
            else:
                full_response = st.write_stream(stream_edge_function(processed_input, current_lat, current_lon))

    # 💡 답변이 끝나면 대화 기록에 저장하고, 평가 대상이면 말풍선 바로 아래에 평가 줄을 붙입니다.
    # (예전처럼 st.rerun()으로 입력창을 바꿔치기하지 않으므로 바로 다음 질문을 입력할 수 있습니다.)
    add_assistant_message(full_response)

# ==========================================
# 💡 [자동 스크롤] 스크립트가 끝나는 마지막 지점에서 항상 실행됩니다.
# ==========================================
scroll_to_bottom()
