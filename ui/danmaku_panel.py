"""弹幕互动面板"""
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QGroupBox, QFormLayout, QCheckBox,
    QListWidget, QListWidgetItem, QSpinBox, QTextEdit, QSplitter
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor


class DanmakuPanel(QWidget):
    """弹幕互动页面"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._last_reply_time = 0
        self._build_ui()
        self._connect_signals()
        self._load_config()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        # 连接控制
        conn_group = QGroupBox("直播间连接")
        conn_layout = QHBoxLayout(conn_group)

        self.edit_room_url = QLineEdit()
        self.edit_room_url.setPlaceholderText("输入直播间URL，如：https://live.douyin.com/123456 或直接输入房间号")
        conn_layout.addWidget(self.edit_room_url, 3)

        self.btn_connect = QPushButton("连接")
        self.btn_connect.setFixedHeight(38)
        self.btn_connect.setProperty("class", "primary")
        self.btn_connect.clicked.connect(self._on_connect)
        conn_layout.addWidget(self.btn_connect)

        self.btn_disconnect = QPushButton("断开")
        self.btn_disconnect.setFixedHeight(38)
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.clicked.connect(self._on_disconnect)
        conn_layout.addWidget(self.btn_disconnect)

        layout.addWidget(conn_group)

        # 中间区域：弹幕列表 + 回复记录
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 弹幕实时列表
        danmaku_group = QGroupBox("实时弹幕")
        danmaku_layout = QVBoxLayout(danmaku_group)
        self.list_danmaku = QListWidget()
        self.list_danmaku.setFont(QFont("Microsoft YaHei", 10))
        danmaku_layout.addWidget(self.list_danmaku)
        splitter.addWidget(danmaku_group)

        # AI回复记录
        reply_group = QGroupBox("AI回复记录")
        reply_layout = QVBoxLayout(reply_group)
        self.list_replies = QListWidget()
        self.list_replies.setFont(QFont("Microsoft YaHei", 10))
        reply_layout.addWidget(self.list_replies)
        splitter.addWidget(reply_group)

        layout.addWidget(splitter, 1)

        # 互动设置
        settings_group = QGroupBox("互动设置")
        settings_form = QFormLayout(settings_group)

        self.chk_auto_reply = QCheckBox("启用AI自动回复弹幕")
        self.chk_auto_reply.setChecked(True)
        settings_form.addRow(self.chk_auto_reply)

        self.chk_welcome = QCheckBox("新用户进入自动欢迎")
        self.chk_welcome.setChecked(True)
        settings_form.addRow(self.chk_welcome)

        self.chk_thanks = QCheckBox("送礼/下单自动感谢")
        self.chk_thanks.setChecked(True)
        settings_form.addRow(self.chk_thanks)

        self.spin_reply_interval = QSpinBox()
        self.spin_reply_interval.setRange(5, 120)
        self.spin_reply_interval.setValue(30)
        self.spin_reply_interval.setSuffix(" 秒")
        settings_form.addRow("回复最小间隔：", self.spin_reply_interval)

        self.edit_keywords = QLineEdit()
        self.edit_keywords.setPlaceholderText("触发关键词，逗号分隔：多少钱,怎么买,有优惠")
        settings_form.addRow("触发关键词：", self.edit_keywords)

        layout.addWidget(settings_group)

        # 状态
        self.lbl_status = QLabel("状态：未连接")
        self.lbl_status.setStyleSheet("color: #9ca3af; font-size: 12px; padding: 4px 0;")
        layout.addWidget(self.lbl_status)

    def _connect_signals(self):
        connector = self.main_window.douyin_connector
        connector.danmaku_received.connect(self._on_danmaku)
        connector.connected.connect(self._on_connected)
        connector.disconnected.connect(self._on_disconnected)
        connector.error_occurred.connect(self._on_error)
        connector.reconnecting.connect(self._on_reconnecting)
        connector.stats_updated.connect(self._on_stats)
        connector.live_ended.connect(self._on_live_ended)

    def _load_config(self):
        dc = self.main_window.config.danmaku
        self.edit_room_url.setText(dc.room_url)
        self.chk_welcome.setChecked(dc.welcome_enabled)
        self.chk_thanks.setChecked(dc.thanks_enabled)
        self.spin_reply_interval.setValue(dc.reply_interval)
        self.edit_keywords.setText(",".join(dc.keywords))

    def _on_connect(self):
        url = self.edit_room_url.text().strip()
        if not url:
            self.lbl_status.setText("状态：请输入直播间URL")
            return

        self.main_window.config.danmaku.room_url = url
        self.main_window.douyin_connector.set_room(url)
        self.main_window.douyin_connector.start_connect()
        self.lbl_status.setText("状态：正在连接...")

    def _on_disconnect(self):
        self.main_window.douyin_connector.stop_connect()

    def _on_connected(self):
        self.btn_connect.setEnabled(False)
        self.btn_disconnect.setEnabled(True)
        self.lbl_status.setText("状态：已连接 ✓")
        self.lbl_status.setStyleSheet("color: green;")

    def _on_disconnected(self):
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        self.lbl_status.setText("状态：已断开")
        self.lbl_status.setStyleSheet("color: #888;")

    def _on_reconnecting(self, count: int):
        """断线自动重连中"""
        self.btn_connect.setEnabled(False)
        self.btn_disconnect.setEnabled(True)
        self.lbl_status.setText(f"状态：连接断开，正在自动重连（第{count}次）...")
        self.lbl_status.setStyleSheet("color: #f59e0b;")

    def _on_error(self, msg):
        # 只更新状态文本；按钮状态由connected/disconnected/reconnecting统一管理
        self.lbl_status.setText(f"状态：{msg}")
        self.lbl_status.setStyleSheet("color: red;")

    def _on_danmaku(self, username: str, content: str, msg_type: str):
        """收到弹幕（分类型着色显示）"""
        type_prefix = {
            "chat": "💬", "enter": "👋", "gift": "🎁",
            "like": "❤️", "follow": "⭐", "fansclub": "🏅",
        }.get(msg_type, "")
        item = QListWidgetItem(f"{type_prefix} {username}: {content}")
        # 不同消息类型用不同颜色，提升可读性
        color_map = {
            "enter": "#00C07F",    # 进场-翡翠绿
            "gift": "#FFAA2B",     # 礼物-琥珀橙
            "like": "#ec4899",     # 点赞-粉
            "follow": "#FF4D5E",   # 关注-珊瑚红
            "fansclub": "#8b5cf6", # 粉丝团-紫
        }
        if msg_type in color_map:
            item.setForeground(QColor(color_map[msg_type]))
        self.list_danmaku.insertItem(0, item)

        # 限制列表长度
        if self.list_danmaku.count() > 200:
            self.list_danmaku.takeItem(self.list_danmaku.count() - 1)

        # 自动回复逻辑
        if not self.chk_auto_reply.isChecked():
            return

        now = time.time()
        interval = self.spin_reply_interval.value()
        if now - self._last_reply_time < interval:
            return

        reply_text = None

        if msg_type == "enter" and self.chk_welcome.isChecked():
            reply_text = f"欢迎{username}来到直播间！点点关注不迷路哦！"
        elif msg_type == "gift" and self.chk_thanks.isChecked():
            reply_text = f"感谢{username}的礼物！太感谢了！"
        elif msg_type == "follow" and self.chk_thanks.isChecked():
            reply_text = f"感谢{username}的关注！欢迎加入我们的大家庭！"
        elif msg_type == "chat":
            # 检查关键词
            keywords = [k.strip() for k in self.edit_keywords.text().split(",") if k.strip()]
            if any(kw in content for kw in keywords):
                # 用AI生成回复
                try:
                    products = self.main_window.db.get_enabled_products()
                    current_product = products[0] if products else None
                    reply_text = self.main_window.script_generator.generate_danmaku_reply(
                        content, username, current_product
                    )
                except Exception:
                    reply_text = f"{username}，这个问题问得好！小黄车里都有详细介绍，点进去看看哦！"

        if reply_text:
            self._last_reply_time = now
            # 显示回复记录
            reply_item = QListWidgetItem(f"→ 回复{username}: {reply_text}")
            reply_item.setForeground(QColor("#4a9eff"))
            self.list_replies.insertItem(0, reply_item)

            # 插入播报引擎优先播放
            self.main_window.broadcast_engine.insert_text(reply_text)

    def _on_stats(self, stats_text: str):
        """直播间统计更新（在线人数/累计观看）"""
        self.lbl_status.setText(f"状态：已连接 ✓ | {stats_text}")

    def _on_live_ended(self):
        """主播下播"""
        self.lbl_status.setText("状态：直播已结束（主播下播）")
        self.lbl_status.setStyleSheet("color: #f59e0b;")
        item = QListWidgetItem("📢 直播已结束，主播下播了")
        item.setForeground(QColor("#ef4444"))
        self.list_danmaku.insertItem(0, item)
