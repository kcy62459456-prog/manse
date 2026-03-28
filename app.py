import math
import datetime as dt
from zoneinfo import ZoneInfo
import requests
import streamlit as st
from timezonefinder import TimezoneFinder
import swisseph as swe
import pandas as pd
import os
import json

import firebase_admin
from firebase_admin import credentials, firestore
from streamlit_oauth import OAuth2Component

# =============================================================================
# [MODULE 1] 파이어베이스 및 구글 OAuth 설정 (🔥 클라우드 배포용)
# =============================================================================
if not firebase_admin._apps:
    key_dict = json.loads(st.secrets["FIREBASE_KEY"])
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred)

db_client = firestore.client()

CLIENT_ID = st.secrets["OAUTH_CLIENT_ID"]
CLIENT_SECRET = st.secrets["OAUTH_CLIENT_SECRET"]
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# 🔥 진짜 라이브 본점 주소!
REDIRECT_URI = "https://mansecalendar.streamlit.app/" 

oauth2 = OAuth2Component(CLIENT_ID, CLIENT_SECRET, AUTHORIZE_URL, TOKEN_URL, TOKEN_URL, REVOKE_URL)

# =============================================================================
# [MODULE 2] 상수 및 설정 (CONSTANTS)
# =============================================================================
STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
STEM_ELEMENTS = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]  
BRANCH_ELEMENTS = [4, 2, 0, 0, 2, 1, 1, 2, 3, 3, 2, 4]

JIJANGGAN = {
    "子": ["壬", "癸"], "丑": ["癸", "辛", "己"],
    "寅": ["戊", "丙", "甲"], "卯": ["甲", "乙"],
    "辰": ["乙", "癸", "戊"], "巳": ["戊", "庚", "丙"],
    "午": ["丙", "己", "丁"], "未": ["丁", "乙", "己"],
    "申": ["戊", "壬", "庚"], "酉": ["庚", "辛"],
    "戌": ["辛", "丁", "戊"], "亥": ["戊", "甲", "壬"]
}

SIPSIN_NAMES = {
    0: ["비견", "겁재"], 1: ["식신", "상관"],
    2: ["편재", "정재"], 3: ["편관", "정관"], 4: ["편인", "정인"]
}

UNSEONG_ORDER = ["절", "태", "양", "장생", "목욕", "관대", "건록", "제왕", "쇠", "병", "사", "묘"]

MAJOR_TERMS = [
    ("입춘", 315.0, "寅"), ("경칩", 345.0, "卯"), ("청명", 15.0,  "辰"),
    ("입하", 45.0,  "巳"), ("망종", 75.0,  "午"), ("소서", 105.0, "未"),
    ("입추", 135.0, "申"), ("백로", 165.0, "酉"), ("한로", 195.0, "戌"),
    ("입동", 225.0, "亥"), ("대설", 255.0, "子"), ("소한", 285.0, "丑"),
]

Y_STEM_TO_YIN_MONTH_STEM = {"甲": "丙", "己": "丙", "乙": "戊", "庚": "戊", "丙": "庚", "辛": "庚", "丁": "壬", "壬": "壬", "戊": "甲", "癸": "甲"}
D_STEM_TO_ZI_HOUR_STEM = {"甲": "甲", "己": "甲", "乙": "丙", "庚": "丙", "丙": "戊", "辛": "戊", "丁": "庚", "壬": "庚", "戊": "壬", "癸": "壬"}

FALLBACK_CITIES = {
    "cincinnati": (39.1031, -84.5120), "seoul": (37.5665, 126.9780),
    "busan": (35.1796, 129.0756), "gwangju": (35.1595, 126.8526),
}
TF = TimezoneFinder()

# =============================================================================
# [MODULE 3] 데이터베이스 처리 (DATABASE - 프라이빗 연동!)
# =============================================================================
def load_db(user_email):
    try:
        docs = db_client.collection('saju_records').where('user_email', '==', user_email).stream()
        records = [doc.to_dict() for doc in docs]
        df = pd.DataFrame(records)
        if df.empty:
            return pd.DataFrame(columns=["이름", "성별", "생년월일", "생시", "시각 기준", "도시", "위도", "경도"])
        return df
    except Exception as e:
        st.error(f"DB 오류: {e}")
        return pd.DataFrame(columns=["이름", "성별", "생년월일", "생시", "시각기준", "도시", "위도", "경도"])

def save_record(data_dict, user_email):
    data_dict["생년월일"] = str(data_dict["생년월일"])
    data_dict["user_email"] = user_email
    doc_id = f"{user_email}_{data_dict['이름']}"
    db_client.collection('saju_records').document(doc_id).set(data_dict)

def delete_record(name, user_email):
    doc_id = f"{user_email}_{name}"
    db_client.collection('saju_records').document(doc_id).delete()

@st.cache_data(ttl=3600)
def geocode_osm_cached(place):
    clean_place = place.lower().strip()
    if clean_place in FALLBACK_CITIES: return FALLBACK_CITIES[clean_place]
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "ManseryeokApp/11.0"}
    try:
        r = requests.get(url, params={"q": place, "format": "json", "limit": 1}, headers=headers, timeout=5)
        if r.ok and r.json(): return float(r.json()[0]['lat']), float(r.json()[0]['lon'])
    except: pass
    return None, None

def parse_hms(s: str) -> dt.time:
    s = (s or "").strip()
    parts = s.split(":")
    try:
        if len(parts) >= 2: return dt.time(int(parts[0]), int(parts[1]))
    except: pass
    return dt.time(12, 0)

# =============================================================================
# [MODULE 4] 사주 핵심 로직 (CORE LOGIC)
# =============================================================================
def get_element_idx(char: str) -> int:
    if char in STEMS: return STEM_ELEMENTS[STEMS.index(char)]
    if char in BRANCHES: return BRANCH_ELEMENTS[BRANCHES.index(char)]
    return 0

def get_polarity(char: str) -> int:
    if char in STEMS: return STEMS.index(char) % 2
    if char in BRANCHES: return BRANCHES.index(char) % 2
    return 0

def get_sipsin(day_stem: str, target: str) -> str:
    d_elem = get_element_idx(day_stem)
    t_elem = get_element_idx(target)
    relation = (t_elem - d_elem) % 5
    d_pol = get_polarity(day_stem)
    t_pol = get_polarity(target)
    if target == "子": t_pol = 0
    elif target in ["亥", "午"]: t_pol = 1
    elif target == "巳": t_pol = 0
    is_diff = 1 if d_pol != t_pol else 0
    return SIPSIN_NAMES[relation][is_diff]

def get_12unseong(stem: str, branch: str) -> str:
    start_map = {"甲": ("亥", 1), "丙": ("寅", 1), "戊": ("寅", 1), "庚": ("巳", 1), "壬": ("申", 1),
                 "乙": ("午", -1), "丁": ("酉", -1), "己": ("酉", -1), "辛": ("子", -1), "癸": ("卯", -1)}
    start_branch, direction = start_map[stem]
    start_idx, target_idx = BRANCHES.index(start_branch), BRANCHES.index(branch)
    diff = (target_idx - start_idx) % 12 if direction == 1 else (start_idx - target_idx) % 12
    return UNSEONG_ORDER[(3 + diff) % 12]

def calculate_voids(stem, branch):
    diff = (BRANCHES.index(branch) - STEMS.index(stem)) % 12
    void_map = {0: ["戌", "亥"], 10: ["申", "酉"], 8: ["午", "未"], 6: ["辰", "巳"], 4: ["寅", "卯"], 2: ["子", "丑"]}
    return void_map.get(diff, [])

def get_shinsal_list(pillar_char, pillar_type, col_idx, s_list, b_list):
    shinsals = []
    y_s, m_s, d_s, h_s = s_list
    y_b, m_b, d_b, h_b = b_list
    me = pillar_char
    
    if pillar_type == 'branch':
        frames = {'수국': ['申', '子', '辰'], '화국': ['寅', '午', '戌'], '금국': ['巳', '酉', '丑'], '목국': ['亥', '卯', '未']}
        
        # 나 자신(현재 기둥)을 제외한 나머지 지지들만 모은 리스트 생성
        other_b = [b for i, b in enumerate(b_list) if i != col_idx]

        if (me=='辰' and any(b in frames['수국'] for b in other_b)) or (me=='戌' and any(b in frames['화국'] for b in other_b)) or (me=='丑' and any(b in frames['금국'] for b in other_b)) or (me=='未' and any(b in frames['목국'] for b in other_b)): shinsals.append("화개")
        if (me=='寅' and any(b in frames['수국'] for b in other_b)) or (me=='申' and any(b in frames['화국'] for b in other_b)) or (me=='亥' and any(b in frames['금국'] for b in other_b)) or (me=='巳' and any(b in frames['목국'] for b in other_b)): shinsals.append("역마")
        if (me=='酉' and any(b in frames['수국'] for b in other_b)) or (me=='卯' and any(b in frames['화국'] for b in other_b)) or (me=='午' and any(b in frames['금국'] for b in other_b)) or (me=='子' and any(b in frames['목국'] for b in other_b)): shinsals.append("도화")

        chonul_map = {"甲": ["丑","未"], "戊": ["丑","未"], "庚": ["丑","未"], "乙": ["子","申"], "己": ["子","申"], "丙": ["亥","酉"], "丁": ["亥","酉"], "辛": ["寅","午"], "壬": ["巳","卯"], "癸": ["巳","卯"]}
        if me in chonul_map.get(d_s, []): shinsals.append("천을귀인")
        
        if me == {"甲":"巳", "乙":"午", "丙":"申", "丁":"酉", "戊":"申", "己":"酉", "庚":"亥", "辛":"子", "壬":"寅", "癸":"卯"}.get(d_s): shinsals.append("문창귀인")
        if me == BRANCHES[(BRANCHES.index(m_b) - 1) % 12]: shinsals.append("천의성")
        if me == {"甲":"卯", "丙":"午", "戊":"午", "庚":"酉", "壬":"子"}.get(d_s): shinsals.append("양인")
        if me == {"子":"未", "丑":"午", "寅":"酉", "卯":"申", "辰":"亥", "巳":"戌", "午":"丑", "未":"子", "申":"卯", "酉":"寅", "戌":"巳", "亥":"辰"}.get(d_b): shinsals.append("원진")
        if me == {"子":"酉", "丑":"午", "寅":"未", "卯":"申", "辰":"亥", "巳":"戌", "午":"丑", "未":"寅", "申":"卯", "酉":"子", "戌":"巳", "亥":"辰"}.get(d_b): shinsals.append("귀문")
        
        if me in (calculate_voids(y_s, y_b) if col_idx == 2 else calculate_voids(d_s, d_b)): shinsals.append("공망")
            
    elif pillar_type == 'stem':
        s_set = set(s_list)
        if {"甲","戊","庚"}.issubset(s_set) or {"辛","壬","癸"}.issubset(s_set) or {"乙","丙","丁"}.issubset(s_set): shinsals.append("삼기")
        
        wd_map = '丙' if m_b in ['寅','午','戌'] else '壬' if m_b in ['申','子','辰'] else '甲' if m_b in ['亥','卯','未'] else '庚' if m_b in ['巳','酉','丑'] else ''
        if me == wd_map: shinsals.append("월덕귀인")
        
        td_map = {"子":"巳", "丑":"庚", "寅":"丁", "卯":"申", "辰":"壬", "巳":"辛", "午":"亥", "未":"甲", "申":"癸", "酉":"寅", "戌":"丙", "亥":"乙"}
        if me == td_map.get(m_b): shinsals.append("천덕귀인")
        
        wk_map = '壬' if m_b in ['寅','午','戌'] else '丙' if m_b in ['申','子','辰'] else '庚' if m_b in ['亥','卯','未'] else '甲' if m_b in ['巳','酉','丑'] else ''
        if me == wk_map: shinsals.append("월공")
    
    return list(set(shinsals))

def get_ganji_shinsal(stem, branch):
    ganji = stem + branch
    res = []
    if ganji in ["庚辰", "庚戌", "壬辰", "壬戌", "戊戌"]: res.append("괴강")
    if ganji in ["甲辰", "乙未", "丙戌", "丁丑", "戊辰", "壬戌", "癸丑"]: res.append("백호")
    return res

def jd_ut_from_utc(dt_utc: dt.datetime) -> float:
    hour = dt_utc.hour + dt_utc.minute/60 + dt_utc.second/3600
    return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour, swe.GREG_CAL)

def utc_from_jd_ut(jd_ut: float) -> dt.datetime:
    y, m, d, hour = swe.revjul(jd_ut, swe.GREG_CAL)
    hh = int(hour)
    min_val = int((hour - hh) * 60)
    sec = int(round((((hour - hh) * 60) - min_val) * 60))
    if sec == 60: sec = 0; min_val += 1
    if min_val == 60: min_val = 0; hh += 1
    return dt.datetime(y, m, d, hh, min_val, sec, tzinfo=dt.timezone.utc)

@st.cache_data
def calculate_saju_data(birth_date, time_str, basis_option, lat, lon, gender):
    b_time = parse_hms(time_str)
    naive = dt.datetime.combine(birth_date, b_time)
    
    if basis_option.startswith("표준시"):
        tz_str = TF.timezone_at(lat=lat, lng=lon) or "Asia/Seoul"
        local = naive.replace(tzinfo=ZoneInfo(tz_str))
        utc_dt = local.astimezone(dt.timezone.utc)
    else:
        utc_dt = naive.replace(tzinfo=dt.timezone.utc) - dt.timedelta(seconds=lon * 240.0)

    jd_ut = jd_ut_from_utc(utc_dt)
    eot_days = swe.time_equ(jd_ut)
    lat_dt = utc_dt + dt.timedelta(seconds=(lon*240.0 + eot_days*86400.0))
    
    birth_utc_for_year = utc_from_jd_ut(jd_ut)
    y_year = birth_utc_for_year.year
    jd_start = swe.julday(y_year, 1, 1, 0.0, swe.GREG_CAL)
    lichun = swe.solcross_ut(315.0, jd_start, swe.FLG_MOSEPH) 
    if jd_ut < lichun: y_year -= 1
    y_idx = (y_year - 1984) % 60 
    y_s, y_b = STEMS[y_idx % 10], BRANCHES[y_idx % 12]

    best_term = None
    for name, lon_deg, branch in MAJOR_TERMS:
        jx = swe.solcross_ut(lon_deg, jd_ut - 40.0, swe.FLG_MOSEPH)
        if jx <= jd_ut:
            if (best_term is None) or (jx > best_term[3]):
                best_term = (name, lon_deg, branch, jx)
    
    if not best_term: 
        m_s, m_b, term_jd = "甲", "寅", 0.0
    else:
        m_branch = best_term[2]
        term_jd = best_term[3]
        m_idx_in_order = ["寅","卯","辰","巳","午","未","申","酉","戌","亥","子","丑"].index(m_branch)
        yin_stem = Y_STEM_TO_YIN_MONTH_STEM[y_s]
        m_s = STEMS[(STEMS.index(yin_stem) + m_idx_in_order) % 10]
        m_b = m_branch

    adj_dt = lat_dt + dt.timedelta(days=1) if lat_dt.hour >= 23 else lat_dt
    jdn = int(math.floor(swe.julday(adj_dt.year, adj_dt.month, adj_dt.day, 0, swe.GREG_CAL) + 0.5))
    d_idx = (jdn + 49) % 60
    d_s, d_b = STEMS[d_idx % 10], BRANCHES[d_idx % 12]

    minutes = lat_dt.hour * 60 + lat_dt.minute + lat_dt.second/60.0
    h_idx_val = int(((minutes + 60) // 120) % 12)
    h_b = BRANCHES[h_idx_val]
    h_s = STEMS[(STEMS.index(D_STEM_TO_ZI_HOUR_STEM[d_s]) + h_idx_val) % 10]

    s_list = [y_s, m_s, d_s, h_s]
    b_list = [y_b, m_b, d_b, h_b]
    
    y_idx_int = STEMS.index(y_s)
    forward = ((y_idx_int % 2 == 0) and gender == "남") or ((y_idx_int % 2 != 0) and gender == "여")
    
    curr_term_idx = next(i for i, t in enumerate(MAJOR_TERMS) if t[2] == m_b)
    if forward:
        nxt_jd = swe.solcross_ut(MAJOR_TERMS[(curr_term_idx + 1) % 12][1], jd_ut, swe.FLG_MOSEPH)
        diff_days = nxt_jd - jd_ut
    else:
        diff_days = jd_ut - term_jd
    
    dw_num = diff_days / 3.0

    daewoon_list = [{'s': m_s, 'b': m_b, 'age': 0.0}]
    ms_idx, mb_idx = STEMS.index(m_s), BRANCHES.index(m_b)
    
    for i in range(1, 11):
        offset = i if forward else -i
        ds = STEMS[(ms_idx + offset)%10]
        db = BRANCHES[(mb_idx + offset)%12]
        start_age = dw_num + (i-1)*10 if i > 1 else dw_num
        daewoon_list.append({'s': ds, 'b': db, 'age': start_age})
        
    return {
        's_list': s_list, 'b_list': b_list, 'b_year': y_year, 
        'dw_num': dw_num, 'daewoon': daewoon_list, 'forward': forward, 'd_s': d_s
    }

# =============================================================================
# [MODULE 5] UI 렌더링 (VIEW)
# =============================================================================
def render_pillar_html(title, stem, branch, s_list, b_list, is_luck=False):
    day_stem = s_list[2] 
    s_idx = get_element_idx(stem)
    b_idx = get_element_idx(branch)
    
    s_sipsin = get_sipsin(day_stem, stem)
    b_sipsin = get_sipsin(day_stem, branch)
    if title == "일주": s_sipsin = "본원"
    
    unseong = get_12unseong(day_stem, branch)
    hiddens_str = " ".join(JIJANGGAN.get(branch, []))
    hiddens_html = f'<div class="jijanggan">{hiddens_str}</div>'
    
    col_idx = {"연주":0, "월주":1, "일주":2, "시주":3}.get(title, -1)
    
    shinsals = list(set(get_shinsal_list(stem, 'stem', col_idx, s_list, b_list) + 
                        get_shinsal_list(branch, 'branch', col_idx, s_list, b_list) + 
                        get_ganji_shinsal(stem, branch)))
    
    badges_html = "".join([f'<span class="badge">{s}</span>' for s in shinsals])
    card_cls = "luck-card" if is_luck else "pillar-card"
    
    return f'<div class="{card_cls}"><div class="small-text">{title}</div><div class="sipsin-badge">{s_sipsin}</div><div class="char-box bg-{s_idx}">{stem}</div><div class="char-box bg-{b_idx}">{branch}</div>{hiddens_html}<div class="sipsin-badge">{b_sipsin}</div><div class="unseong-text">{unseong}</div><div class="shinsal-container">{badges_html}</div></div>'

def render_mini_card(stem, branch, day_stem, bottom_label, is_active=False):
    s_idx = get_element_idx(stem)
    b_idx = get_element_idx(branch)
    s_sipsin = get_sipsin(day_stem, stem)
    b_sipsin = get_sipsin(day_stem, branch)
    unseong = get_12unseong(day_stem, branch)
    active_cls = "dw-active" if is_active else ""
    
    return f'<div class="mini-card-container {active_cls}"><div class="mini-sipsin">{s_sipsin}</div><div class="mini-char bg-{s_idx}">{stem}</div><div class="mini-char bg-{b_idx}">{branch}</div><div class="mini-sipsin">{b_sipsin}</div><div class="mini-unseong">{unseong}</div><div class="mini-age">{bottom_label}</div></div>'

# =============================================================================
# [MODULE 6] 메인 애플리케이션 (MAIN APP)
# =============================================================================
def main():
    st.set_page_config(page_title="초정밀 만세력 V11 (라이브 배포)", layout="wide")

    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700;900&family=Noto+Serif+KR:wght@400;700;900&display=swap');
        * { box-sizing: border-box; }
        html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
        @media (min-width: 768px) { section[data-testid="stSidebar"] { min-width: 450px !important; max-width: 500px !important; } }
        .total-flex-container { display: flex; flex-direction: row; align-items: flex-start; justify-content: center; gap: 4px; flex-wrap: nowrap; overflow-x: auto; padding-bottom: 10px; margin-bottom: 20px; }
        .pillar-card, .luck-card { background-color: transparent; padding: 0px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 2px; flex: 0 0 auto; border: none; min-width: 60px; }
        .char-box { width: 64px; height: 64px; border-radius: 8px; display: flex; justify-content: center; align-items: center; font-family: 'Noto Serif KR', serif !important; font-size: 2.3em !important; font-weight: 900 !important; margin: 0 auto; box-shadow: 0 1px 3px rgba(0,0,0,0.15); }
        .small-text { font-size: 0.9em; color: var(--text-color) !important; font-weight: 700; margin-bottom: 2px;}
        .sipsin-badge { font-size: 0.75em; color: var(--text-color); background-color: rgba(128, 128, 128, 0.15); padding: 2px 6px; border-radius: 4px; font-weight: bold; white-space: nowrap; margin-bottom: 2px; margin-top: 2px; }
        .unseong-text { font-size: 0.9em; color: var(--text-color) !important; font-weight: 700; margin-top: 2px; margin-bottom: 2px; }
        .jijanggan { font-size: 0.75em; color: var(--text-color) !important; opacity: 0.7; letter-spacing: 0px; margin-top: 2px; margin-bottom: 2px;}
        .shinsal-container { display: flex; flex-direction: column; align-items: center; gap: 3px; margin-top: 6px; width: 100%; }
        .badge { font-size: 0.65em; padding: 3px 6px; border-radius: 3px; font-weight: normal; color: var(--text-color); background-color: rgba(128, 128, 128, 0.2); display: inline-block; width: max-content; }
        .bg-0 { background-color: #C8E6C9; color: #004D40; } .bg-1 { background-color: #FFCDD2; color: #B71C1C; } .bg-2 { background-color: #FFF9C4; color: #E65100; } .bg-3 { background-color: #FFFFFF; color: #212121; } .bg-4 { background-color: #212121; color: #FFFFFF; } 
        div[data-testid="stHorizontalBlock"] button { background-color: transparent !important; border: none !important; box-shadow: none !important; color: var(--text-color) !important; padding: 0 !important; margin: 0 auto !important; height: auto !important; }
        div[data-testid="stHorizontalBlock"] button:hover { color: #FF4B4B !important; }
        .mini-card-container { display: flex; flex-direction: column; align-items: center; background: transparent; padding: 4px; cursor: pointer; width: 55px !important; margin: 0 auto; }
        .dw-active { background-color: rgba(100, 150, 255, 0.15); border-radius: 8px; }
        .mini-sipsin { font-size: 0.7em; color: var(--text-color) !important; opacity: 0.8; margin-bottom: 2px; white-space: nowrap; }
        .mini-char { width: 36px; height: 36px; border-radius: 6px; display: flex; justify-content: center; align-items: center; font-family: 'Noto Serif KR', serif !important; font-size: 1.5em !important; font-weight: 900 !important; margin: 2px 0; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }
        .mini-unseong { font-size: 0.65em; color: var(--text-color) !important; opacity: 0.7; margin-top: 2px; }
        .mini-age { font-size: 0.8em; font-weight: bold; color: var(--text-color) !important; margin-top: 4px; }
    </style>
    """, unsafe_allow_html=True)

    if "token" not in st.session_state:
        with st.sidebar:
            st.title("🔐 프라이빗 만세력")
            st.write("나만의 명식을 보관하려면 먼저 로그인해 줘!")
            result = oauth2.authorize_button(
                name="Google로 로그인",
                icon="https://www.google.com/favicon.ico",
                redirect_uri=REDIRECT_URI,
                scope="openid email profile"
            )
            if result and 'token' in result:
                st.session_state.token = result.get('token')
                st.rerun()
        
        st.info("👈 왼쪽 사이드바에서 구글 계정으로 로그인해 주세요!")
        return 

    if "user_email" not in st.session_state:
        token = st.session_state["token"]["access_token"]
        user_info = requests.get("https://www.googleapis.com/oauth2/v1/userinfo", headers={"Authorization": f"Bearer {token}"}).json()
        st.session_state.user_email = user_info.get("email")
        st.session_state.user_name = user_info.get("name", "동지")
        st.rerun()

    user_email = st.session_state.user_email
    
    st.title("🌌 초정밀 만세력")
    
    if 'is_calculated' not in st.session_state: st.session_state.is_calculated = False
    
    if 'db' not in st.session_state: 
        st.session_state.db = load_db(user_email)
        
    if 'show_daewoon' not in st.session_state: st.session_state.show_daewoon = False
    if 'show_seun' not in st.session_state: st.session_state.show_seun = False
    if 'sel_dw_idx' not in st.session_state: st.session_state.sel_dw_idx = -1
    if 'sel_seun_year' not in st.session_state: st.session_state.sel_seun_year = -1

    def reset_luck_view():
        st.session_state.show_daewoon = False
        st.session_state.show_seun = False
        st.session_state.sel_dw_idx = -1
        st.session_state.sel_seun_year = -1

    with st.sidebar:
        st.success(f"환영해, {st.session_state.user_name} 동지! (로그인됨)")
        if st.button("로그아웃"):
            for key in ['token', 'user_email', 'user_name', 'db']:
                if key in st.session_state: del st.session_state[key]
            st.rerun()
            
        st.divider()
        st.header(f"🗂️ 내 전용 명식 보관함")
        saved_list = st.session_state.db['이름'].tolist()
        selected_profile = st.selectbox("불러오기", ["(선택 안함)"] + saved_list)
        
        def_name, def_gender, def_date, def_time, def_basis, def_place, def_lat, def_lon = \
            "사용자", "여", dt.date(1998, 1, 27), "12:00", "표준시 (현대)", "Seoul", 37.5665, 126.9780

        if selected_profile != "(선택 안함)":
            row = st.session_state.db[st.session_state.db['이름'] == selected_profile].iloc[0]
            def_name, def_gender = row['이름'], row['성별']
            def_date = dt.datetime.strptime(str(row['생년월일']), "%Y-%m-%d").date()
            def_time, def_basis, def_place = row['생시'], row['시각기준'], row['도시']
            def_lat, def_lon = float(row['위도']), float(row['경도'])

        st.divider()
        st.header("📝 정보 입력")
        name = st.text_input("이름", def_name)
        gender = st.radio("성별", ["남", "여"], index=0 if def_gender=="남" else 1, horizontal=True)
        birth_date = st.date_input("생년월일", def_date, min_value=dt.date(1, 1, 1), max_value=dt.date(2100, 12, 31))
        time_str = st.text_input("생시", def_time)
        basis = st.radio("기준", ["표준시 (현대)", "LMT (옛날/지역시)"], index=0 if "표준" in def_basis else 1)
        
        st.caption("장소")
        col_p1, col_p2 = st.columns([2,1])
        place = col_p1.text_input("도시", def_place, label_visibility="collapsed")
        if col_p2.button("검색"):
            lat, lon = geocode_osm_cached(place)
            if lat:
                st.session_state.lat, st.session_state.lon = lat, lon
                st.success("OK")
                st.rerun()
            else: st.error("실패")

        lat = st.number_input("위도", value=st.session_state.get('lat', def_lat), format="%.4f")
        lon = st.number_input("경도", value=st.session_state.get('lon', def_lon), format="%.4f")
        
        c1, c2 = st.columns(2)
        if c1.button("🔥 명식 뽑기", type="primary"):
            st.session_state.is_calculated = True
            reset_luck_view()
            st.rerun()
            
        if c2.button("💾 저장"):
            new_row = {"이름": name, "성별": gender, "생년월일": birth_date, "생시": time_str, "시각기준": basis, "도시": place, "위도": lat, "경도": lon}
            save_record(new_row, user_email)
            st.session_state.db = load_db(user_email)
            st.toast(f"내 금고에 안전하게 저장됨: {name}")
            st.rerun()

        if selected_profile != "(선택 안함)" and st.button("🗑️ 삭제"):
            delete_record(selected_profile, user_email)
            st.session_state.db = load_db(user_email)
            st.toast("내 금고에서 삭제됨")
            st.rerun()

    if st.session_state.is_calculated:
        try:
            data = calculate_saju_data(birth_date, time_str, basis, lat, lon, gender)
            s_list, b_list, daewoon_list, d_s = data['s_list'], data['b_list'], data['daewoon'], data['d_s']
            daewoon_visual = daewoon_list[::-1]
            
            if st.session_state.sel_dw_idx == -1: 
                st.session_state.sel_dw_idx = 10 
            
            sel_dw = daewoon_visual[st.session_state.sel_dw_idx]
            
            if st.session_state.sel_seun_year == -1:
                st.session_state.sel_seun_year = data['b_year'] + int(sel_dw['age'])
            
            seun_visual = []
            base_start_year = data['b_year'] + int(sel_dw['age'])
            for k in range(10):
                this_y = base_start_year + k
                seun_visual.append({'y': this_y, 'age': sel_dw['age'] + k, 's': STEMS[(this_y-1984)%10], 'b': BRANCHES[(this_y-1984)%12]})
            seun_visual = seun_visual[::-1]

            st.write("") 
            st.markdown(f"### 🌺 **{name}** 님의 원국 ({basis})")
            
            html_parts = []
            if st.session_state.show_seun and st.session_state.sel_seun_year != -1:
                target_seun = next((x for x in seun_visual if x['y'] == st.session_state.sel_seun_year), seun_visual[-1])
                html_parts.append(render_pillar_html(f"세운({target_seun['y']})", target_seun['s'], target_seun['b'], s_list, b_list, is_luck=True))
                
            if st.session_state.show_daewoon and st.session_state.sel_dw_idx != -1:
                html_parts.append(render_pillar_html("대운", sel_dw['s'], sel_dw['b'], s_list, b_list, is_luck=True))
                html_parts.append('<div style="width: 15px; flex-shrink: 0;"></div>')

            for p_name, idx in [("시주", 3), ("일주", 2), ("월주", 1), ("연주", 0)]:
                html_parts.append(render_pillar_html(p_name, s_list[idx], b_list[idx], s_list, b_list))
            
            st.markdown(f'<div class="total-flex-container">{"".join(html_parts)}</div>', unsafe_allow_html=True)
            st.divider()
            
            st.subheader("🌊 대운의 흐름 (⬅️)")
            st.caption(f"대운 수: {data['dw_num']:.1f} ({'순행' if data['forward'] else '역행'})")
            
            dw_cols = st.columns(11) 
            for i, dw in enumerate(daewoon_visual):
                with dw_cols[i]:
                    if st.button(f"{dw['age']:.1f}", key=f"dw_btn_{i}", use_container_width=True):
                        st.session_state.sel_dw_idx = i
                        st.session_state.show_daewoon = True
                        st.session_state.show_seun = False 
                        st.session_state.sel_seun_year = -1
                        st.rerun()
                    
                    is_active = (i == st.session_state.sel_dw_idx) and st.session_state.show_daewoon
                    st.markdown(render_mini_card(dw['s'], dw['b'], d_s, "", is_active), unsafe_allow_html=True)

            if st.session_state.show_daewoon and st.session_state.sel_dw_idx != -1:
                st.divider()
                st.markdown(f"#### 📅 **{sel_dw['s']}{sel_dw['b']}** 대운 기간의 세운 (⬅️)")
                
                seun_cols = st.columns(10)
                for k, item in enumerate(seun_visual):
                    with seun_cols[k]:
                        year_short = str(item['y'])[2:]
                        if st.button(f"'{year_short}", key=f"seun_btn_{k}", use_container_width=True):
                            st.session_state.sel_seun_year = item['y']
                            st.session_state.show_seun = True
                            st.rerun()
                            
                        is_sel = (item['y'] == st.session_state.sel_seun_year) and st.session_state.show_seun
                        st.markdown(render_mini_card(item['s'], item['b'], d_s, f"{int(item['age'])}세", is_sel), unsafe_allow_html=True)

        except Exception as e:
            st.error(f"계산 중 오류가 발생했습니다: {e}")

if __name__ == "__main__":
    main()
