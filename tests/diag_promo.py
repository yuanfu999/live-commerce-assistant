# -*- coding: utf-8 -*-
"""诊断3：用正确的 room_id + author_id 直接调用商品接口，验证 HTTP 路径是否可行"""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

web_rid = "980307700648"
room_id = "7667330965001227008"
author_id = "1179141068823693"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
    "Referer": f"https://live.douyin.com/{web_rid}",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
s = requests.Session()
# 先拿 ttwid
s.get(f"https://live.douyin.com/{web_rid}", headers=headers, timeout=15)
print("cookies:", list(s.cookies.keys()))

api = "https://live.douyin.com/live/promotions/page/"
params = {
    "device_platform": "webapp", "aid": "6383", "channel": "channel_pc_web",
    "room_id": room_id, "author_id": author_id, "offset": "0", "limit": "50",
    "pc_client_type": "1", "version_code": "320100", "version_name": "32.1.0",
    "cookie_enabled": "true", "browser_language": "zh-CN", "browser_platform": "Win32",
    "browser_name": "Edge", "browser_version": "140.0.0.0",
}
api_headers = {
    "User-Agent": headers["User-Agent"],
    "Referer": f"https://live.douyin.com/{web_rid}",
    "Origin": "https://live.douyin.com",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}
r = s.post(api, params=params, headers=api_headers, data="", timeout=15)
print("POST /live/promotions/page/ status:", r.status_code, "len:", len(r.text))
print("body head:", r.text[:500])
try:
    d = r.json()
    print("status_code:", d.get("status_code"), "keys:", list(d.keys()))
    data = d.get("data", {})
    if isinstance(data, dict):
        print("data keys:", list(data.keys()))
        promos = data.get("promotions") or data.get("products") or []
        print("promotions count:", len(promos))
        if promos:
            print("first promo keys:", list(promos[0].keys())[:30])
except Exception as e:
    print("not json:", e)
