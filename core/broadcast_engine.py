"""播报引擎 - 核心调度，控制话术循环播报"""
import os
import time
import threading
from typing import List, Optional
from PyQt6.QtCore import QThread, pyqtSignal
from models.product import Product
from models.script import Script
from core.tts_engine import TTSEngine
from database.db_manager import DBManager
from core import app_logger


class BroadcastEngine(QThread):
    """
    播报引擎（QThread后台运行）
    
    信号：
        script_started: 开始播报一条话术 (话术内容, 商品名, 进度文本)
        script_finished: 一条话术播报完成
        product_changed: 切换商品 (商品名, 商品序号/总数)
        broadcast_stopped: 播报停止
        status_changed: 状态文本变化
    """
    script_started = pyqtSignal(str, str, str)   # content, product_name, progress
    script_finished = pyqtSignal()
    product_changed = pyqtSignal(str, str)        # product_name, "第X/N个"
    broadcast_stopped = pyqtSignal()
    status_changed = pyqtSignal(str)

    def __init__(self, tts_engine: TTSEngine, db: DBManager, parent=None):
        super().__init__(parent)
        self.tts_engine = tts_engine
        self.db = db

        # 播报状态
        self._running = False
        self._paused = False
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # 初始非暂停
        self._skip_event = threading.Event()  # 跳过当前话术标志

        # 播报队列
        self._products: List[Product] = []
        self._scripts_map: dict = {}  # product_id -> [Script]
        self._current_product_idx = 0
        self._current_script_idx = 0

        # 配置
        self.pause_seconds = 2.0
        self.auto_loop = True

        # 插入队列（弹幕回复等优先播报）
        self._insert_queue: List[str] = []
        self._insert_lock = threading.Lock()

        # 声音克隆 + 数字人模式
        self.voice_clone_engine = None  # VoiceCloneEngine 实例
        self.digital_human_engine = None  # DigitalHumanEngine 实例
        self.use_clone_voice = False  # 是否使用克隆音色
        self.use_digital_human = False  # 是否启用数字人

        # TTS预合成缓冲：提前合成下一条话术，避免网络慢时卡顿
        self._prefetch_cache = {}  # text -> audio_path
        self._prefetch_lock = threading.Lock()
        self.enable_prefetch = True  # 是否启用预合成

    def load_products(self, products: List[Product]):
        """加载商品和对应话术"""
        self._products = products
        self._scripts_map = {}
        for p in products:
            scripts = self.db.get_scripts_by_product(p.id, "main")
            if scripts:
                self._scripts_map[p.id] = scripts
        self._current_product_idx = 0
        self._current_script_idx = 0

    def insert_text(self, text: str):
        """插入一条优先播报文本（如弹幕回复）"""
        with self._insert_lock:
            self._insert_queue.append(text)

    def start_broadcast(self):
        """开始播报"""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._skip_event.clear()
        self._pause_event.set()
        self._paused = False
        self.start()
        app_logger.log_info("开始播报")

    def stop_broadcast(self):
        """停止播报"""
        self._running = False
        self._stop_event.set()
        self._pause_event.set()  # 解除暂停以便线程退出
        self.tts_engine.stop()
        self._clear_prefetch()
        app_logger.log_info("停止播报")

    def pause_broadcast(self):
        """暂停"""
        self._paused = True
        self._pause_event.clear()
        self.tts_engine.stop()
        self.status_changed.emit("已暂停")

    def resume_broadcast(self):
        """继续"""
        self._paused = False
        self._pause_event.set()
        self.status_changed.emit("播报中...")

    def skip_current(self):
        """跳过当前"""
        self._skip_event.set()
        self.tts_engine.stop()

    # ========== TTS预合成缓冲 ==========
    def _start_prefetch(self, text: str):
        """后台预合成下一条话术（缓冲），减少播报间的网络等待"""
        if not text or not self.enable_prefetch:
            return
        with self._prefetch_lock:
            if text in self._prefetch_cache:
                return

        def _do_prefetch():
            if self._stop_event.is_set():
                return
            try:
                path = self.tts_engine.synthesize(text)
                with self._prefetch_lock:
                    if self._stop_event.is_set():
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                    else:
                        self._prefetch_cache[text] = path
            except Exception as e:
                app_logger.log_warn("预合成失败(播报时将实时合成): " + str(e)[:60])

        threading.Thread(target=_do_prefetch, daemon=True, name="TTSPrefetch").start()

    def _get_prefetched(self, text: str) -> Optional[str]:
        """取出预合成的音频路径（未命中返回None）"""
        with self._prefetch_lock:
            path = self._prefetch_cache.pop(text, None)
        if path and not os.path.exists(path):
            return None
        return path

    def _clear_prefetch(self):
        """清空预合成缓存并删除临时音频"""
        with self._prefetch_lock:
            for path in self._prefetch_cache.values():
                try:
                    os.remove(path)
                except OSError:
                    pass
            self._prefetch_cache.clear()

    def _adaptive_pause(self, text: str) -> float:
        """根据话术长度动态计算间隔：长话术播完后停顿稍长，避免突兀"""
        base = self.pause_seconds
        # 每50字增加0.5秒，上限为基础值的2.5倍
        extra = (len(text) // 50) * 0.5
        return min(base + extra, base * 2.5)

    def run(self):
        """播报主循环（在QThread中运行）"""
        self.status_changed.emit("播报中...")

        while self._running and not self._stop_event.is_set():
            # 检查暂停
            self._pause_event.wait()
            if self._stop_event.is_set():
                break

            # 优先处理插入队列（弹幕回复等）
            insert_text = None
            with self._insert_lock:
                if self._insert_queue:
                    insert_text = self._insert_queue.pop(0)

            if insert_text:
                self._play_text(insert_text, "互动回复", "")
                continue

            # 获取当前商品
            if not self._products:
                self.status_changed.emit("没有可播报的商品")
                break

            if self._current_product_idx >= len(self._products):
                if self.auto_loop:
                    self._current_product_idx = 0
                    self._current_script_idx = 0
                else:
                    break

            product = self._products[self._current_product_idx]
            scripts = self._scripts_map.get(product.id, [])

            if not scripts:
                # 没有话术，跳过该商品
                self._current_product_idx += 1
                self._current_script_idx = 0
                continue

            # 发出商品切换信号
            product_info = f"第{self._current_product_idx + 1}/{len(self._products)}个"
            self.product_changed.emit(product.name, product_info)

            # 播报当前商品的N条话术
            scripts_to_play = min(product.scripts_per_round, len(scripts))
            start_idx = self._current_script_idx

            interrupted = False
            for i in range(start_idx, scripts_to_play):
                if self._stop_event.is_set():
                    break
                self._pause_event.wait()
                if self._stop_event.is_set():
                    break

                # 检查是否有插入的弹幕回复
                has_insert = False
                with self._insert_lock:
                    if self._insert_queue:
                        has_insert = True
                if has_insert:
                    self._current_script_idx = i
                    interrupted = True
                    break

                script = scripts[i % len(scripts)]
                progress = f"第{i + 1}/{scripts_to_play}条"
                # 预合成下一条话术（缓冲），减少播报间隔的网络等待
                if i + 1 < scripts_to_play:
                    next_script = scripts[(i + 1) % len(scripts)]
                    self._start_prefetch(next_script.content)
                self._play_text(script.content, product.name, progress)

                # 记录播放次数
                if script.id:
                    self.db.increment_play_count(script.id)
                self.db.add_history(product.id, script.content, product_name=product.name)
                self._current_script_idx = i + 1

                # 话术间隔（自适应：长话术停顿稍长）
                if not self._stop_event.is_set():
                    self._stop_event.wait(self._adaptive_pause(script.content))

            if not interrupted:
                # 当前商品播完，切换下一个
                self._current_product_idx += 1
                self._current_script_idx = 0

        self._running = False
        self.broadcast_stopped.emit()
        self.status_changed.emit("已停止")

    def _play_text(self, text: str, product_name: str, progress: str):
        """合成并播放一条话术"""
        self.script_started.emit(text, product_name, progress)

        # 合成取消检查：停止/跳过时立即中断合成，避免卡在synthesize里
        def cancel_check():
            return self._stop_event.is_set() or self._skip_event.is_set()

        try:
            audio_path = None
            # 优先使用预合成缓冲（仅非克隆模式，克隆音色无法预合成）
            if not (self.use_clone_voice and self.voice_clone_engine):
                audio_path = self._get_prefetched(text)

            if audio_path is None:
                # 未命中缓冲，实时合成（克隆不可用时自动降级TTS，避免报错循环）
                if self.use_clone_voice and self.voice_clone_engine:
                    if not self.voice_clone_engine.has_reference:
                        self.status_changed.emit("克隆音色未配置参考音频，已自动切换为TTS播报")
                        self.use_clone_voice = False
                        audio_path = self.tts_engine.synthesize(text, cancel_check=cancel_check)
                    else:
                        self.status_changed.emit("克隆音色合成中...")
                        try:
                            audio_path = self.voice_clone_engine.synthesize(text)
                        except Exception as clone_err:
                            self.status_changed.emit(f"克隆合成失败，已切换TTS: {str(clone_err)[:30]}")
                            audio_path = self.tts_engine.synthesize(text, cancel_check=cancel_check)
                else:
                    # 普通TTS模式
                    audio_path = self.tts_engine.synthesize(text, cancel_check=cancel_check)

            # 合成完发现已被停止/跳过，直接返回
            if cancel_check():
                return

            # 数字人模式：音频送入MuseTalk生成视频
            if self.use_digital_human and self.digital_human_engine:
                self.status_changed.emit("数字人生成中...")
                self.digital_human_engine.push_audio_chunk(audio_path)

            # 播放音频（观众听到声音）
            self._skip_event.clear()
            duration = self.tts_engine.play(audio_path)
            # 等待播放完成（可被跳过/停止打断）
            wait_start = time.time()
            while time.time() - wait_start < duration:
                if self._stop_event.is_set():
                    self.tts_engine.stop()
                    return
                if self._skip_event.is_set():
                    # 用户点了"跳过当前"，立即跳出等待
                    break
                if self._paused:
                    self._pause_event.wait()
                time.sleep(0.1)
        except Exception as e:
            app_logger.log_error(f"播放出错: {str(e)[:100]}")
            self.status_changed.emit(f"播放出错: {str(e)[:50]}")

        self.script_finished.emit()
