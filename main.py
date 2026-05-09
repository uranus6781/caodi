def json_to_m3u(json_content):
    data = json.loads(json_content)
    lines = ["#EXTM3U"]
    lines.append(f"#PLAYLISTNAME: Sáng TV - Last Updated: {data.get('last_updated')}")
    lines.append("")

    # Duyệt qua các kênh trong JSON (buncha, hoiquan)
    for key in ["buncha", "hoiquan"]:
        matches = data.get(key, [])
        group_title = "Bún Chả TV" if key == "buncha" else "Hội Quán TV"
        
        for m in matches:
            stream_url = m.get("stream_url")
            # Chỉ thêm vào m3u nếu có link stream thực tế (không phải link chờ)
            if stream_url and stream_url != "https://example.com/waiting.mp4":
                title = f"{m['trang_thai']} {m['title']} - {m['thoi_gian']}"
                logo = m.get("logo_nha") or m.get("logo_khach") or ""
                
                lines.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group_title}",{title}')
                lines.append(stream_url)
                lines.append("")
    
    return "\n".join(lines)
