import requests
from bs4 import BeautifulSoup
import os

def scrape_data():
    url = "https://sv2.hoiquan2.live/lich-thi-dau/bong-da"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    matches_list = []
    
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.encoding = 'utf-8'
        if response.status_code != 200:
            return matches_list

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Tập trung vào các container chứa trận đấu
        items = soup.select('.item-match, .match-item')

        for item in items:
            try:
                # Lấy thời gian
                time_tag = item.select_one('.time, .match-time')
                time_val = time_tag.text.strip() if time_tag else "LIVE"

                # Lấy tên và logo 2 đội
                # Giả định cấu trúc: đội 1 - logo - vs - logo - đội 2
                teams = item.select('.team-name, .name')
                logos = item.select('img')
                
                if len(teams) >= 2:
                    t1, t2 = teams[0].text.strip(), teams[1].text.strip()
                    display_name = f"{time_val} | {t1} vs {t2}"
                else:
                    display_name = f"{time_val} | " + item.select_one('.match-name').text.strip()

                # Lấy logo chính (thường là logo giải đấu hoặc logo đội 1)
                logo_url = logos[0]['src'] if logos else ""
                if logo_url.startswith('//'): logo_url = "https:" + logo_url

                # Lấy link xem
                link_tag = item.find('a', href=True)
                url_view = link_tag['href'] if link_tag else ""
                if url_view.startswith('/'): url_view = "https://sv2.hoiquan2.live" + url_view

                if url_view:
                    matches_list.append({
                        "name": display_name,
                        "url": url_view,
                        "logo": logo_url
                    })
            except:
                continue
    except Exception as e:
        print(f"Error: {e}")
    
    return matches_list

def export_m3u(data):
    with open("bongda.m3u", "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for m in data:
            # Format chuẩn y hệt file mẫu bạn gửi
            f.write(f'#EXTINF:-1 tvg-id="" tvg-logo="{m["logo"]}" group-title="Bóng Đá Trực Tiếp",{m["name"]}\n')
            f.write(f'{m["url"]}\n')
    print(f"✅ Đã tạo xong bongda.m3u với {len(data)} trận.")

if __name__ == "__main__":
    data = scrape_data()
    export_m3u(data)
