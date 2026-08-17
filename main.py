"""
AI直播带货口播助手 - 主入口
"""
import sys
import os

# 确保项目根目录在path中
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# QtWebEngine 必须在 QApplication 创建前导入
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
except ImportError:
    pass

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from ui.main_window import MainWindow


# ==================== 设计系统："On-Air 控制台" ====================
# 配色灵感：直播间的 ON-AIR 指示灯 —— 珊瑚红=正在直播，深梅炭=控制台设备，
# 暖纸白=长时间阅读不刺眼。避免通用 indigo+冷灰模板。
COLORS = {
    "bg": "#F8F7F5",              # 暖纸白（内容区背景）
    "card": "#FFFFFF",            # 卡片
    "border": "#EAE8F2",          # 柔和紫灰边框
    "text_primary": "#26243A",    # 暖墨色文字
    "text_secondary": "#8B88A2",  # 次要文字
    "accent": "#FF4D5E",          # 直播珊瑚红（主操作）
    "accent_hover": "#E8434F",
    "accent_soft": "#FFF0F1",     # 珊瑚红浅底
    "success": "#00C07F",         # 翡翠绿
    "warning": "#FFAA2B",         # 琥珀橙
    "danger": "#F5365C",          # 警戒红
    "ink": "#232135",             # 深梅炭（侧边栏）
    "ink_deep": "#1A1828",
    "sidebar_hover": "#322F4A",
    "sidebar_active": "#3B3757",
}

GLOBAL_STYLE = f"""
    QMainWindow {{
        background-color: {COLORS['bg']};
    }}
    QWidget {{
        font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
        color: {COLORS['text_primary']};
    }}

    /* ── 分组卡片 ── */
    QGroupBox {{
        font-weight: 600;
        font-size: 13px;
        letter-spacing: 1px;
        border: 1px solid {COLORS['border']};
        border-radius: 12px;
        margin-top: 12px;
        padding: 18px 16px 16px 16px;
        background-color: {COLORS['card']};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 18px;
        padding: 0 10px;
        color: {COLORS['text_primary']};
    }}

    /* ── 按钮体系 ── */
    QPushButton {{
        padding: 8px 18px;
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        background-color: {COLORS['card']};
        font-size: 13px;
        color: {COLORS['text_primary']};
    }}
    QPushButton:hover {{
        background-color: #F4F2FA;
        border-color: #D9D6E8;
    }}
    QPushButton:pressed {{
        background-color: #ECEAF5;
    }}
    QPushButton:disabled {{
        background-color: #F4F3F8;
        color: #B9B6C9;
        border-color: {COLORS['border']};
    }}
    /* 主操作（直播珊瑚红） */
    QPushButton[class="primary"] {{
        background-color: {COLORS['accent']};
        color: white;
        border: none;
        font-weight: 600;
    }}
    QPushButton[class="primary"]:hover {{
        background-color: {COLORS['accent_hover']};
    }}
    QPushButton[class="primary"]:pressed {{
        background-color: #D63B47;
    }}
    QPushButton[class="primary"]:disabled {{
        background-color: #FFB3BA;
        color: #FFE0E3;
    }}
    /* 成功/启动（翡翠绿） */
    QPushButton[class="success"] {{
        background-color: {COLORS['success']};
        color: white;
        border: none;
        font-weight: 600;
    }}
    QPushButton[class="success"]:hover {{
        background-color: #00A66E;
    }}
    QPushButton[class="success"]:disabled {{
        background-color: #96E8C6;
        color: #D2F7E7;
    }}
    /* 警告（琥珀橙） */
    QPushButton[class="warning"] {{
        background-color: {COLORS['warning']};
        color: #4A3600;
        border: none;
        font-weight: 600;
    }}
    QPushButton[class="warning"]:hover {{
        background-color: #F09800;
    }}
    /* 危险（警戒红） */
    QPushButton[class="danger"] {{
        background-color: {COLORS['danger']};
        color: white;
        border: none;
        font-weight: 600;
    }}
    QPushButton[class="danger"]:hover {{
        background-color: #E02B50;
    }}
    QPushButton[class="danger"]:disabled {{
        background-color: #FBAEBF;
        color: #FDDCE4;
    }}
    /* 文字按钮（无边框） */
    QPushButton[class="text-danger"] {{
        background-color: transparent;
        border: none;
        color: {COLORS['danger']};
    }}
    QPushButton[class="text-danger"]:hover {{
        background-color: #FEF0F3;
    }}

    /* ── 输入控件 ── */
    QLineEdit, QSpinBox, QComboBox {{
        padding: 8px 12px;
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        background-color: {COLORS['card']};
        font-size: 13px;
        color: {COLORS['text_primary']};
        selection-background-color: {COLORS['accent_soft']};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 30px;
        border-left: 1px solid {COLORS['border']};
        border-top-right-radius: 8px;
        border-bottom-right-radius: 8px;
        background-color: #FAFAF8;
    }}
    QComboBox::down-arrow {{
        image: url(__RES_DIR__/arrow_down.svg);
        width: 10px;
        height: 6px;
    }}
    QComboBox::down-arrow:disabled {{
        image: none;
    }}
    QSpinBox, QDoubleSpinBox {{
        padding-right: 26px;
    }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 24px;
        border-left: 1px solid {COLORS['border']};
        border-bottom: 1px solid {COLORS['border']};
        border-top-right-radius: 8px;
        background-color: #FAFAF8;
    }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: 24px;
        border-left: 1px solid {COLORS['border']};
        border-bottom-right-radius: 8px;
        background-color: #FAFAF8;
    }}
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
        background-color: {COLORS['accent_soft']};
    }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        image: url(__RES_DIR__/arrow_up_small.svg);
        width: 8px;
        height: 5px;
    }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        image: url(__RES_DIR__/arrow_down_small.svg);
        width: 8px;
        height: 5px;
    }}
    QComboBox QAbstractItemView {{
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        background-color: {COLORS['card']};
        selection-background-color: {COLORS['accent_soft']};
        selection-color: {COLORS['accent']};
        padding: 4px;
        outline: none;
    }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
        border-color: {COLORS['accent']};
    }}
    QTextEdit {{
        padding: 10px;
        border: 1px solid {COLORS['border']};
        border-radius: 10px;
        background-color: {COLORS['card']};
        font-size: 13px;
        line-height: 1.5;
    }}
    QTextEdit:focus {{
        border-color: {COLORS['accent']};
    }}

    /* ── 复选框 ── */
    QCheckBox {{
        spacing: 8px;
        font-size: 13px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 2px solid #CDCADD;
        border-radius: 5px;
        background-color: white;
    }}
    QCheckBox::indicator:checked {{
        background-color: {COLORS['accent']};
        border-color: {COLORS['accent']};
    }}
    QCheckBox::indicator:hover {{
        border-color: {COLORS['accent']};
    }}

    /* ── 表格 ── */
    QTableWidget {{
        gridline-color: {COLORS['border']};
        border: 1px solid {COLORS['border']};
        border-radius: 10px;
        background-color: {COLORS['card']};
        font-size: 13px;
        alternate-background-color: #FBFAF8;
    }}
    QTableWidget::item {{
        padding: 7px 10px;
    }}
    QTableWidget::item:selected {{
        background-color: {COLORS['accent_soft']};
        color: {COLORS['text_primary']};
    }}
    QHeaderView::section {{
        background-color: #F6F5F2;
        padding: 9px 10px;
        border: none;
        border-bottom: 1px solid {COLORS['border']};
        font-weight: 600;
        font-size: 12px;
        letter-spacing: 1px;
        color: {COLORS['text_secondary']};
    }}

    /* ── 列表 ── */
    QListWidget {{
        border: 1px solid {COLORS['border']};
        border-radius: 10px;
        background-color: {COLORS['card']};
        font-size: 13px;
        padding: 4px;
        outline: none;
    }}
    QListWidget::item {{
        padding: 9px 12px;
        border-radius: 8px;
        margin: 2px 0;
    }}
    QListWidget::item:selected {{
        background-color: {COLORS['accent_soft']};
        color: #D63B47;
    }}
    QListWidget::item:hover:!selected {{
        background-color: #F4F2FA;
    }}

    /* ── 进度条（直播珊瑚红渐变） ── */
    QProgressBar {{
        border: none;
        border-radius: 4px;
        background-color: #F0EEF6;
        text-align: center;
    }}
    QProgressBar::chunk {{
        border-radius: 4px;
        background-color: {COLORS['accent']};
    }}

    /* ── 分割线 ── */
    QFrame[frameShape="4"], QFrame[frameShape="5"] {{
        color: {COLORS['border']};
        max-height: 1px;
    }}

    /* ── 状态栏（深梅炭） ── */
    QStatusBar {{
        background-color: {COLORS['ink']};
        color: #A5A1BC;
        font-size: 12px;
        padding: 5px 14px;
    }}

    /* ── 滚动条（纤细隐形） ── */
    QScrollBar:vertical {{
        width: 8px;
        background: transparent;
    }}
    QScrollBar::handle:vertical {{
        background: #D5D2E2;
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {COLORS['accent']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        height: 8px;
        background: transparent;
    }}
    QScrollBar::handle:horizontal {{
        background: #D5D2E2;
        border-radius: 4px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {COLORS['accent']};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    /* ── 提示气泡 ── */
    QToolTip {{
        background-color: {COLORS['ink']};
        color: #F0EFF6;
        border: none;
        border-radius: 8px;
        padding: 7px 12px;
        font-size: 12px;
    }}

    /* ── 滑块 ── */
    QSlider::groove:horizontal {{
        height: 6px;
        border-radius: 3px;
        background: #F0EEF6;
    }}
    QSlider::handle:horizontal {{
        width: 18px;
        height: 18px;
        margin: -6px 0;
        border-radius: 9px;
        background: {COLORS['accent']};
        border: 3px solid white;
    }}
    QSlider::sub-page:horizontal {{
        border-radius: 3px;
        background: {COLORS['accent']};
    }}
"""


def main():
    app = QApplication(sys.argv)

    # 设置全局字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    # 设置全局样式（替换资源目录占位符为绝对路径，url需正斜杠）
    res_dir = os.path.join(APP_DIR, "resources").replace(os.sep, "/")
    app.setStyleSheet(GLOBAL_STYLE.replace("__RES_DIR__", res_dir))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
