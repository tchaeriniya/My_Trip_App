import json, re, uuid
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote, unquote, unquote_plus, urlparse, parse_qs

import requests
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Trip Planner", page_icon="🧳", layout="wide", initial_sidebar_state="collapsed")

DATA_FILE = Path("data/trips.json")
HTML = Path(__file__).parent / "map_template.html"
WEEK = "월화수목금토일"
CATS = {"맛집": ("🍽️", "#FF6B5E"), "관광": ("📸", "#3B82F6"), "쇼핑": ("🛍️", "#A855F7"),
        "숙소": ("🏨", "#10B981"), "기타": ("📍", "#14B8A6")}
COUNTRIES = {"일본": ("🇯🇵", "jp"), "태국": ("🇹🇭", "th"), "베트남": ("🇻🇳", "vn"), "대만": ("🇹🇼", "tw"),
             "홍콩": ("🇭🇰", "hk"), "마카오": ("🇲🇴", "mo"), "싱가포르": ("🇸🇬", "sg"), "필리핀": ("🇵🇭", "ph"),
             "인도네시아": ("🇮🇩", "id"), "말레이시아": ("🇲🇾", "my"), "중국": ("🇨🇳", "cn"), "괌": ("🇬🇺", "gu"),
             "튀르키예": ("🇹🇷", "tr"), "이탈리아": ("🇮🇹", "it"), "프랑스": ("🇫🇷", "fr"), "스페인": ("🇪🇸", "es"),
             "영국": ("🇬🇧", "gb"), "독일": ("🇩🇪", "de"), "스위스": ("🇨🇭", "ch"), "체코": ("🇨🇿", "cz"),
             "포르투갈": ("🇵🇹", "pt"), "그리스": ("🇬🇷", "gr"), "미국": ("🇺🇸", "us"), "캐나다": ("🇨🇦", "ca"),
             "호주": ("🇦🇺", "au"), "뉴질랜드": ("🇳🇿", "nz"), "기타(직접 입력)": ("🌍", "")}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

st.markdown("""<style>
.block-container{padding-top:1.2rem;padding-bottom:4rem;max-width:1100px}
#MainMenu,footer{visibility:hidden}
.stButton>button,.stDownloadButton>button,.stLinkButton>a{border-radius:12px;font-weight:600}
div[data-testid="stExpander"]{border-radius:14px;border:1px solid #E5E8EB}
div[data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:.5rem}
div[data-testid="stHorizontalBlock"]>div[data-testid="stColumn"],div[data-testid="stHorizontalBlock"]>div[data-testid="column"]{min-width:0!important}
.hero{background:linear-gradient(135deg,#3182F6,#6AA9FF);color:#fff;border-radius:20px;padding:18px 20px;margin:8px 0 14px}
.hero h2{margin:0;font-size:1.4rem;color:#fff;padding:0}.hero p{margin:4px 0 0;opacity:.9;font-size:.9rem}
</style>""", unsafe_allow_html=True)

# ---------- 저장/불러오기 ----------
def load():
    try: return json.loads(DATA_FILE.read_text("utf-8"))
    except Exception: return {}

def save():
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(st.session_state.trips, ensure_ascii=False), "utf-8")

for k, v in {"trips": load(), "cur": None, "fid": 0, "results": [], "ldraft": {}, "view": "edit"}.items():
    st.session_state.setdefault(k, v)
S = st.session_state
for _t in S.trips.values():
    _t.setdefault("flights", {})
    for _l in _t["days"]:
        for _p in _l:
            if _p["cat"] not in CATS: _p["cat"] = "기타"

# ---------- 구글맵 링크 / 장소 검색 (무료) ----------
F = r"(-?\d{1,3}\.\d+)"
def _extract(u):
    name = lat = lng = None
    m = re.search(r"/maps/(?:place|search)/([^/@?]+)", u)
    if m: name = unquote_plus(m.group(1))
    else:
        qs = parse_qs(urlparse(u).query); q = (qs.get("q") or qs.get("query") or [""])[0]
        if q and not re.fullmatch(r"\s*-?\d+\.\d+\s*,\s*-?\d+\.\d+\s*", q): name = q
    m = re.search(r"!3d" + F + r"!4d" + F, u) or re.search(r"@" + F + "," + F, u) or \
        re.search(r"[?&](?:q|query|ll|center)=(?:loc:)?" + F + r",\s*" + F, u)
    if m: lat, lng = float(m.group(1)), float(m.group(2))
    return name, lat, lng

@st.cache_data(ttl=3600, show_spinner=False)
def parse_gmaps(url):
    url = url.strip()
    if not url.startswith("http"): url = "https://" + url
    name, lat, lng = _extract(unquote(url))
    if lat is None or any(h in url for h in ("goo.gl", "g.co")):
        try:
            r = requests.get(url, headers=UA, timeout=10, allow_redirects=True)
            final = r.url
            if "consent." in urlparse(final).netloc:
                final = (parse_qs(urlparse(final).query).get("continue") or [final])[0]
            n2, la2, lo2 = _extract(unquote(final))
            if not n2:
                t = re.search(r"<title>(.*?)</title>", r.text, re.S)
                if t: n2 = re.sub(r"\s*-\s*Google\s*(지도|Maps)\s*$", "", t.group(1).strip()) or None
                if n2 in ("Google Maps", "Google 지도"): n2 = None
            if la2 is None:
                m = re.search(r"@" + F + "," + F, r.text)
                if m: la2, lo2 = float(m.group(1)), float(m.group(2))
            name, lat, lng = n2 or name, la2 if la2 is not None else lat, lo2 if la2 is not None else lng
        except Exception: pass
    if not name and lat is None: return None
    return {"name": name or "", "lat": lat, "lng": lng, "url": url, "address": ""}

@st.cache_data(ttl=3600, show_spinner=False)
def search_places(q, cc):
    p = {"q": q, "format": "jsonv2", "limit": 8, "accept-language": "ko,en"}
    if cc: p["countrycodes"] = cc
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search", params=p, headers={"User-Agent": "my-trip-planner/1.0"}, timeout=10).json()
    except Exception: return []
    out = []
    for it in r:
        parts = [x.strip() for x in it["display_name"].split(",")]
        name, addr = it.get("name") or parts[0], ", ".join(parts[1:4])
        out.append({"name": name, "address": addr, "lat": float(it["lat"]), "lng": float(it["lon"]),
                    "url": "https://www.google.com/maps/search/?api=1&query=" + quote(f"{name} {parts[1] if len(parts) > 1 else ''}")})
    return out

# ---------- 콜백 ----------
def days_of(tid, di): return S.trips[tid]["days"][di]
def cb_move(tid, di, i, d):
    l = days_of(tid, di); j = i + d
    if 0 <= j < len(l): l[i], l[j] = l[j], l[i]; save()
def cb_del(tid, di, i): days_of(tid, di).pop(i); save()
def cb_save(tid, di, i):
    p = days_of(tid, di)[i]; k = p["id"]
    p.update(name=S[f"n_{k}"].strip() or p["name"], cat=S[f"c_{k}"], time=S[f"t_{k}"].strip(), memo=S[f"m_{k}"].strip()); save()

# ---------- 여행 만들기 ----------
def create_form():
    with st.form("new_trip", clear_on_submit=True):
        name = st.text_input("여행 이름", placeholder="예: 2월 도쿄 가족여행")
        c = st.selectbox("국가", list(COUNTRIES))
        other = st.text_input("국가명 직접 입력") if c.startswith("기타") else ""
        d0 = date.today() + timedelta(days=30)
        rng = st.date_input("여행 기간", value=(d0, d0 + timedelta(days=3)), format="YYYY.MM.DD")
        if st.form_submit_button("여행 만들기", type="primary", use_container_width=True):
            if len(rng) != 2: st.error("시작일과 종료일을 모두 선택해주세요."); return
            n = (rng[1] - rng[0]).days + 1
            if n > 30: st.error("최대 30일까지 가능해요."); return
            country = other or c; flag, cc = COUNTRIES[c]
            tid = uuid.uuid4().hex[:8]
            S.trips[tid] = {"id": tid, "name": name or f"{country} 여행", "country": country, "flag": flag, "cc": cc,
                            "start": rng[0].isoformat(), "days": [[] for _ in range(n)]}
            S.cur = tid; save(); st.rerun()

# ---------- 지도 ----------
def map_view(t):
    start = date.fromisoformat(t["start"]); days = []
    for i, pl in enumerate(t["days"]):
        d = start + timedelta(days=i)
        days.append({"label": f"Day {i+1}", "date": f"{d.month}/{d.day} ({WEEK[d.weekday()]})", "top": t.get("flights", {}).get("out") if i == 0 else None,
                                          "bottom": t.get("flights", {}).get("ret") if i == len(t["days"]) - 1 else None, "places": [
            {"name": p["name"], "cat": p["cat"], "emoji": CATS[p["cat"]][0], "color": CATS[p["cat"]][1], "time": p.get("time", ""),
             "memo": p.get("memo", ""), "address": p.get("address", ""), "lat": p.get("lat"), "lng": p.get("lng"),
             "url": p.get("url") or "https://www.google.com/maps/search/?api=1&query=" + quote(p["name"])} for p in pl]})
    js = json.dumps(days, ensure_ascii=False).replace("</", "<\\/")
    components.html(HTML.read_text("utf-8").replace("__DATA__", js), height=680)
    st.caption("리스트를 스크롤하면 지도가 해당 장소로 이동해요. 지도는 OpenStreetMap 기반(무료)입니다.")

# ---------- 장소 추가 ----------
def add_ui(t, di):
    fid = S.fid
    with st.container(border=True):
        st.markdown("**➕ 장소 추가**")
        mode = st.radio("방법", ["🔗 구글맵 링크", "🔎 장소 검색", "✏️ 직접 입력"], horizontal=True, label_visibility="collapsed", key="mode")
        d = {}
        if mode.startswith("🔗"):
            link = st.text_input("구글맵 공유 링크 붙여넣기", key=f"l{fid}", placeholder="https://maps.app.goo.gl/...")
            if link:
                if S.ldraft.get("src") != link:
                    with st.spinner("장소 정보를 불러오는 중..."):
                        S.ldraft = {"src": link, "d": parse_gmaps(link)}
                d = S.ldraft["d"] or {}
                if not d: st.warning("링크에서 장소를 찾지 못했어요. 직접 입력으로 추가해 주세요.")
                elif d["lat"] is None: st.info("좌표를 읽지 못해 지도에는 표시되지 않아요. (긴 링크를 쓰면 해결돼요)")
        elif mode.startswith("🔎"):
            q = st.text_input("장소명", key=f"q{fid}", placeholder="예: 이치란 라멘 시부야")
            only = st.checkbox(f"{t['country']} 안에서만 검색", True) if t["cc"] else False
            if st.button("검색", use_container_width=True) and q:
                S.results = search_places(q, t["cc"] if only else "")
                if not S.results: st.warning("결과가 없어요. 구글맵 링크로 추가해 보세요.")
            if S.results:
                i = st.selectbox("결과 선택", range(len(S.results)), key=f"s{fid}",
                                 format_func=lambda i: f"{S.results[i]['name']} · {S.results[i]['address']}")
                d = S.results[i]
        else:
            link = st.text_input("구글맵 링크 (선택)", key=f"u{fid}"); d = {"url": link}
        sig = f"{mode}{d.get('lat')}{d.get('lng')}{d.get('name')}"
        name = st.text_input("장소명", value=d.get("name", ""), key=f"nm{fid}{sig}")
        cat = st.pills("카테고리", list(CATS), format_func=lambda c: f"{CATS[c][0]} {c}", default="맛집", key=f"ct{fid}") or "맛집"
        c1, c2 = st.columns([1, 2])
        tm = c1.text_input("시간", key=f"tm{fid}", placeholder="12:30")
        memo = c2.text_input("메모", key=f"mm{fid}", placeholder="예약 필수, 웨이팅 30분…")
        if st.button("일정에 추가", type="primary", use_container_width=True):
            if not name.strip(): st.error("장소명을 입력해주세요."); return
            days_of(t["id"], di).append({"id": uuid.uuid4().hex[:8], "name": name.strip(), "cat": cat, "time": tm.strip(), "memo": memo.strip(),
                "lat": d.get("lat"), "lng": d.get("lng"), "url": d.get("url", ""), "address": d.get("address", "")})
            S.fid += 1; S.results = []; S.ldraft = {}; save(); st.rerun()

FLD = [("no", "항공편명"), ("dep", "출발 공항"), ("arr", "도착 공항"), ("dep_time", "출발 시각"), ("arr_time", "도착 시각")]
def fk(tid, kind, f): return f"f_{tid}_{kind}_{f}"

def get_key():
    try: return st.secrets.get("AVIATIONSTACK_KEY", "")
    except Exception: return ""

def lookup_flight(code, d):
    key = get_key()
    if not key: return None, "nokey"
    code = re.sub(r"\s+", "", code).upper()
    for extra in ({"flight_date": d}, {}):
        try:
            r = requests.get("http://api.aviationstack.com/v1/flights", timeout=10,
                             params={"access_key": key, "flight_iata": code, **extra}).json()
        except Exception: continue
        if r.get("data"):
            dp, ar = r["data"][0]["departure"], r["data"][0]["arrival"]
            hm = lambda s: s[11:16] if s else ""
            return {"dep": dp.get("iata") or "", "arr": ar.get("iata") or "",
                    "dep_time": hm(dp.get("scheduled")), "arr_time": hm(ar.get("scheduled"))}, "ok"
    return None, "none"

def cb_lookup(tid, kind, d):
    res, st_ = lookup_flight(S[fk(tid, kind, "no")], d)
    if res:
        for f, v in res.items(): S[fk(tid, kind, f)] = v
        S[f"msg_{tid}_{kind}"] = "✅ 시간을 불러왔어요. 확인 후 저장을 눌러주세요."
    else:
        S[f"msg_{tid}_{kind}"] = ("⚠️ 자동 조회 설정이 없어요. 직접 입력해 주세요." if st_ == "nokey"
                                  else "⚠️ 항공편을 찾지 못했어요. 직접 입력해 주세요.")

def cb_fsave(tid, kind):
    v = {f: S[fk(tid, kind, f)].strip() for f, _ in FLD}; v["no"] = v["no"].upper()
    if any(v.values()): S.trips[tid]["flights"][kind] = v; save()

def cb_fdel(tid, kind):
    S.trips[tid]["flights"].pop(kind, None)
    for f, _ in FLD: S[fk(tid, kind, f)] = ""
    save()

def flight_box(t, kind, label, d):
    tid = t["id"]; f = t["flights"].get(kind)
    for fld, _ in FLD: S.setdefault(fk(tid, kind, fld), f.get(fld, "") if f else "")
    title = f"✈️ {label}" + (f" · {f['no']}  {f['dep']} {f['dep_time']} → {f['arr']} {f['arr_time']}" if f else " (눌러서 등록)")
    with st.expander(title):
        c1, c2 = st.columns([3, 2])
        c1.text_input("항공편명", key=fk(tid, kind, "no"), placeholder="예: KE703")
        c2.write(""); c2.write("")
        c2.button("⏱ 시간 자동조회", key=f"lk_{tid}_{kind}", on_click=cb_lookup, args=(tid, kind, d.isoformat()), use_container_width=True)
        if S.get(f"msg_{tid}_{kind}"): st.caption(S[f"msg_{tid}_{kind}"])
        a, b = st.columns(2)
        a.text_input("출발 공항", key=fk(tid, kind, "dep"), placeholder="ICN")
        b.text_input("도착 공항", key=fk(tid, kind, "arr"), placeholder="NRT")
        a.text_input("출발 시각", key=fk(tid, kind, "dep_time"), placeholder="09:30")
        b.text_input("도착 시각", key=fk(tid, kind, "arr_time"), placeholder="11:50")
        x = st.columns(2)
        x[0].button("저장", key=f"fs_{tid}_{kind}", on_click=cb_fsave, args=(tid, kind), type="primary", use_container_width=True)
        x[1].button("삭제", key=f"fd_{tid}_{kind}", on_click=cb_fdel, args=(tid, kind), use_container_width=True)

def edit_view(t):
    n = len(t["days"])
    if S.get("day") is None or S.day >= n: S.day = 0
    day = st.pills("일차", range(n), format_func=lambda i: f"Day {i+1}", key="day", label_visibility="collapsed")
    di = day if day is not None else 0
    d = date.fromisoformat(t["start"]) + timedelta(days=di)
    st.markdown(f"**Day {di+1}** · {d.month}/{d.day} ({WEEK[d.weekday()]})")
    if di == 0: flight_box(t, "out", "출국 항공편", date.fromisoformat(t["start"]))
    for i, p in enumerate(t["days"][di]):
        k = p["id"]; e = CATS[p["cat"]][0]
        with st.expander(f"{i+1}. {e} {p['name']}" + (f"  ·  {p['time']}" if p.get("time") else "")):
            if p.get("memo"): st.caption(f"📝 {p['memo']}")
            st.text_input("장소명", p["name"], key=f"n_{k}")
            a, b = st.columns(2)
            a.selectbox("카테고리", list(CATS), list(CATS).index(p["cat"]), key=f"c_{k}")
            b.text_input("시간", p.get("time", ""), key=f"t_{k}")
            st.text_area("메모", p.get("memo", ""), key=f"m_{k}")
            x = st.columns(4); tid = t["id"]
            x[0].button("저장", key=f"s_{k}", on_click=cb_save, args=(tid, di, i), use_container_width=True)
            x[1].button("↑", key=f"u_{k}", on_click=cb_move, args=(tid, di, i, -1), use_container_width=True)
            x[2].button("↓", key=f"d_{k}", on_click=cb_move, args=(tid, di, i, 1), use_container_width=True)
            x[3].button("🗑️", key=f"x_{k}", on_click=cb_del, args=(tid, di, i), use_container_width=True)
            st.link_button("Google 지도에서 열기", p.get("url") or "https://www.google.com/maps/search/?api=1&query=" + quote(p["name"]), use_container_width=True)
    if not t["days"][di]: st.caption("아직 장소가 없어요. 아래에서 추가해 보세요 👇")
    add_ui(t, di)
    if di == n - 1: flight_box(t, "ret", "귀국 항공편", date.fromisoformat(t["start"]) + timedelta(days=n - 1))

# ---------- 메인 ----------
st.markdown("## 🧳 Trip Planner")
if not S.trips:
    st.write("해외여행 일정을 만들어 볼까요?"); create_form(); st.stop()

ids = list(S.trips)
if S.cur not in S.trips: S.cur = ids[0]
a, b = st.columns([3, 2])
S.cur = a.selectbox("여행", ids, index=ids.index(S.cur), format_func=lambda i: f"{S.trips[i]['flag']} {S.trips[i]['name']}", label_visibility="collapsed")
with b.popover("＋ 새 여행", use_container_width=True): create_form()

t = S.trips[S.cur]; n = len(t["days"]); s = date.fromisoformat(t["start"]); e = s + timedelta(days=n - 1)
st.markdown(f"<div class='hero'><h2>{t['flag']} {t['name']}</h2><p>{t['country']} · {s:%Y.%m.%d} – {e:%m.%d} · {n-1}박 {n}일</p></div>", unsafe_allow_html=True)

view = st.segmented_control("보기", ["edit", "map"], format_func=lambda v: "✏️ 일정 짜기" if v == "edit" else "🗺️ 지도로 보기",
                            key="view", label_visibility="collapsed") or "edit"
map_view(t) if view == "map" else edit_view(t)

with st.expander("⚙️ 설정"):
    st.download_button("📥 일정 백업(JSON)", json.dumps(t, ensure_ascii=False, indent=1), f"{t['name']}.json", "application/json", use_container_width=True)
    if st.checkbox("이 여행을 삭제합니다") and st.button("삭제", type="primary"):
        del S.trips[S.cur]; S.cur = None; save(); st.rerun()
