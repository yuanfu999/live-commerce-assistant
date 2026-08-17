"""语音配置面板"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox, QGroupBox, QFormLayout,
    QSlider, QCheckBox, QDoubleSpinBox,
    QFileDialog, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from ui.msgbox import QMessageBox
from core.tts_engine import CHINESE_VOICES


class PreviewThread(QThread):
    """后台预览音色"""
    done = pyqtSignal(str)

    def __init__(self, engine, voice_id):
        super().__init__()
        self.engine = engine
        self.voice_id = voice_id

    def run(self):
        try:
            self.engine.preview_voice(self.voice_id)
            self.done.emit("播放完成")
        except Exception as e:
            self.done.emit(f"播放失败: {e}")


class VoiceConfigPanel(QWidget):
    """语音配置页面"""
    _clone_test_done = pyqtSignal(str)  # 克隆测试完成信号

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._preview_thread = None
        self._build_ui()
        self._load_config()
        self._clone_test_done.connect(self._on_clone_test_done)

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

        title = QLabel("语音配置")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        layout.addWidget(title)

        # TTS音色选择
        voice_group = QGroupBox("TTS音色")
        voice_form = QFormLayout(voice_group)

        self.combo_voice = QComboBox()
        for voice_id, display_name, category in CHINESE_VOICES:
            self.combo_voice.addItem(f"[{category}] {display_name}", voice_id)
        voice_form.addRow("音色：", self.combo_voice)

        preview_layout = QHBoxLayout()
        self.btn_preview = QPushButton("试听")
        self.btn_preview.clicked.connect(self._on_preview)
        preview_layout.addWidget(self.btn_preview)
        self.lbl_preview_status = QLabel("")
        preview_layout.addWidget(self.lbl_preview_status)
        preview_layout.addStretch()
        voice_form.addRow("", preview_layout)

        layout.addWidget(voice_group)

        # 语速和音量
        param_group = QGroupBox("参数调节")
        param_form = QFormLayout(param_group)

        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.5, 2.0)
        self.spin_speed.setSingleStep(0.1)
        self.spin_speed.setValue(1.0)
        self.spin_speed.setSuffix("x")
        param_form.addRow("语速：", self.spin_speed)

        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(100)
        self.lbl_volume = QLabel("100%")
        self.slider_volume.valueChanged.connect(lambda v: self.lbl_volume.setText(f"{v}%"))
        vol_layout = QHBoxLayout()
        vol_layout.addWidget(self.slider_volume)
        vol_layout.addWidget(self.lbl_volume)
        param_form.addRow("音量：", vol_layout)

        layout.addWidget(param_group)

        # 变声设置
        vc_group = QGroupBox("变声效果")
        vc_form = QFormLayout(vc_group)

        self.chk_voice_change = QCheckBox("启用变声")
        vc_form.addRow(self.chk_voice_change)

        self.spin_vc_speed = QDoubleSpinBox()
        self.spin_vc_speed.setRange(1.1, 2.0)
        self.spin_vc_speed.setSingleStep(0.05)
        self.spin_vc_speed.setValue(1.3)
        self.spin_vc_speed.setSuffix("x")
        vc_form.addRow("变声强度：", self.spin_vc_speed)

        vc_note = QLabel("提示：1.2=轻微加速，1.3=推荐，1.5=很快很尖")
        vc_note.setStyleSheet("color: #888;")
        vc_form.addRow(vc_note)

        layout.addWidget(vc_group)

        # 声音克隆设置
        clone_group = QGroupBox("声音克隆（GPT-SoVITS）")
        clone_form = QFormLayout(clone_group)

        self.chk_clone_voice = QCheckBox("启用克隆音色（替代上方 TTS 音色）")
        clone_form.addRow(self.chk_clone_voice)

        ref_layout = QHBoxLayout()
        self.lbl_ref_audio = QLabel("未选择参考音频")
        self.lbl_ref_audio.setStyleSheet("color: #6b7280;")
        ref_layout.addWidget(self.lbl_ref_audio, 1)
        btn_ref = QPushButton("选择音频")
        btn_ref.clicked.connect(self._on_select_ref_audio)
        ref_layout.addWidget(btn_ref)
        clone_form.addRow("参考音频：", ref_layout)

        clone_tip = QLabel("提示：录制5-10秒清晰语音作为参考，存放于 voice_samples/ 目录")
        clone_tip.setStyleSheet("color: #9ca3af; font-size: 11px;")
        clone_tip.setWordWrap(True)
        clone_form.addRow(clone_tip)

        self.btn_test_clone = QPushButton("测试克隆效果")
        self.btn_test_clone.clicked.connect(self._on_test_clone)
        clone_form.addRow(self.btn_test_clone)

        layout.addWidget(clone_group)

        # 保存按钮
        btn_save = QPushButton("保存配置")
        btn_save.setFixedHeight(40)
        btn_save.setProperty("class", "primary")
        btn_save.clicked.connect(self._on_save)
        layout.addWidget(btn_save)

        layout.addStretch()

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

    def _load_config(self):
        """从配置加载当前设置"""
        vc = self.main_window.config.voice
        # 设置音色下拉框
        for i in range(self.combo_voice.count()):
            if self.combo_voice.itemData(i) == vc.tts_voice:
                self.combo_voice.setCurrentIndex(i)
                break
        self.spin_speed.setValue(vc.speed)
        self.slider_volume.setValue(vc.volume)
        self.chk_voice_change.setChecked(vc.enable_voice_change)
        self.spin_vc_speed.setValue(vc.voice_change_speed)

    def _on_save(self):
        """保存配置"""
        vc = self.main_window.config.voice
        vc.tts_voice = self.combo_voice.currentData()
        vc.speed = self.spin_speed.value()
        vc.volume = self.slider_volume.value()
        vc.enable_voice_change = self.chk_voice_change.isChecked()
        vc.voice_change_speed = self.spin_vc_speed.value()

        # 更新TTS引擎
        self.main_window.tts_engine.update_config(vc)

        # 声音克隆配置（校验：勾选克隆但未选参考音频时阻止并提示）
        use_clone = self.chk_clone_voice.isChecked()
        if use_clone:
            ref_path = self.lbl_ref_audio.property("full_path")
            if not ref_path:
                QMessageBox.warning(
                    self, "无法启用克隆音色",
                    "已勾选「启用克隆音色」，但尚未选择参考音频。\n\n"
                    "请先点击「选择音频」，录制/选择一段5-10秒清晰语音作为参考，\n"
                    "否则播报时会因缺少参考音频而报错。\n\n"
                    "本次已自动取消克隆音色勾选（仍使用上方 TTS 音色播报）。"
                )
                self.chk_clone_voice.setChecked(False)
                use_clone = False
            elif not os.path.exists(ref_path):
                QMessageBox.warning(
                    self, "参考音频不存在",
                    f"参考音频文件不存在：\n{ref_path}\n\n请重新选择。"
                )
                self.chk_clone_voice.setChecked(False)
                use_clone = False
            else:
                try:
                    self.main_window.voice_clone_engine.set_reference_audio(ref_path)
                except Exception as e:
                    QMessageBox.warning(self, "参考音频设置失败", str(e))
                    self.chk_clone_voice.setChecked(False)
                    use_clone = False

        self.main_window.broadcast_engine.use_clone_voice = use_clone

        self.main_window.save_config()
        QMessageBox.information(self, "成功", "语音配置已保存")

    def _on_preview(self):
        """试听音色"""
        voice_id = self.combo_voice.currentData()
        self.lbl_preview_status.setText("正在合成...")
        self.btn_preview.setEnabled(False)

        self._preview_thread = PreviewThread(self.main_window.tts_engine, voice_id)
        self._preview_thread.done.connect(self._on_preview_done)
        self._preview_thread.start()

    def _on_preview_done(self, msg):
        self.btn_preview.setEnabled(True)
        self.lbl_preview_status.setText(msg)

    def _on_select_ref_audio(self):
        """选择参考音频"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择参考音频",
            "",
            "音频文件 (*.wav *.mp3 *.flac *.ogg *.m4a)"
        )
        if file_path:
            self.lbl_ref_audio.setText(os.path.basename(file_path))
            self.lbl_ref_audio.setStyleSheet("color: #1a1a2e; font-weight: 500;")
            self.lbl_ref_audio.setProperty("full_path", file_path)

    def _on_test_clone(self):
        """测试克隆效果"""
        ref_path = self.lbl_ref_audio.property("full_path")
        if not ref_path:
            QMessageBox.warning(self, "提示", "请先选择参考音频")
            return

        engine = self.main_window.voice_clone_engine
        try:
            engine.set_reference_audio(ref_path, "这是一段测试语音")
        except Exception as e:
            QMessageBox.critical(self, "失败", str(e))
            return

        self.btn_test_clone.setEnabled(False)
        self.btn_test_clone.setText("正在合成...")

        # 在后台线程中执行合成+播放
        def do_test():
            try:
                out = engine.synthesize("大家好，欢迎来到我的直播间，今天给大家带来的是一款超值好物。")
                # 用TTS引擎播放（pygame）
                self.main_window.tts_engine.play(out)
                self._clone_test_done.emit("克隆音频已播放")
            except Exception as e:
                self._clone_test_done.emit(f"合成失败: {str(e)[:200]}")

        import threading
        t = threading.Thread(target=do_test, daemon=True)
        t.start()

    def _on_clone_test_done(self, msg: str):
        self.btn_test_clone.setEnabled(True)
        self.btn_test_clone.setText("测试克隆效果")
        if msg.startswith("合成失败"):
            QMessageBox.warning(self, "提示", msg)
