import streamlit as st
import requests
import spacy
import time
import re
import json
from sentence_transformers import SentenceTransformer

# ==========================================
# 1. 환경 설정 및 변수[cite: 6]
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

st.set_page_config(page_title="인터스텔라 AI 챗봇", page_icon="🤖")

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
    # "3학년 2반 시간표" → (답변) → "그럼 화요일은?"처럼 학년/반을 반복 안 물어도 되게 해줍니다.
    st.session_state.last_class = None
if "pending_feedback" not in st.session_state:
    # 💡 [RLHF] 직전 답변이 knowledge_qa 항목(reliability < 9.0)에서 나온 경우,
    # edge function이 돌려준 {"qa_id":..., "delta":..., "enabled": true, "question":..., "raw_answer":...}가
    # 여기 저장됩니다. 값이 있으면 채팅 입력창 대신 "좋아요 / 싫어요 / 자세한 대답" 버튼 3개를 띄웁니다.
    st.session_state.pending_feedback = None

# ==========================================
# 2. 핵심 로직 함수들 (Streamlit 캐싱 적용)[cite: 6]
# ==========================================
@st.cache_resource(show_spinner="AI 엔진을 불러오는 중입니다...")
def load_ai_model():
    model = SentenceTransformer('snunlp/KR-SBERT-V40K-klueNLI-augSTS')
    try:
        nlp = spacy.load("ko_core_news_sm")
    except:
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
    💡 [DB 스케일업] 예전에는 knowledge_qa 전체를 파이썬 메모리로 끌어와
    model.encode(전체문장들) 후 util.cos_sim으로 직접 비교했습니다.
    데이터가 수만 건이 되면 매번 전체를 다시 인코딩/비교해야 해서 느려집니다.

    이제는 '사용자의 질문 하나'만 로컬 모델로 인코딩하고, 실제 유사도 계산은
    Postgres(pgvector)의 match_knowledge_qa RPC 함수에 맡깁니다. DB에 미리
    ivfflat/hnsw 인덱스를 걸어두면, 지식 데이터가 아무리 많아져도 인덱스
    검색이라 속도가 거의 그대로 유지됩니다.

    ⚠️ 주의: 여기서 만드는 쿼리 벡터와 knowledge_qa.embedding 컬럼에 저장된
    벡터는 반드시 '같은 모델(KR-SBERT)'로 만들어져야 코사인 유사도 비교가
    의미가 있습니다. Edge Function 쪽 자기학습 로직도 Gemini가 아닌
    KR-SBERT로 임베딩을 만들도록 맞춰야 합니다 (아래 백필 스크립트 참고).
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
    except:
        return 35.415, 127.873

# ==========================================
# 💡 [자동 캐시 갱신] 두 가지 방식을 함께 적용
#   1) 사이트 접속/새로고침 시: session_state가 초기화되는 것을 감지해서 즉시 캐시를 비웁니다.
#   2) 대화 도중에도: 캐시에 ttl=60(초)을 걸어둬서, 60초가 지나면 다음 메시지를 보낼 때
#      (Streamlit은 메시지를 보낼 때마다 스크립트 전체를 다시 실행하므로) 자동으로
#      Supabase에서 최신 데이터를 다시 불러옵니다. 새로고침 없이도 최신화됩니다.
# ==========================================
# Streamlit은 브라우저를 새로고침하면 웹소켓 연결이 새로 맺어지며 st.session_state가
# 완전히 초기화됩니다. 반면 챗봇에 메시지를 입력해서 발생하는 rerun은 같은 세션이
# 유지되어 session_state가 그대로 남습니다.
# 즉 "app_initialized가 아직 없는 시점 = 사이트 접속/새로고침 시점"이므로,
# 이 시점에만 캐시를 즉시 지워서 Supabase의 최신 데이터를 다시 불러오게 합니다.
if "app_initialized" not in st.session_state:
    load_database_st.clear()
    st.session_state.app_initialized = True

model, nlp = load_ai_model()
knowledge_base, combined_sentences, TOPIC_KEYWORDS = load_database_st()
current_lat, current_lon = get_current_location()

if "embeddings_synced" not in st.session_state:
    # 💡 embedding이 비어있는 새 데이터가 있으면 자동으로 채워둡니다 (수동 스크립트 실행 불필요)
    sync_missing_embeddings(model)
    st.session_state.embeddings_synced = True

def rewrite_question(user_input):
    if nlp is None: return user_input
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
    💡 [신규] 질문에서 조사/어미/동사 등을 제외한 '내용어(명사류)'만 추출합니다.
    조건(conditions)이 질문 토큰에 다 포함되는지만 보면, "산청고"라는 키워드 하나만
    있는 일반 항목이 "산청고 학생회장이 누구야?" 같은 질문에도 그냥 매칭돼버립니다.
    질문 안에 '학생회장'처럼 그 키워드 그룹이 다루지 않는 핵심 명사가 남아있는지를
    판단하기 위해, 명사(NOUN)/고유명사(PROPN)만 따로 뽑아둡니다.
    """
    if nlp is None:
        return set(user_input.split())
    return {tok.text for tok in nlp(user_input) if tok.pos_ in ("NOUN", "PROPN") and len(tok.text) > 1}


def keyword_match(user_input, coverage_threshold=0.6):
    """
    💡 [1차 검색 - 키워드 AND 조건 매칭 + 명사 커버리지 검사]
    edge function의 `conditions.every(cond => intentMessage.includes(cond))` 로직을
    파이썬 쪽에도 적용하되, 부분 문자열이 아니라 '완전한 단어' 단위로 비교합니다.

    knowledge_base 행의 keywords 컬럼에 "인터스텔라+가입,인터스텔라+지원" 처럼
    '+'로 AND 조건을, ','로 OR(여러 조합)을 표현해두면,
    "인터스텔라에 들어가려면 어떻게 해야해?" 라는 질문은 조건 2개짜리(인터스텔라+가입류)에
    먼저 걸리고, "인터스텔라가 뭐야?"처럼 단일 키워드(인터스텔라)만 있는 일반 정의 항목보다
    우선순위를 갖게 됩니다.

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

            # 조건이 명사를 전부 커버하면 무조건 통과, 아니면 임계값 이상일 때만 통과
            if coverage_score >= coverage_threshold:
                candidates.append((idx, len(conditions), coverage_score))

    if not candidates:
        return None

    # 조건 개수가 많을수록(=더 구체적인 질문일수록) 우선, 그 다음 커버리지 점수 우선
    candidates.sort(key=lambda x: (-x[1], -x[2]))
    return candidates[0][0]

# ==========================================
# 3. 출력 제너레이터 (스트리밍 타이핑 효과)[cite: 6]
# ==========================================
def stream_text(text):
    for char in text:
        yield char
        time.sleep(0.03)

def stream_edge_function(original_input, lat, lon):
    edge_url = f"{SUPABASE_URL}/functions/v1/functional_answer"
    data = {
        "user_message": original_input, 
        "lat": lat, 
        "lon": lon,
        "last_suggestion": st.session_state.last_suggestion,
        "last_intent": st.session_state.last_intent,  # 💡 직전 턴의 의도(rice/weather/dayofweek/subjects 등)를 함께 전송
        "last_class": st.session_state.last_class      # 💡 시간표 조회 시 사용한 학년/반 맥락도 함께 전송
    }
    
    try:
        response = requests.post(edge_url, json=data, headers=headers, stream=True)
        if response.status_code == 200:
            for line in response.iter_lines():
                if line:
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

                            # 💡 [RLHF] 이번 답변이 좋아요/싫어요/자세한 대답 버튼 대상이면
                            # (reliability < 9.0인 knowledge_qa 항목에서 나온 답변) 저장해두고,
                            # 다음 렌더링에서 chat_input 대신 버튼 3개를 띄웁니다.
                            feedback = context.get("feedback")
                            st.session_state.pending_feedback = feedback if feedback and feedback.get("enabled") else None
                        
                        # 💡 엣지 펑션의 최종 응답을 한 글자씩 쪼개서 타이핑 효과 부여
                        reply_text = res_json.get('reply', '')
                        for char in reply_text:
                            yield char
                            time.sleep(0.03)
        else:
            # 💡 에러 메시지에도 타이핑 효과 부여
            error_msg = f"엣지 펑션 연결 실패. (HTTP {response.status_code})"
            for char in error_msg:
                yield char
                time.sleep(0.03)
    except Exception as e:
        error_msg = f"서버 통신 오류: {e}"
        for char in error_msg:
            yield char
            time.sleep(0.03)

# ==========================================
# 💡 [RLHF] "자세한 대답" 버튼 클릭 시 LLM(Gemini) 답변 스트리밍
# ==========================================
def stream_detail_answer(fb: dict):
    """
    fb: st.session_state.pending_feedback (qa_id, question, raw_answer 포함).
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
            for line in response.iter_lines():
                if line:
                    res_json = json.loads(line.decode('utf-8'))
                    if 'reply' in res_json:
                        context = res_json.get("context")
                        if context is not None:
                            st.session_state.last_intent = context.get("last_intent")
                            st.session_state.last_class = context.get("last_class")
                            feedback = context.get("feedback")
                            st.session_state.pending_feedback = feedback if feedback and feedback.get("enabled") else None

                        reply_text = res_json.get('reply', '')
                        for char in reply_text:
                            yield char
                            time.sleep(0.03)
        else:
            error_msg = f"엣지 펑션 연결 실패. (HTTP {response.status_code})"
            for char in error_msg:
                yield char
                time.sleep(0.03)
    except Exception as e:
        error_msg = f"서버 통신 오류: {e}"
        for char in error_msg:
            yield char
            time.sleep(0.03)

# ==========================================
# 💡 [RLHF] 좋아요/싫어요 피드백 전송
# ==========================================
def send_feedback(vote: str):
    """
    vote: "up" 또는 "down".
    edge function에 action="feedback"으로 요청을 보내면, 서버가 해당
    knowledge_qa 행의 reliability를 등급별 delta(0.2 / 0.5)만큼 조정합니다.
    (reliability >= 9.0인 항목은 애초에 pending_feedback이 설정되지 않으므로 여기까지 오지 않음)
    """
    fb = st.session_state.pending_feedback
    if not fb:
        return
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
    st.session_state.pending_feedback = None

# ==========================================
# 4. Streamlit UI 구성[cite: 6]
# ==========================================
st.title("인터스텔라 AI 챗봇")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 💡 [RLHF] 직전 답변에 피드백이 걸려있으면, 채팅 입력칸을 잠시 가리고
# 그 자리에 "좋아요 / 싫어요 / 자세한 대답" 버튼 3개를 띄웁니다.
# 좋아요/싫어요는 reliability만 조정하고, 자세한 대답은 그때 처음 LLM(Gemini)을 호출합니다.
if st.session_state.pending_feedback:
    st.markdown("**방금 답변, 도움이 되었나요?**")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("👍 좋아요", use_container_width=True, key="feedback_up_btn"):
            send_feedback("up")
            st.rerun()
    with col2:
        if st.button("👎 싫어요", use_container_width=True, key="feedback_down_btn"):
            send_feedback("down")
            st.rerun()
    with col3:
        if st.button("🔍 자세한 대답", use_container_width=True, key="feedback_detail_btn"):
            fb = st.session_state.pending_feedback
            with st.chat_message("assistant"):
                full_response = st.write_stream(stream_detail_answer(fb))
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            st.rerun()
    user_input = None
else:
    user_input = st.chat_input("메시지를 입력하세요...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)
        
    with st.chat_message("assistant"):
        if user_input == "종료":
            st.markdown("챗봇이 종료되었습니다.")
            st.stop()
            
        processed_input = rewrite_question(user_input)
        update_topic(processed_input)
        
        # 지식 베이스 검사
        if len(knowledge_base) == 0:
            # 💡 기존 st.markdown을 st.write_stream으로 교체하여 타이핑 효과 적용
            full_response = st.write_stream(stream_text("지식 베이스가 비어있습니다. DB를 확인해주세요."))
        else:
            # 💡 [1차: 키워드 AND 매칭] 정의성 질문("~가 뭐야")과 절차성 질문("~하려면 어떻게")처럼
            # 핵심 개체명은 같지만 의도가 다른 질문을 구분하기 위해 키워드 매칭을 먼저 시도합니다.
            matched_idx = keyword_match(processed_input)

            if matched_idx is not None:
                best_match_index = matched_idx
                matched_answer = knowledge_base[best_match_index]["answer"]
            else:
                # 💡 [2차: 임베딩 유사도 폴백 - DB 스케일업 버전]
                # 예전: model.encode(전체 DB) 후 파이썬에서 cos_sim 직접 계산 (DB가 커지면 느려짐)
                # 지금: 쿼리 하나만 인코딩하고, 실제 유사도 검색은 pgvector RPC(match_knowledge_qa)가
                #       DB 인덱스로 처리 → 지식 데이터가 수만 건이어도 속도 거의 그대로 유지.
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
                
        st.session_state.messages.append({"role": "assistant", "content": full_response})

    # 💡 답변 출력 직후 즉시 재실행하여, pending_feedback이 설정된 경우
    # 사용자가 다음 메시지를 입력할 때까지 기다리지 않고 바로 피드백 버튼을 띄웁니다.
    st.rerun()