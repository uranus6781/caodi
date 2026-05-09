import os
import re
import time
import json
import datetime
import requests

from github import Github
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from playwright_stealth import Stealth

# =========================================================
# CONFIG
# =========================================================
CHANNELS = [
    {"id": "buncha", "name": "Bún Chả TV", "url": "https://bunchatv4.net/truc-tiep-bong-da-xoilac-tv", "base_url": "https://bunchatv4.net"},
    {"id": "hoiquan", "name": "Hội Quán TV", "url": "https://sv2.hoiquan3.live/lich-thi-dau/bong-da", "base_url": "https://sv2.hoiquan3.live"}
]

FILE_PATH = "bongda.json"
WAITING_VIDEO_URL = "https://example.com/waiting.mp4"
LIMIT_MATCHES = 10  
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))
GITHUB_TOKEN = os.getenv("GH_TOKEN")
REPO_NAME = os.getenv("GH_REPO", "Eternal161/dausoco")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

# =========================================================
# LOGO & PARSE (Giữ nguyên logic của bạn)
# =========================================================
def get_team_logo(team_name):
    if not team_name or team_name == "Unknown": return ""
    return f"https://ui-avatars.com/api/?name={requests.utils.quote(team_name[:2])}&size=200&background=1565C0&color=ffffff&bold=true"

def parse_url_to_info(url):
    try:
        parts = url.rstrip('/').split('/')
        slug = next((p.split('?')[0] for p in reversed(parts) if "-vs-" in p), "")
        if not slug: return "Unknown", "Unknown", "Chưa có lịch"
        slug = re.sub(r'-\d{6,}$', '', slug)
        time_match = re.search(r"-(\d{4}-\d{2}-\d{2}-\d{4})$", slug)
        if time_match:
            t = time_match.group(1)
            thoi_gian = f"{t[0:2]}:{t[2:4]} {t[5:7]}/{t[8:10]}/{t[11:15]}"
            teams_slug = slug[:slug.rfind("-" + t)]
        else:
            thoi_gian = "Unknown"; teams_slug = slug
        teams = teams_slug.split("-vs-", 1)
        return teams[0].replace("-", " ").title().strip(), teams[1].replace("-", " ").title().strip() if len(teams) > 1 else "Unknown", thoi_gian
    except: return "Unknown", "Unknown", "Unknown"

# =========================================================
# CAPTURE STREAM (Đã sửa lỗi cấu trúc)
# =========================================================
def capture_stream(context, match_url):
    page = context.new_page()
    Stealth().apply_stealth_sync(page)
    streams = set()

    def process_url(url):
        u = url.lower()
        if any(bad in u for bad in [".mp4", ".jpg", ".png", "waiting", "google", "ads-"]): return
        if any(k in u for k in [".m3u8", "wssession", "sign=", "token=", "taoxanh", "100ycdn", "edgemax"]):
            streams.add(url)
            print(f" 🎯 TÓM ĐƯỢC: {url[:70]}...")

    page.on("request", lambda req: process_url(req.url))
    page.on("response", lambda res: process_url(res.url))

    try:
        page.goto(match_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)

        # Click kích hoạt luồng
        frames = page.frames
        for frame in frames:
            try:
                box = frame.frame_element().bounding_box()
                if box:
                    page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
            except: continue

        deadline = time.time() + 15
        while time.time() < deadline:
            if any(k in "".join(streams).lower() for k in ["token", "sign", "wssession"]): break
            time.sleep(1)
    except: pass
    finally:
        page.screenshot(path="last_debug.png")
        page.close()

    if not streams: return None

    # BỘ CHẤM ĐIỂM (Nằm bên trong hàm)
    scored_streams = []
    for s in streams:
        score = 0
        low = s.lower()
        if "100ycdn" in low: score += 6000
        if "edgemax" in low or "hqtv" in low: score += 5000
        if any(k in low for k in ["token=", "sign=", "wssession="]): score += 2000
        if ".m3u8" in low: score += 500
        scored_streams.append((score, s))
    
    scored_streams.sort(key=lambda x: x[0], reverse=True)
    print(f" ✅ CHỐT LINK: {scored_streams[0][1][:70]}...")
    return scored_streams[0][1]

# =========================================================
# OUTPUT & PUSH (JSON + M3U)
# =========================================================
def json_to_m3u(json_content):
    data = json.loads(json_content)
    lines = ["#EXTM3U", f"#PLAYLISTNAME: Sáng TV - {data.get('last_updated')}", ""]
    for c_id in ["buncha", "hoiquan"]:
        for m in data.get(c_id, []):
            url = m.get("stream_url")
            if url:
                lines.append(f'#EXTINF:-1 tvg-logo="{m["logo_nha"]}" group-title="{c_id.upper()}", {m["title"]}')
                lines.append(url)
    return "\n".join(lines)

def push_to_github(json_content):
    if not GITHUB_TOKEN: return
    m3u_content = json_to_m3u(json_content)
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)
    now = datetime.datetime.now(VN_TZ).strftime("%H:%M %d/%m/%Y")
    for f_path, content in {"bongda.json": json_content, "bongda.m3u": m3u_content}.items():
        try:
            existing = repo.get_contents(f_path)
            repo.update_file(existing.path, f"⚽ Update {f_path}: {now}", content, existing.sha)
        except:
            repo.create_file(f_path, f"✅ Create {f_path}: {now}", content)

# =========================================================
# SCRAPE MAIN
# =========================================================
def scrape_and_push():
    all_data = {"buncha": [], "hoiquan": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=_HEADERS["User-Agent"])

        for channel in CHANNELS:
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            try:
                page.goto(channel["url"], wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
                for _ in range(3): page.mouse.wheel(0, 2000); page.wait_for_timeout(500)
                
                links = []
                seen = set()
                for el in page.locator("a[href*='-vs-']").all():
                    href = el.get_attribute("href")
                    if href and "-vs-" in href and href not in seen:
                        seen.add(href)
                        links.append(href if href.startswith("http") else f"{channel['base_url'].rstrip('/')}/{href.lstrip('/')}")
                
                for idx, href in enumerate(links[:LIMIT_MATCHES]):
                    doi_nha, doi_khach, thoi_gian = parse_url_to_info(href)
                    is_live = False
                    status = "Chờ đợi"
                    try:
                        m_time = datetime.datetime.strptime(thoi_gian, "%H:%M %d/%m/%Y").replace(tzinfo=VN_TZ)
                        diff = (datetime.datetime.now(VN_TZ) - m_time).total_seconds() / 60
                        if -10 <= diff <= 130: is_live = True; status = "Đang trực tiếp 🔴"
                    except: pass

                    match_info = {
                        "title": f"{doi_nha} vs {doi_khach}",
                        "thoi_gian": thoi_gian, "trang_thai": status, "is_live": is_live,
                        "logo_nha": get_team_logo(doi_nha), "stream_url": WAITING_VIDEO_URL, "link_xem": href
                    }
                    all_data[channel["id"]].append(match_info)
            except Exception as e: print(f"Lỗi quét {channel['id']}: {e}")
            finally: page.close()

        # Bắt luồng cho các trận Live
        for c_id in all_data:
            for m in all_data[c_id]:
                if m["is_live"]:
                    print(f"🎥 Đang bắt luồng: {m['title']}")
                    s_url = capture_stream(context, m["link_xem"])
                    if s_url: m["stream_url"] = s_url

        browser.close()
    
    push_to_github(json.dumps(all_data, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    scrape_and_push()
