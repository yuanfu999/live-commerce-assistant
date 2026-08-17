"""数字人直播面板"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QGroupBox, QFormLayout, QFileDialog,
    QComboBox, QSpinBox, QCheckBox,
    QProgressBar, QTextEdit, QFrame, QScrollArea
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from ui.msgbox import QMessageBox


class GenerateWorker(QThread):
    """后台生成视频的工作线程"""
    finished = pyqtSignal(str)  # 输出路径
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, engine, audio_path, output_path=None):
        super().__init__()
        self.engine = engine
        self.audio_path = audio_path
        self.output_path = output_path

    def run(self):
        try:
            self.progress.emit("正在生成数字人视频...")
            result = self.engine.generate_video(self.audio_path, self.output_path)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class DigitalHumanPanel(QWidget):
    """数字人直播配置页面"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        # 外层布局：仅放一个滚动区，避免内容超出窗口时被遮盖
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        # 内容容器
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 标题
        title = QLabel("数字人直播")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        subtitle = QLabel("真人视频驱动 · 720p实时口型同步")
        subtitle.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(subtitle)

        # 源视频设置
        source_group = QGroupBox("源视频（真人出镜素材）")
        source_layout = QVBoxLayout(source_group)

        select_layout = QHBoxLayout()
        self.lbl_source = QLabel("未选择源视频")
        self.lbl_source.setStyleSheet("color: #6b7280;")
        select_layout.addWidget(self.lbl_source, 1)

        btn_select = QPushButton("选择视频")
        btn_select.setFixedHeight(36)
        btn_select.clicked.connect(self._on_select_video)
        select_layout.addWidget(btn_select)

        source_layout.addLayout(select_layout)

        tip = QLabel("提示：录制一段30秒-2分钟的正面出镜视频（720p，光线均匀，背景简洁，嘴巴闭合自然状态）")
        tip.setStyleSheet("color: #9ca3af; font-size: 11px;")
        tip.setWordWrap(True)
        source_layout.addWidget(tip)

        layout.addWidget(source_group)

        # 输出设置
        output_group = QGroupBox("输出设置")
        output_form = QFormLayout(output_group)
        output_form.setSpacing(10)

        self.combo_resolution = QComboBox()
        self.combo_resolution.addItems(["1280x720 (720p)", "960x540 (540p)", "640x360 (360p)"])
        output_form.addRow("分辨率：", self.combo_resolution)

        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(15, 30)
        self.spin_fps.setValue(25)
        self.spin_fps.setSuffix(" fps")
        output_form.addRow("帧率：", self.spin_fps)

        self.chk_virtual_cam = QCheckBox("启用虚拟摄像头输出（OBS）")
        self.chk_virtual_cam.setChecked(True)
        output_form.addRow(self.chk_virtual_cam)

        layout.addWidget(output_group)

        # 操作按钮
        btn_group = QGroupBox("操作")
        btn_layout = QHBoxLayout(btn_group)

        self.btn_generate = QPushButton("生成视频（离线模式）")
        self.btn_generate.setFixedHeight(42)
        self.btn_generate.setProperty("class", "primary")
        self.btn_generate.clicked.connect(self._on_generate)
        btn_layout.addWidget(self.btn_generate)

        self.btn_realtime = QPushButton("启动实时数字人")
        self.btn_realtime.setFixedHeight(42)
        self.btn_realtime.setProperty("class", "success")
        self.btn_realtime.clicked.connect(self._on_start_realtime)
        btn_layout.addWidget(self.btn_realtime)

        self.btn_stop = QPushButton("停止")
        self.btn_stop.setFixedHeight(42)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setProperty("class", "danger")
        self.btn_stop.clicked.connect(self._on_stop)
        btn_layout.addWidget(self.btn_stop)

        layout.addWidget(btn_group)

        # 状态/日志
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout(log_group)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMinimumHeight(160)
        self.txt_log.setStyleSheet("font-size: 12px; font-family: Consolas, monospace;")
        log_layout.addWidget(self.txt_log)

        layout.addWidget(log_group)

        # 环境状态
        self.lbl_env_status = QLabel("")
        self.lbl_env_status.setStyleSheet("color: #9ca3af; font-size: 11px;")
        layout.addWidget(self.lbl_env_status)

        layout.addStretch()

        # 将内容装入滚动区
        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

        # 检查环境
        self._check_env()

    def _check_env(self):
        """检查环境状态"""
        engine = self.main_window.digital_human_engine
        success, msg = engine.test_environment()
        if success:
            self.lbl_env_status.setText("环境状态：就绪")
            self.lbl_env_status.setStyleSheet("color: #10b981; font-size: 11px;")
        else:
            self.lbl_env_status.setText(f"环境状态：{msg.split(chr(10))[0]}")
            self.lbl_env_status.setStyleSheet("color: #f59e0b; font-size: 11px;")

    def _on_select_video(self):
        """选择源视频"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择真人出镜视频",
            "",
            "视频文件 (*.mp4 *.avi *.mov *.mkv *.webm)"
        )
        if file_path:
            try:
                self.main_window.digital_human_engine.set_source_video(file_path)
                self.lbl_source.setText(os.path.basename(file_path))
                self.lbl_source.setStyleSheet("color: #1a1a2e; font-weight: 500;")
                self._log(f"已设置源视频: {file_path}")
            except Exception as e:
                QMessageBox.warning(self, "错误", str(e))

    def _on_generate(self):
        """离线生成数字人视频"""
        engine = self.main_window.digital_human_engine

        if not engine._source_video:
            QMessageBox.warning(self, "提示", "请先选择源视频")
            return

        # 选择音频文件
        audio_path, _ = QFileDialog.getOpenFileName(
            self, "选择驱动音频",
            "",
            "音频文件 (*.wav *.mp3 *.flac)"
        )
        if not audio_path:
            return

        self.btn_generate.setEnabled(False)
        self._log("开始生成数字人视频...")

        self._worker = GenerateWorker(engine, audio_path)
        self._worker.finished.connect(self._on_generate_done)
        self._worker.error.connect(self._on_generate_error)
        self._worker.progress.connect(self._log)
        self._worker.start()

    def _on_generate_done(self, output_path: str):
        """生成完成"""
        self.btn_generate.setEnabled(True)
        self._log(f"生成完成: {output_path}")
        QMessageBox.information(self, "成功", f"数字人视频已生成:\n{output_path}")

    def _on_generate_error(self, error: str):
        """生成失败"""
        self.btn_generate.setEnabled(True)
        self._log(f"错误: {error}")
        QMessageBox.critical(self, "生成失败", error)

    def _on_start_realtime(self):
        """启动实时数字人"""
        engine = self.main_window.digital_human_engine

        if not engine._source_video:
            QMessageBox.warning(self, "提示", "请先选择源视频")
            return

        # 设置分辨率
        res_text = self.combo_resolution.currentText()
        if "720" in res_text:
            engine.resolution = (1280, 720)
        elif "540" in res_text:
            engine.resolution = (960, 540)
        else:
            engine.resolution = (640, 360)

        engine.fps = self.spin_fps.value()
        engine.use_virtual_camera = self.chk_virtual_cam.isChecked()

        try:
            engine.start_realtime()
            # 联动播报引擎：启用数字人模式
            self.main_window.broadcast_engine.use_digital_human = True
            self.btn_realtime.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self._log("实时数字人已启动")
            if engine.use_virtual_camera:
                self._log("虚拟摄像头已开启，请在OBS/抖音直播伴侣中选择")
        except Exception as e:
            QMessageBox.critical(self, "启动失败", str(e))

    def _on_stop(self):
        """停止"""
        self.main_window.digital_human_engine.stop_realtime()
        # 联动播报引擎：关闭数字人模式
        self.main_window.broadcast_engine.use_digital_human = False
        self.btn_realtime.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._log("已停止")

    def _log(self, text: str):
        """添加日志"""
        from datetime import datetime
        time_str = datetime.now().strftime("%H:%M:%S")
        self.txt_log.append(f"[{time_str}] {text}")
