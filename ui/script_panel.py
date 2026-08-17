"""话术库面板"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox, QListWidget, QListWidgetItem,
    QGroupBox, QSpinBox, QTextEdit,
    QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QFont
from ui.msgbox import QMessageBox, QInputDialog
from models.script import STYLE_PROMO, STYLE_REVIEW, STYLE_PARENTING, STYLE_CUSTOM


class GenerateThread(QThread):
    """后台生成话术"""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, generator, product, count, style, custom_prompt=""):
        super().__init__()
        self.generator = generator
        self.product = product
        self.count = count
        self.style = style
        self.custom_prompt = custom_prompt

    def run(self):
        try:
            scripts = self.generator.generate_product_scripts(
                self.product, self.count, self.style,
                custom_style_desc=self.custom_prompt,
                progress_callback=lambda msg: self.progress.emit(msg)
            )
            self.finished.emit(scripts)
        except Exception as e:
            self.error.emit(str(e))


class ScriptDetailDialog(QDialog):
    """话术详情对话框：查看完整内容并可编辑"""

    def __init__(self, content: str, product_name: str, style: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("话术详情")
        self.setMinimumSize(560, 400)

        layout = QVBoxLayout(self)
        info = QLabel(f"商品：{product_name or '通用'}    风格：{style}")
        info.setStyleSheet("color: #6b7280;")
        layout.addWidget(info)

        self.edit_content = QTextEdit()
        self.edit_content.setPlainText(content)
        self.edit_content.setFont(QFont("Microsoft YaHei", 11))
        layout.addWidget(self.edit_content)

        self.lbl_count = QLabel(f"共 {len(content)} 字")
        self.lbl_count.setStyleSheet("color: #9ca3af; font-size: 11px;")
        layout.addWidget(self.lbl_count)
        self.edit_content.textChanged.connect(
            lambda: self.lbl_count.setText(f"共 {len(self.edit_content.toPlainText())} 字")
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存修改")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_content(self) -> str:
        return self.edit_content.toPlainText().strip()


class ScriptPanel(QWidget):
    """话术库页面"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._gen_thread = None
        self._build_ui()
        self._load_products()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        # 左侧：生成控制
        left = QVBoxLayout()
        title = QLabel("话术库")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        left.addWidget(title)

        gen_group = QGroupBox("AI生成话术")
        gen_layout = QVBoxLayout(gen_group)

        gen_layout.addWidget(QLabel("选择商品："))
        self.combo_product = QComboBox()
        gen_layout.addWidget(self.combo_product)

        gen_layout.addWidget(QLabel("话术风格："))
        self.combo_style = QComboBox()
        self.combo_style.addItems([STYLE_PROMO, STYLE_REVIEW, STYLE_PARENTING, STYLE_CUSTOM])
        self.combo_style.currentTextChanged.connect(self._on_style_changed)
        gen_layout.addWidget(self.combo_style)

        # 自定义提示词（选择“自定义”风格时显示）
        self.lbl_custom_prompt = QLabel("自定义提示词：")
        gen_layout.addWidget(self.lbl_custom_prompt)
        self.txt_custom_prompt = QTextEdit()
        self.txt_custom_prompt.setPlaceholderText(
            "输入自定义生成要求，例如：\n"
            "用温柔亲切的宝妈口吻，突出产品安全无毒、适合宝宝，\n"
            "每条150字左右，结尾加一句引导下单的话。"
        )
        self.txt_custom_prompt.setFixedHeight(90)
        gen_layout.addWidget(self.txt_custom_prompt)
        self._on_style_changed(self.combo_style.currentText())
        # 加载已保存的自定义提示词
        try:
            saved = self.main_window.config.custom_script_prompt
            if saved:
                self.txt_custom_prompt.setPlainText(saved)
        except Exception:
            pass

        gen_layout.addWidget(QLabel("生成条数："))
        self.spin_count = QSpinBox()
        self.spin_count.setRange(1, 20)
        self.spin_count.setValue(5)
        gen_layout.addWidget(self.spin_count)

        self.btn_generate = QPushButton("生成话术")
        self.btn_generate.setFixedHeight(40)
        self.btn_generate.setProperty("class", "primary")
        self.btn_generate.clicked.connect(self._on_generate)
        gen_layout.addWidget(self.btn_generate)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        gen_layout.addWidget(self.lbl_status)

        left.addWidget(gen_group)
        left.addStretch()
        layout.addLayout(left, 1)

        # 右侧：话术列表
        right = QVBoxLayout()
        list_header = QHBoxLayout()
        list_header.addWidget(QLabel("已生成的话术："))
        list_header.addStretch()
        btn_select_all = QPushButton("全选")
        btn_select_all.clicked.connect(self._on_select_all)
        list_header.addWidget(btn_select_all)
        btn_deselect_all = QPushButton("取消全选")
        btn_deselect_all.clicked.connect(self._on_deselect_all)
        list_header.addWidget(btn_deselect_all)
        right.addLayout(list_header)

        hint = QLabel("双击话术可查看/编辑完整内容；勾选左侧复选框可批量删除")
        hint.setStyleSheet("color: #9ca3af; font-size: 11px;")
        right.addWidget(hint)

        self.script_list = QListWidget()
        self.script_list.setFont(QFont("Microsoft YaHei", 10))
        self.script_list.setWordWrap(True)
        self.script_list.itemDoubleClicked.connect(self._on_show_detail)
        right.addWidget(self.script_list)

        # 操作按钮
        btn_layout = QHBoxLayout()

        btn_regenerate = QPushButton("重新生成选中")
        btn_regenerate.setProperty("class", "primary")
        btn_regenerate.clicked.connect(self._on_regenerate)
        btn_layout.addWidget(btn_regenerate)

        btn_delete = QPushButton("删除选中")
        btn_delete.clicked.connect(self._on_delete)
        btn_layout.addWidget(btn_delete)

        btn_add_manual = QPushButton("手动添加")
        btn_add_manual.clicked.connect(self._on_add_manual)
        btn_layout.addWidget(btn_add_manual)

        btn_layout.addStretch()
        right.addLayout(btn_layout)

        layout.addLayout(right, 2)

    def _load_products(self):
        """加载商品到下拉框"""
        self.refresh_products()

    def refresh_products(self):
        """刷新商品下拉框（公开方法，供外部调用）"""
        # 记住当前选中的商品
        current_id = self.combo_product.currentData()
        self.combo_product.clear()
        products = self.main_window.db.get_all_products()
        for p in products:
            self.combo_product.addItem(p.name, p.id)
        # 恢复选中状态
        if current_id is not None:
            for i in range(self.combo_product.count()):
                if self.combo_product.itemData(i) == current_id:
                    self.combo_product.setCurrentIndex(i)
                    break
        # 加载已有话术
        self._refresh_scripts()

    def _refresh_scripts(self):
        """刷新话术列表"""
        self.script_list.clear()
        # 一次构建 商品id->名称 映射，避免循环查库
        product_names = {p.id: p.name for p in self.main_window.db.get_all_products()}
        scripts = self.main_window.db.get_all_scripts()
        for s in scripts:
            product_name = product_names.get(s.product_id, "")
            prefix = f"[{product_name}] " if product_name else "[通用] "
            full_text = prefix + s.content
            item = QListWidgetItem(full_text)
            item.setData(Qt.ItemDataRole.UserRole, s.id)
            item.setToolTip(s.content)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.script_list.addItem(item)
        self._recalc_item_heights()

    def _recalc_item_heights(self):
        """根据当前列表宽度重新计算每条话术的高度（完整显示）"""
        width = self.script_list.viewport().width() - 55
        if width < 100:
            return
        font_metrics = self.script_list.fontMetrics()
        for i in range(self.script_list.count()):
            item = self.script_list.item(i)
            rect = font_metrics.boundingRect(
                0, 0, width, 0, Qt.TextFlag.TextWordWrap, item.text())
            item.setSizeHint(QSize(width, rect.height() + 18))

    def resizeEvent(self, event):
        """窗口大小变化时重新计算话术高度，保证完整显示"""
        super().resizeEvent(event)
        self._recalc_item_heights()

    def showEvent(self, event):
        """面板显示时重新计算（首次显示时宽度才准确）"""
        super().showEvent(event)
        self._recalc_item_heights()

    def _get_script_by_id(self, script_id):
        """根据id查找话术对象"""
        for s in self.main_window.db.get_all_scripts():
            if s.id == script_id:
                return s
        return None

    def _on_show_detail(self, item):
        """双击话术：弹出详情对话框查看/编辑完整内容"""
        script_id = item.data(Qt.ItemDataRole.UserRole)
        script = self._get_script_by_id(script_id)
        if not script:
            return
        product_name = ""
        if script.product_id:
            for p in self.main_window.db.get_all_products():
                if p.id == script.product_id:
                    product_name = p.name
                    break
        dlg = ScriptDetailDialog(script.content, product_name, script.style, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_content = dlg.get_content()
            if new_content and new_content != script.content:
                self.main_window.db.update_script_content(script_id, new_content)
                self._refresh_scripts()
                self.lbl_status.setText("话术已更新")

    def _on_regenerate(self):
        """重新生成选中话术（AI生成一条新内容替换）"""
        checked = [
            self.script_list.item(i) for i in range(self.script_list.count())
            if self.script_list.item(i).checkState() == Qt.CheckState.Checked
        ]
        if len(checked) > 1:
            QMessageBox.information(self, "提示", "重新生成一次只能处理一条，请只勾选一条话术")
            return
        item = checked[0] if checked else self.script_list.currentItem()
        if not item:
            QMessageBox.information(self, "提示", "请先在列表中选中一条话术")
            return
        script_id = item.data(Qt.ItemDataRole.UserRole)
        script = self._get_script_by_id(script_id)
        if not script:
            return

        if not script.product_id:
            QMessageBox.warning(self, "提示", "该话术没有关联商品，无法重新生成。\n可双击进行手动编辑。")
            return

        if not self.main_window.ai_engine.is_configured:
            QMessageBox.warning(self, "提示", "请先在模型配置中设置并激活AI模型")
            return

        product = None
        for p in self.main_window.db.get_all_products():
            if p.id == script.product_id:
                product = p
                break
        if not product:
            QMessageBox.warning(self, "提示", "关联商品已被删除，无法重新生成")
            return

        self.lbl_status.setText("正在重新生成该话术...")
        self._regen_thread = GenerateThread(
            self.main_window.script_generator, product, 1,
            script.style if script.style in (STYLE_PROMO, STYLE_REVIEW, STYLE_PARENTING) else STYLE_PROMO
        )
        self._regen_thread.finished.connect(
            lambda scripts: self._on_regen_done(script_id, scripts))
        self._regen_thread.error.connect(self._on_gen_error)
        self._regen_thread.start()

    def _on_regen_done(self, script_id, scripts):
        """重新生成完成：替换原话术内容"""
        if scripts:
            self.main_window.db.update_script_content(script_id, scripts[0].content)
            self.lbl_status.setText("已重新生成该话术！")
            self._refresh_scripts()
        else:
            self.lbl_status.setText("重新生成失败，请重试")

    def _on_style_changed(self, style: str):
        """话术风格切换：仅“自定义”时显示提示词输入框"""
        is_custom = (style == STYLE_CUSTOM)
        self.lbl_custom_prompt.setVisible(is_custom)
        self.txt_custom_prompt.setVisible(is_custom)

    def _on_generate(self):
        """生成话术"""
        product_id = self.combo_product.currentData()
        if not product_id:
            QMessageBox.warning(self, "提示", "请先在商品管理中添加商品")
            return

        if not self.main_window.ai_engine.is_configured:
            QMessageBox.warning(self, "提示", "请先在模型配置中设置并激活AI模型")
            return

        # 获取商品
        products = self.main_window.db.get_all_products()
        product = None
        for p in products:
            if p.id == product_id:
                product = p
                break

        if not product:
            return

        style = self.combo_style.currentText()
        count = self.spin_count.value()
        custom_prompt = self.txt_custom_prompt.toPlainText().strip()

        # 持久化自定义提示词
        try:
            self.main_window.config.custom_script_prompt = custom_prompt
            self.main_window.save_config()
        except Exception:
            pass

        self.btn_generate.setEnabled(False)
        self.lbl_status.setText("正在生成话术，请稍候...")

        self._gen_thread = GenerateThread(
            self.main_window.script_generator, product, count, style, custom_prompt
        )
        self._gen_thread.finished.connect(self._on_gen_done)
        self._gen_thread.error.connect(self._on_gen_error)
        self._gen_thread.progress.connect(self.lbl_status.setText)
        self._gen_thread.start()

    def _on_gen_done(self, scripts):
        """生成完成"""
        self.btn_generate.setEnabled(True)
        if scripts:
            self.main_window.db.add_scripts_batch(scripts)
            self.lbl_status.setText(f"成功生成 {len(scripts)} 条话术！")
            self._refresh_scripts()
        else:
            self.lbl_status.setText("未能生成话术，请检查模型配置。")

    def _on_gen_error(self, msg):
        """生成失败"""
        self.btn_generate.setEnabled(True)
        self.lbl_status.setText(f"生成失败：{msg[:100]}")

    def _on_select_all(self):
        """全选所有话术"""
        for i in range(self.script_list.count()):
            self.script_list.item(i).setCheckState(Qt.CheckState.Checked)

    def _on_deselect_all(self):
        """取消全选"""
        for i in range(self.script_list.count()):
            self.script_list.item(i).setCheckState(Qt.CheckState.Unchecked)

    def _on_delete(self):
        """删除勾选的话术（支持多选批量删除）"""
        checked_ids = []
        for i in range(self.script_list.count()):
            item = self.script_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked_ids.append(item.data(Qt.ItemDataRole.UserRole))
        if not checked_ids:
            QMessageBox.information(self, "提示", "请先勾选要删除的话术")
            return
        n = len(checked_ids)
        msg = "确定要删除这条话术吗？" if n == 1 else f"确定要删除选中的 {n} 条话术吗？"
        if QMessageBox.question(self, "确认删除", msg) != QMessageBox.StandardButton.Yes:
            return
        for sid in checked_ids:
            self.main_window.db.delete_script(sid)
        self._refresh_scripts()
        self.lbl_status.setText(f"已删除 {n} 条话术")

    def _on_add_manual(self):
        """手动添加话术"""
        product_id = self.combo_product.currentData() or 0
        text, ok = QInputDialog.getMultiLineText(self, "手动添加话术", "输入话术内容：")
        if ok and text.strip():
            from models.script import Script, SCRIPT_TYPE_MAIN
            import time
            script = Script(
                product_id=product_id,
                script_type=SCRIPT_TYPE_MAIN,
                content=text.strip(),
                style="手动添加",
                created_at=time.time(),
            )
            self.main_window.db.add_script(script)
            self._refresh_scripts()
