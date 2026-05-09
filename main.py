# main.py
from playwright.sync_api import sync_playwright
import time
import re
from datetime import datetime

def scrape_hoiquan_to_m3u():
    m3u_content = "#EXTM3U\n"
    m3u_content += f"# Playlist generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    m3u_content += "# Source: sv2.hoiquan2.live\n\n"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        print("🌐 Đang mở trang lịch thi đấu...")
        page.goto("https://sv2.hoiquan2.live/lich-thi-dau/bong-da", wait_until="networkidle", timeout=60000)
        time.sleep(7)
        
        # Lấy danh sách các trận
        matches = page.query_selector_all('a[href*="/truc-tiep/"], a[href*="/match/"], div[class*="match"], .grid a, article a')
        
        print(f"Tìm thấy {len(matches)} trận. Đang scrape top 10...")
        
        count = 0
        for match_link in matches[:15]:   # dư để lọc
            try:
                # Extract thông tin trên trang lịch
                title_elem = match_link.query_selector('h3, .team, strong, span')
                raw_title = title_elem.inner_text().strip() if title_elem else match_link.inner_text().strip()
                
                # Mở trang trận đấu
                href = match_link.get_attribute('href')
                if not href:
                    continue
                if href.startswith('/'):
                    href = "https://sv2.hoiquan2.live" + href
                
                print(f"[{count+1}/10] Đang scrape: {raw_title[:60]}...")
                page.goto(href, wait_until="networkidle", timeout=45000)
                time.sleep(5)
                
                # === LẤY CHI TIẾT TRẬN ĐẤU ===
                match_info = page.evaluate('''() => {
                    const data = {
                        league: '',
                        time: '',
                        team1: '',
                        team2: '',
                        logo1: '',
                        logo2: '',
                        title: ''
                    };
                    
                    // Giải đấu
                    const leagueEl = document.querySelector('h1, .league, .competition, [class*="league"]');
                    if (leagueEl) data.league = leagueEl.innerText.trim();
                    
                    // Thời gian
                    const timeEl = document.querySelector('[class*="time"], .kickoff, .match-time, time');
                    if (timeEl) data.time = timeEl.innerText.trim();
                    
                    // Tên 2 đội
                    const teams = Array.from(document.querySelectorAll('.team-name, .team, strong, h2'));
                    if (teams.length >= 2) {
                        data.team1 = teams[0].innerText.trim();
                        data.team2 = teams[1].innerText.trim();
                    } else {
                        // fallback
                        const vsText = document.body.innerText.match(/(.+?)\s+vs\s+(.+?)(?:\n|$)/i);
                        if (vsText) {
                            data.team1 = vsText[1].trim();
                            data.team2 = vsText[2].trim();
                        }
                    }
                    
                    // Logo
                    const imgs = Array.from(document.querySelectorAll('img'));
                    for (let img of imgs) {
                        const src = img.src || '';
                        if (src.includes('logo') || src.includes('team') || src.includes('flag')) {
                            if (!data.logo1) data.logo1 = src;
                            else if (!data.logo2) data.logo2 = src;
                        }
                    }
                    
                    data.title = `${data.team1} vs ${data.team2}`;
                    return data;
                }''')
                
                # Tìm link stream
                streams = page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('a, button'))
                        .filter(el => {
                            const href = (el.href || el.getAttribute('data-link') || '').toLowerCase();
                            const text = (el.innerText || '').toLowerCase();
                            return href.includes('.m3u8') || href.includes('stream') || 
                                   text.includes('xem') || text.includes('blv') || 
                                   text.includes('lương sơn') || text.includes('bún chả');
                        })
                        .map(el => ({
                            url: el.href || el.getAttribute('data-link') || '',
                            label: el.innerText.trim() || 'Stream'
                        }));
                }''')
                
                clean_title = f"{match_info['team1']} vs {match_info['team2']}"
                if match_info['time']:
                    clean_title = f"[{match_info['time']}] {clean_title}"
                if match_info['league']:
                    clean_title = f"{match_info['league']} - {clean_title}"
                
                for stream in streams:
                    if '.m3u8' in stream['url'] or 'stream' in stream['url']:
                        # Thêm metadata vào #EXTINF
                        extinf = f'#EXTINF:-1 group-title="Hội Quán TV",'
                        extinf += f'tvg-logo="{match_info["logo1"] or ""}" '
                        extinf += f'tvg-name="{clean_title}" '
                        extinf += f'{clean_title} | {stream["label"]}\n'
                        
                        m3u_content += extinf
                        m3u_content += f'{stream["url"]}\n\n'
                
                count += 1
                if count >= 10:
                    break
                
                page.go_back()
                time.sleep(3)
                
            except Exception as e:
                print(f"Lỗi: {e}")
                continue
        
        browser.close()
    
    # Lưu file
    with open("bongda.m3u", "w", encoding="utf-8") as f:
        f.write(m3u_content)
    
    print(f"\n✅ Hoàn thành! Đã scrape {count} trận với thông tin đầy đủ.")

if __name__ == "__main__":
    scrape_hoiquan_to_m3u()
