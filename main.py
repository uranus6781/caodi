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
    {
        "id": "buncha",
        "name": "Bún Chả TV",
        "url": "https://bunchatv4.net/truc-tiep-bong-da-xoilac-tv",
        "base_url": "https://bunchatv4.net"
    },
    {
        "id": "hoiquan",
        "name": "Hội Quán TV",
        "url": "https://sv2.hoiquan3.live/lich-thi-dau/bong-da",
        "base_url": "https://sv2.hoiquan3.live"
    }
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
    if not team_name or team_name == "Unknown":
        return ""
    return f"https://ui-avatars.com/api/?name={requests.utils.quote(team_name[:2])}&size=200&background=1565C0&color=ffffff&bold=true"

def parse_url_to_info(url):
    try:
        parts = url.rstrip('/').split('/')
        slug = ""
        for p in reversed(parts):
            if "-vs-" in p:
                slug = p.split('?')[0].split('#')[0]
                break
        if not slug: return "Unknown", "Unknown", "Unknown"
        slug = re.sub(r'-\d{6,}$', '', slug)
        time_match = re.search(r"-(\d{4}-\d{2}-\d{2}-\d{4})$", slug)
        if time_match:
            t = time_match.group(1)
            thoi_gian = f"{t[0:2]}:{t[2:4]} {t[5:7]}/{t[8:10]}/{t[11:15]}"
            teams_slug = slug[:slug.rfind("-" + t)]
        else:
            thoi_gian = "Unknown"
            teams_slug = slug
        teams = teams_slug.split("-vs-", 1)
        doi_nha = teams[0].replace("-", " ").title().strip()
        doi_khach = teams[1].replace("-", " ").title().strip() if len(teams) > 1 else "Unknown"
        return doi_nha, doi_khach, thoi_gian
    except:
        return "Unknown", "Unknown", "Unknown"

# =========================================================
# CORE: CAPTURE STREAM (FIXED)
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
        page.wait_for_timeout(10000) # Đợi load player

        # Click kích hoạt video thông qua Iframe
        for frame in page.frames:
            try:
                box = frame.frame_element().bounding_box()
                if box:
                    page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
            except: continue

        # Đợi luồng m3u8 phát sinh
        deadline = time.time() + 15
        while time.time() < deadline:
            if any(s['score'] >= 5000 for s in found_streams): break
            time.sleep(1)

    except Exception as e:
        print(f"   ❌ Lỗi Capture: {e}")
    finally:
        page.screenshot(path="last_debug.png") # Luôn chụp ảnh để debug
        page.close()

    if not found_streams: return None
    found_streams.sort(key=lambda x: x['score'], reverse=True)
    return found_streams[0]['url']

# =========================================================
# GENERATE CONTENT
# =========================================================
def generate_m3u(data):
    lines = ["#EXTM3U", f"#PLAYLISTNAME: Sáng TV - Update: {data['last_updated']}", ""]
    for cid in ["buncha", "hoiquan"]:
        matches = data.get(cid, [])
        gname = "Bún Chả TV" if cid == "buncha" else "Hội Quán TV"
        for m in matches:
            if m['stream_url'] and m['stream_url'] != WAITING_VIDEO_URL:
                lines.append(f'#EXTINF:-1 tvg-logo="{m["logo_nha"]}" group-title="{gname}", {m["title"]}')
                lines.append(m['stream_url'])
    return "\n".join(lines)

# =========================================================
# GITHUB PUSH
# =========================================================
def push_to_github(all_data):
    if not GITHUB_TOKEN: return
    
    json_content = json.dumps(all_data, indent=2, ensure_ascii=False)
    m3u_content = generate_m3u(all_data)
    
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)
    now_str = datetime.datetime.now(VN_TZ).strftime("%H:%M %d/%m/%Y")

    files = {
        FILE_PATH_JSON: json_content,
        FILE_PATH_M3U: m3u_content
    }

    for path, content in files.items():
        try:
            existing = repo.get_contents(path)
            repo.update_file(existing.path, f"⚽ Update {path}: {now_str}", content, existing.sha)
            print(f"✅ Updated {path}")
        except:
            repo.create_file(path, f"✅ Created {path}: {now_str}", content)
            print(f"✅ Created {path}")

# =========================================================
# MAIN SCRAPER
# =========================================================
def scrape_and_push():
    all_channel_data = {"buncha": [], "hoiquan": []}
    print(f"--- START: {datetime.datetime.now(VN_TZ)} ---")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=_HEADERS["User-Agent"],
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh"
        )

        # 1. Quét lịch thi đấu
        for channel in CHANNELS:
            print(f"📺 Quét kênh: {channel['name']}")
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            try:
                page.goto(channel["url"], wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
                
                # Cuộn trang để load trận
                for _ in range(3): 
                    page.mouse.wheel(0, 2000)
                    page.wait_for_timeout(800)

                links = []
                seen = set()
                for el in page.locator("a[href*='-vs-']").all():
                    href = el.get_attribute("href")
                    if href and "-vs-" in href and href not in seen:
                        seen.add(href)
                        full_url = href if href.startswith("http") else f"{channel['base_url'].rstrip('/')}/{href.lstrip('/')}"
                        links.append(full_url)
                
                for idx, href in enumerate(links[:LIMIT_MATCHES]):
                    doi_nha, doi_khach, thoi_gian = parse_url_to_info(href)
                    is_live, status = False, "Sắp diễn ra ⏳"
                    
                    try:
                        m_time = datetime.datetime.strptime(thoi_gian, "%H:%M %d/%m/%Y").replace(tzinfo=VN_TZ)
                        diff = (datetime.datetime.now(VN_TZ) - m_time).total_seconds() / 60
                        if -15 <= diff <= 150:
                            is_live = True
                            status = "Đang trực tiếp 🔴"
                        elif diff > 150:
                            status = "Đã kết thúc 🏁"
                    except: pass

                    all_channel_data[channel["id"]].append({
                        "title": f"{doi_nha} vs {doi_khach}",
                        "trang_thai": status,
                        "is_live": is_live,
                        "thoi_gian": thoi_gian,
                        "logo_nha": get_team_logo(doi_nha),
                        "link_xem": href,
                        "stream_url": WAITING_VIDEO_URL
                    })
            except Exception as e: print(f"❌ Lỗi quét {channel['id']}: {e}")
            finally: page.close()

        # 2. Bắt luồng cho các trận Live
        for cid in all_channel_data:
            live_matches = [m for m in all_channel_data[cid] if m["is_live"]]
            print(f"🎥 Kênh {cid}: Có {len(live_matches)} trận đang Live")
            for m in live_matches:
                print(f"   ► Bắt luồng: {m['title']}")
                stream = capture_stream(context, m["link_xem"])
                if stream: m["stream_url"] = stream

        browser.close()

    # 3. Tổng hợp và đẩy lên GitHub
    final_data = {
        "playlist_name": "Sáng TV",
        "last_updated": datetime.datetime.now(VN_TZ).strftime("%H:%M %d/%m/%Y"),
        **all_channel_data
    }
    push_to_github(final_data)
    print("--- HOÀN TẤT ---")

if __name__ == "__main__":
    scrape_and_push()
