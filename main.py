import requests
from bs4 import BeautifulSoup
import datetime

def scrape_hoiquan():
    url = "https://sv2.hoiquan2.live/lich-thi-dau/bong-da"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    channels = []
    
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            print(f"Lỗi truy cập: {response.status_code}")
            return channels

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Tìm tất cả các khối trận đấu (item-match hoặc cấu trúc tương đương trên web)
        # Lưu ý: Cấu trúc web này thường nằm trong các div có class 'match-item' hoặc 'row'
        matches = soup.select('.item-match, .match-item') 

        for match in matches:
            try:
                # 1. Lấy thời gian (thường nằm ở thẻ có class 'time')
                time_val = match.select_one('.time, .match-time').text.strip() if match.select_one('.time, .match-time') else ""
                
                # 2. Lấy tên 2 đội và ghép lại
                teams = match.select('.team-name, .name')
                if len(teams) >= 2:
                    team1 = teams[0].text.strip()
                    team2 = teams[1].text.strip()
                    display_name = f"{time_val} | {team1} vs {team2}"
                else:
                    display_name = match.select_one('.match-name').text.strip()

                # 3. Lấy Logo (Ưu tiên logo giải đấu hoặc đội 1)
                img_tag = match.find('img')
                logo_url = img_tag['src'] if img_tag and img_tag.has_attr('src') else ""
                if logo_url and logo_url.startswith('//'):
                    logo_url = "https:" + logo_url

                # 4. Lấy link xem (Redirect link hoặc link trực tiếp)
                link_tag = match.find('a', href=True)
                stream_url = link_tag['href'] if link_tag else ""
                
                if stream_url:
                    # Chuyển link tương đối thành tuyệt đối nếu cần
                    if stream_url.startswith('/'):
                        stream_url = "https://sv2.hoiquan2.live" + stream_url
                    
                    channels.append({
                        "name": display_name,
                        "url": stream_url,
                        "logo": logo_url,
                        "group": "Bóng Đá Trực Tiếp"
                    })
            except Exception as e:
                continue

    except Exception as e:
        print(f"Lỗi cào dữ liệu: {e}")
    
    return channels

def write_m3u(data, filename="bongda.m3u"):
    if not data:
        print("Không có dữ liệu để ghi file.")
        return

    with open(filename, "w", encoding="utf-8") as f:
        # Header bắt buộc
        f.write("#EXTM3U\n")
        
        for item in data:
            # Format y hệt file mẫu: #EXTINF:-1 tvg-id="" tvg-logo="LINK" group-title="NHÓM",TÊN
            line = f'#EXTINF:-1 tvg-id="" tvg-logo="{item["logo"]}" group-title="{item["group"]}",{item["name"]}\n'
            f.write(line)
            f.write(f'{item["url"]}\n')
            
    print(f"--- Đã tạo file {filename} thành công với {len(data)} trận đấu ---")

if __name__ == "__main__":
    print("🤖 Bot đang quét lịch thi đấu...")
    data = scrape_hoiquan()
    write_m3u(data)
