"""播报历史面板"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTableWidget, QTableWidgetItem, QGroupBox,
    QHeaderView
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from ui.msgbox import QMessageBox
from datetime import datetime


class HistoryPanel(QWidget):
    """播报历史记录页面"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._build_ui()
        self.refresh_list()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        # 标题和操作
        top_layout = QHBoxLayout()
        title = QLabel("播报历史")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        top_layout.addWidget(title)
        top_layout.addStretch()

        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setFixedHeight(36)
        self.btn_refresh.clicked.connect(self.refresh_list)
        top_layout.addWidget(self.btn_refresh)

        self.btn_clear = QPushButton("清空记录")
        self.btn_clear.setFixedHeight(36)
        self.btn_clear.setProperty("class", "text-danger")
        self.btn_clear.clicked.connect(self._on_clear)
        top_layout.addWidget(self.btn_clear)

        layout.addLayout(top_layout)

        # 历史表格
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["时间", "商品", "话术内容", "时长"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        # 统计
        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.lbl_stats)

    def refresh_list(self):
        """刷新历史记录"""
        history = self.main_window.db.get_broadcast_history(limit=200)
        self.table.setRowCount(len(history))

        total_duration = 0
        for row, h in enumerate(history):
            # 时间
            time_str = datetime.fromtimestamp(h["broadcast_at"]).strftime("%m-%d %H:%M:%S")
            self.table.setItem(row, 0, QTableWidgetItem(time_str))

            # 商品
            self.table.setItem(row, 1, QTableWidgetItem(h["product_name"] or "-"))

            # 话术内容（截断显示）
            content = h["script_content"]
            if len(content) > 60:
                content = content[:60] + "..."
            self.table.setItem(row, 2, QTableWidgetItem(content))

            # 时长
            duration = h.get("duration", 0)
            total_duration += duration
            self.table.setItem(row, 3, QTableWidgetItem(f"{duration:.1f}s"))

        self.lbl_stats.setText(f"共 {len(history)} 条记录 | 总播报时长: {total_duration:.0f}秒 ({total_duration/60:.1f}分钟)")

    def _on_clear(self):
        ret = QMessageBox.question(self, "确认", "确定清空所有播报历史记录？")
        if ret == QMessageBox.StandardButton.Yes:
            self.main_window.db.clear_broadcast_history()
            self.refresh_list()
