# -*- coding: utf-8 -*-
"""下载 DouyinLiveWebFetcher 的 webmssdk 签名脚本 sign.js 到 core/js/"""
import os, sys
import requests

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
js_dir = os.path.join(base, "core", "js")
os.makedirs(js_dir, exist_ok=True)

urls = [
    "https://raw.githubusercontent.com/saermart/DouyinLiveWebFetcher/main/sign.js",
    "https://ghproxy.net/https://raw.githubusercontent.com/saermart/DouyinLiveWebFetcher/main/sign.js",
]
dest = os.path.join(js_dir, "sign.js")
ok = False
for u in urls:
    try:
        print("downloading:", u)
        r = requests.get(u, timeout=30)
        print("  status:", r.status_code, "len:", len(r.text))
        if r.status_code == 200 and len(r.text) > 1000 and "get_sign" in r.text:
            with open(dest, "w", encoding="utf-8") as f:
                f.write(r.text)
            print("  saved ->", dest, "has get_sign:", "get_sign" in r.text)
            ok = True
            break
    except Exception as e:
        print("  err:", e)
print("RESULT:", "OK" if ok else "FAILED")
