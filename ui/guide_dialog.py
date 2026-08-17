"""快速入门引导对话框 - 帮助新用户按步骤完成直播准备"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QCheckBox, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


# 导航索引（与 main_window 的 stack 顺序一致）
TAB_BROADCAST = 0
TAB_PRODUCT = 1
TAB_SCRIPT = 2
TAB_MODEL = 7
TAB_VOICE = 8


class GuideDialog(QDialog):
    """快速入门引导：商品 → 话术 → 语音 → 开始"""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("快速入门")
        self.setMinimumWidth(520)
        self.setModal(True)
        self._build_ui()
        self.refresh_status()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("🚀 快速开始直播")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        subtitle = QLabel("按以下 4 步准备，即可开始自动直播带货：")
        subtitle.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(subtitle)

        # 步骤列表
        self.step_rows = []
        steps = [
            ("1", "配置 AI 模型", "用于生成话术，推荐使用本地 Ollama 或 DeepSeek", TAB_MODEL, "去配置"),
            ("2", "添加商品", "添加要带货的商品信息（名称、价格、卖点）", TAB_PRODUCT, "去添加"),
            ("3", "生成话术", "用 AI 为商品生成讲解话术", TAB_SCRIPT, "去生成"),
            ("4", "语音设置", "选择喜欢的播报音色（可选，有默认音色）", TAB_VOICE, "去设置"),
        ]
        for num, name, desc, tab_idx, btn_text in steps:
            row = self._make_step_row(num, name, desc, tab_idx, btn_text)
            self.step_rows.append(row)
            layout.addWidget(row["frame"])

        # 开始直播按钮
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #e8eaed;")
        layout.addWidget(sep)

        self.btn_start = QPushButton("✅ 开始直播播报")
        self.btn_start.setFixedHeight(46)
        self.btn_start.setProperty("class", "success")
        self.btn_start.clicked.connect(self._on_start)
        layout.addWidget(self.btn_start)

        self.lbl_hint = QLabel("")
        self.lbl_hint.setStyleSheet("color: #f59e0b; font-size: 12px;")
        self.lbl_hint.setWordWrap(True)
        layout.addWidget(self.lbl_hint)

        # 不再显示
        bottom = QHBoxLayout()
        self.chk_no_more = QCheckBox("下次启动不再显示此引导")
        self.chk_no_more.setStyleSheet("font-size: 12px; color: #6b7280;")
        bottom.addWidget(self.chk_no_more)
        bottom.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.setFixedHeight(34)
        btn_close.clicked.connect(self._on_close)
        bottom.addWidget(btn_close)
        layout.addLayout(bottom)

    def _make_step_row(self, num, name, desc, tab_idx, btn_text):
        """构建一个步骤行"""
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background-color: #f9fafb; border: 1px solid #e8eaed; "
            "border-radius: 10px; padding: 10px; }"
        )
        h = QHBoxLayout(frame)
        h.setContentsMargins(12, 10, 12, 10)

        status_lbl = QLabel("○")
        status_lbl.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        status_lbl.setStyleSheet("color: #d1d5db; background: transparent; border: none;")
        status_lbl.setFixedWidth(28)
        h.addWidget(status_lbl)

        text_box = QVBoxLayout()
        name_lbl = QLabel(f"第{num}步：{name}")
        name_lbl.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        name_lbl.setStyleSheet("background: transparent; border: none;")
        text_box.addWidget(name_lbl)
        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet("color: #6b7280; font-size: 11px; background: transparent; border: none;")
        desc_lbl.setWordWrap(True)
        text_box.addWidget(desc_lbl)
        h.addLayout(text_box, 1)

        btn = QPushButton(btn_text)
        btn.setFixedHeight(32)
        btn.setFixedWidth(76)
        btn.clicked.connect(lambda checked, idx=tab_idx: self._goto(idx))
        h.addWidget(btn)

        return {"frame": frame, "status": status_lbl, "tab": tab_idx}

    def refresh_status(self):
        """刷新各步骤完成状态"""
        mw = self.main_window
        # 步骤1：AI模型
        model_ok = mw.ai_engine.is_configured
        # 步骤2：商品
        products = mw.db.get_enabled_products()
        product_ok = len(products) > 0
        # 步骤3：话术
        scripts = mw.db.get_all_scripts()
        script_ok = len(scripts) > 0
        # 步骤4：语音（默认即可用）
        voice_ok = True

        flags = [model_ok, product_ok, script_ok, voice_ok]
        for i, row in enumerate(self.step_rows):
            if flags[i]:
                row["status"].setText("✓")
                row["status"].setStyleSheet("color: #10b981; background: transparent; border: none;")
            else:
                row["status"].setText("○")
                row["status"].setStyleSheet("color: #d1d5db; background: transparent; border: none;")

        # 开始按钮：商品+话术都就绪才可开始
        can_start = product_ok and script_ok
        self.btn_start.setEnabled(can_start)
        if not can_start:
            hints = []
            if not product_ok:
                hints.append("先添加商品")
            if not script_ok:
                hints.append("再生成话术")
            self.lbl_hint.setText("还需：" + "、".join(hints) + "，完成后即可开始直播")
        else:
            self.lbl_hint.setText("准备就绪！点击“开始直播播报”即可自动循环讲解商品")

    def _goto(self, tab_idx):
        """跳转到对应标签页并关闭引导"""
        self._save_no_more()
        self.main_window.nav_list.setCurrentRow(tab_idx)
        self.accept()

    def _on_start(self):
        """跳转到播报主控页"""
        self._save_no_more()
        self.main_window.nav_list.setCurrentRow(TAB_BROADCAST)
        self.accept()

    def _on_close(self):
        self._save_no_more()
        self.accept()

    def _save_no_more(self):
        """保存'不再显示'选项"""
        if self.chk_no_more.isChecked():
            self.main_window.config.show_guide = False
            self.main_window.save_config()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_status()
