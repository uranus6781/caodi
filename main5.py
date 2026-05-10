import os
import re
import time
import json
import datetime
import requests
from github import Github, Auth
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

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

LOGO_PROVIDER = {
    "buncha": "https://bunchatv.com/images/logo.png",
    "hoiquan": "https://sv2.hoiquan3.live/logo.png"
}

# =========================================================
# UTILS (ĐÃ TỐI ƯU TỐC ĐỘ)
# =========================================================
def get_team_logo(team_name):
    """Lấy logo tốc độ cao, không quét web tránh treo script"""
    if not team_name or team_name == "Unknown": return ""
    name = re.sub(r"\bFc\b$", "FC", team_name.strip())
    # Sử dụng API logo nhanh hoặc UI-Avatar chất lượng cao
    return f"https://ui-avatars.com/api/?name={requests.utils.quote(name[:2])}&size=200&background=1565C0&color=ffffff&bold=true"

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
    
    # Lọc request ngay lập tức để tiết kiệm tài nguyên
    page.on("request", lambda req: (found_streams.append({"url": req.url, "score": 6000 if "100ycdn" in req.url else 5000}) 
                                    if any(k in req.url.lower() for k in [".m3u8", "wssession", "100ycdn"]) else None))
    
    try:
        page.goto(match_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        # Xóa nhanh các phần tử che chắn
        page.evaluate("() => { document.querySelectorAll('*').forEach(el => { if(parseInt(window.getComputedStyle(el).zIndex) > 10) el.remove(); }); }")
        
        for frame in page.frames:
            try:
                box = frame.frame_element().bounding_box()
                if box: page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
            except: continue
        
        # Chờ tối đa 10s để bắt link
        start_wait = time.time()
        while time.time() - start_wait < 10:
            if any(s['score'] >= 5000 for s in found_streams): break
            time.sleep(1)
    except: pass
    finally: page.close()
    
    if not found_streams: return None
    found_streams.sort(key=lambda x: x['score'], reverse=True)
    return found_streams[0]['url']

# =========================================================
# MAIN
# =========================================================
def scrape_and_push():
    all_channel_data = {"buncha": [], "hoiquan": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(viewport={"width": 1280, "height": 720}, user_agent=_HEADERS["User-Agent"])

        for channel in CHANNELS:
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            try:
                page.goto(channel["url"], wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)
                
                # Cuộn nhanh lấy nội dung
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(1000)

                match_elements = page.locator("a[href*='-vs-']").all()
                seen = set()
                
                for el in match_elements:
                    href = el.get_attribute("href")
                    if not href or "-vs-" not in href or href in seen: continue
                    seen.add(href)
                    
                    full_url = href if href.startswith("http") else f"{channel['base_url'].rstrip('/')}/{href.lstrip('/')}"
                    
                    # Lấy logo trực tiếp từ web (lọc bỏ rác)
                    logo_url = ""
                    try:
                        images = el.locator("img").all()
                        for img in images:
                            src = img.get_attribute("src")
                            if src and not any(k in src.lower() for k in ["league", "cup", "logo-giai", "icon"]):
                                logo_url = src if src.startswith("http") else f"{channel['base_url'].rstrip('/')}/{src.lstrip('/')}"
                                break
                    except: pass
                    
                    doi_nha, doi_khach, thoi_gian = parse_url_to_info(full_url)
                    if not logo_url: logo_url = get_team_logo(doi_nha)

                    # Kiểm tra LIVE nhanh
                    is_live = False
                    status = "Chờ"
                    try:
                        txt = el.inner_text().lower()
                        if "trực tiếp" in txt or "🔴" in txt or "truc-tiep" in full_url:
                            is_live = True
                            status = "Đang trực tiếp 🔴"
                    except: pass

                    all_channel_data[channel["id"]].append({
                        "title": f"{doi_nha} vs {doi_khach}", "trang_thai": status, "is_live": is_live,
                        "thoi_gian": thoi_gian, "logo_nha": logo_url, "link_xem": full_url, "stream_url": WAITING_VIDEO_URL
                    })
                    if len(seen) >= LIMIT_MATCHES: break
            except: pass
            finally: page.close()

        # Chỉ bắt luồng trận nào thực sự LIVE
        for cid in all_channel_data:
            for m in all_channel_data[cid]:
                if m["is_live"]:
                    print(f"🎥 Bắt luồng: {m['title']}")
                    stream = capture_stream(context, m["link_xem"])
                    if stream: m["stream_url"] = stream

        browser.close()
    
    push_to_github(all_channel_data)

def generate_m3u(data):
    lines = ["#EXTM3U", f"#PLAYLISTNAME: ⚽ Sáng TV - {datetime.datetime.now(VN_TZ).strftime('%H:%M %d/%m/%Y')}", ""]
    for cid in ["buncha", "hoiquan"]:
        for m in data.get(cid, []):
            if m['stream_url'] != WAITING_VIDEO_URL:
                logo = m.get("logo_nha") or LOGO_PROVIDER.get(cid, "")
                lines.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="{"⭐ BÚN CHẢ TV" if cid == "buncha" else "🔥 HỘI QUÁN TV"}",{m["title"]}')
                lines.append(m['stream_url'])
                lines.append("")
    return "\n".join(lines)

def push_to_github(all_data):
    if not GITHUB_TOKEN: return
    try:
        g = Github(auth=Auth.Token(GITHUB_TOKEN.strip()))
        repo = g.get_repo(REPO_NAME)
        files = {FILE_PATH_JSON: json.dumps(all_data, indent=2, ensure_ascii=False), FILE_PATH_M3U: generate_m3u(all_data)}
        for path, content in files.items():
            try:
                existing = repo.get_contents(path)
                repo.update_file(existing.path, f"⚽ Update {path}", content, existing.sha)
            except:
                repo.create_file(path, f"🚀 Initial {path}", content)
        print("✅ Đã đẩy dữ liệu lên GitHub thành công!")
    except Exception as e: print(f"❌ Lỗi GitHub: {e}")

if __name__ == "__main__":
    scrape_and_push()
