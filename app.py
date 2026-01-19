import math
import datetime as dt
from zoneinfo import ZoneInfo
import requests
import streamlit as st
from timezonefinder import TimezoneFinder
import swisseph as swe
import pandas as pd
import os

# ---------------------------------------------------------
# 1. 기초 데이터
# ---------------------------------------------------------
STEMS = ["甲","乙","丙","丁","戊","己","庚","辛","壬","癸"]
BRANCHES = ["子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"]
STEM_ELEMENTS = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]  
BRANCH_ELEMENTS = [4, 2, 0, 0, 2, 1, 1, 2, 3, 3, 2, 4]

JIJANGGAN = {
    "子": ["壬", "癸"],       "丑": ["癸", "辛", "己"],
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

UNSEONG_ORDER = ["절","태","양","장생","목욕","관대","건록","제왕","쇠","병","사","묘"]

MAJOR_TERMS = [
    ("입춘", 315.0, "寅"), ("경칩", 345.0, "卯"), ("청명", 15.0,  "辰"),
    ("입하", 45.0,  "巳"), ("망종", 75.0,  "午"), ("소서", 105.0, "未"),
    ("입추", 135.0, "申"), ("백로", 165.0, "酉"), ("한로", 195.0, "戌"),
    ("입동", 225.0, "亥"), ("대설", 255.0, "子"), ("소한", 285.0, "丑"),
]

Y_STEM_TO_YIN_MONTH_STEM = {
    "甲": "丙", "己": "丙", "乙": "戊", "庚": "戊", "丙": "庚", "辛": "庚",
    "丁": "壬", "壬": "壬", "戊": "甲", "癸": "甲",
}
D_STEM_TO_ZI_HOUR_STEM = {
    "甲": "甲", "己": "甲", "乙": "丙", "庚": "丙", "丙": "戊", "辛": "戊",
    "丁": "庚", "壬": "庚", "戊": "壬", "癸": "壬",
}

TF = TimezoneFinder()
DB_FILE = "saju_db.csv"

# ---------------------------------------------------------
# 2. 로직 함수들
# ---------------------------------------------------------
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
    elif target == "亥": t_pol = 1
    elif target == "午": t_pol = 1
    elif target == "巳": t_pol = 0
    is_diff = 1 if d_pol != t_pol else 0
    return SIPSIN_NAMES[relation][is_diff]

def get_12unseong(stem: str, branch: str) -> str:
    start_map = {
        "甲": ("亥", 1), "丙": ("寅", 1), "戊": ("寅", 1), "庚": ("巳", 1), "壬": ("申", 1),
        "乙": ("午", -1), "丁": ("酉", -1), "己": ("酉", -1), "辛": ("子", -1), "癸": ("卯", -1)
    }
    start_branch, direction = start_map[stem]
    start_idx = BRANCHES.index(start_branch)
    target_idx = BRANCHES.index(branch)
    if direction == 1: diff = (target_idx - start_idx) % 12
    else: diff = (start_idx - target_idx) % 12
    return UNSEONG_ORDER[(3 + diff) % 12]

def calculate_voids(stem, branch):
    s_idx = STEMS.index(stem)
    b_idx = BRANCHES.index(branch)
    diff = (b_idx - s_idx) % 12
    void_map = {
        0:  ["戌", "亥"], 10: ["申", "酉"], 8:  ["午", "未"],
        6:  ["辰", "巳"], 4:  ["寅", "卯"], 2:  ["子", "丑"]
    }
    return void_map.get(diff, [])

# ---------------------------------------------------------
# 3. 신살 계산 로직
# ---------------------------------------------------------
def get_shinsal(pillar_char, pillar_type, col_idx, s_list, b_list):
    shinsals = []
    y_s, m_s, d_s, h_s = s_list
    y_b, m_b, d_b, h_b = b_list
    
    if pillar_type == 'branch':
        me = pillar_char
        groups = {
            '수': {'frame': ['申','子','辰'], '역마': '寅', '도화': '酉', '화개': '辰'},
            '화': {'frame': ['寅','午','戌'], '역마': '申', '도화': '卯', '화개': '戌'},
            '금': {'frame': ['巳','酉','丑'], '역마': '亥', '도화': '午', '화개': '丑'},
            '목': {'frame': ['亥','卯','未'], '역마': '巳', '도화': '子', '화개': '未'},
        }
        active_frames = []
        for g_name, g_info in groups.items():
            if any(b in g_info['frame'] for b in b_list):
                active_frames.append(g_info)
        for g in active_frames:
            if me == g['역마']: shinsals.append("역마")
            if me == g['도화']: shinsals.append("도화")
            if me == g['화개']: shinsals.append("화개")

        chonul_map = {
            "甲": ["丑","未"], "戊": ["丑","未"], "庚": ["丑","未"],
            "乙": ["子","申"], "己": ["子","申"],
            "丙": ["亥","酉"], "丁": ["亥","酉"],
            "辛": ["寅","午"], "壬": ["巳","卯"], "癸": ["巳","卯"]
        }
        if me in chonul_map.get(d_s, []): shinsals.append("천을귀인")
        
        munchang_map = {"甲":"巳", "乙":"午", "丙":"申", "丁":"酉", "戊":"申", 
                        "己":"酉", "庚":"亥", "辛":"子", "壬":"寅", "癸":"卯"}
        if me == munchang_map.get(d_s): shinsals.append("문창귀인")
        
        prev_idx = (BRANCHES.index(m_b) - 1) % 12
        cheoneui = BRANCHES[prev_idx]
        if me == cheoneui: shinsals.append("천의성")

        yangin_map = {"甲":"卯", "丙":"午", "戊":"午", "庚":"酉", "壬":"子"} 
        if me == yangin_map.get(d_s): shinsals.append("양인")
        
        wonjin_map = {"子":"未", "丑":"午", "寅":"酉", "卯":"申", "辰":"亥", "巳":"戌", 
                      "午":"丑", "未":"子", "申":"卯", "酉":"寅", "戌":"巳", "亥":"辰"}
        if me == wonjin_map.get(d_b): shinsals.append("원진")
        
        gwimun_map = {"子":"酉", "丑":"午", "寅":"未", "卯":"申", "辰":"亥", "巳":"戌",
                      "午":"丑", "未":"寅", "申":"卯", "酉":"子", "戌":"巳", "亥":"辰"}
        if me == gwimun_map.get(d_b): shinsals.append("귀문")
        
        if col_idx == 2: target_voids = calculate_voids(y_s, y_b) 
        else: target_voids = calculate_voids(d_s, d_b) 
        if me in target_voids: shinsals.append("공망")

    elif pillar_type == 'stem':
        me = pillar_char
        s_set = set(s_list)
        if {"甲","戊","庚"}.issubset(s_set): shinsals.append("삼기")
        elif {"辛","壬","癸"}.issubset(s_set): shinsals.append("삼기")
        elif {"乙","丙","丁"}.issubset(s_set): shinsals.append("삼기")
        
        wd_map = {}
        if m_b in ['寅','午','戌']: wd_map = '丙'
        elif m_b in ['申','子','辰']: wd_map = '壬'
        elif m_b in ['亥','卯','未']: wd_map = '甲'
        elif m_b in ['巳','酉','丑']: wd_map = '庚'
        if me == wd_map: shinsals.append("월덕귀인")
        
        td_map = {"子":"巳", "丑":"庚", "寅":"丁", "卯":"申", "辰":"壬", "巳":"辛",
                  "午":"亥", "未":"甲", "申":"癸", "酉":"寅", "戌":"丙", "亥":"乙"}
        if me == td_map.get(m_b): shinsals.append("천덕귀인")
        
        wk_map = {}
        if m_b in ['寅','午','戌']: wk_map = '壬'
        elif m_b in ['申','子','辰']: wk_map = '丙'
        elif m_b in ['亥','卯','未']: wk_map = '庚'
        elif m_b in ['巳','酉','丑']: wk_map = '甲'
        if me == wk_map: shinsals.append("월공")
    
    return list(set(shinsals))

def get_pillar_shinsal(stem, branch):
    ganji = stem + branch
    res = []
    if ganji in ["庚辰", "庚戌", "壬辰", "壬戌", "戊戌"]: res.append("괴강")
    if ganji in ["甲辰", "乙未", "丙戌", "丁丑", "戊辰", "壬戌", "癸丑"]: res.append("백호")
    return res

# ---------------------------------------------------------
# 4. 천문 계산
# ---------------------------------------------------------
def parse_hms(s: str) -> dt.time:
    s = (s or "").strip()
    parts = s.split(":")
    if len(parts) not in (2, 3): return dt.time(12, 0)
    try: return dt.time(int(parts[0]), int(parts[1]))
    except: return dt.time(12, 0)

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

def apparent_solar_datetime(utc_dt: dt.datetime, lon_deg: float) -> tuple[dt.datetime, float]:
    jd_ut = jd_ut_from_utc(utc_dt)
    eot_days = swe.time_equ(jd_ut)
    lat_dt = utc_dt + dt.timedelta(seconds=(lon_deg*240.0 + eot_days*86400.0))
    return lat_dt, eot_days * 1440.0

def year_pillar(jd_ut_birth: float):
    birth_utc = utc_from_jd_ut(jd_ut_birth)
    y = birth_utc.year
    jd_start = swe.julday(y, 1, 1, 0.0, swe.GREG_CAL)
    lichun = swe.solcross_ut(315.0, jd_start, swe.FLG_SWIEPH)
    if jd_ut_birth < lichun: y -= 1
    idx = (y - 1984) % 60 
    return STEMS[idx % 10], BRANCHES[idx % 12], y

def month_pillar(jd_ut_birth: float, year_stem: str):
    best = None
    for name, lon, branch in MAJOR_TERMS:
        jx = swe.solcross_ut(lon, jd_ut_birth - 40.0, swe.FLG_SWIEPH)
        if jx <= jd_ut_birth:
            if (best is None) or (jx > best[3]):
                best = (name, lon, branch, jx)
    if not best: return "甲", "寅", 0.0
    m_branch = best[2]
    order = ["寅","卯","辰","巳","午","未","申","酉","戌","亥","子","丑"]
    m_idx = order.index(m_branch)
    yin_stem = Y_STEM_TO_YIN_MONTH_STEM[year_stem]
    m_stem = STEMS[(STEMS.index(yin_stem) + m_idx) % 10]
    return m_stem, m_branch, best[3]

def day_pillar(lat_dt: dt.datetime):
    adj_dt = lat_dt
    if lat_dt.hour >= 23: adj_dt = lat_dt + dt.timedelta(days=1)
    jd = swe.julday(adj_dt.year, adj_dt.month, adj_dt.day, 0, swe.GREG_CAL)
    jdn = int(math.floor(jd + 0.5))
    idx = (jdn + 49) % 60
    return STEMS[idx % 10], BRANCHES[idx % 12], jdn

def hour_pillar(lat_dt: dt.datetime, day_stem: str):
    minutes = lat_dt.hour * 60 + lat_dt.minute + lat_dt.second/60.0
    idx = int(((minutes + 60) // 120) % 12)
    h_branch = BRANCHES[idx]
    zi_stem = D_STEM_TO_ZI_HOUR_STEM[day_stem]
    h_stem = STEMS[(STEMS.index(zi_stem) + idx) % 10]
    return h_stem, h_branch

def geocode_osm(place):
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "manseryeok-v2"}
    try:
        r = requests.get(url, params={"q": place, "format": "json", "limit": 1}, headers=headers, timeout=5)
        if r.ok and r.json():
            return float(r.json()[0]['lat']), float(r.json()[0]['lon'])
    except:
        pass
    return None, None

def load_db():
    if os.path.exists(DB_FILE):
        return pd.read_csv(DB_FILE)
    return pd.DataFrame(columns=["이름", "성별", "생년월일", "시간", "시각기준", "도시", "위도", "경도"])

def save_db(df):
    df.to_csv(DB_FILE, index=False)

# ---------------------------------------------------------
# 5. UI / CSS 스타일링 (V5.8 - Square Scroll & Zero Gap)
# ---------------------------------------------------------
st.set_page_config(page_title="초정밀 만세력 V5.8", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;500;700;900&family=Noto+Serif+KR:wght@400;700;900&display=swap');
    * { box-sizing: border-box; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
    
    /* 1. 상단 원국 */
    .total-flex-container {
        display: flex; flex-direction: row; align-items: flex-start; justify-content: center; 
        gap: 1px; flex-wrap: nowrap; overflow-x: auto; padding-bottom: 10px; margin-bottom: 20px;
        -webkit-overflow-scrolling: touch;
    }
    .pillar-card, .luck-card {
        background-color: transparent; padding: 0px; text-align: center; 
        display: flex; flex-direction: column; align-items: center; 
        gap: 1px; flex: 0 0 auto; border: none; min-width: 44px;
    }
    .luck-card { background-color: transparent !important; }

    /* PC 기본 스타일 */
    .char-box {
        width: 70px; height: 70px; border-radius: 16px;
        display: flex; justify-content: center; align-items: center;
        font-family: 'Noto Serif KR', serif; font-size: 2.3em; font-weight: 900;
        box-shadow: 0 3px 6px rgba(0,0,0,0.1); margin: 0 auto;
    }
    .small-text { font-size: 0.8em; color: #333; font-weight: 700; margin-bottom: 1px;}
    .unseong-badge { font-size: 0.7em; color: #2c3e50; background-color: #f1f3f5; padding: 1px 5px; border-radius: 8px; font-weight: bold; white-space: nowrap;}
    .jijanggan { font-size: 0.7em; color: #666; letter-spacing: -1px; margin-top: -1px; margin-bottom: 1px;}
    .shinsal-container { display: flex; flex-wrap: wrap; justify-content: center; gap: 1px; margin-top: 1px; max-width: 70px; }
    .badge { font-size: 0.6em; padding: 1px 3px; border-radius: 4px; font-weight: 600; color: white; opacity: 0.95; }

    /* 모바일 원국 최적화 */
    @media only screen and (max-width: 600px) {
        .total-flex-container { justify-content: flex-start; gap: 1px !important; }
        .pillar-card, .luck-card { min-width: 14vw; } /* 조금 넉넉하게 */
        .char-box {
            width: 12vw; height: 12vw; font-size: 6vw;
            border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .small-text { font-size: 3vw; }
        .unseong-badge { font-size: 2.5vw; padding: 0 2px; }
        .jijanggan { font-size: 2.5vw; }
        .shinsal-container { max-width: 12vw; }
        .badge { font-size: 2vw; padding: 0 1px; }
    }

    /* 오행 색상 */
    .bg-0 { background-color: #C8E6C9; color: #004D40; border: 2px solid #81C784; } 
    .bg-1 { background-color: #FFCDD2; color: #B71C1C; border: 2px solid #E57373; } 
    .bg-2 { background-color: #FFF9C4; color: #E65100; border: 2px solid #FFF176; } 
    .bg-3 { background-color: #F5F5F5; color: #212121; border: 2px solid #E0E0E0; } 
    .bg-4 { background-color: #212121; color: #FFFFFF; border: 2px solid #616161; } 
    .badge-good { background-color: #D81B60; }
    .badge-power { background-color: #546E7A; }
    .badge-rel { background-color: #6D4C41; }
    .badge-12 { background-color: #3949AB; }
    .badge-gong { background-color: #424242; } 
    
    /* 2. 하단 리스트: Gap 0, Scrollable, Square */
    div[data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important; 
        overflow-x: auto !important; 
        gap: 0px !important; 
        padding: 0px !important;
        align-items: flex-start !important;
    }
    div[data-testid="column"] {
        padding: 0px !important; margin: 0px !important; 
        min-width: 0px !important;
        flex: 0 0 auto !important;
    }
    
    /* 버튼 스타일 초기화 */
    div[data-testid="stHorizontalBlock"] button {
        width: 100% !important; padding: 0 !important; margin: 0 !important;
        background-color: transparent !important; border: none !important;
        border-radius: 0 !important; box-shadow: none !important;
    }

    /* 타일 내용 */
    .mini-card-container {
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        width: 100%; height: 100%;
    }
    .dw-active { background-color: #E3F2FD; } 
    
    /* [핵심] 모바일 타일 - 정사각형 & 10개 정렬 */
    @media only screen and (max-width: 600px) {
        /* 각 기둥을 화면의 10%로 고정 */
        div[data-testid="column"] {
            width: 10vw !important;
            flex: 0 0 10vw !important;
        }
        /* 글자 박스도 너비에 맞춰 높이 설정 (정사각형 효과) */
        .mini-char {
            width: 90% !important; 
            height: 9vw !important; /* 너비와 비슷하게 */
            font-size: 4.5vw !important;
            border-radius: 4px; 
            display: flex; justify-content: center; align-items: center;
            font-family: 'Noto Serif KR', serif; font-weight: bold;
            margin: 1px auto !important;
        }
        .mini-sipsin, .mini-unseong { display: none; } /* 공간 확보 위해 숨김 */
        .mini-age { font-size: 2.5vw !important; font-weight: bold; color: #555; margin-top: 2px; }
    }

    /* PC 타일 */
    @media only screen and (min-width: 601px) {
        div[data-testid="column"] { width: 45px !important; flex: 0 0 45px !important; }
        .mini-char {
            width: 36px; height: 36px; font-size: 1.2em; 
            border-radius: 8px; margin: 2px auto;
            display: flex; justify-content: center; align-items: center;
            font-family: 'Noto Serif KR', serif; font-weight: bold;
        }
        .mini-sipsin { font-size: 0.6em; color: #666; }
        .mini-unseong { font-size: 0.6em; color: #888; }
        .mini-age { font-size: 0.7em; font-weight: bold; margin-top: 3px; }
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# HTML 생성 함수
# ---------------------------------------------------------
def generate_pillar_html(title, stem, branch, s_list, b_list, is_luck=False):
    day_stem = s_list[2] 
    s_idx = get_element_idx(stem)
    b_idx = get_element_idx(branch)
    
    s_sipsin = get_sipsin(day_stem, stem)
    b_sipsin = get_sipsin(day_stem, branch)
    if title == "일주": s_sipsin = "본원"
    
    unseong = get_12unseong(day_stem, branch)
    hiddens = JIJANGGAN.get(branch, [])
    hiddens_html = f'<div class="jijanggan">{" ".join(hiddens)}</div>'
    
    col_idx = -1
    if title == "연주": col_idx = 0
    elif title == "월주": col_idx = 1
    elif title == "일주": col_idx = 2
    elif title == "시주": col_idx = 3
    
    stem_shinsal = get_shinsal(stem, 'stem', col_idx, s_list, b_list)
    branch_shinsal = get_shinsal(branch, 'branch', col_idx, s_list, b_list)
    pillar_shinsal = get_pillar_shinsal(stem, branch)
    
    badges_html = ""
    for s in stem_shinsal:
        color = "badge-good" if "귀인" in s or "삼기" in s or "공" in s else "badge-power"
        badges_html += f'<span class="badge {color}">{s}</span>'
    for s in pillar_shinsal:
        badges_html += f'<span class="badge badge-power">{s}</span>'
    for s in branch_shinsal:
        if s in ["역마","도화","화개"]: color = "badge-12"
        elif "귀인" in s or "천의" in s: color = "badge-good"
        elif s == "공망": color = "badge-gong"
        else: color = "badge-rel"
        badges_html += f'<span class="badge {color}">{s}</span>'
    
    card_cls = "luck-card" if is_luck else "pillar-card"
    
    return f"""<div class="{card_cls}"><div class="small-text">{title}</div><div class="small-text">{s_sipsin}</div><div class="char-box bg-{s_idx}">{stem}</div><div class="char-box bg-{b_idx}">{branch}</div>{hiddens_html}<div class="small-text">{b_sipsin}</div><div class="unseong-badge">{unseong}</div><div class="shinsal-container">{badges_html}</div></div>"""

def draw_mini_pillar(stem, branch, day_stem, top_label, bottom_label, is_active=False):
    s_idx = get_element_idx(stem)
    b_idx = get_element_idx(branch)
    s_sipsin = get_sipsin(day_stem, stem)
    b_sipsin = get_sipsin(day_stem, branch)
    unseong = get_12unseong(day_stem, branch)
    active_cls = "dw-active" if is_active else ""
    return f"""<div class="mini-card-container {active_cls}"><div class="mini-sipsin">{s_sipsin}</div><div class="mini-char bg-{s_idx}">{stem}</div><div class="mini-char bg-{b_idx}">{branch}</div><div class="mini-sipsin">{b_sipsin}</div><div class="mini-unseong">{unseong}</div><div class="mini-age">{bottom_label}</div></div>"""

# ---------------------------------------------------------
# 6. 메인 앱
# ---------------------------------------------------------
st.title("🌌 초정밀 만세력 V5.8")

if 'is_calculated' not in st.session_state: st.session_state.is_calculated = False
if 'db' not in st.session_state: st.session_state.db = load_db()

def reset_luck_view():
    st.session_state.show_daewoon = False
    st.session_state.show_seun = False
    st.session_state.sel_dw_idx = -1
    st.session_state.sel_seun_year = -1

if 'show_daewoon' not in st.session_state: st.session_state.show_daewoon = False
if 'show_seun' not in st.session_state: st.session_state.show_seun = False

with st.sidebar:
    st.header("🗂️ 명식 보관함")
    saved_list = st.session_state.db['이름'].tolist()
    selected_profile = st.selectbox("불러오기", ["(선택 안함)"] + saved_list)
    
    def_name, def_gender, def_date, def_time, def_basis, def_place, def_lat, def_lon = \
        "사용자", "여", dt.date(1998, 1, 27), "12:00", "표준시 (현대)", "Seoul", 37.5665, 126.9780

    if selected_profile != "(선택 안함)":
        row = st.session_state.db[st.session_state.db['이름'] == selected_profile].iloc[0]
        def_name = row['이름']
        def_gender = row['성별']
        def_date = dt.datetime.strptime(str(row['생년월일']), "%Y-%m-%d").date()
        def_time = row['시간']
        def_basis = row['시각기준']
        def_place = row['도시']
        def_lat = float(row['위도'])
        def_lon = float(row['경도'])

    st.divider()
    st.header("📝 정보 입력")
    name = st.text_input("이름", def_name)
    gender = st.radio("성별", ["남", "여"], index=0 if def_gender=="남" else 1, horizontal=True)
    birth_date = st.date_input("생년월일", def_date, min_value=dt.date(1, 1, 1), max_value=dt.date(2100, 12, 31))
    time_str = st.text_input("시간", def_time)
    basis = st.radio("기준", ["표준시 (현대)", "LMT (옛날/지역시)"], index=0 if "표준" in def_basis else 1)
    
    st.caption("장소")
    col_p1, col_p2 = st.columns([2,1])
    place = col_p1.text_input("도시", def_place, label_visibility="collapsed")
    if col_p2.button("검색"):
        lat, lon = geocode_osm(place)
        if lat:
            st.session_state.lat, st.session_state.lon = lat, lon
            st.success("OK")
            st.rerun()

    lat = st.number_input("위도", value=st.session_state.get('lat', def_lat), format="%.4f")
    lon = st.number_input("경도", value=st.session_state.get('lon', def_lon), format="%.4f")
    
    c1, c2 = st.columns(2)
    if c1.button("🔥 명식 뽑기", type="primary"):
        st.session_state.is_calculated = True
        reset_luck_view()
        st.rerun()
        
    if c2.button("💾 저장"):
        new_row = {
            "이름": name, "성별": gender, "생년월일": birth_date, "시간": time_str,
            "시각기준": basis, "도시": place, "위도": lat, "경도": lon
        }
        df = st.session_state.db
        if name in df['이름'].values:
            df.loc[df['이름'] == name, :] = list(new_row.values())
            st.toast(f"수정됨: {name}")
        else:
            new_df = pd.DataFrame([new_row])
            df = pd.concat([df, new_df], ignore_index=True)
            st.toast(f"저장됨: {name}")
        st.session_state.db = df
        save_db(df)
        st.rerun()

    if selected_profile != "(선택 안함)":
        if st.button(f"🗑️ 삭제"):
            df = st.session_state.db
            df = df[df['이름'] != selected_profile]
            st.session_state.db = df
            save_db(df)
            st.toast("삭제됨")
            st.rerun()

if st.session_state.is_calculated:
    try:
        b_time = parse_hms(time_str)
        naive = dt.datetime.combine(birth_date, b_time)
        if basis.startswith("표준시"):
            tz_str = TF.timezone_at(lat=lat, lng=lon) or "Asia/Seoul"
            local = naive.replace(tzinfo=ZoneInfo(tz_str))
            utc_dt = local.astimezone(dt.timezone.utc)
        else:
            utc_dt = naive.replace(tzinfo=dt.timezone.utc) - dt.timedelta(seconds=lon * 240.0)

        lat_dt, _ = apparent_solar_datetime(utc_dt, lon)
        jd_ut = jd_ut_from_utc(utc_dt)
        
        y_s, y_b, b_year = year_pillar(jd_ut)
        m_s, m_b, term_jd = month_pillar(jd_ut, y_s)
        d_s, d_b, _ = day_pillar(lat_dt)
        h_s, h_b = hour_pillar(lat_dt, d_s)
        
        s_list = [y_s, m_s, d_s, h_s]
        b_list = [y_b, m_b, d_b, h_b]
        
        y_idx = STEMS.index(y_s)
        is_yang = (y_idx % 2 == 0)
        is_man = (gender == "남")
        forward = (is_man and is_yang) or (not is_man and not is_yang)
        
        curr_idx = -1
        for i, (nm, deg, br) in enumerate(MAJOR_TERMS):
            if br == m_b: curr_idx = i; break
        
        if forward:
            nxt = (curr_idx + 1) % 12
            nxt_jd = swe.solcross_ut(MAJOR_TERMS[nxt][1], jd_ut, swe.FLG_SWIEPH)
            diff = nxt_jd - jd_ut
        else:
            diff = jd_ut - term_jd
        
        dw_num_float = diff / 3.0
        
        ms_idx = STEMS.index(m_s)
        mb_idx = BRANCHES.index(m_b)
        daewoon_raw = []
        for i in range(1, 11):
            offset = i if forward else -i
            ds = STEMS[(ms_idx + offset)%10]
            db = BRANCHES[(mb_idx + offset)%12]
            if i == 1: start_age = dw_num_float
            else: start_age = dw_num_float + (i-1)*10
            daewoon_raw.append({'s':ds, 'b':db, 'age':start_age})
        
        daewoon_visual = daewoon_raw[::-1]
        if 'sel_dw_idx' not in st.session_state: st.session_state.sel_dw_idx = 9

        sel_dw = daewoon_visual[st.session_state.sel_dw_idx]
        
        if 'sel_seun_year' not in st.session_state:
            st.session_state.sel_seun_year = b_year + int(sel_dw['age'])

        sel_seun = None
        seun_visual = []
        base_start_year = b_year + int(sel_dw['age'])
        for k in range(10):
            this_y = base_start_year + k
            off = (this_y - 1984)
            ss = STEMS[off%10]
            bb = BRANCHES[off%12]
            current_age_float = sel_dw['age'] + k
            item = {'y':this_y, 'age': current_age_float, 's':ss, 'b':bb}
            seun_visual.append(item)
            if this_y == st.session_state.sel_seun_year:
                sel_seun = item
        
        seun_visual = seun_visual[::-1]
        if sel_seun is None: sel_seun = seun_visual[-1]

        st.write("") 
        st.markdown(f"### 🌺 **{name}**님의 원국 ({basis})")
        
        dynamic_html = ""
        
        if st.session_state.show_seun and st.session_state.sel_seun_year != -1:
            this_y = st.session_state.sel_seun_year
            off = (this_y - 1984)
            ss = STEMS[off%10]
            bb = BRANCHES[off%12]
            dynamic_html += generate_pillar_html(f"세운({this_y})", ss, bb, s_list, b_list, is_luck=True)
            
        if st.session_state.show_daewoon and st.session_state.sel_dw_idx != -1:
            dw = daewoon_visual[st.session_state.sel_dw_idx]
            dynamic_html += generate_pillar_html("대운", dw['s'], dw['b'], s_list, b_list, is_luck=True)
            dynamic_html += '<div style="width: 15px; flex-shrink: 0;"></div>' 
            
        dynamic_html += generate_pillar_html("시주", h_s, h_b, s_list, b_list)
        dynamic_html += generate_pillar_html("일주", d_s, d_b, s_list, b_list)
        dynamic_html += generate_pillar_html("월주", m_s, m_b, s_list, b_list)
        dynamic_html += generate_pillar_html("연주", y_s, y_b, s_list, b_list)
        
        final_html = f'<div class="total-flex-container">{dynamic_html}</div>'
        st.markdown(final_html, unsafe_allow_html=True)

        st.divider()
        
        st.subheader("🌊 대운의 흐름 (우측통행 ⬅️)")
        st.caption(f"대운수: {dw_num_float:.2f} ({'순행' if forward else '역행'})")
        
        dw_cols = st.columns(10)
        for i, dw in enumerate(daewoon_visual):
            with dw_cols[i]:
                label = f"{dw['age']:.2f}세"
                if st.button(label, key=f"dw_btn_{i}", use_container_width=True):
                    st.session_state.sel_dw_idx = i
                    st.session_state.show_daewoon = True
                    st.session_state.show_seun = False 
                    st.session_state.sel_seun_year = -1
                    st.rerun()
                
                is_active = (i == st.session_state.sel_dw_idx) and st.session_state.show_daewoon
                card = draw_mini_pillar(dw['s'], dw['b'], d_s, "", label, is_active)
                st.markdown(card, unsafe_allow_html=True)

        if st.session_state.show_daewoon and st.session_state.sel_dw_idx != -1:
            sel_dw = daewoon_visual[st.session_state.sel_dw_idx]
            st.divider()
            st.markdown(f"#### 📅 **{sel_dw['s']}{sel_dw['b']}** 대운 기간의 세운 (⬅️)")
            
            seun_cols = st.columns(10)
            for k, item in enumerate(seun_visual):
                with seun_cols[k]:
                    age_disp = f"{item['age']:.1f}세"
                    btn_label = f"{item['y']}"
                    if st.button(btn_label, key=f"seun_btn_{k}", use_container_width=True):
                        st.session_state.sel_seun_year = item['y']
                        st.session_state.show_seun = True
                        st.rerun()
                        
                    is_sel = (item['y'] == st.session_state.sel_seun_year) and st.session_state.show_seun
                    card = draw_mini_pillar(item['s'], item['b'], d_s, "", f"{item['y']}<br>({age_disp})", is_sel)
                    st.markdown(card, unsafe_allow_html=True)

    except Exception as e:
        st.error(f"오류: {e}")
