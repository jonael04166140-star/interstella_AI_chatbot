import streamlit as st
import requests
import spacy
import time
import re
import json
import numpy as np
from sentence_transformers import SentenceTransformer, util

# ==========================================
# 1. 환경 설정 및 변수[cite: 6]
# ==========================================
SUPABASE_URL = "https://hxpbryalkbdbusrepsne.supabase.co"  
ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh4cGJyeWFsa2JkYnVzcmVwc25lIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODMyNzU2MDgsImV4cCI6MjA5ODg1MTYwOH0.vwL_b5eB9PjmXGKnOghV5ahR4Gmcjzr7Jjc9R_of9Jg"                          
headers = {"apikey": ANON_KEY, "Authorization": f"Bearer {ANON_KEY}", "Content-Type": "application/json"}

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
    # 구체적인 기능(rice/weather/dayofweek)을 기억해서 "그럼 모레는?" 같은
    # 후속 질문에 같은 기능을 재사용할 수 있게 해줍니다.
    st.session_state.last_intent = None

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

@st.cache_data(ttl=60, show_spinner="지식 데이터를 AI 벡터 공간에 맵핑 중...")
def get_db_vectors(sentences):
    if sentences:
        return model.encode(sentences)
    return None

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
    get_db_vectors.clear()
    st.session_state.app_initialized = True

model, nlp = load_ai_model()
knowledge_base, combined_sentences, TOPIC_KEYWORDS = load_database_st()
db_vectors = get_db_vectors(combined_sentences)
current_lat, current_lon = get_current_location()

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
        "last_intent": st.session_state.last_intent  # 💡 직전 턴의 의도(rice/weather/dayofweek 등)를 함께 전송
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

                        # 💡 서버가 이번 응답에서 어떤 의도를 사용했는지 알려주면 세션에 저장.
                        # 다음 턴에 이 값을 다시 보내서 "그럼 모레는?" 같은 후속 질문에 이어붙입니다.
                        context = res_json.get("context")
                        if context is not None:
                            st.session_state.last_intent = context.get("last_intent")
                        
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
# 4. Streamlit UI 구성[cite: 6]
# ==========================================
st.title("인터스텔라 AI 챗봇")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if user_input := st.chat_input("메시지를 입력하세요..."):
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
        if db_vectors is None or len(knowledge_base) == 0:
            # 💡 기존 st.markdown을 st.write_stream으로 교체하여 타이핑 효과 적용
            full_response = st.write_stream(stream_text("지식 베이스가 비어있습니다. DB를 확인해주세요."))
        else:
            user_vector = model.encode(processed_input)
            cosine_scores = util.cos_sim(user_vector, db_vectors)[0]
            
            best_match_index = np.argmax(cosine_scores)
            best_score = cosine_scores[best_match_index].item()
            
            if best_score >= 0.60:
                matched_answer = knowledge_base[best_match_index]["answer"]
                
                if "!edgefunction@" in matched_answer:
                    full_response = st.write_stream(stream_edge_function(processed_input, current_lat, current_lon))
                else:
                    full_response = st.write_stream(stream_text(matched_answer))
            else:
                full_response = st.write_stream(stream_edge_function(processed_input, current_lat, current_lon))
                
        st.session_state.messages.append({"role": "assistant", "content": full_response})