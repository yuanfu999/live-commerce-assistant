"""抖音直播间弹幕连接器 - WebSocket协议抓取弹幕"""
import asyncio
import json
import re
import time
import gzip
import threading
from typing import Optional, Callable, List, Dict
from PyQt6.QtCore import QThread, pyqtSignal

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    import requests
except ImportError:
    requests = None

from core import app_logger


# ==================== protobuf wire-format 轻量解析/编码 ====================
# 抹音WebSocket二进制帧为protobuf编码（PushFrame->gzip(Response)->Message），
# 不依赖protobuf库，以下函数手工读写wire format。

def _pb_read_varint(data, pos):
    """读取varint，返回(值, 新偏移)"""
    result = 0
    shift = 0
    n = len(data)
    while pos < n:
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
    return result, pos


def _pb_parse(data):
    """解析protobuf字段，返回 {field_number: [value, ...]}（varint->int，长度前缀->bytes）"""
    fields = {}
    pos = 0
    n = len(data)
    while pos < n:
        try:
            key, pos = _pb_read_varint(data, pos)
        except Exception:
            break
        field_num = key >> 3
        wire_type = key & 0x07
        if field_num == 0:
            break
        if wire_type == 0:      # varint
            val, pos = _pb_read_varint(data, pos)
        elif wire_type == 1:    # 64位定长
            val = data[pos:pos + 8]
            pos += 8
        elif wire_type == 2:    # 长度前缀（字符串/bytes/嵌套消息）
            length, pos = _pb_read_varint(data, pos)
            if length < 0 or pos + length > n:
                break
            val = data[pos:pos + length]
            pos += length
        elif wire_type == 5:    # 32位定长
            val = data[pos:pos + 4]
            pos += 4
        else:
            break
        fields.setdefault(field_num, []).append(val)
    return fields


def _pb_encode_varint(n):
    """整数编码为varint"""
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _pb_field(field_num, wire_type, value):
    """编码单个protobuf字段"""
    key = _pb_encode_varint((field_num << 3) | wire_type)
    if wire_type == 0:      # varint
        return key + _pb_encode_varint(value)
    if wire_type == 2:      # 长度前缀
        if isinstance(value, str):
            value = value.encode('utf-8')
        return key + _pb_encode_varint(len(value)) + value
    return key


class DouyinConnector(QThread):
    """
    抖音直播间弹幕连接（QThread后台运行）

    参照开源项目 DouyinLiveWebFetcher (saermart) 的协议实现：
    - WSS推送流解析: PushFrame -> gzip(Response) -> Message[]
    - 支持消息类型: 弹幕/礼物/点赞/关注/进场/粉丝团/统计/下播

    信号：
        danmaku_received: 收到弹幕 (username, content, msg_type)
            msg_type: "chat"|"enter"|"gift"|"like"|"follow"|"fansclub"
        stats_updated: 直播间统计数据更新（在线人数/累计观看）
        live_ended: 主播下播
        connected: 连接成功
        disconnected: 断开连接
        error_occurred: 发生错误
    """
    danmaku_received = pyqtSignal(str, str, str)  # username, content, type
    stats_updated = pyqtSignal(str)               # 统计信息文本
    live_ended = pyqtSignal()
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    error_occurred = pyqtSignal(str)
    reconnecting = pyqtSignal(int)  # 断线重连中（当前重试次数）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._room_url = ""
        self._room_id = ""
        self._stop_event = threading.Event()
        self.cookie = ""  # 抹音登录cookie
        # 断线自动重连配置
        self._reconnect_count = 0
        self.max_reconnect = 10  # 最大重连次数
        self.reconnect_wait = 5  # 重连间隔（秒）
        # 礼物连击去重：(用户,礼物名)->上次播报时间戳，避免连击刷屏与AI重复感谢
        self._gift_last = {}

    def set_room(self, url: str):
        """设置直播间URL"""
        self._room_url = url.strip()

    def start_connect(self):
        """开始连接"""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self.start()

    def stop_connect(self):
        """断开连接"""
        self._running = False
        self._stop_event.set()

    def run(self):
        """后台线程运行异步事件循环（带断线自动重连）"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            while self._running and not self._stop_event.is_set():
                try:
                    loop.run_until_complete(self._async_connect())
                except Exception as e:
                    if self._running:
                        self.error_occurred.emit(f"连接错误: {str(e)}")
                # 连接已结束：若为用户主动停止则退出，否则尝试重连
                if not self._running or self._stop_event.is_set():
                    break
                self._reconnect_count += 1
                if self._reconnect_count > self.max_reconnect:
                    self.error_occurred.emit(
                        f"连续重连{self.max_reconnect}次失败，已停止。请检查网络后手动重连"
                    )
                    break
                self.reconnecting.emit(self._reconnect_count)
                # 等待重连间隔（可被停止信号打断）
                if self._stop_event.wait(self.reconnect_wait):
                    break
        finally:
            loop.close()
            self.disconnected.emit()

    async def _async_connect(self):
        """异步连接抖音直播间（参照DouyinLiveWebFetcher的连接参数）"""
        if not aiohttp:
            self.error_occurred.emit("缺少aiohttp库，请运行: pip install aiohttp")
            return

        # 从URL提取web_rid（短号）
        web_rid = self._extract_room_id(self._room_url)
        if not web_rid:
            self.error_occurred.emit("无法解析直播间ID，请输入正确的直播间URL")
            return

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
            "Referer": "https://live.douyin.com/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        try:
            async with aiohttp.ClientSession() as session:
                # 第一步：访问直播间页面，获取真实room_id和ttwid cookie
                room_id, ttwid = await self._fetch_room_info(session, web_rid, headers)
                if not room_id:
                    self.error_occurred.emit("获取直播间信息失败（直播间可能未开播或被限制访问）")
                    return
                self._room_id = room_id

                # 第二步：构造WebSocket URL（与开源项目一致的标准参数）
                import random
                now_ms = int(time.time() * 1000)
                did = str(random.randint(7300000000000000000, 7399999999999999999))
                internal_ext = (
                    f"internal_src:dim|wss_push_room_id:{room_id}"
                    f"|wss_push_did:{did}|first_req_ms:{now_ms}"
                    f"|fetch_time:{now_ms}|seq:1|wss_info:0-{now_ms}-0-0|wrds_v:{now_ms}"
                )
                ws_url = (
                    "wss://webcast100-ws-web-lq.douyin.com/webcast/im/push/v2/"
                    "?app_name=douyin_web&version_code=180800"
                    "&webcast_sdk_version=1.0.14-beta.0"
                    "&update_version_code=1.0.14-beta.0"
                    "&compress=gzip&device_platform=web&cookie_enabled=true"
                    "&screen_width=1920&screen_height=1080"
                    "&browser_language=zh-CN&browser_platform=Win32"
                    "&browser_name=Mozilla"
                    "&browser_version=5.0%20(Windows%20NT%2010.0;%20Win64;%20x64)%20"
                    "AppleWebKit/537.36%20(KHTML,%20like%20Gecko)%20Chrome/140.0.0.0%20Safari/537.36"
                    "&browser_online=true&tz_name=Asia/Shanghai"
                    f"&cursor=&internal_ext={internal_ext}"
                    "&host=https://live.douyin.com&aid=6383&live_id=1&did_rule=3"
                    "&endpoint=live_pc&support_wrds=1"
                    f"&user_unique_id={did}&im_path=/webcast/im/fetch/"
                    "&identity=audience&need_persist_msg_count=15"
                    "&insert_task_id=&live_reason="
                    f"&room_id={room_id}&heartbeatDuration=0"
                )

                # 第二步补充：为 wss URL 生成 signature（抖音现要求，否则握手被拒）
                try:
                    from core.signer import generate_signature
                    signature = generate_signature(ws_url)
                    if signature:
                        ws_url += f"&signature={signature}"
                        app_logger.log_info("wss 签名生成成功")
                    else:
                        app_logger.log_error("wss 签名生成失败，将尝试无签名连接（可能被拒绝）")
                except Exception as _se:
                    app_logger.log_error("wss 签名异常: " + str(_se))

                ws_headers = dict(headers)
                if ttwid:
                    ws_headers["Cookie"] = f"ttwid={ttwid}"

                async with session.ws_connect(ws_url, headers=ws_headers, timeout=15) as ws:
                    self.connected.emit()
                    self._reconnect_count = 0  # 连接成功，重置重连计数
                    app_logger.log_info("弹幕连接成功 room_id=" + str(room_id))

                    # 启动心跳任务（每10秒发送PushFrame hb，参照开源项目）
                    hb_task = asyncio.ensure_future(self._heartbeat_loop(ws))
                    try:
                        while self._running:
                            try:
                                msg = await asyncio.wait_for(ws.receive(), timeout=30)
                            except asyncio.TimeoutError:
                                continue  # 心跳任务负责保活
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                self._parse_message(msg.data)
                            elif msg.type == aiohttp.WSMsgType.BINARY:
                                await self._handle_binary(ws, msg.data)
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
                    finally:
                        hb_task.cancel()
        except Exception as e:
            if self._running:
                app_logger.log_error("弹幕连接失败: " + str(e))
                self.error_occurred.emit(f"连接失败: {str(e)}")

    async def _heartbeat_loop(self, ws):
        """心跳保活：每10秒发送PushFrame(payload_type='hb')"""
        hb_frame = _pb_field(7, 2, b"hb")
        while True:
            await asyncio.sleep(10)
            try:
                await ws.ping(hb_frame)
            except Exception:
                break
    
    async def _fetch_room_info(self, session, web_rid: str, headers: dict):
        """访问直播间页面，解析真实room_id并获取ttwid cookie。
        返回 (room_id, ttwid)，失败时room_id为空字符串"""
        text = ""
        ttwid = ""
        try:
            async with session.get(f"https://live.douyin.com/{web_rid}",
                                   headers=headers, timeout=15) as resp:
                # 从Set-Cookie提取ttwid
                for h in resp.headers.getall("Set-Cookie", []):
                    m = re.search(r'ttwid=([^;]+)', h)
                    if m:
                        ttwid = m.group(1)
                        break
                text = await resp.text()
        except Exception as e:
            app_logger.log_error("访问直播间页面失败: " + str(e))
            return "", ""
    
        # 解析真实room_id（19位内部ID，非URL中的短号）
        # 抖音2024末改版：页面数据从 RENDER_DATA 迁移到 self.__pace_f 流式结构，
        # 统一走 _extract_ids_from_html 兼容新旧两种格式
        room_id, _author_id, _sec_uid = DouyinConnector._extract_ids_from_html(text)
        if not room_id:
            # 页面无有效数据：可能未开播或反爬限制
            app_logger.log_warn("未能从直播间页面解析真实room_id（web_rid=" + str(web_rid) + "）")
        return room_id, ttwid

    @staticmethod
    def _extract_ids_from_html(html: str):
        """从直播间页面HTML提取 (room_id, author_id, sec_uid)。

        兼容两种数据结构：
        - 新版 self.__pace_f 流式数据：字段以反斜杠转义嵌入，如
          \\"roomId\\":\\"7667...\\",\\"anchor\\":{\\"id_str\\":\\"1179...\\",\\"sec_uid\\":\\"MS4w...\\"}
        - 旧版 RENDER_DATA JSON（保留兜底）
        """
        room_id, author_id, sec_uid = "", "", ""
        if not html:
            return room_id, author_id, sec_uid

        # ---- 1) 新版转义结构（当前线上）----
        m = re.search(r'\\"roomId\\":\\"(\d{15,})\\"', html)
        if not m:
            m = re.search(r'"roomId"\s*:\s*"(\d{15,})"', html)
        if m:
            room_id = m.group(1)

        # author_id 优先取 anchor.id_str（紧跟在 roomId/web_rid 之后）
        m = re.search(r'\\"anchor\\":\{\\"id_str\\":\\"(\d+)\\"', html)
        if not m:
            m = re.search(r'"anchor"\s*:\s*\{\s*"id_str"\s*:\s*"(\d+)"', html)
        if m:
            author_id = m.group(1)

        m = re.search(r'\\"sec_uid\\":\\"([\w\-]+)\\"', html)
        if not m:
            m = re.search(r'"sec_uid"\s*:\s*"([\w\-]+)"', html)
        if m:
            sec_uid = m.group(1)

        # ---- 2) 旧版 RENDER_DATA JSON 兜底 ----
        if not room_id:
            render_match = re.search(
                r'<script id="RENDER_DATA" type="application/json">(.*?)</script>',
                html, re.DOTALL
            )
            if render_match:
                try:
                    from urllib.parse import unquote
                    render_data = json.loads(unquote(render_match.group(1)))
                    room_id, aid = DouyinConnector._extract_room_and_author(render_data)
                    if aid and not author_id:
                        author_id = aid
                except Exception:
                    pass

        # ---- 3) 通用正则兜底 ----
        if not room_id:
            m = re.search(r'\\?"room_id\\?"\s*:\s*\\?"(\d{15,})\\?"', html)
            if m:
                room_id = m.group(1)
        if not author_id:
            m = re.search(r'\\?"owner_user_id\\?"\s*:\s*\\?"?(\d{6,})', html)
            if m:
                author_id = m.group(1)

        return room_id, author_id, sec_uid

    def _extract_room_id(self, url: str) -> str:
        """从URL中提取room_id"""
        # 支持格式：
        # https://live.douyin.com/123456789
        # https://live.douyin.com/123456789?xxx
        # 直接输入数字
        if url.isdigit():
            return url

        match = re.search(r'live\.douyin\.com/(\d+)', url)
        if match:
            return match.group(1)

        # 尝试匹配其他格式
        match = re.search(r'room_id=(\d+)', url)
        if match:
            return match.group(1)

        return ""

    @staticmethod
    def fetch_room_products(room_url: str, cookie: str = "") -> List[Dict]:
        """
        拉取直播间小黄车商品列表
        接口: POST https://live.douyin.com/live/promotions/page/
        
        返回: [{"name": ..., "price": ..., "image": ..., "index": ...}, ...]
        """
        if not requests:
            raise Exception("缺少requests库，请运行: pip install requests")

        # 提取web_rid
        web_rid = ""
        if room_url.strip().isdigit():
            web_rid = room_url.strip()
        else:
            match = re.search(r'live\.douyin\.com/(\d+)', room_url)
            if match:
                web_rid = match.group(1)

        if not web_rid:
            raise Exception("无法解析直播间ID，请输入正确的直播间URL或房间号")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
            "Referer": f"https://live.douyin.com/{web_rid}",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if cookie:
            headers["Cookie"] = cookie

        session = requests.Session()
        if cookie:
            for item in cookie.split(";"):
                item = item.strip()
                if "=" in item:
                    k, v = item.split("=", 1)
                    session.cookies.set(k.strip(), v.strip(), domain=".douyin.com")

        # 第一步：访问直播间页面，获取真实room_id、author_id和ttwid cookie
        try:
            page_resp = session.get(
                f"https://live.douyin.com/{web_rid}",
                headers=headers,
                timeout=15
            )
            page_resp.raise_for_status()
        except Exception as e:
            raise Exception(f"访问直播间页面失败: {str(e)}")

        # 自动从Set-Cookie提取ttwid（商品接口必须携带）
        if not session.cookies.get("ttwid", domain=".douyin.com"):
            for h in page_resp.headers.get("Set-Cookie", "").split(","):
                m = re.search(r'ttwid=([^;]+)', h)
                if m:
                    session.cookies.set("ttwid", m.group(1), domain=".douyin.com")
                    break
            # requests自动处理的cookie也可能包含ttwid
            if page_resp.cookies.get("ttwid"):
                session.cookies.set("ttwid", page_resp.cookies["ttwid"], domain=".douyin.com")

        page_text = page_resp.text
        real_room_id = ""
        author_id = ""

        # 从页面提取 room_id 和 author_id（兼容新版 __pace_f / 旧版 RENDER_DATA）
        real_room_id, author_id, _sec_uid = DouyinConnector._extract_ids_from_html(page_text)
        render_match = re.search(
            r'<script id="RENDER_DATA" type="application/json">(.*?)</script>',
            page_text, re.DOTALL
        )

        if not real_room_id:
            real_room_id = web_rid

        # 第二步：调用商品列表API
        products = []

        # 方式A: POST /live/promotions/page/（新版接口）
        api_url = "https://live.douyin.com/live/promotions/page/"
        params = {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "room_id": real_room_id,
            "author_id": author_id,
            "offset": "0",
            "limit": "50",
            "pc_client_type": "1",
            "version_code": "320100",
            "version_name": "32.1.0",
            "cookie_enabled": "true",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Edge",
            "browser_version": "126.0.0.0",
        }

        api_headers = {
            "User-Agent": headers["User-Agent"],
            "Referer": f"https://live.douyin.com/{web_rid}",
            "Origin": "https://live.douyin.com",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        if cookie:
            api_headers["Cookie"] = cookie

        try:
            resp = session.post(api_url, params=params, headers=api_headers, data="", timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                products = DouyinConnector._parse_promotions_response(data)
        except Exception:
            pass

        # 方式B: GET /live/promotion/v2/（旧版接口，部分环境仍可用）
        if not products:
            try:
                v2_url = "https://live.douyin.com/live/promotion/v2/"
                v2_params = {
                    "room_id": real_room_id,
                    "author_id": author_id,
                    "aid": "6383",
                    "app_name": "douyin_web",
                    "device_platform": "web",
                    "language": "zh-CN",
                    "enter_from": "page_refresh",
                    "cookie_enabled": "true",
                    "browser_language": "zh-CN",
                    "browser_platform": "Win32",
                    "browser_name": "Edge",
                    "browser_version": "140.0.0.0",
                }
                resp2 = session.get(v2_url, params=v2_params, headers=api_headers, timeout=15)
                if resp2.status_code == 200:
                    data2 = resp2.json()
                    products = DouyinConnector._parse_promotions_response(data2)
            except Exception:
                pass

        # 第三步：如果API失败，从RENDER_DATA递归搜索
        if not products and render_match:
            try:
                from urllib.parse import unquote
                render_data = json.loads(unquote(render_match.group(1)))
                products = DouyinConnector._search_products_in_data(render_data)
            except Exception:
                pass

        # 第四步：从HTML正则提取
        if not products:
            products = DouyinConnector._extract_products_from_html(page_text)

        if not products:
            raise Exception(
                "未能获取到商品列表。\n\n"
                "可能原因：\n"
                "1. 直播间未开播或未挂载小黄车\n"
                "2. 抖音接口反爬限制（缺少a_bogus签名）\n"
                "3. Cookie已过期\n\n"
                "建议：在浏览器登录抖音后复制Cookie填入，或手动添加商品。"
            )

        return products

    @staticmethod
    def _extract_room_and_author(data, depth=0):
        """递归查找真实room_id和author_id"""
        if depth > 8:
            return "", ""
        if isinstance(data, dict):
            # 查找 roomInfo.room 结构
            room_info = data.get("roomInfo", {}).get("room", {})
            if room_info and room_info.get("id_str"):
                rid = str(room_info["id_str"])
                # author_id 可能在 owner 或 author 中
                aid = ""
                owner = room_info.get("owner", {})
                if isinstance(owner, dict):
                    aid = str(owner.get("id_str", "") or owner.get("user_id", ""))
                if not aid:
                    author = room_info.get("author", {})
                    if isinstance(author, dict):
                        aid = str(author.get("id_str", "") or author.get("user_id", ""))
                if not aid:
                    aid = str(room_info.get("owner_user_id", ""))
                return rid, aid

            # 查找其他结构
            if data.get("id_str") and data.get("status") is not None and len(str(data.get("id_str", ""))) > 15:
                rid = str(data["id_str"])
                aid = ""
                owner = data.get("owner", {})
                if isinstance(owner, dict):
                    aid = str(owner.get("id_str", "") or owner.get("user_id", ""))
                return rid, aid

            for val in data.values():
                if isinstance(val, (dict, list)):
                    rid, aid = DouyinConnector._extract_room_and_author(val, depth + 1)
                    if rid:
                        return rid, aid
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    rid, aid = DouyinConnector._extract_room_and_author(item, depth + 1)
                    if rid:
                        return rid, aid
        return "", ""

    @staticmethod
    def _parse_promotions_response(data: dict) -> List[Dict]:
        """解析 /live/promotions/page/ 接口返回"""
        products = []
        if not isinstance(data, dict):
            return products

        # 响应结构: {"data": {"promotions": [...]}, "status_code": 0}
        promotions = []
        d = data.get("data", data)
        if isinstance(d, dict):
            promotions = (
                d.get("promotions", []) or
                d.get("products", []) or
                d.get("product_list", []) or
                []
            )

        if not promotions:
            return products

        for idx, item in enumerate(promotions):
            if not isinstance(item, dict):
                continue

            # 商品可能在 item 本身或 item["product"] 中
            prod = item.get("product", item) if isinstance(item.get("product"), dict) else item

            name = (
                prod.get("title", "") or
                prod.get("name", "") or
                item.get("title", "") or
                item.get("name", "") or
                ""
            )
            if not name:
                continue

            # 现价（抹音通常以分为单位）
            price = DouyinConnector._format_price(
                prod.get("price", "") or prod.get("min_price", "") or
                prod.get("promotion_price", "") or item.get("price", "") or ""
            )
            # 划线原价（市场价）
            market_price = DouyinConnector._format_price(
                prod.get("market_price", "") or prod.get("origin_price", "") or
                item.get("market_price", "") or ""
            )
            # 价格区间（多sku时 min~max）
            max_price = DouyinConnector._format_price(
                prod.get("max_price", "") or item.get("max_price", "") or ""
            )
            if max_price and price and max_price != price:
                price = f"{price}~{max_price}"

            image = (
                prod.get("cover", "") or
                prod.get("img", "") or
                prod.get("image", "") or
                item.get("cover", "") or
                ""
            )
            # 图片可能是url列表或 {url_list:[...]}
            if isinstance(image, list):
                image = image[0] if image else ""
            if isinstance(image, dict):
                image = image.get("url_list", [""])[0] if image.get("url_list") else ""

            # 销量（已售件数）
            sales = (
                item.get("sales", "") or item.get("sell_num", "") or
                prod.get("sales", "") or prod.get("sell_num", "") or
                (item.get("stat", {}).get("sales", "") if isinstance(item.get("stat"), dict) else "") or
                ""
            )
            sales = str(sales) if sales not in ("", None) else ""

            # 商品ID
            product_id = str(
                prod.get("product_id", "") or prod.get("promotion_id", "") or
                item.get("product_id", "") or item.get("promotion_id", "") or
                prod.get("id", "") or ""
            )
            # 商品详情链接
            url = (
                item.get("detail_url", "") or item.get("short_url", "") or
                item.get("schema_url", "") or prod.get("detail_url", "") or ""
            )

            products.append({
                "name": name,
                "price": price,
                "image": image,
                "market_price": market_price,
                "sales": sales,
                "product_id": product_id,
                "url": url,
                "index": idx + 1,
            })

        return products

    @staticmethod
    def _format_price(price_val) -> str:
        """抹音价格归一化：分->元。接口价格多以分为单位（整数），转为“xx元”"""
        if price_val in ("", None):
            return ""
        price_str = str(price_val).strip()
        if not price_str:
            return ""
        if price_str.isdigit() and int(price_str) >= 100:
            return f"{int(price_str) / 100:.2f}".rstrip("0").rstrip(".") + "元"
        if price_str.replace(".", "", 1).isdigit():
            return f"{price_str}元"
        return price_str
    
    @staticmethod
    def _search_products_in_data(data, depth=0) -> List[Dict]:
        """递归搜索JSON数据中的商品列表"""
        if depth > 10:
            return []
    
        products = []
    
        if isinstance(data, dict):
            # 检查当前层是否包含商品列表
            for key in ["products", "product_list", "productList", "goods", "goodsList"]:
                if key in data and isinstance(data[key], list) and len(data[key]) > 0:
                    parsed = DouyinConnector._parse_product_list(data[key])
                    if parsed:
                        return parsed
    
            # 检查特定的抹音数据结构
            if "productInfo" in data and isinstance(data["productInfo"], dict):
                for key in ["products", "product_list"]:
                    if key in data["productInfo"] and isinstance(data["productInfo"][key], list):
                        parsed = DouyinConnector._parse_product_list(data["productInfo"][key])
                        if parsed:
                            return parsed
    
            # 递归搜索子层
            for key, val in data.items():
                if isinstance(val, (dict, list)):
                    found = DouyinConnector._search_products_in_data(val, depth + 1)
                    if found:
                        return found
    
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    found = DouyinConnector._search_products_in_data(item, depth + 1)
                    if found:
                        return found
    
        return products
    
    @staticmethod
    def _parse_product_list(items: list) -> List[Dict]:
        """解析商品列表数组"""
        products = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            # 提取商品名称
            name = (
                item.get("title", "") or
                item.get("name", "") or
                item.get("product_name", "") or
                item.get("product", {}).get("title", "") if isinstance(item.get("product"), dict) else "" or
                ""
            )
            if not name:
                continue
    
            # 提取价格
            price = ""
            price_val = (
                item.get("price", "") or
                item.get("market_price", "") or
                item.get("min_price", "") or
                item.get("promotion_price", "") or
                (item.get("product", {}).get("price", "") if isinstance(item.get("product"), dict) else "")
            )
            if price_val:
                price_str = str(price_val)
                # 抹音价格通常以分为单位
                if price_str.isdigit() and int(price_str) > 100:
                    price = f"{int(price_str)/100:.1f}元"
                elif price_str.replace(".", "").isdigit():
                    price = f"{price_str}元"
                else:
                    price = price_str
    
            # 提取图片
            image = (
                item.get("cover", "") or
                item.get("img", "") or
                item.get("image", "") or
                item.get("cover_url", "") or
                (item.get("product", {}).get("cover", "") if isinstance(item.get("product"), dict) else "")
            )
    
            products.append({
                "name": name,
                "price": price,
                "image": image,
                "index": idx + 1,
            })
    
        return products
    
    @staticmethod
    def _extract_products_from_html(html: str) -> List[Dict]:
        """从HTML中提取商品数据（正则匹配）"""
        products = []
    
        # 尝试匹配页面中的商品卡片数据
        # 抹音直播间商品通常包含 title + price 的JSON结构
        patterns = [
            r'"title"\s*:\s*"([^"]+)"[^}]*?"price"\s*:\s*"?(\d+)"?',
            r'"product_name"\s*:\s*"([^"]+)"[^}]*?"price"\s*:\s*"?(\d+)"?',
        ]
    
        for pattern in patterns:
            matches = re.findall(pattern, html)
            if matches:
                for idx, (name, price_val) in enumerate(matches):
                    if len(name) > 2 and not name.startswith("http"):
                        price = f"{int(price_val)/100:.1f}元" if price_val.isdigit() and int(price_val) > 100 else f"{price_val}元"
                        products.append({
                            "name": name,
                            "price": price,
                            "image": "",
                            "index": idx + 1,
                        })
                if products:
                    break
    
        return products

    def _parse_message(self, data: str):
        """解析文本消息"""
        try:
            msg_data = json.loads(data)
            if isinstance(msg_data, dict):
                # 根据消息类型分发
                method = msg_data.get("method", "")
                payload = msg_data.get("payload", {})

                if "WebcastChatMessage" in method:
                    user = payload.get("user", {}).get("nickname", "观众")
                    content = payload.get("content", "")
                    if content:
                        self.danmaku_received.emit(user, content, "chat")

                elif "WebcastMemberMessage" in method:
                    user = payload.get("user", {}).get("nickname", "观众")
                    self.danmaku_received.emit(user, "进入直播间", "enter")

                elif "WebcastGiftMessage" in method:
                    user = payload.get("user", {}).get("nickname", "观众")
                    gift_name = payload.get("gift", {}).get("name", "礼物")
                    self.danmaku_received.emit(user, f"送了{gift_name}", "gift")

                elif "WebcastLikeMessage" in method:
                    user = payload.get("user", {}).get("nickname", "观众")
                    self.danmaku_received.emit(user, "点赞了", "like")
        except (json.JSONDecodeError, KeyError):
            pass

    async def _handle_binary(self, ws, data: bytes):
        """处理二进制帧：PushFrame(protobuf) -> gzip解压payload -> Response -> 逐条Message解析"""
        try:
            fields = _pb_parse(data)
            # PushFrame: logId=2, payload=8
            log_id = 0
            if fields.get(2):
                v = fields[2][0]
                log_id = v if isinstance(v, int) else 0
            payload = fields.get(8, [b""])[0]

            # 获取Response：payload为gzip压缩；若解不开则尝试整帧直接作为Response
            if payload:
                try:
                    resp_data = gzip.decompress(payload)
                except Exception:
                    resp_data = payload
            else:
                try:
                    resp_data = gzip.decompress(data)
                except Exception:
                    resp_data = data

            resp_fields = _pb_parse(resp_data)
            # Response: messagesList=1, internalExt=5, needAck=9
            internal_ext = resp_fields.get(5, [b""])[0]
            need_ack = False
            if resp_fields.get(9):
                v = resp_fields[9][0]
                need_ack = bool(v if isinstance(v, int) else 0)

            # 逐条解析弹幕消息
            for m in resp_fields.get(1, []):
                self._parse_response_message(m)

            # 服务端要求ack时回发，保持长连接不被断开
            if need_ack and internal_ext:
                try:
                    ack = (_pb_field(2, 0, log_id) +
                           _pb_field(7, 2, b"ack") +
                           _pb_field(8, 2, internal_ext))
                    await ws.send_bytes(ack)
                except Exception:
                    pass
        except Exception as e:
            app_logger.log_warn("弹幕消息解析异常: " + str(e)[:60])

    def _parse_response_message(self, msg_data: bytes):
        """解析单条Message：method=1, payload=2
        消息类型及字段号参照 DouyinLiveWebFetcher 的 douyin.proto 定义"""
        try:
            fields = _pb_parse(msg_data)
            method = fields.get(1, [b""])[0]
            payload = fields.get(2, [b""])[0]
            if isinstance(method, bytes):
                method = method.decode('utf-8', errors='ignore')
            if not method:
                return

            if "WebcastChatMessage" in method:
                self._emit_chat(payload)
            elif "WebcastGiftMessage" in method:
                self._emit_gift(payload)
            elif "WebcastLikeMessage" in method:
                self._emit_like(payload)
            elif "WebcastSocialMessage" in method:
                self._emit_social(payload)
            elif "WebcastMemberMessage" in method:
                self._emit_member(payload)
            elif "WebcastRoomUserSeqMessage" in method:
                self._emit_stats(payload)
            elif "WebcastControlMessage" in method:
                self._emit_control(payload)
            elif "WebcastFansclubMessage" in method:
                self._emit_fansclub(payload)
            elif "WebcastEmojiChatMessage" in method:
                self._emit_emoji_chat(payload)
            elif "WebcastRoomStatsMessage" in method:
                self._emit_room_stats(payload)
        except Exception:
            pass

    def _emit_chat(self, payload: bytes):
        """WebcastChatMessage: user=2(nickname=3), content=3"""
        try:
            fields = _pb_parse(payload)
            user = self._nickname_from_user_field(fields.get(2))
            content = ""
            if fields.get(3):
                c = fields[3][0]
                if isinstance(c, bytes):
                    content = c.decode('utf-8', errors='ignore')
            if content:
                self.danmaku_received.emit(user, content, "chat")
        except Exception:
            pass

    def _emit_gift(self, payload: bytes):
        """WebcastGiftMessage: user=7, gift=15(GiftStruct: name=16, diamondCount=12), comboCount=6, repeatCount=5"""
        try:
            fields = _pb_parse(payload)
            user = self._nickname_from_user_field(fields.get(7))
            gift_name = "礼物"
            diamond = 0
            if fields.get(15):
                gift_fields = _pb_parse(fields[15][0])
                if gift_fields.get(16):
                    n = gift_fields[16][0]
                    if isinstance(n, bytes):
                        gift_name = n.decode('utf-8', errors='ignore') or "礼物"
                if gift_fields.get(12):
                    v = gift_fields[12][0]
                    diamond = v if isinstance(v, int) else 0
            # 数量：优先comboCount=6，其次repeatCount=5
            count = 1
            for fnum in (6, 5):
                if fields.get(fnum):
                    v = fields[fnum][0]
                    if isinstance(v, int) and v > 0:
                        count = v
                        break
            # 连击去重：抹音连击礼物会在数秒内推送多条，同一用户同一礼物
            # 5秒内只播报一次，避免弹幕列表刷屏与AI重复感谢（参照开源项目按combo合并的思路）
            now = time.time()
            key = (user, gift_name)
            if now - self._gift_last.get(key, 0) < 5:
                self._gift_last[key] = now
                return
            self._gift_last[key] = now
            text = f"送出了 {gift_name}x{count}"
            if diamond > 0:
                text += f"（{diamond}抖币）"
            self.danmaku_received.emit(user, text, "gift")
        except Exception:
            pass

    def _emit_like(self, payload: bytes):
        """WebcastLikeMessage: user=5, count=2, total=3"""
        try:
            fields = _pb_parse(payload)
            user = self._nickname_from_user_field(fields.get(5))
            count = 0
            if fields.get(2):
                v = fields[2][0]
                count = v if isinstance(v, int) else 0
            text = f"点了{count}个赞" if count > 0 else "点赞了"
            self.danmaku_received.emit(user, text, "like")
        except Exception:
            pass

    def _emit_social(self, payload: bytes):
        """WebcastSocialMessage: user=2 —— 关注事件"""
        try:
            fields = _pb_parse(payload)
            user = self._nickname_from_user_field(fields.get(2))
            self.danmaku_received.emit(user, "关注了主播", "follow")
        except Exception:
            pass

    def _emit_member(self, payload: bytes):
        """WebcastMemberMessage: user=2, memberCount=3 —— 进入直播间"""
        try:
            fields = _pb_parse(payload)
            user = self._nickname_from_user_field(fields.get(2))
            self.danmaku_received.emit(user, "进入直播间", "enter")
        except Exception:
            pass

    def _emit_stats(self, payload: bytes):
        """WebcastRoomUserSeqMessage: total=3, totalUser=7, totalStr=9, totalPvForAnchor=11"""
        try:
            fields = _pb_parse(payload)
            # 优先用字符串字段（已格式化，如"43.6万"）
            total_str = ""
            if fields.get(9):
                v = fields[9][0]
                if isinstance(v, bytes):
                    total_str = v.decode('utf-8', errors='ignore')
            pv_str = ""
            if fields.get(11):
                v = fields[11][0]
                if isinstance(v, bytes):
                    pv_str = v.decode('utf-8', errors='ignore')
            if not total_str and fields.get(3):
                v = fields[3][0]
                total_str = str(v) if isinstance(v, int) else ""
            if total_str or pv_str:
                stats = f"当前观看: {total_str}"
                if pv_str:
                    stats += f" | 累计观看: {pv_str}"
                self.stats_updated.emit(stats)
        except Exception:
            pass

    def _emit_control(self, payload: bytes):
        """WebcastControlMessage: status=2，status==3表示下播"""
        try:
            fields = _pb_parse(payload)
            if fields.get(2):
                v = fields[2][0]
                status = v if isinstance(v, int) else 0
                if status == 3:
                    app_logger.log_info("直播间已结束（主播下播）")
                    self.live_ended.emit()
                    self._running = False
        except Exception:
            pass

    def _emit_fansclub(self, payload: bytes):
        """WebcastFansclubMessage: content=3, user=4 —— 粉丝团消息"""
        try:
            fields = _pb_parse(payload)
            content = ""
            if fields.get(3):
                v = fields[3][0]
                if isinstance(v, bytes):
                    content = v.decode('utf-8', errors='ignore')
            if content:
                user = self._nickname_from_user_field(fields.get(4))
                self.danmaku_received.emit(user, content, "fansclub")
        except Exception:
            pass

    def _emit_emoji_chat(self, payload: bytes):
        """WebcastEmojiChatMessage: 表情弹幕（user=2, defaultContent=文本描述）
        开源项目会单独解析表情弹幕，这里归入普通聊天显示，避免互动消息遗漏"""
        try:
            fields = _pb_parse(payload)
            user = self._nickname_from_user_field(fields.get(2))
            # 尝试提取可读的默认文本（如“[微笑]”），无则回退到通用标记
            content = "[表情]"
            for vals in fields.values():
                for v in vals:
                    if isinstance(v, bytes) and 0 < len(v) <= 24:
                        try:
                            s = v.decode('utf-8')
                        except Exception:
                            continue
                        if s.startswith("[") and s.endswith("]"):
                            content = s
                            break
            self.danmaku_received.emit(user, content, "chat")
        except Exception:
            pass

    def _emit_room_stats(self, payload: bytes):
        """WebcastRoomStatsMessage: 直播间实时统计文本（如“1234人正在看”）
        字段号因版本而异，直接扫描所有字符串字段取含关键词的一条，鲁棒且不会误解析"""
        try:
            fields = _pb_parse(payload)
            for vals in fields.values():
                for v in vals:
                    if isinstance(v, bytes):
                        try:
                            s = v.decode('utf-8')
                        except Exception:
                            continue
                        if s and any(k in s for k in ("看", "在线", "人气", "观众")):
                            self.stats_updated.emit(s)
                            return
        except Exception:
            pass

    @staticmethod
    def _nickname_from_user_field(user_field_list) -> str:
        """从User字段提取昵称（User.nickname=3）"""
        try:
            if user_field_list:
                user_fields = _pb_parse(user_field_list[0])
                if user_fields.get(3):
                    nick = user_fields[3][0]
                    if isinstance(nick, bytes):
                        return nick.decode('utf-8', errors='ignore') or "观众"
        except Exception:
            pass
        return "观众"
