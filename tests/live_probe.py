# -*- coding: utf-8 -*-
"""
实测脚本：用真实直播间链接验证
  1) 弹幕连接（评论/点赞/关注/礼物/进场/统计）
  2) 小黄车商品 HTTP 拉取（fetch_room_products）

用法:
  python tests/live_probe.py "<直播间URL>" [连接秒数]
"""
import sys
import os
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from core.douyin_connector import DouyinConnector


def test_products(url):
    print("\n" + "=" * 60)
    print("【测试一】小黄车商品 HTTP 拉取")
    print("=" * 60)
    t0 = time.time()
    try:
        products = DouyinConnector.fetch_room_products(url, cookie="")
        print(f"成功拉取 {len(products)} 个商品（耗时 {time.time()-t0:.1f}s）：")
        for p in products[:20]:
            print(f"  [{p.get('index')}] {p.get('name')} | 价格:{p.get('price')} "
                  f"| 原价:{p.get('market_price')} | 已售:{p.get('sales')} "
                  f"| id:{p.get('product_id')}")
    except Exception as e:
        print(f"HTTP 拉取失败：{e}")
    print("(注：GUI 中的浏览器拉取方式 ProductFetchDialog 需要 WebEngine 窗口，"
          "会自动携带 a_bogus 签名，成功率更高)")


def test_danmaku(url, seconds):
    print("\n" + "=" * 60)
    print(f"【测试二】弹幕连接（持续 {seconds} 秒）")
    print("=" * 60)

    app = QApplication.instance() or QApplication(sys.argv)
    conn = DouyinConnector()
    conn.set_room(url)

    counter = Counter()
    samples = {}

    def on_danmaku(user, content, mtype):
        counter[mtype] += 1
        # 每种类型保留前若干条样例
        samples.setdefault(mtype, [])
        if len(samples[mtype]) < 5:
            samples[mtype].append(f"{user}: {content}")
        print(f"  [{mtype}] {user}: {content}")

    def on_stats(text):
        counter["stats"] += 1
        print(f"  [stats] {text}")

    def on_connected():
        print(">> 连接成功，开始接收消息...")

    def on_error(msg):
        print(f">> 错误: {msg}")

    def on_live_ended():
        print(">> 主播已下播")

    def on_reconnect(n):
        print(f">> 断线重连中... 第{n}次")

    conn.danmaku_received.connect(on_danmaku)
    conn.stats_updated.connect(on_stats)
    conn.connected.connect(on_connected)
    conn.error_occurred.connect(on_error)
    conn.live_ended.connect(on_live_ended)
    conn.reconnecting.connect(on_reconnect)

    def finish():
        conn.stop_connect()
        QTimer.singleShot(1500, app.quit)

    QTimer.singleShot(seconds * 1000, finish)
    conn.start_connect()
    app.exec()

    print("\n---- 消息统计 ----")
    if not counter:
        print("  未收到任何消息（可能未开播/被限流/需要登录cookie）")
    for k, v in counter.most_common():
        print(f"  {k}: {v} 条")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else ""
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 35
    if not url:
        print("请提供直播间URL")
        sys.exit(1)
    print("测试直播间:", url)
    test_products(url)
    test_danmaku(url, seconds)
