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
# CONFIGURATION
# =========================================================
CHANNELS = [
    {"id": "buncha", "name": "Bún Chả TV", "url": "https://bunchatv4.net/truc-tiep-bong-da-xoilac-tv", "base_url": "https://bunchatv4.net"},
    {"id": "hoiquan", "name": "Hội Quán TV", "url": "https://sv2.hoiquan3.live/lich-thi-dau/bong-da", "base_url": "https://sv2.hoiquan3.live"}
]

FILE_PATH_JSON = "bongda.json"
FILE_PATH_M3U = "bongda.m3u"
WAITING_VIDEO_URL = "https://example.com/waiting.mp4"
LIMIT_MATCHES = 12

VN_TZ = datetime.timezone(datetime.timedelta(hours=7))
GITHUB_TOKEN = os.getenv("GH_TOKEN")
REPO_NAME = os.getenv("GH_REPO", "Eternal161/dausoco")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

# =========================================================
# UTILS
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
# CORE: CAPTURE STREAM
# =========================================================
def capture_stream(context, match_url):
    page = context.new_page()
    Stealth().apply_stealth_sync(page)
    found_streams = []

    def process_url(url):
        u = url.lower()
        if any(bad in u for bad in [".mp4", ".jpg", ".png", "google", "ads-", "analytics"]): return
        if any(k in u for k in [".m3u8", "wssession", "sign=", "token=", "100ycdn", "edgemaxcdn"]):
            score = 0
            if "100ycdn" in u: score += 6000
            if "edgemax" in u or "hqtv" in u: score += 5000
            if any(k in u for k in ["token=", "sign=", "wssession="]): score += 2000
            found_streams.append({"url": url, "score": score})
            print(f"   🎯 TÓM ĐƯỢC ({score}đ): {url[:65]}...")

    page.on("request", lambda req: process_url(req.url))

    try:
        page.goto(match_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(10000) 

        # Click kích hoạt video qua mọi Frame (Iframe-Deep-Click)
        for frame in page.frames:
            try:
                box = frame.frame_element().bounding_box()
                if box:
                    page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
            except: continue

        deadline = time.time() + 15
        while time.time() < deadline:
            if any(s['score'] >= 5000 for s in found_streams): break
            page.mouse.wheel(0, 100) # Cuộn nhẹ để kích hoạt script player
            time.sleep(1)
    except Exception as e:
        print(f"   ❌ Lỗi Capture: {e}")
    finally:
        page.screenshot(path="last_debug.png")
        page.close()

    if not found_streams: return None
    found_streams.sort(key=lambda x: x['score'], reverse=True)
    return found_streams[0]['url']

# =========================================================
# OUTPUT & GITHUB
# =========================================================
def generate_m3u(data):
    # Đường dẫn logo của từng Provider (Thay link ảnh của bạn vào đây)
    LOGO_PROVIDER = {
        "buncha": "https://bunchatv.com/images/logo.png", 
        "hoiquan": "https://sv2.hoiquan3.live/logo.png"
    }
    
    lines = ["#EXTM3U", f"#PLAYLISTNAME: ⚽ Xem ngay - {data['last_updated']}", ""]
    
    for cid in ["buncha", "hoiquan"]:
        matches = data.get(cid, [])
        # Tên nhóm hiển thị trên App
        group_name = "⭐ BÚN CHẢ TV" if cid == "buncha" else "🔥 HỘI QUÁN TV"
        # Logo mặc định của Group/Provider
        provider_logo = LOGO_PROVIDER.get(cid, "")
        
        for m in matches:
            if m['stream_url'] and m['stream_url'] != WAITING_VIDEO_URL:
                # Định dạng tiêu đề: [Giờ] Đội A vs Đội B
                display_time = m['thoi_gian'].split(' ')[0] if m['thoi_gian'] != "Unknown" else "Live"
                title = f"{display_time} ⚽ {m['title']}"
                
                # Ưu tiên logo đội bóng, nếu không có thì dùng logo Provider
                logo_display = m.get("logo_nha") if m.get("logo_nha") else provider_logo
                
                # Metadata chuẩn M3U Plus
                inf_line = (
                    f'#EXTINF:-1 tvg-id="{m["title"]}" '
                    f'tvg-name="{m["title"]}" '
                    f'tvg-logo="{logo_display}" '
                    f'group-title="{group_name}",'
                    f'{title}'
                )
                
                lines.append(inf_line)
                lines.append(m['stream_url'])
                lines.append("") 
                
    return "\n".join(lines)
    
def push_to_github(all_data):
    if not GITHUB_TOKEN: return
    
    json_content = json.dumps(all_data, indent=2, ensure_ascii=False)
    m3u_content = generate_m3u(all_data)
    
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)
    now_str = datetime.datetime.now(VN_TZ).strftime("%H:%M %d/%m/%Y")

    # Đếm số trận live để ghi vào commit message cho chuyên nghiệp
    live_count = sum(1 for cid in ["buncha", "hoiquan"] 
                     for m in all_data.get(cid, []) 
                     if m['stream_url'] != WAITING_VIDEO_URL)

    files = {
        FILE_PATH_JSON: json_content,
        FILE_PATH_M3U: m3u_content
    }

    for path, content in files.items():
        try:
            existing = repo.get_contents(path)
            # Commit message đẹp mắt
            commit_msg = f"⚽ Update {path} | 🔴 Live: {live_count} | 🕒 {now_str}"
            repo.update_file(existing.path, commit_msg, content, existing.sha)
            print(f"✅ Updated {path} ({live_count} matches)")
        except Exception as e:
            repo.create_file(path, f"🚀 Initial {path}", content)
            print(f"✅ Created {path}")

# =========================================================
# MAIN
# =========================================================
def scrape_and_push():
    all_channel_data = {"buncha": [], "hoiquan": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=_HEADERS["User-Agent"], locale="vi-VN")

        for channel in CHANNELS:
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            try:
                page.goto(channel["url"], wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
                
                links = []
                seen = set()
                for el in page.locator("a[href*='-vs-']").all():
                    href = el.get_attribute("href")
                    if href and "-vs-" in href and href not in seen:
                        seen.add(href)
                        links.append(href if href.startswith("http") else f"{channel['base_url'].rstrip('/')}/{href.lstrip('/')}")
                
                for href in links[:LIMIT_MATCHES]:
                    doi_nha, doi_khach, thoi_gian = parse_url_to_info(href)
                    is_live, status = False, "Chờ đợi"
                    try:
                        m_time = datetime.datetime.strptime(thoi_gian, "%H:%M %d/%m/%Y").replace(tzinfo=VN_TZ)
                        diff = (datetime.datetime.now(VN_TZ) - m_time).total_seconds() / 60
                        if -15 <= diff <= 150: is_live = True; status = "Đang trực tiếp 🔴"
                        elif diff > 150: status = "Đã kết thúc 🏁"
                    except: is_live = True # Fallback

                    all_channel_data[channel["id"]].append({
                        "title": f"{doi_nha} vs {doi_khach}", "trang_thai": status, "is_live": is_live,
                        "thoi_gian": thoi_gian, "logo_nha": get_team_logo(doi_nha), "link_xem": href, "stream_url": WAITING_VIDEO_URL
                    })
            except: pass
            finally: page.close()

        for cid in all_channel_data:
            for m in all_channel_data[cid]:
                if m["is_live"]:
                    print(f"🎥 Bắt luồng: {m['title']}")
                    stream = capture_stream(context, m["link_xem"])
                    if stream: m["stream_url"] = stream

        browser.close()

    push_to_github({"playlist_name": "Sáng TV", "last_updated": datetime.datetime.now(VN_TZ).strftime("%H:%M %d/%m/%Y"), **all_channel_data})

if __name__ == "__main__":
    scrape_and_push()
