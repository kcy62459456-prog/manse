import math
import datetime as dt
from zoneinfo import ZoneInfo
import requests
import streamlit as st
from timezonefinder import TimezoneFinder
import swisseph as swe

# ---------------------------------------------------------
# 1. 기초 데이터
# ---------------------------------------------------------
STEMS = ["甲","乙","丙","丁","戊","己","庚","辛","壬","癸"]
BRANCHES = ["子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"]

# 오행 (0:목, 1:화, 2:토, 3:금, 4:수)
STEM_ELEMENTS = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]  
BRANCH_ELEMENTS = [4, 2, 0, 0, 2, 1, 1, 2, 3, 3, 2, 4]

# 지장간
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

# ---------------------------------------------------------
# 3. 천문 계산
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

# ---------------------------------------------------------
# 4. UI / CSS 스타일링 (색상 리마스터)
# ---------------------------------------------------------
st.set_page_config(page_title="프리미엄 만세력", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;500;700&family=Noto+Serif+KR:wght@400;700&display=swap');
    
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
    
    /* ------------------------------ */
    /* 1. 메인 카드 (4주) 스타일 */
    /* ------------------------------ */
    .pillar-card {
        background-color: transparent; padding: 5px;
        text-align: center; display: flex; flex-direction: column; align-items: center; gap: 8px;
    }
    
    /* [색상 업데이트] 더 진하고 선명하게 */
    /* 목: 아주 진한 초록 */
    .bg-0 { background-color: #E8F5E9; color: #1B5E20; border: 1px solid #C8E6C9; } 
    /* 화: 진한 붉은색 */
    .bg-1 { background-color: #FFEBEE; color: #B71C1C; border: 1px solid #FFCDD2; } 
    /* 토: 진한 황토색/갈색 (가독성 UP) */
    .bg-2 { background-color: #FFFDE7; color: #AF601A; border: 1px solid #FFF9C4; } 
    /* 금: 진한 차콜 그레이 (흰색과 대비) */
    .bg-3 { background-color: #FAFAFA; color: #424242; border: 1px solid #BDBDBD; } 
    /* 수: 블랙 + 화이트 (유지) */
    .bg-4 { background-color: #212121; color: #FFFFFF; border: 1px solid #424242; } 

    .char-box {
        width: 70px; height: 70px; border-radius: 18px;
        display: flex; justify-content: center; align-items: center;
        font-family: 'Noto Serif KR', serif; font-size: 2.2em; font-weight: bold;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05); margin: 0 auto;
    }

    .small-text { font-size: 0.85em; color: #555; font-weight: 500; margin-bottom: 2px;}
    .unseong-badge { 
        font-size: 0.8em; color: #2c3e50; background-color: #f1f3f5; 
        padding: 3px 8px; border-radius: 12px; font-weight: bold;
    }
    .jijanggan {
        font-size: 0.75em; color: #777; letter-spacing: 2px;
        margin-top: -2px; margin-bottom: 2px;
    }
    
    /* ------------------------------ */
    /* 2. 미니 카드 (대운/세운) 스타일 */
    /* ------------------------------ */
    .mini-card-container {
        display: flex; flex-direction: column; align-items: center;
        background: #fff; border-radius: 8px; padding: 10px 2px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #eee;
        cursor: pointer; transition: 0.2s;
        margin-bottom: 5px; width: 100%;
    }
    .mini-card-container:hover { transform: translateY(-3px); box-shadow: 0 4px 8px rgba(0,0,0,0.15); }
    
    /* 선택된 대운 강조 */
    .dw-active { border: 2px solid #2196F3; background-color: #E3F2FD; }

    .mini-sipsin { font-size: 0.7em; color: #666; margin-bottom: 2px; white-space: nowrap; }
    .mini-char {
        width: 40px; height: 40px; border-radius: 10px;
        display: flex; justify-content: center; align-items: center;
        font-family: 'Noto Serif KR', serif; font-size: 1.4em; font-weight: bold;
        margin: 2px 0;
    }
    .mini-unseong { font-size: 0.7em; color: #888; margin-top: 2px; }
    .mini-age { font-size: 0.8em; font-weight: bold; color: #333; margin-top: 5px; }
    
</style>
""", unsafe_allow_html=True)

# 메인 4주 그리기 함수
def draw_pillar_main(title, stem, branch, day_stem):
    s_idx = get_element_idx(stem)
    b_idx = get_element_idx(branch)
    s_sipsin = get_sipsin(day_stem, stem) if title != "일주" else "본원"
    b_sipsin = get_sipsin(day_stem, branch)
    unseong = get_12unseong(day_stem, branch)
    hiddens = JIJANGGAN.get(branch, [])
    hidden_str = " ".join(hiddens)

    html = f"""
    <div class="pillar-card">
        <div class="small-text">{title}</div>
        <div class="small-text">{s_sipsin}</div>
        <div class="char-box bg-{s_idx}">{stem}</div>
        <div class="char-box bg-{b_idx}">{branch}</div>
        <div class="jijanggan">{hidden_str}</div>
        <div class="small-text">{b_sipsin}</div>
        <div class="unseong-badge">{unseong}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# 대운/세운용 미니 카드 그리기 함수
def draw_mini_pillar(stem, branch, day_stem, top_label, bottom_label, is_active=False):
    s_idx = get_element_idx(stem)
    b_idx = get_element_idx(branch)
    s_sipsin = get_sipsin(day_stem, stem)
    b_sipsin = get_sipsin(day_stem, branch)
    unseong = get_12unseong(day_stem, branch)
    
    active_cls = "dw-active" if is_active else ""
    
    html = f"""
    <div class="mini-card-container {active_cls}">
        <div class="mini-sipsin">{s_sipsin}</div>
        <div class="mini-char bg-{s_idx}">{stem}</div>
        <div class="mini-char bg-{b_idx}">{branch}</div>
        <div class="mini-sipsin">{b_sipsin}</div>
        <div class="mini-unseong">{unseong}</div>
        <div class="mini-age">{bottom_label}</div>
    </div>
    """
    return html

# ---------------------------------------------------------
# 5. 메인 앱
# ---------------------------------------------------------
st.title("🌟 프리미엄 만세력 V2 (Bold)")

if 'is_calculated' not in st.session_state:
    st.session_state.is_calculated = False

with st.sidebar:
    st.header("사주 정보 입력")
    name = st.text_input("이름", "사용자")
    gender = st.radio("성별", ["남", "여"], horizontal=True)
    birth_date = st.date_input("생년월일", dt.date(1998, 1, 27))
    time_str = st.text_input("태어난 시각 (HH:MM)", "12:00")
    
    st.subheader("출생지")
    place = st.text_input("도시 검색", "Seoul")
    if st.button("장소 검색"):
        lat, lon = geocode_osm(place)
        if lat:
            st.session_state.lat, st.session_state.lon = lat, lon
            st.success("위치 저장됨")
    
    lat = st.number_input("위도", value=st.session_state.get('lat', 37.5665), format="%.4f")
    lon = st.number_input("경도", value=st.session_state.get('lon', 126.9780), format="%.4f")
    
    if st.button("명식 뽑기", type="primary"):
        st.session_state.is_calculated = True
        st.session_state.sel_dw_idx = 0 

if st.session_state.is_calculated:
    try:
        # 1. 계산
        b_time = parse_hms(time_str)
        naive = dt.datetime.combine(birth_date, b_time)
        tz_str = TF.timezone_at(lat=lat, lng=lon) or "Asia/Seoul"
        utc_dt = naive.replace(tzinfo=ZoneInfo(tz_str)).astimezone(dt.timezone.utc)
        lat_dt, _ = apparent_solar_datetime(utc_dt, lon)
        jd_ut = jd_ut_from_utc(utc_dt)
        
        y_s, y_b, b_year = year_pillar(jd_ut)
        m_s, m_b, term_jd = month_pillar(jd_ut, y_s)
        d_s, d_b, _ = day_pillar(lat_dt)
        h_s, h_b = hour_pillar(lat_dt, d_s)
        
        # 2. 메인 명식 출력
        st.write("") 
        st.markdown(f"### 🌺 **{name}**님의 원국")
        
        col1, col2, col3, col4 = st.columns(4)
        with col4: draw_pillar_main("연주", y_s, y_b, d_s)
        with col3: draw_pillar_main("월주", m_s, m_b, d_s)
        with col2: draw_pillar_main("일주", d_s, d_b, d_s)
        with col1: draw_pillar_main("시주", h_s, h_b, d_s)
        
        st.divider()
        
        # 3. 대운 계산
        y_idx = STEMS.index(y_s)
        is_yang = (y_idx % 2 == 0)
        is_man = (gender == "남")
        forward = (is_man and is_yang) or (not is_man and not is_yang)
        
        # 대운수
        curr_idx = -1
        for i, (nm, deg, br) in enumerate(MAJOR_TERMS):
            if br == m_b: curr_idx = i; break
        
        if forward:
            nxt = (curr_idx + 1) % 12
            nxt_jd = swe.solcross_ut(MAJOR_TERMS[nxt][1], jd_ut, swe.FLG_SWIEPH)
            diff = nxt_jd - jd_ut
        else:
            diff = jd_ut - term_jd
        dw_num = max(1, round(diff / 3))
        
        # 4. 대운 UI (우측통행)
        st.subheader("🌊 대운의 흐름 (우측통행 ⬅️)")
        st.caption(f"대운수: {dw_num} ({'순행' if forward else '역행'})")
        
        # 데이터 준비
        ms_idx = STEMS.index(m_s)
        mb_idx = BRANCHES.index(m_b)
        daewoon_raw = []
        for i in range(1, 11):
            offset = i if forward else -i
            ds = STEMS[(ms_idx + offset)%10]
            db = BRANCHES[(mb_idx + offset)%12]
            age = dw_num + (i-1)*10
            if i==1: age = dw_num
            daewoon_raw.append({'s':ds, 'b':db, 'age':age})
        
        daewoon_visual = daewoon_raw[::-1]
            
        if 'sel_dw_idx' not in st.session_state: st.session_state.sel_dw_idx = 9

        dw_cols = st.columns(10)
        for i, dw in enumerate(daewoon_visual):
            with dw_cols[i]:
                if st.button(f"{dw['age']}세", key=f"dw_btn_{i}", use_container_width=True):
                    st.session_state.sel_dw_idx = i
                    st.rerun()
                
                is_active = (i == st.session_state.sel_dw_idx)
                card_html = draw_mini_pillar(
                    dw['s'], dw['b'], d_s, 
                    top_label="", 
                    bottom_label=f"{dw['age']}세",
                    is_active=is_active
                )
                st.markdown(card_html, unsafe_allow_html=True)

        # 5. 세운 UI (우측통행)
        st.divider()
        sel = daewoon_visual[st.session_state.sel_dw_idx]
        st.markdown(f"#### 📅 **{sel['s']}{sel['b']}** 대운 기간의 세운 (⬅️)")
        
        seun_cols = st.columns(10)
        start_y = b_year + sel['age'] - 1
        
        seun_raw = []
        for k in range(10):
            this_y = start_y + k
            off = (this_y - 1984)
            ss = STEMS[off%10]
            bb = BRANCHES[off%12]
            seun_raw.append({'y':this_y, 'age':sel['age']+k, 's':ss, 'b':bb})
            
        seun_visual = seun_raw[::-1]
        
        for k, item in enumerate(seun_visual):
            with seun_cols[k]:
                card_html = draw_mini_pillar(
                    item['s'], item['b'], d_s,
                    top_label="",
                    bottom_label=f"{item['y']}<br>({item['age']}세)",
                    is_active=False
                )
                st.markdown(card_html, unsafe_allow_html=True)

    except Exception as e:
        st.error(f"오류 발생: {e}")