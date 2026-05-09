import os
import re
import time
import datetime
import requests
from github import Github, Auth
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from playwright_stealth import Stealth

# =========================================================
# CONFIG REPO & CHANNELS
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
# Cập nhật repo mới của Huy ở đây
REPO_NAME = os.getenv("GH_REPO", "uranus6781/caodi")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

# =========================================================
# UTILS (LOGO & PARSE)
# =========================================================
def get_team_logo(team_name):
    if not team_name or team_name == "Unknown": return ""
    return f"https://ui-avatars.com/api/?name={requests.utils.quote(team_name[:2])}&size=200&background=1565C0&color=ffffff&bold=true"

def parse_url_to_info(url):
    try:
        parts = url.rstrip('/').split('/')
        slug = next((p.split('?')[0] for p in reversed(parts) if "-vs-" in p), "")
        if not slug: return "Unknown", "Unknown", "LIVE"
        
        slug = re.sub(r'-\d{6,}$', '', slug)
        time_match = re.search(r"-(\d{4}-\d{2}-\d{2}-\d{4})$", slug)
        thoi_gian = f"{time_match.group(1)[0:2]}:{time_match.group(1)[2:4]}" if time_match else "LIVE"
        
        teams_slug = slug[:slug.rfind("-" + time_match.group(1))] if time_match else slug
        teams = teams_slug.split("-vs-", 1)
        return teams[0].replace("-", " ").title(), teams[1].replace("-", " ").title() if len(teams)>1 else "Unknown", thoi_gian
    except: return "Unknown", "Unknown", "LIVE"

# =========================================================
# SĂN LINK M3U8 (PLAYWRIGHT)
# =========================================================
def capture_stream(context, match_url):
    page = context.new_page()
    Stealth().apply_stealth_sync(page)
    streams = set()

    def process_url(url):
        u = url.lower()
        # Loại bỏ rác quảng cáo
        if any(bad in u for bad in [".mp4", ".jpg", ".png", "waiting", "ad", "banner", "loop"]): return
        # Tóm link m3u8 và các server xịn của Hội Quán
        if any(k in u for k in [".m3u8", "100ycdn", "edgemaxcdn", "taoxanh", "rapidlive", "wssession="]):
            streams.add(url)

    page.on("request", lambda req: process_url(req.url))
    try:
        page.goto(match_url, wait_until="load", timeout=50000)
        # Giả lập click vào giữa màn hình để kích hoạt player nếu cần
        page.mouse.click(500, 500) 
        page.wait_for_timeout(8000) # Chờ load luồng
        
        if streams:
            # Ưu tiên server 100ycdn (thường là link xịn nhất của Hội Quán)
            best = sorted(list(streams), key=lambda s: ("100ycdn" in s)*10 + ("token" in s)*5 + ("m3u8" in s), reverse=True)
            return best[0]
    except: pass
    finally: page.close()
    return None

# =========================================================
# PUSH M3U TO GITHUB
# =========================================================
def push_to_github(matches):
    content = "#EXTM3U\n"
    if not matches:
        content += '#EXTINF:-1 tvg-logo="" group-title="Hệ thống",Hiện chưa có trận trực tiếp\n'
        content += f'{WAITING_VIDEO_URL}\n'
    else:
        for m in matches:
            content += f'#EXTINF:-1 tvg-id="" tvg-logo="{m["logo"]}" group-title="Bóng Đá Trực Tiếp",{m["time"]} | {m["title"]}\n'
            content += f'{m["stream"]}\n'

    if not GITHUB_TOKEN:
        print("⚠️ Không có token. Ghi file tại chỗ.")
        with open(M3U_FILE_PATH, "w", encoding="utf-8") as f: f.write(content)
        return

    try:
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth)
        repo = g.get_repo(REPO_NAME)
        msg = f"⚽ Cập nhật M3U: {datetime.datetime.now(VN_TZ).strftime('%H:%M %d/%m/%Y')}"
        
        try:
            f_obj = repo.get_contents(M3U_FILE_PATH)
            repo.update_file(f_obj.path, msg, content, f_obj.sha)
            print(f"✅ Đã cập nhật {M3U_FILE_PATH}")
        except:
            repo.create_file(M3U_FILE_PATH, msg, content)
            print(f"✅ Đã tạo mới {M3U_FILE_PATH}")
    except Exception as e:
        print(f"❌ Lỗi Push GitHub: {e}")

def main():
    all_data = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=_HEADERS["User-Agent"])
        
        for channel in CHANNELS:
            page = context.new_page()
            try:
                page.goto(channel["url"], wait_until="domcontentloaded")
                links = list(set([el.get_attribute("href") for el in page.locator("a[href*='-vs-']").all()]))
                
                for href in links[:12]: # Giới hạn 12 trận để tránh bot chạy quá lâu
                    if not href.startswith("http"): href = channel["base_url"] + href
                    nha, khach, gio = parse_url_to_info(href)
                    
                    print(f"🎬 Săn link: {nha} vs {khach}")
                    stream = capture_stream(context, href)
                    
                    all_data.append({
                        "title": f"{nha} vs {khach}",
                        "time": gio,
                        "logo": get_team_logo(nha),
                        "stream": stream if stream else WAITING_VIDEO_URL
                    })
            except: pass
            finally: page.close()
        browser.close()
    
    push_to_github(all_data)

if __name__ == "__main__":
    main()
