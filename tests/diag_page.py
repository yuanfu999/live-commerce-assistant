# -*- coding: utf-8 -*-
"""诊断：抓取直播间页面，检查 room_id 数据结构现状"""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

url = sys.argv[1]
web_rid = re.search(r'live\.douyin\.com/(\d+)', url).group(1)
print("web_rid =", web_rid)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
    "Referer": "https://live.douyin.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
s = requests.Session()
r = s.get(f"https://live.douyin.com/{web_rid}", headers=headers, timeout=15)
print("status:", r.status_code, "len:", len(r.text))
print("cookies:", dict(s.cookies))
html = r.text

print("\n-- 关键标记检测 --")
for tag in ["RENDER_DATA", "__pace_f", "room_id", "id_str", "roomInfo",
            "web_rid", "self.__pace", "loginGuide", "验证", "滑块", "captcha"]:
    print(f"  {tag!r:16}: {'YES' if tag in html else '-'}  (count={html.count(tag)})")

print("\n-- room_id 候选 --")
for pat in [r'"room_id"\s*:\s*"?(\d{15,})"?', r'"id_str"\s*:\s*"(\d{15,})"',
            r'roomId\\?"?\s*[:=]\s*\\?"?(\d{15,})']:
    m = re.findall(pat, html)
    print(f"  {pat[:40]:42} -> {list(set(m))[:5]}")

# 保存前2000字符看结构
snippet = html[:2000]
print("\n-- HTML 开头片段 --")
print(snippet)
