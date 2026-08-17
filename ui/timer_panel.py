"""定时任务面板"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QGroupBox, QFormLayout, QCheckBox,
    QSpinBox, QTextEdit, QComboBox, QScrollArea, QFrame
)
from PyQt6.QtGui import QFont
from ui.msgbox import QMessageBox


class TimerPanel(QWidget):
    """定时播报配置页面"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._build_ui()
        self._load_config()

    def _build_ui(self):
        # 外层滚动区，避免内容超出窗口时无法查看
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("定时播报")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        layout.addWidget(title)

        # 开关和报时
        switch_group = QGroupBox("基本设置")
        switch_form = QFormLayout(switch_group)

        self.chk_enabled = QCheckBox("启用定时播报")
        switch_form.addRow(self.chk_enabled)

        self.chk_announce_time = QCheckBox("整点/半点自动报时")
        self.chk_announce_time.setChecked(True)
        switch_form.addRow(self.chk_announce_time)

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 60)
        self.spin_interval.setValue(10)
        self.spin_interval.setSuffix(" 分钟")
        switch_form.addRow("自定义提醒间隔：", self.spin_interval)

        layout.addWidget(switch_group)

        # 播报内容模式
        mode_group = QGroupBox("播报内容")
        mode_layout = QVBoxLayout(mode_group)

        mode_sel_layout = QHBoxLayout()
        mode_sel_layout.addWidget(QLabel("内容模式："))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("自定义文案（轮换播报）", "custom")
        self.combo_mode.addItem("AI生成文案（根据提示词）", "ai")
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        mode_sel_layout.addWidget(self.combo_mode, 1)
        mode_layout.addLayout(mode_sel_layout)

        # 自定义文案输入
        self.txt_messages = QTextEdit()
        self.txt_messages.setPlaceholderText(
            "每行一条提醒话术，如：\n"
            "家人们，点关注不迷路！\n"
            "刚进来的宝宝们点点关注，一会儿有福利！\n"
            "喜欢主播的给个小心心哦！"
        )
        self.txt_messages.setFixedHeight(120)
        mode_layout.addWidget(self.txt_messages)

        # AI提示词输入（AI模式时显示）
        self.txt_ai_prompt = QTextEdit()
        self.txt_ai_prompt.setPlaceholderText(
            "输入提示词，AI将根据此提示词自动生成播报文案，如：\n"
            "生成提醒观众点关注、加粉丝团的话术，语气活泼可爱，多用网络流行语\n"
            "生成感谢观众送礼物的话术，要真诚感恩"
        )
        self.txt_ai_prompt.setFixedHeight(120)
        self.txt_ai_prompt.setVisible(False)
        mode_layout.addWidget(self.txt_ai_prompt)

        self.lbl_mode_tip = QLabel("")
        self.lbl_mode_tip.setStyleSheet("color: #9ca3af; font-size: 11px;")
        self.lbl_mode_tip.setWordWrap(True)
        mode_layout.addWidget(self.lbl_mode_tip)

        layout.addWidget(mode_group)

        # 控制按钮
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("启动定时服务")
        self.btn_start.setFixedHeight(42)
        self.btn_start.setMinimumWidth(120)
        self.btn_start.setProperty("class", "success")
        self.btn_start.clicked.connect(self._on_start)
        btn_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("停止")
        self.btn_stop.setFixedHeight(42)
        self.btn_stop.setMinimumWidth(80)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setProperty("class", "danger")
        self.btn_stop.clicked.connect(self._on_stop)
        btn_layout.addWidget(self.btn_stop)

        self.btn_save = QPushButton("保存配置")
        self.btn_save.setFixedHeight(42)
        self.btn_save.setMinimumWidth(100)
        self.btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

        # 状态
        self.lbl_status = QLabel("状态：未启动")
        self.lbl_status.setStyleSheet("color: #9ca3af; font-size: 12px; padding: 4px 0;")
        layout.addWidget(self.lbl_status)

        layout.addStretch()

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

        self._on_mode_changed()

    def _on_mode_changed(self):
        """切换内容模式时更新界面"""
        mode = self.combo_mode.currentData()
        is_ai = (mode == "ai")
        self.txt_messages.setVisible(not is_ai)
        self.txt_ai_prompt.setVisible(is_ai)
        if is_ai:
            self.lbl_mode_tip.setText(
                "提示：每次触发时AI会根据提示词实时生成一条新文案进行播报，"
                "需确保AI模型已配置且可正常连接。生成失败时自动回退到自定义文案。"
            )
        else:
            self.lbl_mode_tip.setText("提示：播报时按顺序轮换使用上方填写的话术。")

    def _load_config(self):
        tc = self.main_window.config.timer
        self.chk_enabled.setChecked(tc.enabled)
        self.chk_announce_time.setChecked(tc.announce_time)
        self.spin_interval.setValue(tc.interval_minutes)
        self.txt_messages.setPlainText("\n".join(tc.messages))
        self.txt_ai_prompt.setPlainText(tc.ai_prompt)
        # 设置模式下拉框
        for i in range(self.combo_mode.count()):
            if self.combo_mode.itemData(i) == tc.mode:
                self.combo_mode.setCurrentIndex(i)
                break

    def _on_save(self):
        tc = self.main_window.config.timer
        tc.enabled = self.chk_enabled.isChecked()
        tc.announce_time = self.chk_announce_time.isChecked()
        tc.interval_minutes = self.spin_interval.value()
        tc.mode = self.combo_mode.currentData() or "custom"
        tc.ai_prompt = self.txt_ai_prompt.toPlainText().strip()
        tc.messages = [line.strip() for line in self.txt_messages.toPlainText().split("\n") if line.strip()]
        self.main_window.save_config()
        QMessageBox.information(self, "成功", "定时播报配置已保存")

    def _on_start(self):
        self._on_save()
        timer = self.main_window.timer_service
        tc = self.main_window.config.timer
        timer.enabled = tc.enabled
        timer.announce_time = tc.announce_time
        timer.interval_minutes = tc.interval_minutes
        timer.mode = tc.mode
        timer.ai_prompt = tc.ai_prompt
        timer.messages = tc.messages
        timer.start_service()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        mode_desc = "AI生成文案" if tc.mode == "ai" else "自定义文案"
        self.lbl_status.setText(f"状态：运行中（{mode_desc}模式）")

    def _on_stop(self):
        self.main_window.timer_service.stop_service()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.lbl_status.setText("状态：已停止")
