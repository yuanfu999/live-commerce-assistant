# -*- coding: utf-8 -*-
"""诊断2：在新版 __pace_f 结构中定位 room_id / author_id / sec_uid 的可靠提取模式"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

url = sys.argv[1]
web_rid = re.search(r'live\.douyin\.com/(\d+)', url).group(1)
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
    "Referer": "https://live.douyin.com/",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
s = requests.Session()
html = s.get(f"https://live.douyin.com/{web_rid}", headers=headers, timeout=15).text

def show(label, pat, n=6):
    m = re.findall(pat, html)
    uniq = list(dict.fromkeys(m))
    print(f"{label}: {uniq[:n]}")

print("=== room_id 相关 ===")
show("roomId(escaped)",   r'\\"roomId\\":\\"(\d{15,})\\"')
show("roomId(plain)",     r'"roomId"\s*:\s*"(\d{15,})"')
show("id_str(escaped)",   r'\\"id_str\\":\\"(\d{15,})\\"')
show("room_id(escaped)",  r'\\"room_id\\":\\"(\d{15,})\\"')

print("\n=== author/owner/sec_uid 相关 ===")
show("owner_user_id(esc)", r'\\"owner_user_id\\":\\?"?(\d{6,})\\?"?')
show("web_rid(esc)",       r'\\"web_rid\\":\\"(\d+)\\"')
show("sec_uid(esc)",       r'\\"sec_uid\\":\\"([\w\-]+)\\"')
show("id_str all 6+",      r'\\"id_str\\":\\"(\d{6,})\\"')
show("user_id(esc)",       r'\\"user_id\\":\\?"?(\d{6,})\\?"?')

# 打印 roomId 附近上下文，理解owner嵌套
m = re.search(r'roomId\\":\\"(\d{15,})\\"', html)
if m:
    start = max(0, m.start() - 200)
    end = min(len(html), m.end() + 600)
    print("\n=== roomId 附近上下文 ===")
    print(html[start:end])
