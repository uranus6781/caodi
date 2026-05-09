import os
import re
import time
import datetime
import requests
from github import Github, Auth
from playwright.sync_api import sync_playwright
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

def get_team_logo(team_name):
    if not team_name or team_name == "Unknown": return ""
    return f"https://ui-avatars.com/api/?name={requests.utils.quote(team_name[:2])}&size=200&background=1565C0&color=ffffff&bold=true"

def parse_url_to_info(url):
    try:
        slug = url.split('/')[-1].split('?')[0]
        # Xử lý lấy tên đội từ slug (ví dụ: man-city-vs-arsenal-123456)
        clean_slug = re.sub(r'-\d+$', '', slug) # Bỏ ID số ở cuối
        if "-vs-" in clean_slug:
            parts = clean_slug.split("-vs-")
            nha = parts[0].replace("-", " ").title()
            khach = parts[1].replace("-", " ").title()
            return nha, khach
    except: pass
    return "Trận Đấu", "Sắp Đá"

def capture_stream(context, match_url):
    page = context.new_page()
    Stealth().apply_stealth_sync(page)
    streams = set()

    def process_url(url):
        u = url.lower()
        if any(k in u for k in [".m3u8", "100ycdn", "edgemaxcdn", "taoxanh", "rapidlive"]):
            if not any(bad in u for bad in ["ad", "banner", "loop", "waiting"]):
                streams.add(url)

    page.on("request", lambda req: process_url(req.url))
    try:
        page.goto(match_url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(10000) # Chờ lâu hơn để luồng kịp load
        if streams:
            best = sorted(list(streams), key=lambda s: ("100ycdn" in s)*10 + ("token" in s)*5, reverse=True)
            return best[0]
    except: pass
    finally: page.close()
    return None

def main():
    all_data = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=_HEADERS["User-Agent"])
        
        for channel in CHANNELS:
            page = context.new_page()
            try:
                print(f"🚀 Truy cập: {channel['url']}")
                page.goto(channel["url"], wait_until="load")
                page.wait_for_timeout(5000)
                
                # CÁCH TÌM LINK MỚI: Tìm tất cả thẻ <a> có chứa "-vs-" trong href
                links = []
                hrefs = page.eval_on_selector_all("a", "elements => elements.map(el => el.href)")
                for h in hrefs:
                    if "-vs-" in h and h not in links:
                        links.append(h)
                
                print(f"✅ Tìm thấy {len(links)} trận đấu.")
                
                for href in links[:10]: # Lấy 10 trận đầu tiên
                    nha, khach = parse_url_to_info(href)
                    print(f"🎬 Đang săn link: {nha} vs {khach}")
                    
                    stream = capture_stream(context, href)
                    if stream:
                        all_data.append({
                            "title": f"{nha} vs {khach}",
                            "time": datetime.datetime.now(VN_TZ).strftime("%H:%M"),
                            "logo": get_team_logo(nha),
                            "stream": stream
                        })
            except Exception as e:
                print(f"Lỗi quét: {e}")
            finally:
                page.close()
        browser.close()

    # Ghi file và push
    push_to_github(all_data)

def push_to_github(matches):
    content = "#EXTM3U\n"
    if not matches:
        content += '#EXTINF:-1 tvg-logo="" group-title="Hệ thống",Hiện chưa có trận trực tiếp hoặc lỗi bot\n'
        content += f'{WAITING_VIDEO_URL}\n'
    else:
        for m in matches:
            content += f'#EXTINF:-1 tvg-id="" tvg-logo="{m["logo"]}" group-title="Bóng Đá Trực Tiếp",{m["time"]} | {m["title"]}\n'
            content += f'{m["stream"]}\n'

    auth = Auth.Token(GITHUB_TOKEN)
    g = Github(auth=auth)
    repo = g.get_repo(REPO_NAME)
    msg = f"⚽ Update: {datetime.datetime.now(VN_TZ).strftime('%H:%M %d/%m/%Y')}"
    
    try:
        f_obj = repo.get_contents(M3U_FILE_PATH)
        repo.update_file(f_obj.path, msg, content, f_obj.sha)
    except:
        repo.create_file(M3U_FILE_PATH, msg, content)
    print("✅ Đã đẩy file lên GitHub.")

if __name__ == "__main__":
    main()
