"""播报主控面板"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTextEdit, QListWidget, QListWidgetItem,
    QProgressBar, QGroupBox, QGridLayout, QSplitter
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class BroadcastPanel(QWidget):
    """播报主控页面"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # === 控制按钮区 ===
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ 开始播报")
        self.btn_start.setFixedHeight(46)
        self.btn_start.setProperty("class", "primary")

        self.btn_pause = QPushButton("暂停")
        self.btn_pause.setFixedHeight(46)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setProperty("class", "warning")

        self.btn_stop = QPushButton("停止")
        self.btn_stop.setFixedHeight(46)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setProperty("class", "danger")

        self.btn_skip = QPushButton("跳过")
        self.btn_skip.setFixedHeight(46)
        self.btn_skip.setEnabled(False)

        self.btn_guide = QPushButton("❔ 快速入门")
        self.btn_guide.setFixedHeight(46)
        self.btn_guide.clicked.connect(lambda: self.main_window.show_guide())

        btn_layout.addWidget(self.btn_start, 2)
        btn_layout.addWidget(self.btn_pause, 1)
        btn_layout.addWidget(self.btn_stop, 1)
        btn_layout.addWidget(self.btn_skip, 1)
        btn_layout.addWidget(self.btn_guide, 1)
        layout.addLayout(btn_layout)

        # === 当前播报信息 ===
        info_group = QGroupBox("当前播报")
        info_layout = QGridLayout(info_group)

        self.lbl_product = QLabel("商品：--")
        self.lbl_product.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        info_layout.addWidget(self.lbl_product, 0, 0)

        self.lbl_progress_info = QLabel("进度：--")
        info_layout.addWidget(self.lbl_progress_info, 0, 1)

        self.txt_subtitle = QTextEdit()
        self.txt_subtitle.setReadOnly(True)
        self.txt_subtitle.setFixedHeight(80)
        self.txt_subtitle.setFont(QFont("Microsoft YaHei", 13))
        self.txt_subtitle.setPlaceholderText("播报字幕将显示在这里...")
        info_layout.addWidget(self.txt_subtitle, 1, 0, 1, 2)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        info_layout.addWidget(self.progress_bar, 2, 0, 1, 2)

        layout.addWidget(info_group)

        # === 下方：播报队列 ===
        queue_group = QGroupBox("播报队列")
        queue_layout = QVBoxLayout(queue_group)

        self.list_queue = QListWidget()
        self.list_queue.setFont(QFont("Microsoft YaHei", 10))
        queue_layout.addWidget(self.list_queue)

        btn_refresh = QPushButton("刷新队列")
        btn_refresh.setFixedHeight(32)
        btn_refresh.clicked.connect(self.refresh_queue)
        queue_layout.addWidget(btn_refresh)

        layout.addWidget(queue_group, 1)

    def _connect_signals(self):
        """连接信号"""
        engine = self.main_window.broadcast_engine
        self.btn_start.clicked.connect(self._on_start)
        self.btn_pause.clicked.connect(self._on_pause)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_skip.clicked.connect(self._on_skip)

        engine.script_started.connect(self._on_script_started)
        engine.product_changed.connect(self._on_product_changed)
        engine.broadcast_stopped.connect(self._on_stopped)

    def _on_start(self):
        """开始播报"""
        engine = self.main_window.broadcast_engine
        products = self.main_window.db.get_enabled_products()

        if not products:
            self.txt_subtitle.setPlainText("没有可播报的商品，请先在商品管理中添加商品并生成话术。")
            return

        # 检查是否有话术
        has_scripts = False
        for p in products:
            if self.main_window.db.get_scripts_by_product(p.id, "main"):
                has_scripts = True
                break

        if not has_scripts:
            self.txt_subtitle.setPlainText("商品没有话术，请先在话术库中为商品生成话术。")
            return

        engine.load_products(products)
        engine.start_broadcast()
        self.main_window._set_live_indicator(True)

        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.btn_skip.setEnabled(True)
        self.refresh_queue()

    def _on_pause(self):
        engine = self.main_window.broadcast_engine
        if engine._paused:
            engine.resume_broadcast()
            self.btn_pause.setText("暂停")
        else:
            engine.pause_broadcast()
            self.btn_pause.setText("继续")

    def _on_stop(self):
        self.main_window.broadcast_engine.stop_broadcast()

    def _on_skip(self):
        self.main_window.broadcast_engine.skip_current()

    def _on_stopped(self):
        """播报停止后恢复按钮"""
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("暂停")
        self.btn_stop.setEnabled(False)
        self.btn_skip.setEnabled(False)
        self.lbl_product.setText("商品：--")
        self.lbl_progress_info.setText("进度：--")
        self.progress_bar.setValue(0)

    def _on_script_started(self, content: str, product_name: str, progress: str):
        """话术开始播报"""
        self.txt_subtitle.setPlainText(content)
        self.lbl_progress_info.setText(f"进度：{progress}")

    def _on_product_changed(self, product_name: str, info: str):
        """商品切换"""
        self.lbl_product.setText(f"商品：{product_name}  ({info})")

    def refresh_queue(self):
        """刷新播报队列显示"""
        self.list_queue.clear()
        products = self.main_window.db.get_enabled_products()
        for i, p in enumerate(products, 1):
            scripts = self.main_window.db.get_scripts_by_product(p.id, "main")
            status = f"{len(scripts)}条话术" if scripts else "无话术"
            item = QListWidgetItem(f"{i}. {p.name}  [{status}]")
            self.list_queue.addItem(item)
