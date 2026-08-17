"""内嵌浏览器拉取直播间商品 - 页面JS上下文调用接口，自动携带登录态和反爬签名"""
import json
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel
from PyQt6.QtCore import QTimer, pyqtSignal, QUrl, Qt

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_AVAILABLE = True
except ImportError:
    WEBENGINE_AVAILABLE = False


# 在直播间页面上下文中执行的JS：
# 1. 从页面提取真实room_id和author_id（兼容新版 __pace_f 转义结构 / 旧版 RENDER_DATA）
# 2. fetch调用商品接口（webmssdk会自动追加a_bogus/msToken等签名）
# 3. 结果写入window.__productFetchResult供Python轮询
FETCH_JS = r"""
window.__productFetchResult = null;
(function() {
    try {
        var roomId = "";
        var authorId = "";

        // 方式1（旧版）：RENDER_DATA JSON
        var el = document.getElementById("RENDER_DATA");
        if (el) {
            try {
                var data = JSON.parse(decodeURIComponent(el.textContent));
                var findRoom = function(obj, depth) {
                    if (!obj || depth > 8 || typeof obj !== "object") return null;
                    if (obj.roomInfo && obj.roomInfo.room && obj.roomInfo.room.id_str) {
                        var room = obj.roomInfo.room;
                        var aid = "";
                        if (room.owner && room.owner.id_str) aid = String(room.owner.id_str);
                        else if (room.owner_user_id) aid = String(room.owner_user_id);
                        return {room_id: String(room.id_str), author_id: aid};
                    }
                    for (var k in obj) {
                        var r = findRoom(obj[k], depth + 1);
                        if (r) return r;
                    }
                    return null;
                };
                var found = findRoom(data, 0);
                if (found) { roomId = found.room_id; authorId = found.author_id; }
            } catch(e) {}
        }

        // 方式2（新版 __pace_f 流式数据）：全文正则提取转义字段
        if (!roomId || !authorId) {
            var htmlStr = document.documentElement.innerHTML;
            if (!roomId) {
                var mr = htmlStr.match(/\\"roomId\\":\\"(\d{15,})\\"/) ||
                         htmlStr.match(/"roomId"\s*:\s*"(\d{15,})"/);
                if (mr) roomId = mr[1];
            }
            if (!authorId) {
                var ma = htmlStr.match(/\\"anchor\\":\{\\"id_str\\":\\"(\d+)\\"/) ||
                         htmlStr.match(/"anchor"\s*:\s*\{\s*"id_str"\s*:\s*"(\d+)"/);
                if (ma) authorId = ma[1];
            }
        }

        // 备用：从URL路径提取web_rid（非真实room_id，仅最后兵造）
        if (!roomId) {
            var m = window.location.pathname.match(/^\/(\d+)/);
            if (m) roomId = m[1];
        }
        if (!roomId) {
            window.__productFetchResult = JSON.stringify({error: "未能从页面提取直播间ID"});
            return;
        }
        var url = "/live/promotions/page/?device_platform=webapp&aid=6383"
            + "&channel=channel_pc_web&room_id=" + roomId
            + "&author_id=" + authorId + "&offset=0&limit=50";
        fetch(url, {
            method: "POST",
            credentials: "include",
            headers: {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        }).then(function(r) {
            return r.json();
        }).then(function(d) {
            // 检测登录/错误码（新版接口结构 {code, msg, data}）
            var code = d && (d.code !== undefined ? d.code : d.status_code);
            var msg = d && (d.msg || d.status_message || d.prompts || "");
            var hasData = d && d.data && (d.data.promotions || d.data.products || d.data.product_list);
            if (!hasData && msg && (String(code) === "10001010A" || /未登录|登录后/.test(msg))) {
                window.__productFetchResult = JSON.stringify({error: "抖音未登录：请先在此浏览器窗口登录抖音账号（扫码/输入手机号），登录后重试"});
                return;
            }
            if (!hasData && msg) {
                window.__productFetchResult = JSON.stringify({error: "接口返回: " + msg + " (code=" + code + ")"});
                return;
            }
            window.__productFetchResult = JSON.stringify(d);
        }).catch(function(e) {
            window.__productFetchResult = JSON.stringify({error: "请求失败: " + e.toString()});
        });
    } catch(e) {
        window.__productFetchResult = JSON.stringify({error: "脚本执行失败: " + e.toString()});
    }
})();
"""


class ProductFetchDialog(QDialog):
    """
    内嵌浏览器加载直播间页面，在页面JS上下文中调用商品接口
    （自动携带登录cookie和反爬签名，成功率远高于纯HTTP请求）
    """
    products_fetched = pyqtSignal(list)
    fetch_failed = pyqtSignal(str)

    def __init__(self, room_url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("浏览器拉取商品 - 请勿关闭")
        self.resize(1000, 700)
        self.setModal(False)
        self._room_url = room_url
        self._done = False
        self._poll_count = 0

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(800)
        self._poll_timer.timeout.connect(self._check_result)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.status_label = QLabel("正在加载直播间页面...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        self.webview = QWebEngineView()
        layout.addWidget(self.webview)

    def start_fetch(self):
        """开始拉取：加载直播间页面"""
        self.webview.loadFinished.connect(self._on_page_loaded)
        self.webview.load(QUrl(self._room_url))

    def _on_page_loaded(self, ok: bool):
        if not ok:
            self._fail("直播间页面加载失败，请检查URL或网络")
            return
        self.status_label.setText("页面加载完成，正在调用商品接口...")
        # 等待页面JS SDK（webmssdk）初始化后再执行fetch
        QTimer.singleShot(2500, self._run_fetch_js)

    def _run_fetch_js(self):
        if self._done:
            return
        self.webview.page().runJavaScript(FETCH_JS)
        self._poll_count = 0
        self._poll_timer.start()

    def _check_result(self):
        self._poll_count += 1
        if self._poll_count > 30:  # 约24秒超时
            self._fail("拉取超时。请确认：1.已在浏览器中登录抖音 2.直播间已挂载小黄车商品")
            return
        self.webview.page().runJavaScript(
            "window.__productFetchResult",
            self._on_result
        )

    def _on_result(self, result):
        if self._done or result is None:
            return
        self._done = True
        self._poll_timer.stop()
        try:
            data = json.loads(result)
            if isinstance(data, dict) and "error" in data:
                self._fail(str(data["error"]))
                return
            from core.douyin_connector import DouyinConnector
            products = DouyinConnector._parse_promotions_response(data)
            if products:
                self.status_label.setText(f"成功拉取 {len(products)} 个商品！")
                self.products_fetched.emit(products)
            else:
                self._fail("接口返回为空。可能直播间未挂载小黄车，或登录态已过期（可在页面中手动刷新登录后重试）")
        except Exception as e:
            self._fail(f"结果解析失败: {e}")

    def _fail(self, message: str):
        if self._done:
            return
        self._done = True
        self._poll_timer.stop()
        self.status_label.setText("拉取失败")
        self.fetch_failed.emit(message)
