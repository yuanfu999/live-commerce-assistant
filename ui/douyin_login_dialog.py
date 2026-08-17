"""抖音登录对话框 - 内嵌浏览器获取登录Cookie"""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSignal
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineCookieStore
from PyQt6.QtGui import QFont


class DouyinLoginDialog(QDialog):
    """
    抖音扫码/手机号登录窗口
    
    登录成功后自动获取Cookie，用于后续API调用。
    """
    login_success = pyqtSignal(str)  # cookie字符串

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("抖音登录")
        self.setMinimumSize(900, 650)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)

        self._cookie_str = ""
        self._logged_in = False

        self._build_ui()

        # 定时检查登录状态
        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self._check_login_status)
        self._check_timer.start(2000)  # 每2秒检查一次

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 提示栏
        tip_layout = QHBoxLayout()
        self.lbl_tip = QLabel("请在下方页面完成登录（扫码或手机号），登录成功后将自动获取凭证")
        self.lbl_tip.setFont(QFont("Microsoft YaHei", 10))
        self.lbl_tip.setStyleSheet("color: #6b7280; padding: 4px 0;")
        tip_layout.addWidget(self.lbl_tip, 1)

        self.btn_done = QPushButton("已完成登录")
        self.btn_done.setFixedHeight(32)
        self.btn_done.setStyleSheet("""
            QPushButton { background-color: #FF4D5E; color: white; border-radius: 6px;
                         padding: 0 16px; font-size: 13px; border: none; }
            QPushButton:hover { background-color: #E8434F; }
        """)
        self.btn_done.clicked.connect(self._on_manual_done)
        tip_layout.addWidget(self.btn_done)

        layout.addLayout(tip_layout)

        # 内嵌浏览器
        self.web_view = QWebEngineView()
        self.web_view.load(QUrl("https://live.douyin.com/"))
        layout.addWidget(self.web_view, 1)

        # 状态栏
        self.lbl_status = QLabel("等待登录...")
        self.lbl_status.setStyleSheet("color: #9ca3af; font-size: 11px;")
        layout.addWidget(self.lbl_status)

    def _check_login_status(self):
        """检查是否已登录（通过cookie判断）"""
        if self._logged_in:
            return

        # 获取所有cookie
        profile = self.web_view.page().profile()
        cookie_store = profile.cookieStore()

        # 通过JS获取document.cookie
        self.web_view.page().runJavaScript(
            "document.cookie",
            self._on_cookie_received
        )

    def _on_cookie_received(self, cookie_str):
        """JS回调：收到cookie"""
        if not cookie_str:
            return

        # 检查是否包含登录态标志
        # 抖音登录后通常会有 sessionid 或 passport_csrf_token 等cookie
        login_markers = ["sessionid", "sid_guard", "passport_auth_status"]
        has_login = any(marker in cookie_str for marker in login_markers)

        if has_login and not self._logged_in:
            self._logged_in = True
            self._cookie_str = cookie_str
            self._check_timer.stop()

            self.lbl_status.setText("✓ 登录成功！Cookie已获取")
            self.lbl_status.setStyleSheet("color: #10b981; font-size: 12px; font-weight: 500;")
            self.lbl_tip.setText("登录成功，窗口将在2秒后自动关闭...")

            # 延迟关闭
            QTimer.singleShot(2000, self._finish)

    def _on_manual_done(self):
        """用户手动点击'已完成登录'"""
        self.web_view.page().runJavaScript(
            "document.cookie",
            self._on_manual_cookie
        )

    def _on_manual_cookie(self, cookie_str):
        """手动获取cookie"""
        if cookie_str and len(cookie_str) > 20:
            self._cookie_str = cookie_str
            self._logged_in = True
            self._check_timer.stop()
            self._finish()
        else:
            self.lbl_status.setText("未检测到登录态，请先在页面中完成登录")
            self.lbl_status.setStyleSheet("color: #ef4444; font-size: 11px;")

    def _finish(self):
        """完成登录"""
        self.login_success.emit(self._cookie_str)
        self.accept()

    def get_cookie(self) -> str:
        """获取cookie（对话框关闭后调用）"""
        return self._cookie_str

    def closeEvent(self, event):
        """关闭时停止定时器"""
        self._check_timer.stop()
        event.accept()
