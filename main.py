import os
import re
import time
import datetime
import requests
from github import Github
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from playwright_stealth import Stealth

# =========================================================
# CONFIG
# =========================================================
CHANNELS = [
    {
        "id": "hoiquan",
        "name": "Hội Quán TV",
        "url": "https://sv2.hoiquan3.live/lich-thi-dau/bong-da",
        "base_url": "https://sv2.hoiquan3.live"
    }
]

M3U_FILE_PATH = "bongda.m3u"
WAITING_VIDEO_URL = "https://example.com/waiting.mp4"
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

GITHUB_TOKEN = os.getenv("GH_TOKEN")
REPO_NAME = os.getenv("GH_REPO", "uranus6781/caodi")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

# =========================================================
# LOGO & PARSE (Giữ nguyên logic thông minh của bạn)
# =========================================================
def get_team_logo(team_name):
    if not team_name or team_name == "Unknown": return ""
    return f"https://ui-avatars.com/api/?name={requests.utils.quote(team_name[:2])}&size=200&background=1565C0&color=ffffff&bold=true"

def parse_url_to_info(url):
    try:
        parts = url.rstrip('/').split('/')
        slug = next((p.split('?')[0] for p in reversed(parts) if "-vs-" in p), "")
        if not slug: return "Unknown", "Unknown", "Unknown"
        
        slug = re.sub(r'-\d{6,}$', '', slug)
        time_match = re.search(r"-(\d{4}-\d{2}-\d{2}-\d{4})$", slug)
        thoi_gian = f"{time_match.group(1)[0:2]}:{time_match.group(1)[2:4]}" if time_match else "LIVE"
        
        teams_slug = slug[:slug.rfind("-" + time_match.group(1))] if time_match else slug
        teams = teams_slug.split("-vs-", 1)
        return teams[0].replace("-", " ").title(), teams[1].replace("-", " ").title() if len(teams)>1 else "Unknown", thoi_gian
    except: return "Unknown", "Unknown", "Unknown"

# =========================================================
# CAPTURE STREAM (Dùng Playwright để săn m3u8)
# =========================================================
def capture_stream(context, match_url):
    page = context.new_page()
    Stealth().apply_stealth_sync(page)
    streams = set()

    def process_url(url):
        u = url.lower()
        if any(bad in u for bad in [".mp4", ".jpg", ".png", "waiting", "ad", "banner"]): return
        if any(k in u for k in [".m3u8", "100ycdn", "edgemaxcdn", "taoxanh", "rapidlive"]):
            streams.add(url)

    page.on("request", lambda req: process_url(req.url))
    try:
        page.goto(match_url, wait_until="load", timeout=45000)
        page.wait_for_timeout(5000) # Chờ để bắt link nhảy ra
        
        if streams:
            # Chọn link có điểm cao nhất (ưu tiên 100ycdn hoặc m3u8 có token)
            best = sorted(list(streams), key=lambda s: ("100ycdn" in s) + ("token" in s), reverse=True)
            return best[0]
    except: pass
    finally: page.close()
    return None

# =========================================================
# XUẤT M3U & PUSH GITHUB
# =========================================================
def push_m3u_to_github(matches):
    content = "#EXTM3U\n"
    for m in matches:
        content += f'#EXTINF:-1 tvg-id="" tvg-logo="{m["logo"]}" group-title="Bóng Đá Trực Tiếp",{m["time"]} | {m["title"]}\n'
        content += f'{m["stream"]}\n'

    if not GITHUB_TOKEN:
        with open(M3U_FILE_PATH, "w", encoding="utf-8") as f: f.write(content)
        return

    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)
    msg = f"⚽ Update M3U: {datetime.datetime.now(VN_TZ).strftime('%H:%M %d/%m/%Y')}"
    try:
        f = repo.get_contents(M3U_FILE_PATH)
        repo.update_file(f.path, msg, content, f.sha)
    except:
        repo.create_file(M3U_FILE_PATH, msg, content)

def main():
    all_live_matches = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=_HEADERS["User-Agent"])
        
        for channel in CHANNELS:
            page = context.new_page()
            try:
                page.goto(channel["url"], wait_until="domcontentloaded")
                links = [el.get_attribute("href") for el in page.locator("a[href*='-vs-']").all()]
                
                for href in list(set(links))[:10]:
                    if not href.startswith("http"): href = channel["base_url"] + href
                    nha, khach, gio = parse_url_to_info(href)
                    
                    print(f"🔍 Đang kiểm tra: {nha} vs {khach}")
                    stream = capture_stream(context, href)
                    
                    all_live_matches.append({
                        "title": f"{nha} vs {khach}",
                        "time": gio,
                        "logo": get_team_logo(nha),
                        "stream": stream if stream else WAITING_VIDEO_URL
                    })
            except Exception as e: print(f"Lỗi: {e}")
            finally: page.close()
        browser.close()
    
    push_m3u_to_github(all_live_matches)

if __name__ == "__main__":
    main()
