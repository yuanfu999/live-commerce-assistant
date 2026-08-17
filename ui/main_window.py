"""主窗口 - 左侧导航 + 右侧内容区"""
import os
import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QStackedWidget,
    QLabel, QStatusBar, QApplication
)
from PyQt6.QtCore import Qt, QSize, QThread, QTimer
from PyQt6.QtGui import QFont, QIcon

from models.config import AppConfig
from core.ai_engine import AIEngine
from core.tts_engine import TTSEngine
from core.script_generator import ScriptGenerator
from core.broadcast_engine import BroadcastEngine
from core.timer_service import TimerService
from core.douyin_connector import DouyinConnector
from core.voice_clone_engine import VoiceCloneEngine
from core.digital_human_engine import DigitalHumanEngine
from database.db_manager import DBManager

from ui.broadcast_panel import BroadcastPanel
from ui.product_panel import ProductPanel
from ui.script_panel import ScriptPanel
from ui.model_config_panel import ModelConfigPanel
from ui.voice_config_panel import VoiceConfigPanel
from ui.timer_panel import TimerPanel
from ui.danmaku_panel import DanmakuPanel
from ui.history_panel import HistoryPanel
from ui.member_panel import MemberPanel
from ui.digital_human_panel import DigitalHumanPanel
from ui.log_panel import LogPanel
from ui.guide_dialog import GuideDialog
from core import app_logger


APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(APP_DIR, "config", "settings.json")
DB_PATH = os.path.join(APP_DIR, "config", "data.db")


class TimerPlayThread(QThread):
    """定时播报独立播放线程：主播报未运行时，直接合成并播放一条文本"""

    def __init__(self, tts_engine, text: str, parent=None):
        super().__init__(parent)
        self.tts_engine = tts_engine
        self.text = text

    def run(self):
        try:
            audio_path = self.tts_engine.synthesize(self.text)
            duration = self.tts_engine.play(audio_path)
            # 等待播放完成
            import time
            time.sleep(max(duration, 0.5))
        except Exception:
            pass


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI直播带货口播助手")
        self.setMinimumSize(1100, 700)

        # 加载配置
        self.config = AppConfig.load(CONFIG_PATH)

        # 初始化核心引擎
        self.db = DBManager(DB_PATH)
        self.ai_engine = AIEngine()
        self.tts_engine = TTSEngine(self.config.voice)
        self.script_generator = ScriptGenerator(self.ai_engine)
        self.broadcast_engine = BroadcastEngine(self.tts_engine, self.db)
        self.timer_service = TimerService()
        self.timer_service.ai_engine = self.ai_engine
        self.douyin_connector = DouyinConnector()
        self.voice_clone_engine = VoiceCloneEngine()
        self.digital_human_engine = DigitalHumanEngine()

        # 将克隆/数字人引擎连接到播报引擎
        self.broadcast_engine.voice_clone_engine = self.voice_clone_engine
        self.broadcast_engine.digital_human_engine = self.digital_human_engine

        # 设置当前活跃模型
        active_model = self.config.get_active_model()
        if active_model:
            self.ai_engine.set_model(active_model)

        # 播报引擎配置
        self.broadcast_engine.pause_seconds = self.config.broadcast.pause_between_scripts
        self.broadcast_engine.auto_loop = self.config.broadcast.auto_loop

        # 构建UI
        self._build_ui()
        self._connect_signals()
        self._setup_hotkeys()

        # 状态栏
        self.statusBar().showMessage("就绪 | 热键: Ctrl+Shift+P=暂停/继续  Ctrl+Shift+S=跳过  Ctrl+Shift+X=停止")
        app_logger.log_info("软件启动")
        # 首次启动显示快速入门引导（延迟到窗口显示后）
        QTimer.singleShot(600, self._show_guide_if_needed)

    def _show_guide_if_needed(self):
        """首次使用时显示快速入门引导"""
        if self.config.show_guide:
            dlg = GuideDialog(self)
            dlg.exec()

    def show_guide(self):
        """手动打开快速入门引导"""
        dlg = GuideDialog(self)
        dlg.exec()

    def _build_ui(self):
        """构建界面布局"""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 左侧导航容器（深梅炭渐变背景）
        sidebar = QWidget()
        sidebar.setFixedWidth(196)
        sidebar.setStyleSheet(
            "background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 #262340, stop:1 #1A1828);"
        )
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # 品牌区 + 直播指示灯（签名元素：On-Air）
        brand = QWidget()
        brand.setStyleSheet("background: transparent;")
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(20, 22, 16, 14)
        brand_layout.setSpacing(8)

        brand_name = QLabel("AI直播助手")
        brand_name.setStyleSheet(
            "color: #FFFFFF; font-size: 17px; font-weight: 700; letter-spacing: 2px;"
        )
        brand_layout.addWidget(brand_name)

        live_row = QHBoxLayout()
        live_row.setSpacing(7)
        self.live_dot = QLabel()
        self.live_dot.setFixedSize(9, 9)
        self.live_row_label = QLabel("未开播")
        self.live_row_label.setStyleSheet(
            "color: #7E7A99; font-size: 11px; letter-spacing: 1px;"
        )
        live_row.addWidget(self.live_dot)
        live_row.addWidget(self.live_row_label)
        live_row.addStretch()
        brand_layout.addLayout(live_row)

        sidebar_layout.addWidget(brand)
        # 直播指示灯脉冲动画定时器（需在_set_live_indicator前初始化）
        self._pulse_phase = 0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_tick)
        self._set_live_indicator(False)

        # 导航列表
        self.nav_list = QListWidget()
        self.nav_list.setIconSize(QSize(20, 20))
        self.nav_list.setFont(QFont("Microsoft YaHei", 10))
        self.nav_list.setStyleSheet("""
            QListWidget {
                background: transparent;
                color: #A8A4C0;
                border: none;
                padding: 6px 0;
                outline: none;
            }
            QListWidget::item {
                padding: 13px 18px;
                margin: 2px 10px;
                border-radius: 9px;
                border-left: 3px solid transparent;
                color: #A8A4C0;
                font-size: 13px;
            }
            QListWidget::item:selected {
                background-color: #3B3757;
                color: #FFFFFF;
                border-left: 3px solid #FF4D5E;
                font-weight: 600;
            }
            QListWidget::item:hover:!selected {
                background-color: #322F4A;
                color: #DDD9EC;
            }
        """)

        nav_items = ["  播报主控", "  商品管理", "  话术库", "  弹幕互动", "  定时任务", "  播报历史", "  数字人", "  模型配置", "  语音配置", "  会员中心", "  运行日志"]
        for item_text in nav_items:
            item = QListWidgetItem(item_text)
            item.setSizeHint(QSize(176, 46))
            self.nav_list.addItem(item)

        self.nav_list.setCurrentRow(0)
        sidebar_layout.addWidget(self.nav_list)
        layout.addWidget(sidebar)

        # 右侧内容区（StackedWidget）
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # 创建各面板
        self.broadcast_panel = BroadcastPanel(self)
        self.product_panel = ProductPanel(self)
        self.script_panel = ScriptPanel(self)
        self.danmaku_panel = DanmakuPanel(self)
        self.timer_panel = TimerPanel(self)
        self.history_panel = HistoryPanel(self)
        self.digital_human_panel = DigitalHumanPanel(self)
        self.model_config_panel = ModelConfigPanel(self)
        self.voice_config_panel = VoiceConfigPanel(self)
        self.member_panel = MemberPanel(self)
        self.log_panel = LogPanel(self)

        self.stack.addWidget(self.broadcast_panel)
        self.stack.addWidget(self.product_panel)
        self.stack.addWidget(self.script_panel)
        self.stack.addWidget(self.danmaku_panel)
        self.stack.addWidget(self.timer_panel)
        self.stack.addWidget(self.history_panel)
        self.stack.addWidget(self.digital_human_panel)
        self.stack.addWidget(self.model_config_panel)
        self.stack.addWidget(self.voice_config_panel)
        self.stack.addWidget(self.member_panel)
        self.stack.addWidget(self.log_panel)

    def _connect_signals(self):
        """连接信号"""
        self.nav_list.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav_list.currentRowChanged.connect(self._on_tab_changed)
        self.broadcast_engine.status_changed.connect(self._update_status)
        self.broadcast_engine.broadcast_stopped.connect(lambda: self._set_live_indicator(False))
        # 定时播报触发：主播报运行中则插入队列，否则独立播放
        self.timer_service.trigger_text.connect(self._on_timer_trigger)
        self.timer_service.status_changed.connect(self._update_status)

    def _set_live_indicator(self, live: bool):
        """切换侧边栏直播指示灯状态（On-Air 签名元素）"""
        self._is_live = live
        self._pulse_phase = 0
        if live:
            self.live_row_label.setText("直播中")
            self.live_row_label.setStyleSheet(
                "color: #FF8A94; font-size: 11px; font-weight: 600; letter-spacing: 1px;"
            )
            self._apply_dot_style(1.0)
            if not self._pulse_timer.isActive():
                self._pulse_timer.start(700)
        else:
            self.live_row_label.setText("未开播")
            self.live_row_label.setStyleSheet(
                "color: #7E7A99; font-size: 11px; letter-spacing: 1px;"
            )
            self.live_dot.setStyleSheet(
                "background-color: #55516E; border-radius: 4px;"
            )
            self._pulse_timer.stop()

    def _apply_dot_style(self, intensity: float):
        """根据强度设置指示灯样式（模拟呼吸发光）"""
        glow = int(60 * intensity)
        self.live_dot.setStyleSheet(
            f"background-color: #FF4D5E; border-radius: 4px; "
            f"border: {glow}px solid rgba(255, 77, 94, 25);"
        )

    def _pulse_tick(self):
        """指示灯脉冲：亮→暗交替呼吸"""
        self._pulse_phase = 1 - self._pulse_phase
        self._apply_dot_style(1.0 if self._pulse_phase == 0 else 0.35)

    def _on_timer_trigger(self, text: str):
        """定时播报触发处理"""
        if self.broadcast_engine.isRunning():
            # 主播报循环在跑，插入优先队列由其播放
            self.broadcast_engine.insert_text(text)
        else:
            # 主播报未运行，用独立线程直接合成播放（上一条未播完则跳过，避免重叠）
            prev = getattr(self, "_timer_play_thread", None)
            if prev is not None and prev.isRunning():
                return
            self._timer_play_thread = TimerPlayThread(self.tts_engine, text, parent=self)
            self._timer_play_thread.start()

    def _on_tab_changed(self, index: int):
        """切换标签页时刷新对应面板数据"""
        # 话术库（index=2）：刷新商品下拉框
        if index == 2:
            self.script_panel.refresh_products()
        # 播报主控（index=0）：刷新播报队列
        elif index == 0:
            self.broadcast_panel.refresh_queue()
        # 商品管理（index=1）：刷新商品列表
        elif index == 1:
            self.product_panel.refresh_list()

    def _update_status(self, text: str):
        """更新状态栏"""
        self.statusBar().showMessage(text)

    def save_config(self):
        """保存配置"""
        self.config.save(CONFIG_PATH)

    def _setup_hotkeys(self):
        """设置全局热键"""
        try:
            from pynput import keyboard
            self._hotkey_listener = keyboard.GlobalHotKeys({
                '<ctrl>+<shift>+p': self._hotkey_pause,
                '<ctrl>+<shift>+s': self._hotkey_skip,
                '<ctrl>+<shift>+x': self._hotkey_stop,
            })
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()
        except Exception:
            pass  # 热键注册失败不影响主功能

    def _hotkey_pause(self):
        """热键：暂停/继续"""
        engine = self.broadcast_engine
        if engine._running:
            if engine._paused:
                engine.resume_broadcast()
            else:
                engine.pause_broadcast()

    def _hotkey_skip(self):
        """热键：跳过当前"""
        self.broadcast_engine.skip_current()

    def _hotkey_stop(self):
        """热键：停止播报"""
        self.broadcast_engine.stop_broadcast()

    def closeEvent(self, event):
        """关闭窗口时保存配置、停止所有服务"""
        app_logger.log_info("软件退出，正在清理资源...")
        # 先停止播报，并等待播报线程真正退出（避免pygame跨线程崩溃）
        self.broadcast_engine.stop_broadcast()
        # 等待最多8秒；超时仍未退出说明线程卡在网络IO，交给daemon线程随进程退出
        broadcast_exited = self.broadcast_engine.wait(8000)
        self.timer_service.stop_service()
        self.timer_service.wait(2000)
        self.douyin_connector.stop_connect()
        self.voice_clone_engine.cleanup()
        self.digital_human_engine.cleanup()
        self.save_config()
        # 仅当播报线程真正退出后才清理pygame mixer，否则线程后续play()会崩溃
        if broadcast_exited:
            self.tts_engine.cleanup()
        self.db.close()
        event.accept()
