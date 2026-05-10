import os
import re
import time
import json
import datetime
import requests
from github import Github, Auth                    # ← ĐÃ THÊM: Auth
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
REPO_NAME = os.getenv("GH_REPO", "uranus6781/caodi")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

# =========================================================
# ==================== PHẦN MỚI ĐÃ THÊM ====================
# =========================================================
# LOGO CONFIG - DỄ THAY ĐỔI
# =========================================================
LOGO_PROVIDER = {
    "buncha": "https://bunchatv.com/images/logo.png",   # ← Thay logo Bún Chả TV ở đây
    "hoiquan": "https://sv2.hoiquan3.live/logo.png"     # ← Thay logo Hội Quán TV ở đây
}

LOGO_CACHE = {}  # Cache logo đội bóng để tăng tốc độ

# =========================================================
# UTILS
# =========================================================
def get_team_logo(team_name):
    """Ưu tiên football-logos.cc, chỉ fallback UI Avatar khi không lấy được"""
    if not team_name or team_name == "Unknown":
        return ""

    team_name = re.sub(r"\bFc\b$", "FC", team_name.strip())
    
    if team_name in LOGO_CACHE:
        return LOGO_CACHE[team_name]

    # ==================== ƯU TIÊN 1: football-logos.cc ====================
    try:
        base_slug = team_name.lower().replace(" ", "-").replace(".", "")
        
        # Thử nhiều biến thể slug phổ biến
        slug_variants = [
            base_slug,
            base_slug.replace("manchester-united", "man-utd"),
            base_slug.replace("manchester-city", "man-city"),
            base_slug.replace("tottenham", "spurs"),
            re.sub(r'-\d+$', '', base_slug)  # Xóa số thừa nếu có
        ]

        for slug in slug_variants:
            try:
                url = f"https://football-logos.cc/{slug}/"
                r = requests.get(url, headers=_HEADERS, timeout=8)
                
                if r.status_code == 200:
                    # Tìm logo PNG
                    match = re.search(r'https?://football-logos\.cc/logos/[^"\']+\.png', r.text)
                    if match:
                        logo_url = match.group(0)
                        LOGO_CACHE[team_name] = logo_url
                        print(f"✅ Lấy logo thật: {team_name}")
                        return logo_url
            except:
                continue
    except:
        pass

    # ==================== FALLBACK: UI Avatar ====================
    logo_url = f"https://ui-avatars.com/api/?name={requests.utils.quote(team_name[:2])}&size=200&background=1565C0&color=ffffff&bold=true"
    LOGO_CACHE[team_name] = logo_url
    print(f"⚠️ Dùng UI Avatar cho: {team_name}")
    return logo_url

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
            print(f" 🎯 TÓM ĐƯỢC ({score}đ): {url[:65]}...")
    page.on("request", lambda req: process_url(req.url))
    try:
        page.goto(match_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(10000)
        # --- DIỆT POPUP QUẢNG CÁO ĐANG CHE MÀN HÌNH ---
                page.evaluate("""
                () => {
                    // Xóa các phần tử có z-index cao hoặc được cố định màn hình (thường là popup)
                    const overlays = document.querySelectorAll('*');
                    overlays.forEach(el => {
                        const style = window.getComputedStyle(el);
                        if ((style.position === 'fixed' || style.position === 'absolute') && parseInt(style.zIndex) > 10) {
                            el.remove();
                        }
                    });
                    // Xóa các thẻ div phủ mờ màn hình (backdrop)
                    document.querySelectorAll('[class*="modal"], [class*="overlay"], [class*="popup"]').forEach(el => el.remove());
                }
                """)
                print(f" 🧹 Đã dọn dẹp Popup trên {channel['name']}")
                # ---------------------------------------------
                
                # Cuộn trang để kích hoạt logo lazy-load
        for frame in page.frames:
            try:
                box = frame.frame_element().bounding_box()
                if box:
                    page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
            except: continue
        deadline = time.time() + 15
        while time.time() < deadline:
            if any(s['score'] >= 5000 for s in found_streams): break
            page.mouse.wheel(0, 100)
            time.sleep(1)
    except Exception as e:
        print(f" ❌ Lỗi Capture: {e}")
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
    lines = ["#EXTM3U", f"#PLAYLISTNAME: ⚽ Xem ngay - {data['last_updated']}", ""]
   
    for cid in ["buncha", "hoiquan"]:
        matches = data.get(cid, [])
        group_name = "⭐ BÚN CHẢ TV" if cid == "buncha" else "🔥 HỘI QUÁN TV"
        provider_logo = LOGO_PROVIDER.get(cid, "")           # ← Sử dụng Provider Logo
        
        for m in matches:
            if m['stream_url'] and m['stream_url'] != WAITING_VIDEO_URL:
                display_time = m['thoi_gian'].split(' ')[0] if m['thoi_gian'] != "Unknown" else "Live"
                title = f"{display_time} ⚽ {m['title']}"
               
                # Ưu tiên logo đội nhà → provider_logo
                logo_display = m.get("logo_nha") if m.get("logo_nha") else provider_logo   # ← ĐÃ THÊM LOGIC
                
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
    if not GITHUB_TOKEN: 
        print("⚠️ GH_TOKEN chưa được thiết lập")
        return
   
    json_content = json.dumps(all_data, indent=2, ensure_ascii=False)
    m3u_content = generate_m3u(all_data)
   
    try:
        auth = Auth.Token(GITHUB_TOKEN.strip())          # ← ĐÃ CẢI TIẾN
        g = Github(auth=auth)
        repo = g.get_repo(REPO_NAME)
        now_str = datetime.datetime.now(VN_TZ).strftime("%H:%M %d/%m/%Y")
        
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
                commit_msg = f"⚽ Update {path} | 🔴 Live: {live_count} | 🕒 {now_str}"
                repo.update_file(existing.path, commit_msg, content, existing.sha)
                print(f"✅ Updated {path} ({live_count} matches)")
            except Exception:
                repo.create_file(path, f"🚀 Initial {path}", content)
                print(f"✅ Created {path}")
    except Exception as e:
        print(f"❌ Lỗi push GitHub: {e}")


# =========================================================
# MAIN
# =========================================================
def scrape_and_push():
    all_channel_data = {"buncha": [], "hoiquan": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=_HEADERS["User-Agent"], locale="vi-VN")

        for channel in CHANNELS:
            page = context.new_page(); Stealth().apply_stealth_sync(page)
            try:
                page.goto(channel["url"], wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
                
                # Cuộn trang để kích hoạt logo lazy-load
                for _ in range(3): page.mouse.wheel(0, 1500); page.wait_for_timeout(500)

                match_elements = page.locator("a[href*='-vs-']").all()
                seen = set()
                
                for el in match_elements:
                    href = el.get_attribute("href")
                    if not href or "-vs-" in href == False or href in seen: continue
                    seen.add(href)
                    
                    full_url = href if href.startswith("http") else f"{channel['base_url'].rstrip('/')}/{href.lstrip('/')}"
                    
                    # Lấy logo trực tiếp từ Provider
                    logo_url = ""
                    try:
                        img_el = el.locator("img").first
                        if img_el.count() > 0:
                            src = img_el.get_attribute("src")
                            if src: logo_url = src if src.startswith("http") else f"{channel['base_url'].rstrip('/')}/{src.lstrip('/')}"
                    except: pass
                    
                    doi_nha, doi_khach, thoi_gian = parse_url_to_info(full_url)
                    if not logo_url: logo_url = get_team_logo_fallback(doi_nha)

                    is_live, status = False, "Chờ"
                    try:
                        m_time = datetime.datetime.strptime(thoi_gian, "%H:%M %d/%m/%Y").replace(tzinfo=VN_TZ)
                        diff = (datetime.datetime.now(VN_TZ) - m_time).total_seconds() / 60
                        if -15 <= diff <= 150: is_live = True; status = "Đang trực tiếp 🔴"
                    except: is_live = True

                    all_channel_data[channel["id"]].append({
                        "title": f"{doi_nha} vs {doi_khach}", "trang_thai": status, "is_live": is_live,
                        "thoi_gian": thoi_gian, "logo_nha": logo_url, "link_xem": full_url, "stream_url": WAITING_VIDEO_URL
                    })
            except: pass
            finally: page.close()

        # Bắt luồng cho các trận Live
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
