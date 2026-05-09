import os
import re
import time
import datetime
import requests
from github import Github
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from playwright_stealth import Stealth

# =========================================================
# CONFIG ĐA KÊNH
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

FILE_PATH = "bongda.m3u"
WAITING_VIDEO_URL = "https://example.com/waiting.mp4"
LIMIT_MATCHES = 10
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

GITHUB_TOKEN = os.getenv("GH_TOKEN")
REPO_NAME = os.getenv("GH_REPO", "uranus6781/caodi")   # ← Đã đổi

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

LOGO_CACHE = {}

# =========================================================
# LOGO
# =========================================================
def normalize_team_name(name):
    name = re.sub(r"\bFc\b$", "FC", name)
    return name.strip()

def get_team_logo(team_name):
    if not team_name or team_name == "Unknown":
        return ""
    team_name = normalize_team_name(team_name)
    if team_name in LOGO_CACHE:
        return LOGO_CACHE[team_name]
    try:
        slug = team_name.lower().replace(" ", "-")
        url = f"https://football-logos.cc/{slug}/"
        r = requests.get(url, headers=_HEADERS, timeout=5)
        match = re.search(r'https://football-logos.cc/logos/[^"]+\.png', r.text)
        if match:
            logo = match.group(0)
            LOGO_CACHE[team_name] = logo
            return logo
    except:
        pass
    return f"https://ui-avatars.com/api/?name={requests.utils.quote(team_name[:2])}&size=200&background=1565C0&color=ffffff&bold=true"

# =========================================================
# PARSE MATCH TỪ URL
# =========================================================
def parse_url_to_info(url):
    try:
        parts = url.rstrip('/').split('/')
        slug = ""
        for p in reversed(parts):
            if "-vs-" in p:
                slug = p.split('?')[0].split('#')[0]
                break
        if not slug:
            return "Unknown", "Unknown", "Chưa có lịch"

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
# CAPTURE STREAM
# =========================================================
def capture_stream(context, match_url):
    page = context.new_page()
    Stealth().apply_stealth_sync(page)
    streams = set()

    def process_url(url):
        u = url.lower()
        if any(bad in u for bad in [".mp4", ".jpg", ".png", "waiting", "loop", "saba.m3u8", "/ad/", "/ads/", "/vast/", "quangcao", "banner"]):
            return
        if (".m3u8" in u or "taoxanh.biz" in u or "rapidlive.shop" in u
            or "edgemaxcdn.org" in u or "100ycdn.com" in u or "hqtv" in u or "live-stream" in u):
            streams.add(url)
            print(f" 🎯 TÓM ĐƯỢC: {url[:70]}...")

    page.on("request", lambda req: process_url(req.url))
    page.on("response", lambda res: process_url(res.url))

    try:
        page.add_init_script("""
        (() => {
            const origFetch = window.fetch;
            window.fetch = async (...args) => {
                if (typeof args[0] === 'string') console.log('FETCH_HOOK:', args[0]);
                return origFetch(...args);
            };
        })();
        """)
        page.goto(match_url, wait_until="load", timeout=60000)
        page.wait_for_timeout(4000)

        try:
            vp = page.viewport_size
            if vp:
                cx, cy = vp["width"] // 2, vp["height"] // 2
                for _ in range(3):
                    page.mouse.click(cx, cy)
                    page.wait_for_timeout(800)
        except: pass

        deadline = time.time() + 15
        while time.time() < deadline:
            if any("token=" in s.lower() or "sign=" in s.lower() or "wssession=" in s.lower() or "100ycdn" in s.lower() for s in streams):
                break
            time.sleep(1)
    except Exception as e:
        print(" ❌ STREAM ERROR:", e)
    finally:
        page.close()

    if streams:
        priority = []
        for s in streams:
            score = 0
            lower = s.lower()
            if "100ycdn.com" in lower: score += 6000
            if "edgemaxcdn.org" in lower or "hqtv" in lower: score += 5000
            if "taoxanh.biz" in lower: score += 4000
            if "rapidlive.shop" in lower: score += 4000
            if any(k in lower for k in ["expire=", "sign=", "token=", "wssession="]): score += 1000
            if "playlist.m3u8" in lower: score += 500
            elif "index.m3u8" in lower or "chunklist" in lower: score += 200
            priority.append((score, s))

        priority.sort(reverse=True, key=lambda x: x[0])
        best_url = priority[0][1]
        print(f" ✅ CHỐT LINK: {best_url[:70]}...")
        return best_url
    return None

# =========================================================
# TẠO FILE M3U
# =========================================================
def create_m3u(all_channel_data):
    lines = ["#EXTM3U"]
    lines.append("#PLAYLISTNAME: Bóng Đá Trực Tiếp - Sáng TV")
    lines.append(f"#LASTUPDATED: {datetime.datetime.now(VN_TZ).strftime('%d/%m/%Y %H:%M')}")
    lines.append("")

    total_streams = 0

    for channel_id in ["buncha", "hoiquan"]:
        matches = all_channel_data.get(channel_id, [])
        if not matches:
            continue

        channel_name = "Bún Chả TV" if channel_id == "buncha" else "Hội Quán TV"
        lines.append(f"#EXTGRP:{channel_name}")

        for match in matches:
            stream_url = match.get("stream_url")
            if not stream_url or stream_url == WAITING_VIDEO_URL:
                continue

            title = f"{match['trang_thai']} {match['title']} - {match['thoi_gian']}"
            logo = match.get("logo_nha") or match.get("logo_khach") or ""

            lines.append(f'#EXTINF:-1 tvg-id="{match.get("id","")}" tvg-logo="{logo}" group-title="{channel_name}",{title}')
            lines.append(stream_url)
            lines.append("")

            total_streams += 1

    content = "\n".join(lines)
    print(f"✅ Tạo thành công {total_streams} stream trong file .m3u")
    return content

# =========================================================
# PUSH GITHUB
# =========================================================
def push_to_github(content, file_name=FILE_PATH):
    if not GITHUB_TOKEN:
        print("⚠️ NO GH_TOKEN")
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(content)
        return

    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)          # ← Sử dụng repo mới
    msg = f"⚽ Update M3U: {datetime.datetime.now(VN_TZ).strftime('%H:%M %d/%m/%Y')}"

    try:
        existing = repo.get_contents(file_name)
        repo.update_file(existing.path, msg, content, existing.sha)
        print(f"✅ Updated {file_name} trên GitHub")
    except:
        repo.create_file(file_name, msg, content)
        print(f"✅ Created {file_name} trên GitHub")

# =========================================================
# MAIN
# =========================================================
def scrape_and_push():
    all_channel_data = {"buncha": [], "hoiquan": []}
   
    print("=" * 70)
    print(datetime.datetime.now(VN_TZ).strftime("START %H:%M:%S %d/%m/%Y"))
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--autoplay-policy=no-user-gesture-required",
            ]
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=_HEADERS["User-Agent"],
            ignore_https_errors=True
        )

        for channel in CHANNELS:
            print(f"\n📺 ĐANG QUÉT KÊNH: {channel['name'].upper()}")
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            try:
                page.goto(channel["url"], wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(4000)
            except: pass

            for _ in range(4):
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(1000)

            links = []
            seen = set()
            for el in page.locator("a[href*='-vs-']").all():
                href = el.get_attribute("href")
                if not href or "-vs-" not in href or href in seen: continue
                seen.add(href)
                if not href.startswith("http"):
                    href = channel["base_url"].rstrip('/') + '/' + href.lstrip('/')
                links.append(href)

            if LIMIT_MATCHES:
                links = links[:LIMIT_MATCHES]

            print(f" ✅ TÌM THẤY {len(links)} TRẬN ĐẤU")

            for idx, href in enumerate(links):
                doi_nha, doi_khach, thoi_gian = parse_url_to_info(href)
               
                is_live, status = False, "Chưa đá ⏳"
                try:
                    match_time = datetime.datetime.strptime(thoi_gian, "%H:%M %d/%m/%Y").replace(tzinfo=VN_TZ)
                    diff_minutes = (datetime.datetime.now(VN_TZ) - match_time).total_seconds() / 60
                    if -10 <= diff_minutes <= 120:
                        is_live = True
                        status = "Đang trực tiếp 🔴"
                    elif diff_minutes > 120:
                        status = "Đã kết thúc 🏁"
                except:
                    pass

                match_info = {
                    "id": str(idx + 1),
                    "title": f"{doi_nha} vs {doi_khach}",
                    "doi_nha": doi_nha,
                    "doi_khach": doi_khach,
                    "thoi_gian": thoi_gian,
                    "trang_thai": status,
                    "is_live": is_live,
                    "logo_nha": get_team_logo(doi_nha),
                    "logo_khach": get_team_logo(doi_khach),
                    "stream_url": WAITING_VIDEO_URL,
                    "link_xem": href
                }
                all_channel_data[channel["id"]].append(match_info)
            page.close()

        print("\n🎥 TIẾN HÀNH BẮT LUỒNG...")
        for channel in CHANNELS:
            live_matches = [m for m in all_channel_data[channel["id"]] if m["is_live"]]
            if not live_matches:
                continue
            print(f"\n ► {channel['name']}: {len(live_matches)} trận Live")
            for idx, match in enumerate(live_matches):
                print(f" [{idx+1}/{len(live_matches)}] Cào link: {match['title']}")
                stream = capture_stream(context, match["link_xem"])
                if stream:
                    match["stream_url"] = stream

        browser.close()

    content = create_m3u(all_channel_data)
    
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"💾 Đã lưu file: {FILE_PATH}")

    push_to_github(content)

    print("\n" + "=" * 70)
    print("✅ HOÀN TẤT - FILE M3U ĐÃ SẴN SÀNG")
    print("=" * 70)

if __name__ == "__main__":
    scrape_and_push()
