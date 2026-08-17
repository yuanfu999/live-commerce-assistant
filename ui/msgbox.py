"""统一风格消息弹窗 - QMessageBox 的美化+汉化替代

API 与 QMessageBox 完全兼容，各页面只需把导入替换为
`from ui.msgbox import QMessageBox`，即可让所有弹窗统一为软件风格并使用中文按钮。
"""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QTextEdit
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


# 弹窗图标样式（与软件配色一致）：符号、前景色、背景色
_ICON_STYLES = {
    "info": ("i", "#FF4D5E", "#FFF0F1"),       # 直播珊瑚红
    "question": ("?", "#FF4D5E", "#FFF0F1"),
    "warn": ("!", "#FFAA2B", "#FFF7E8"),       # 琥珀橙
    "error": ("✕", "#F5365C", "#FEF0F3"),      # 警戒红
    "success": ("✓", "#00C07F", "#E8FBF2"),    # 翡翠绿
}


class _StandardButton:
    """兼容 QMessageBox.StandardButton 的返回值"""
    NoButton = 0
    No = 0
    Cancel = 0
    Yes = 1
    Ok = 1


class _MsgDialog(QDialog):
    """自定义消息对话框（匹配软件整体风格）"""

    def __init__(self, title: str, text: str, icon: str = "info", show_cancel: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMaximumWidth(520)
        # 去掉标题栏的问号按钮
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # 顶部：圆形图标 + 标题
        header = QHBoxLayout()
        header.setSpacing(12)
        symbol, fg, bg = _ICON_STYLES.get(icon, _ICON_STYLES["info"])
        icon_lbl = QLabel(symbol)
        icon_lbl.setFixedSize(34, 34)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 17px; "
            f"font-size: 17px; font-weight: bold;"
        )
        header.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        header.addWidget(title_lbl)
        header.addStretch()
        layout.addLayout(header)

        # 正文内容（支持换行、可选中复制）
        msg_lbl = QLabel(str(text))
        msg_lbl.setWordWrap(True)
        msg_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        msg_lbl.setStyleSheet("color: #374151; font-size: 13px;")
        layout.addWidget(msg_lbl)

        # 底部按钮（右对齐，中文）
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        if show_cancel:
            btn_cancel = QPushButton("取消")
            btn_cancel.setFixedHeight(34)
            btn_cancel.setMinimumWidth(84)
            btn_cancel.clicked.connect(self.reject)
            btn_row.addWidget(btn_cancel)
        btn_ok = QPushButton("确定")
        btn_ok.setFixedHeight(34)
        btn_ok.setMinimumWidth(84)
        btn_ok.setProperty("class", "primary")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        btn_ok.setFocus()


class QMessageBox:
    """QMessageBox 直接替代：统一软件风格 + 中文按钮（确定/取消）"""

    StandardButton = _StandardButton

    @staticmethod
    def _exec(parent, title, text, icon, show_cancel):
        dlg = _MsgDialog(title, text, icon, show_cancel, parent)
        result = dlg.exec()
        return _StandardButton.Yes if result == QDialog.DialogCode.Accepted else _StandardButton.No

    @staticmethod
    def information(parent, title, text, *args, **kwargs):
        return QMessageBox._exec(parent, title, text, "info", False)

    @staticmethod
    def warning(parent, title, text, *args, **kwargs):
        return QMessageBox._exec(parent, title, text, "warn", False)

    @staticmethod
    def critical(parent, title, text, *args, **kwargs):
        return QMessageBox._exec(parent, title, text, "error", False)

    @staticmethod
    def question(parent, title, text, *args, **kwargs):
        return QMessageBox._exec(parent, title, text, "question", True)

    @staticmethod
    def about(parent, title, text, *args, **kwargs):
        return QMessageBox._exec(parent, title, text, "info", False)


class _InputDialog(QDialog):
    """自定义输入对话框（匹配软件风格，中文按钮）"""

    def __init__(self, title: str, label: str, text: str = "", multiline: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        lbl = QLabel(label)
        lbl.setStyleSheet("color: #374151; font-size: 13px;")
        layout.addWidget(lbl)

        if multiline:
            self.edit = QTextEdit()
            self.edit.setMinimumHeight(140)
            self.edit.setPlainText(text)
        else:
            self.edit = QLineEdit(text)
            self.edit.setFixedHeight(34)
        layout.addWidget(self.edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setMinimumWidth(84)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        btn_ok = QPushButton("确定")
        btn_ok.setFixedHeight(34)
        btn_ok.setMinimumWidth(84)
        btn_ok.setProperty("class", "primary")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        self.edit.setFocus()
        # 取消默认全选（蓝底看不清），光标移到末尾
        if isinstance(self.edit, QLineEdit):
            self.edit.deselect()
            self.edit.setCursorPosition(len(self.edit.text()))

    def text(self) -> str:
        if isinstance(self.edit, QTextEdit):
            return self.edit.toPlainText()
        return self.edit.text()


class QInputDialog:
    """QInputDialog 直接替代：统一软件风格 + 中文按钮（返回 (text, ok) 与原API一致）"""

    @staticmethod
    def getText(parent, title, label, *args, text="", **kwargs):
        dlg = _InputDialog(title, label, text, False, parent)
        ok = dlg.exec() == QDialog.DialogCode.Accepted
        return dlg.text(), ok

    @staticmethod
    def getMultiLineText(parent, title, label, *args, text="", **kwargs):
        dlg = _InputDialog(title, label, text, True, parent)
        ok = dlg.exec() == QDialog.DialogCode.Accepted
        return dlg.text(), ok
