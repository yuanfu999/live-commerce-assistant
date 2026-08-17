"""运行日志面板 - 查看/导出应用运行日志，便于出问题时自查"""
import os
import shutil
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTextEdit, QFileDialog
)
from PyQt6.QtGui import QFont, QTextCursor
from ui.msgbox import QMessageBox
from core import app_logger


class LogPanel(QWidget):
    """运行日志页面"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("运行日志")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        layout.addWidget(title)

        subtitle = QLabel("记录播报、合成、连接等关键操作，出现问题时可在此查看或导出给技术支持")
        subtitle.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(subtitle)

        # 操作按钮
        btn_layout = QHBoxLayout()

        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setFixedHeight(36)
        self.btn_refresh.clicked.connect(self._refresh)
        btn_layout.addWidget(self.btn_refresh)

        self.btn_export = QPushButton("导出日志")
        self.btn_export.setFixedHeight(36)
        self.btn_export.setProperty("class", "primary")
        self.btn_export.clicked.connect(self._on_export)
        btn_layout.addWidget(self.btn_export)

        self.btn_clear = QPushButton("清空显示")
        self.btn_clear.setFixedHeight(36)
        self.btn_clear.clicked.connect(self._on_clear_view)
        btn_layout.addWidget(self.btn_clear)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 日志显示区
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; font-size: 12px; "
            "background-color: #232135; color: #D8D5E8; border-radius: 10px; padding: 12px;"
        )
        layout.addWidget(self.txt_log, 1)

        # 初始加载
        self._refresh()

    def _refresh(self):
        """刷新日志显示（优先显示完整日志文件，回退到内存缓冲）"""
        lines = self._read_log_file()
        if not lines:
            lines = app_logger.get_recent_logs(500)
        if not lines:
            self.txt_log.setPlainText("暂无日志记录")
            return
        # 只显示最近500行，避免过长
        self.txt_log.setPlainText("\n".join(lines[-500:]))
        # 滚动到底部
        cursor = self.txt_log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.txt_log.setTextCursor(cursor)

    def _read_log_file(self) -> list:
        """读取日志文件内容"""
        path = app_logger.get_log_file_path()
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return [line.rstrip() for line in f.readlines()]
        except Exception:
            return []

    def _on_export(self):
        """导出日志文件"""
        src = app_logger.get_log_file_path()
        if not os.path.exists(src):
            QMessageBox.information(self, "提示", "暂无日志文件可导出")
            return
        default_name = f"运行日志_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        save_path, _ = QFileDialog.getSaveFileName(
            self, "导出日志", default_name, "日志文件 (*.log *.txt)"
        )
        if not save_path:
            return
        try:
            shutil.copy(src, save_path)
            QMessageBox.information(self, "成功", f"日志已导出到：\n{save_path}")
            app_logger.log_info(f"日志已导出: {save_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _on_clear_view(self):
        """清空显示（不删除日志文件）"""
        self.txt_log.setPlainText("（显示已清空，日志文件仍保留，点刷新可重新加载）")

    def showEvent(self, event):
        """切换到本页时自动刷新"""
        super().showEvent(event)
        self._refresh()
