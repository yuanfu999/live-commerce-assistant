"""模型配置面板"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QComboBox, QGroupBox, QFormLayout,
    QListWidget, QListWidgetItem, QTextEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from ui.msgbox import QMessageBox
from models.config import ModelConfig


# 预设模型配置
PRESETS = [
    ("本地Ollama", "http://localhost:11434/v1", "ollama", "qwen2.5:7b"),
    ("DeepSeek", "https://api.deepseek.com", "", "deepseek-chat"),
    ("通义千问", "https://dashscope.aliyuncs.com/compatible-mode/v1", "", "qwen-plus"),
    ("豆包(火山引擎)", "https://ark.cn-beijing.volces.com/api/v3", "", "doubao-pro-32k"),
    ("Moonshot", "https://api.moonshot.cn/v1", "", "moonshot-v1-8k"),
]


class TestConnectionThread(QThread):
    """后台测试连接"""
    result = pyqtSignal(bool, str)

    def __init__(self, config: ModelConfig, engine):
        super().__init__()
        self.config = config
        self.engine = engine

    def run(self):
        ok, msg = self.engine.test_connection(self.config)
        self.result.emit(ok, msg)


class ModelConfigPanel(QWidget):
    """模型配置页面"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._test_thread = None
        self._build_ui()
        self._load_models()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        # 左侧：模型列表
        left = QVBoxLayout()
        title = QLabel("模型配置")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        left.addWidget(title)
        left.addWidget(QLabel("已配置的模型："))

        self.model_list = QListWidget()
        self.model_list.currentRowChanged.connect(self._on_select)
        left.addWidget(self.model_list)

        btn_layout = QHBoxLayout()
        btn_add = QPushButton("+ 新增")
        btn_add.clicked.connect(self._on_add)
        btn_del = QPushButton("删除")
        btn_del.clicked.connect(self._on_delete)
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_del)
        left.addLayout(btn_layout)

        layout.addLayout(left, 1)

        # 右侧：配置表单
        right = QVBoxLayout()
        form_group = QGroupBox("模型配置")
        form = QFormLayout(form_group)

        # 预设选择
        self.combo_preset = QComboBox()
        self.combo_preset.addItem("-- 选择预设 --")
        for name, _, _, _ in PRESETS:
            self.combo_preset.addItem(name)
        self.combo_preset.currentIndexChanged.connect(self._on_preset)
        form.addRow("快速预设：", self.combo_preset)

        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("配置名称，如：本地Ollama")
        form.addRow("名称：", self.edit_name)

        self.edit_url = QLineEdit()
        self.edit_url.setPlaceholderText("http://localhost:11434/v1")
        form.addRow("Base URL：", self.edit_url)

        self.edit_key = QLineEdit()
        self.edit_key.setPlaceholderText("API Key（本地Ollama可填ollama）")
        self.edit_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("API Key：", self.edit_key)

        self.edit_model = QLineEdit()
        self.edit_model.setPlaceholderText("模型名称，如：qwen2.5:7b")
        form.addRow("模型名：", self.edit_model)

        right.addWidget(form_group)

        # 操作按钮
        op_layout = QHBoxLayout()
        self.btn_test = QPushButton("测试连接")
        self.btn_test.setFixedHeight(36)
        self.btn_test.clicked.connect(self._on_test)
        op_layout.addWidget(self.btn_test)

        self.btn_set_active = QPushButton("设为当前使用")
        self.btn_set_active.setFixedHeight(36)
        self.btn_set_active.setProperty("class", "primary")
        self.btn_set_active.clicked.connect(self._on_set_active)
        op_layout.addWidget(self.btn_set_active)

        self.btn_save = QPushButton("保存")
        self.btn_save.setFixedHeight(36)
        self.btn_save.clicked.connect(self._on_save)
        op_layout.addWidget(self.btn_save)

        right.addLayout(op_layout)

        # 测试结果
        self.txt_result = QTextEdit()
        self.txt_result.setReadOnly(True)
        self.txt_result.setFixedHeight(80)
        self.txt_result.setPlaceholderText("测试结果...")
        right.addWidget(self.txt_result)

        right.addStretch()
        layout.addLayout(right, 2)

    def _load_models(self):
        """加载模型列表"""
        self.model_list.clear()
        for m in self.main_window.config.models:
            prefix = "● " if m.is_active else "  "
            self.model_list.addItem(f"{prefix}{m.name} ({m.model_name})")

    def _on_select(self, row):
        if row < 0 or row >= len(self.main_window.config.models):
            return
        m = self.main_window.config.models[row]
        self.edit_name.setText(m.name)
        self.edit_url.setText(m.base_url)
        self.edit_key.setText(m.api_key)
        self.edit_model.setText(m.model_name)

    def _on_preset(self, idx):
        if idx <= 0:
            return
        name, url, key, model = PRESETS[idx - 1]
        self.edit_name.setText(name)
        self.edit_url.setText(url)
        self.edit_key.setText(key)
        self.edit_model.setText(model)
        self.combo_preset.setCurrentIndex(0)

    def _on_add(self):
        self.main_window.config.models.append(ModelConfig(name="新模型"))
        self._load_models()
        self.model_list.setCurrentRow(len(self.main_window.config.models) - 1)

    def _on_delete(self):
        row = self.model_list.currentRow()
        if row < 0:
            return
        if len(self.main_window.config.models) <= 1:
            QMessageBox.warning(self, "提示", "至少保留一个模型配置")
            return
        self.main_window.config.models.pop(row)
        self._load_models()

    def _on_save(self):
        row = self.model_list.currentRow()
        if row < 0:
            return
        name = self.edit_name.text().strip()
        url = self.edit_url.text().strip()
        model = self.edit_model.text().strip()
        # 基础校验：必填项不能为空
        if not name or not url or not model:
            QMessageBox.warning(self, "配置不完整", "请填写名称、Base URL 和模型名后再保存")
            return
        m = self.main_window.config.models[row]
        m.name = name
        m.base_url = url
        m.api_key = self.edit_key.text().strip()
        m.model_name = model
        self._load_models()
        self.model_list.setCurrentRow(row)
        self.main_window.save_config()
        self.txt_result.setPlainText("已保存（建议点“测试连接”验证可用性）")

    def _on_set_active(self):
        row = self.model_list.currentRow()
        if row < 0:
            return
        # 先保存当前编辑
        self._on_save()
        # 激活前先测试连接，避免启用错误的Key/URL导致生成失败
        config = self.main_window.config.models[row]
        self.txt_result.setPlainText("正在测试连接，验证通过后自动激活...")
        self.btn_set_active.setEnabled(False)
        self._active_row = row
        self._test_thread = TestConnectionThread(config, self.main_window.ai_engine)
        self._test_thread.result.connect(self._on_activate_test_result)
        self._test_thread.start()

    def _on_activate_test_result(self, ok: bool, msg: str):
        """激活前连接测试结果"""
        self.btn_set_active.setEnabled(True)
        row = getattr(self, "_active_row", -1)
        self._active_row = -1
        if row < 0:
            return
        if not ok:
            self.txt_result.setPlainText("✗ 连接测试失败，已取消激活：" + msg)
            QMessageBox.warning(
                self, "连接测试失败",
                "该模型连接测试失败，无法激活：\n\n" + msg +
                "\n\n请检查 Base URL、API Key 和模型名是否正确，\n点击“测试连接”验证通过后再设为当前使用。"
            )
            return
        # 验证通过，设置活跃
        for i, m in enumerate(self.main_window.config.models):
            m.is_active = (i == row)
        self._load_models()
        self.model_list.setCurrentRow(row)
        active = self.main_window.config.get_active_model()
        if active:
            self.main_window.ai_engine.set_model(active)
        self.main_window.save_config()
        self.txt_result.setPlainText("✓ " + msg + "\n已切换为：" + (active.name if active else ""))

    def _on_test(self):
        config = ModelConfig(
            name=self.edit_name.text().strip(),
            base_url=self.edit_url.text().strip(),
            api_key=self.edit_key.text().strip(),
            model_name=self.edit_model.text().strip(),
        )
        self.txt_result.setPlainText("正在测试连接...")
        self.btn_test.setEnabled(False)

        self._test_thread = TestConnectionThread(config, self.main_window.ai_engine)
        self._test_thread.result.connect(self._on_test_result)
        self._test_thread.start()

    def _on_test_result(self, ok: bool, msg: str):
        self.btn_test.setEnabled(True)
        self.txt_result.setPlainText(("✓ " if ok else "✗ ") + msg)
