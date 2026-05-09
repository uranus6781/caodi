import requests
from bs4 import BeautifulSoup
import os

def scrape_hoiquan():
    url = "https://sv2.hoiquan2.live/lich-thi-dau/bong-da"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    
    results = []
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            print(f"Lỗi truy cập web: {response.status_code}")
            return results

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Tìm các khối trận đấu dựa trên cấu trúc thực tế của hoiquan2
        # Chúng ta quét rộng để không bỏ sót trận nào
        items = soup.select('.item-match, .match-item, [class*="match"]')

        for item in items:
            try:
                # 1. Lấy thời gian thi đấu
                time_tag = item.select_one('.time, .match-time, span[class*="time"]')
                time_str = time_tag.get_text(strip=True) if time_tag else "LIVE"

                # 2. Lấy tên 2 đội bóng
                teams = item.select('.team-name, .name, strong')
                if len(teams) >= 2:
                    t1 = teams[0].get_text(strip=True)
                    t2 = teams[1].get_text(strip=True)
                    display_name = f"{time_str} | {t1} vs {t2}"
                else:
                    # Dự phòng nếu không tìm thấy 2 đội riêng biệt
                    name_tag = item.select_one('.match-name, a')
                    display_name = f"{time_str} | {name_tag.get_text(strip=True)}" if name_tag else f"{time_str} | Trận đấu bóng đá"

                # 3. Lấy Logo trận đấu/đội bóng
                img = item.find('img')
                logo = img['src'] if img and img.has_attr('src') else ""
                if logo.startswith('//'):
                    logo = "https:" + logo
                elif logo.startswith('/') and not logo.startswith('//'):
                    logo = "https://sv2.hoiquan2.live" + logo

                # 4. Lấy link xem trực tiếp
                link_tag = item.find('a', href=True)
                url_view = link_tag['href'] if link_tag else ""
                if url_view.startswith('/'):
                    url_view = "https://sv2.hoiquan2.live" + url_view

                if url_view and "lich-thi-dau" not in url_view: # Loại bỏ link quay lại chính nó
                    results.append({
                        "name": display_name,
                        "url": url_view,
                        "logo": logo,
                        "group": "Bóng Đá Trực Tiếp"
                    })
            except Exception:
                continue

    except Exception as e:
        print(f"Lỗi trong quá trình cào: {e}")
    
    return results

def save_to_m3u(data, filename="bongda.m3u"):
    """Hàm này thay thế hoàn toàn logic JSON cũ để xuất ra M3U chuẩn"""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            
            if not data:
                # Nếu không có trận nào, ghi 1 dòng thông báo để tránh file trống
                f.write('#EXTINF:-1 tvg-id="" tvg-logo="https://cdn-icons-png.flaticon.com/512/4076/4076432.png" group-title="Thông báo",Hiện chưa có trận nào đang đá\n')
                f.write('https://example.com/no-match.m3u8\n')
            else:
                for item in data:
                    # Ghi dòng thông tin theo cấu trúc file mẫu của bạn
                    f.write(f'#EXTINF:-1 tvg-id="" tvg-logo="{item["logo"]}" group-title="{item["group"]}",{item["name"]}\n')
                    # Ghi dòng link
                    f.write(f'{item["url"]}\n')
                    
        print(f"✅ Đã xuất file M3U thành công tại: {filename}")
    except Exception as e:
        print(f"Lỗi khi ghi file M3U: {e}")

if __name__ == "__main__":
    print("--- Bắt đầu Bot cào bóng đá ---")
    match_data = scrape_hoiquan()
    save_to_m3u(match_data)
