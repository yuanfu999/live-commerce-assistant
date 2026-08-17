"""会员中心面板"""
import time
import json
import os
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QGroupBox, QFormLayout, QLineEdit,
    QFrame, QGridLayout, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPalette, QColor
from ui.msgbox import QMessageBox


# 会员等级配置
MEMBER_TIERS = {
    "free": {"name": "免费版", "color": "#8B88A2", "features": ["基础播报功能", "3个商品上限", "每日50次AI生成"]},
    "basic": {"name": "基础会员", "color": "#FF4D5E", "price": "29元/月", "features": ["无限商品", "无限AI生成", "弹幕互动", "定时播报"]},
    "pro": {"name": "专业会员", "color": "#FFAA2B", "price": "79元/月", "features": ["全部基础功能", "多账号管理", "数据导出", "优先客服"]},
    "enterprise": {"name": "企业版", "color": "#00C07F", "price": "199元/月", "features": ["全部专业功能", "API接口", "定制开发", "专属客服"]},
}


class MemberPanel(QWidget):
    """会员中心页面"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._member_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config", "member.json"
        )
        self._member_data = self._load_member()
        self._build_ui()

    def _load_member(self) -> dict:
        """加载会员数据"""
        default = {
            "tier": "free",
            "username": "",
            "expire_at": 0,
            "balance": 0.0,
            "recharge_history": [],
            "activated_at": 0,
        }
        try:
            if os.path.exists(self._member_file):
                with open(self._member_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default.update(data)
        except Exception:
            pass
        return default

    def _save_member(self):
        """保存会员数据"""
        os.makedirs(os.path.dirname(self._member_file), exist_ok=True)
        with open(self._member_file, "w", encoding="utf-8") as f:
            json.dump(self._member_data, f, ensure_ascii=False, indent=2)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # 标题
        title = QLabel("会员中心")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # 当前会员状态卡片
        self._build_status_card(layout)

        # 会员套餐
        self._build_tier_cards(layout)

        # 充值区域
        self._build_recharge_section(layout)

        # 激活码
        self._build_activate_section(layout)

        layout.addStretch()

    def _build_status_card(self, parent_layout):
        """当前状态卡片"""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #FF4D5E, stop:1 #FF7A5C);
                border-radius: 14px;
                padding: 24px;
            }
        """)
        card.setFixedHeight(130)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)

        tier = self._member_data.get("tier", "free")
        tier_info = MEMBER_TIERS.get(tier, MEMBER_TIERS["free"])

        self.lbl_tier_name = QLabel(tier_info["name"])
        self.lbl_tier_name.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        self.lbl_tier_name.setStyleSheet("color: white; background: transparent;")
        card_layout.addWidget(self.lbl_tier_name)

        # 到期时间
        expire_at = self._member_data.get("expire_at", 0)
        if expire_at > time.time():
            expire_str = datetime.fromtimestamp(expire_at).strftime("%Y-%m-%d")
            status_text = f"有效期至 {expire_str}"
        elif tier == "free":
            status_text = "永久免费 · 功能受限"
        else:
            status_text = "已过期 · 请续费"

        self.lbl_status = QLabel(status_text)
        self.lbl_status.setFont(QFont("Microsoft YaHei", 11))
        self.lbl_status.setStyleSheet("color: rgba(255,255,255,0.85); background: transparent;")
        card_layout.addWidget(self.lbl_status)

        # 余额
        balance = self._member_data.get("balance", 0)
        self.lbl_balance = QLabel(f"账户余额：¥{balance:.2f}")
        self.lbl_balance.setFont(QFont("Microsoft YaHei", 11))
        self.lbl_balance.setStyleSheet("color: rgba(255,255,255,0.7); background: transparent;")
        card_layout.addWidget(self.lbl_balance)

        parent_layout.addWidget(card)

    def _build_tier_cards(self, parent_layout):
        """会员套餐卡片"""
        group = QGroupBox("选择套餐")
        grid = QGridLayout(group)
        grid.setSpacing(14)

        for idx, (key, info) in enumerate(MEMBER_TIERS.items()):
            if key == "free":
                continue
            card = QFrame()
            is_current = self._member_data.get("tier") == key
            border_color = info["color"] if is_current else "#e8eaed"
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: white;
                    border: 2px solid {border_color};
                    border-radius: 12px;
                    padding: 16px;
                }}
                QFrame:hover {{
                    border-color: {info['color']};
                }}
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setSpacing(8)

            name_lbl = QLabel(info["name"])
            name_lbl.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
            name_lbl.setStyleSheet(f"color: {info['color']}; border: none;")
            card_layout.addWidget(name_lbl)

            price_lbl = QLabel(info.get("price", ""))
            price_lbl.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
            price_lbl.setStyleSheet("border: none;")
            card_layout.addWidget(price_lbl)

            features_text = "\n".join(f"✓ {f}" for f in info["features"])
            feat_lbl = QLabel(features_text)
            feat_lbl.setFont(QFont("Microsoft YaHei", 10))
            feat_lbl.setStyleSheet("color: #6b7280; border: none;")
            feat_lbl.setWordWrap(True)
            card_layout.addWidget(feat_lbl)

            btn = QPushButton("当前套餐" if is_current else "立即开通")
            btn.setFixedHeight(36)
            if is_current:
                btn.setEnabled(False)
                btn.setStyleSheet("border: none; background: #f3f4f6; color: #9ca3af; border-radius: 8px;")
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        border: none;
                        background-color: {info['color']};
                        color: white;
                        border-radius: 8px;
                        font-weight: 600;
                    }}
                    QPushButton:hover {{ background-color: {info['color']}dd; }}
                """)
                btn.clicked.connect(lambda checked, k=key: self._on_subscribe(k))
            card_layout.addWidget(btn)

            grid.addWidget(card, 0, idx - 1)

        parent_layout.addWidget(group)

    def _build_recharge_section(self, parent_layout):
        """充值区域"""
        group = QGroupBox("账户充值")
        form = QFormLayout(group)
        form.setSpacing(12)

        amount_layout = QHBoxLayout()
        self.edit_amount = QLineEdit()
        self.edit_amount.setPlaceholderText("输入充值金额（元）")
        amount_layout.addWidget(self.edit_amount)

        btn_recharge = QPushButton("确认充值")
        btn_recharge.setFixedHeight(38)
        btn_recharge.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: 600;
                padding: 0 20px;
            }
            QPushButton:hover { background-color: #059669; }
        """)
        btn_recharge.clicked.connect(self._on_recharge)
        amount_layout.addWidget(btn_recharge)

        form.addRow("充值金额：", amount_layout)

        note = QLabel("提示：正式版将接入微信/支付宝支付，当前为本地模拟充值。")
        note.setStyleSheet("color: #9ca3af; font-size: 11px;")
        form.addRow(note)

        parent_layout.addWidget(group)

    def _build_activate_section(self, parent_layout):
        """激活码区域"""
        group = QGroupBox("激活码兑换")
        form = QFormLayout(group)
        form.setSpacing(12)

        code_layout = QHBoxLayout()
        self.edit_code = QLineEdit()
        self.edit_code.setPlaceholderText("输入激活码，如：VIP-XXXX-XXXX")
        code_layout.addWidget(self.edit_code)

        btn_activate = QPushButton("兑换")
        btn_activate.setFixedHeight(38)
        btn_activate.setStyleSheet("""
            QPushButton {
                background-color: #FF4D5E;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: 600;
                padding: 0 20px;
            }
            QPushButton:hover { background-color: #E8434F; }
        """)
        btn_activate.clicked.connect(self._on_activate)
        code_layout.addWidget(btn_activate)

        form.addRow("激活码：", code_layout)
        parent_layout.addWidget(group)

    def _on_subscribe(self, tier: str):
        """开通会员"""
        info = MEMBER_TIERS[tier]
        ret = QMessageBox.question(
            self, "确认开通",
            f"确定开通「{info['name']}」？\n价格：{info.get('price', '')}\n\n（正式版将跳转支付页面）"
        )
        if ret == QMessageBox.StandardButton.Yes:
            self._member_data["tier"] = tier
            self._member_data["activated_at"] = time.time()
            # 默认开通30天
            self._member_data["expire_at"] = time.time() + 30 * 86400
            self._save_member()
            self._refresh_ui()
            QMessageBox.information(self, "成功", f"已开通「{info['name']}」，有效期30天！")

    def _on_recharge(self):
        """充值"""
        amount_str = self.edit_amount.text().strip()
        try:
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "提示", "请输入有效的充值金额")
            return

        self._member_data["balance"] = self._member_data.get("balance", 0) + amount
        self._member_data.setdefault("recharge_history", []).append({
            "amount": amount,
            "time": time.time(),
            "method": "local_simulate"
        })
        self._save_member()
        self._refresh_ui()
        self.edit_amount.clear()
        QMessageBox.information(self, "充值成功", f"已充值 ¥{amount:.2f}，当前余额 ¥{self._member_data['balance']:.2f}")

    def _on_activate(self):
        """激活码兑换"""
        code = self.edit_code.text().strip().upper()
        if not code:
            QMessageBox.warning(self, "提示", "请输入激活码")
            return

        # 简单验证逻辑（正式版应调用服务器验证）
        valid_codes = {
            "VIP-BASIC-30D": ("basic", 30),
            "VIP-PRO-30D": ("pro", 30),
            "VIP-ENT-30D": ("enterprise", 30),
            "VIP-PRO-365D": ("pro", 365),
        }

        if code in valid_codes:
            tier, days = valid_codes[code]
            self._member_data["tier"] = tier
            self._member_data["activated_at"] = time.time()
            self._member_data["expire_at"] = time.time() + days * 86400
            self._save_member()
            self._refresh_ui()
            self.edit_code.clear()
            info = MEMBER_TIERS[tier]
            QMessageBox.information(self, "兑换成功", f"已激活「{info['name']}」，有效期{days}天！")
        else:
            QMessageBox.warning(self, "兑换失败", "无效的激活码，请检查后重试。")

    def _refresh_ui(self):
        """刷新界面"""
        tier = self._member_data.get("tier", "free")
        tier_info = MEMBER_TIERS.get(tier, MEMBER_TIERS["free"])
        self.lbl_tier_name.setText(tier_info["name"])

        expire_at = self._member_data.get("expire_at", 0)
        if expire_at > time.time():
            expire_str = datetime.fromtimestamp(expire_at).strftime("%Y-%m-%d")
            self.lbl_status.setText(f"有效期至 {expire_str}")
        elif tier == "free":
            self.lbl_status.setText("永久免费 · 功能受限")
        else:
            self.lbl_status.setText("已过期 · 请续费")

        self.lbl_balance.setText(f"账户余额：¥{self._member_data.get('balance', 0):.2f}")

    def get_member_tier(self) -> str:
        """获取当前会员等级"""
        return self._member_data.get("tier", "free")

    def is_vip(self) -> bool:
        """是否为付费会员（未过期）"""
        tier = self._member_data.get("tier", "free")
        if tier == "free":
            return False
        return self._member_data.get("expire_at", 0) > time.time()
