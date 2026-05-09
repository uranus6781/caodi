# main.py
from playwright.sync_api import sync_playwright, TimeoutError
import time
import re
from datetime import datetime

def scrape_hoiquan_to_m3u():
    m3u_content = "#EXTM3U\n"
    m3u_content += f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
    m3u_content += "# Source: hoiquan2.live\n\n"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            print("🌐 Mở trang lịch thi đấu...")
            page.goto("https://sv2.hoiquan2.live/lich-thi-dau/bong-da", wait_until="domcontentloaded", timeout=45000)
            time.sleep(6)
            
            # Lấy các trận (cập nhật selector theo cấu trúc thực tế của site)
            matches = page.query_selector_all('a[href*="/truc-tiep"], a[href*="/match"], div[class*="match"], article a, .live-match')
            
            print(f"🔍 Tìm thấy {len(matches)} trận. Bắt đầu scrape top 10...")
            
            count = 0
            for match in matches[:15]:
                try:
                    raw_text = match.inner_text().strip()[:100]
                    href = match.get_attribute('href')
                    if not href or len(raw_text) < 8:
                        continue
                    if href.startswith('/'):
                        href = "https://sv2.hoiquan2.live" + href
                    
                    print(f"[{count+1}/10] → {raw_text[:70]}...")
                    
                    page.goto(href, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(4)
                    
                    # Lấy thông tin trận
                    info = page.evaluate('''() => {
                        return {
                            league: document.querySelector('h1, .league-name, .competition')?.innerText.trim() || '',
                            time: document.querySelector('.time, .kick-off, time')?.innerText.trim() || '',
                            team1: document.querySelectorAll('.team-name, .home-team, strong')[0]?.innerText.trim() || '',
                            team2: document.querySelectorAll('.team-name, .away-team, strong')[1]?.innerText.trim() || '',
                            logo1: document.querySelectorAll('img')[0]?.src || '',
                            logo2: document.querySelectorAll('img')[1]?.src || ''
                        };
                    }''')
                    
                    # Lấy link stream
                    streams = page.evaluate('''() => {
                        return Array.from(document.querySelectorAll('a[href*=".m3u8"], a[href*="stream"], button, div[onclick*="play"]'))
                            .map(el => ({
                                url: el.href || el.getAttribute('data-link') || '',
                                label: el.innerText.trim() || 'Live'
                            }))
                            .filter(s => s.url && (s.url.includes('.m3u8') || s.url.includes('stream')));
                    }''')
                    
                    title = f"{info['team1']} vs {info['team2']}"
                    if info['time']:
                        title = f"[{info['time']}] {title}"
                    if info['league']:
                        title = f"{info['league']} - {title}"
                    
                    for s in streams:
                        if '.m3u8' in s['url']:
                            extinf = f'#EXTINF:-1 group-title="Hội Quán TV",'
                            if info['logo1']:
                                extinf += f'tvg-logo="{info["logo1"]}" '
                            extinf += f'{title} | {s["label"]}\n'
                            
                            m3u_content += extinf
                            m3u_content += f'{s["url"]}\n\n'
                    
                    count += 1
                    if count >= 10:
                        break
                        
                except Exception as e:
                    print(f"⚠️ Lỗi trận: {e}")
                    continue
                finally:
                    try:
                        page.go_back()
                        time.sleep(2)
                    except:
                        pass
                        
        except Exception as e:
            print(f"❌ Lỗi tổng: {e}")
        finally:
            browser.close()
    
    with open("bongda.m3u", "w", encoding="utf-8") as f:
        f.write(m3u_content)
    
    print(f"✅ Hoàn thành! Scrape {count} trận.")

if __name__ == "__main__":
    scrape_hoiquan_to_m3u()
