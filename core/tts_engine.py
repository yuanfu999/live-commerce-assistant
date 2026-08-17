"""TTS语音引擎 - edge-tts合成 + 变声处理"""
import asyncio
import concurrent.futures
import os
import struct
import tempfile
import threading
import time
import uuid
import wave
import numpy as np
import miniaudio
import edge_tts
import pygame
from typing import Optional, Callable
from models.config import VoiceConfig
from core import app_logger


# 微软已下线大部分中文音色（2024-2025），以下为当前实测可用的音色
CHINESE_VOICES = [
    # (voice_id, 显示名称, 分类)
    ("zh-CN-XiaoxiaoNeural", "晓晓（女声·温柔）", "女声"),
    ("zh-CN-XiaoyiNeural", "晓伊（女声·甜美）", "女声"),
    ("zh-CN-YunxiNeural", "云希（男声·活泼）", "男声"),
    ("zh-CN-YunjianNeural", "云健（男声·沉稳）", "男声"),
    ("zh-CN-YunxiaNeural", "云夏（男声·温和）", "男声"),
    ("zh-CN-YunyangNeural", "云扬（男声·专业）", "男声"),
    ("zh-CN-liaoning-XiaobeiNeural", "晓北（东北话）", "方言"),
    ("zh-CN-shaanxi-XiaoniNeural", "晓妮（陕西话）", "方言"),
]

# 默认音色（音色失效时自动回退到该音色）
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

# 有效音色ID集合，用于校验
VALID_VOICE_IDS = {v[0] for v in CHINESE_VOICES}

# 音频文件清理阈值：超过MAX个时清理到保留KEEP个
MAX_AUDIO_FILES = 80
KEEP_AUDIO_FILES = 50


class TTSEngine:
    """TTS语音合成引擎（线程安全）"""

    def __init__(self, config: VoiceConfig = None):
        self.config = config or VoiceConfig()
        self._audio_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output_audio")
        os.makedirs(self._audio_dir, exist_ok=True)
        # pygame.mixer 非线程安全，所有调用通过锁串行化
        self._lock = threading.RLock()
        self._mixer_ready = False
        self._init_mixer()
        # 持久后台事件循环：避免每次 asyncio.run 创建/销毁循环导致 aiohttp 资源泄漏卡死
        self._loop = None
        self._loop_thread = None
        self._loop_lock = threading.Lock()
        self._start_loop_thread()

    def _start_loop_thread(self):
        """启动持久后台事件循环线程"""
        with self._loop_lock:
            if self._loop_thread and self._loop_thread.is_alive():
                return
            def run_loop():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                self._loop.run_forever()
            self._loop_thread = threading.Thread(target=run_loop, daemon=True, name="TTSEventLoop")
            self._loop_thread.start()
            # 等待loop创建完成
            for _ in range(50):
                if self._loop is not None:
                    break
                time.sleep(0.02)

    def _run_async(self, coro, timeout: float = 30.0, cancel_check: Optional[Callable[[], bool]] = None):
        """
        在持久事件循环中运行协程，带超时与取消检查。
        每秒轮询一次，可被 cancel_check 打断，避免网络慢时无限卡死。
        """
        if self._loop is None:
            raise RuntimeError("TTS事件循环未就绪")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        deadline = time.time() + timeout
        while True:
            try:
                return future.result(timeout=1)
            except concurrent.futures.TimeoutError:
                if time.time() > deadline:
                    future.cancel()
                    raise RuntimeError(f"TTS合成超时({int(timeout)}秒)")
                if cancel_check and cancel_check():
                    future.cancel()
                    raise RuntimeError("已取消")

    def _init_mixer(self):
        """初始化音频混音器"""
        with self._lock:
            try:
                pygame.mixer.init()
                self._mixer_ready = True
            except Exception:
                self._mixer_ready = False

    def update_config(self, config: VoiceConfig):
        self.config = config

    async def _synthesize(self, text: str, output_path: str):
        """调用edge-tts合成语音"""
        # 构造语速参数
        rate = f"+{int((self.config.speed - 1) * 100)}%" if self.config.speed >= 1 \
            else f"-{int((1 - self.config.speed) * 100)}%"
        volume = f"+{self.config.volume - 100}%" if self.config.volume >= 100 \
            else f"-{100 - self.config.volume}%"

        # 音色校验：已下线/未知音色自动回退默认音色，避免NoAudioReceived
        voice = self.config.tts_voice
        if voice not in VALID_VOICE_IDS:
            voice = DEFAULT_VOICE

        communicate = edge_tts.Communicate(
            text,
            voice=voice,
            rate=rate,
            volume=volume,
        )
        await communicate.save(output_path)

    def _decode_audio(self, input_path: str):
        """解码音频文件为原始PCM数据。
        优先使用pygame解码（SDL_mixer对edge-tts输出的MP3解码完整）；
        miniaudio对该类MP3存在只解出一半时长的缺陷，仅作兑底。
        返回 (samples_bytes, sample_rate, num_channels, sample_width)
        """
        try:
            with self._lock:
                if not self._mixer_ready:
                    pygame.mixer.init()
                    self._mixer_ready = True
                sound = pygame.mixer.Sound(input_path)
                raw = sound.get_raw()
                fmt = pygame.mixer.get_init()
            freq, size, channels = fmt
            return raw, freq, channels, abs(size) // 8
        except Exception as e:
            app_logger.log_warn("pygame解码失败，回退miniaudio: " + str(e)[:60])
            decoded = miniaudio.decode_file(input_path)
            return decoded.samples, decoded.sample_rate, decoded.nchannels, decoded.sample_width

    def _verify_duration(self, audio_path: str, text: str):
        """校验音频时长并记录日志。时长明显过短（语速异常快）时疑似截断，记录告警。"""
        try:
            with wave.open(audio_path) as wf:
                duration = wf.getnframes() / wf.getframerate()
        except Exception:
            return
        app_logger.log_info("合成完成: " + str(len(text)) + "字 -> " + str(round(duration, 1)) + "秒")
        # 正常语速约每秒3-6字，超过每秒8字（乘以语速倍率）视为疑似截断
        if len(text) > 30 and duration > 0:
            max_rate = 8.0 * max(self.config.speed, 1.0)
            if len(text) / duration > max_rate:
                app_logger.log_warn(
                    "音频疑似截断: " + str(len(text)) + "字仅" + str(round(duration, 1)) +
                    "秒（语速异常），文件: " + os.path.basename(audio_path)
                )

    def _apply_voice_change(self, input_path: str, output_path: str):
        """应用变声效果（加速升调：提高音调并加快语速）"""
        speed = self.config.voice_change_speed

        samples, sample_rate, num_channels, sample_width = self._decode_audio(input_path)

        audio_data = np.frombuffer(samples, dtype=np.int16).astype(np.float64)

        if num_channels == 2:
            audio_left = audio_data[0::2]
            audio_right = audio_data[1::2]
        else:
            audio_left = audio_data
            audio_right = None

        original_length = len(audio_left)
        new_length = int(original_length / speed)

        old_indices = np.linspace(0, original_length - 1, new_length)
        new_audio_left = np.interp(old_indices, np.arange(original_length), audio_left)

        if audio_right is not None:
            new_audio_right = np.interp(old_indices, np.arange(original_length), audio_right)
            new_audio = np.empty(new_length * 2, dtype=np.float64)
            new_audio[0::2] = new_audio_left
            new_audio[1::2] = new_audio_right
        else:
            new_audio = new_audio_left

        new_audio = np.clip(new_audio, -32768, 32767).astype(np.int16)
        self._write_wav(output_path, new_audio.tobytes(), sample_rate, num_channels, sample_width)

    def _write_wav(self, filepath: str, data: bytes, sample_rate: int, num_channels: int, sample_width: int):
        """写WAV文件"""
        data_size = len(data)
        byte_rate = sample_rate * num_channels * sample_width
        block_align = num_channels * sample_width

        with open(filepath, 'wb') as f:
            f.write(b'RIFF')
            f.write(struct.pack('<I', 36 + data_size))
            f.write(b'WAVE')
            f.write(b'fmt ')
            f.write(struct.pack('<I', 16))
            f.write(struct.pack('<H', 1))
            f.write(struct.pack('<H', num_channels))
            f.write(struct.pack('<I', sample_rate))
            f.write(struct.pack('<I', byte_rate))
            f.write(struct.pack('<H', block_align))
            f.write(struct.pack('<H', sample_width * 8))
            f.write(b'data')
            f.write(struct.pack('<I', data_size))
            f.write(data)

    def synthesize(self, text: str, filename: str = None, cancel_check: Optional[Callable[[], bool]] = None) -> str:
        """
        完整合成流程：文字 → TTS → (可选变声) → WAV文件
        返回输出文件路径。cancel_check 返回True时立即中止（用于停止播报）。
        """
        if filename is None:
            import hashlib
            name_hash = hashlib.md5(text.encode()).hexdigest()[:10]
            # 加唯一后缀防止并发覆盖
            filename = f"tts_{name_hash}_{uuid.uuid4().hex[:6]}.wav"

        output_path = os.path.join(self._audio_dir, filename)
        # 临时文件也用唯一名，避免并发冲突
        temp_mp3 = os.path.join(self._audio_dir, f"_temp_{uuid.uuid4().hex[:8]}.mp3")

        # TTS合成（网络失败自动重试2次，每次最多30秒）
        last_err = None
        for attempt in range(3):
            if cancel_check and cancel_check():
                raise RuntimeError("已取消")
            try:
                self._run_async(self._synthesize(text, temp_mp3), timeout=30, cancel_check=cancel_check)
                last_err = None
                break
            except Exception as e:
                last_err = e
                # 被取消时不重试
                if cancel_check and cancel_check():
                    break
                time.sleep(0.8)
        if last_err is not None:
            if os.path.exists(temp_mp3):
                try:
                    os.remove(temp_mp3)
                except OSError:
                    pass
            raise RuntimeError(f"TTS合成失败: {last_err}")

        # 校验合成文件完整性（防止损坏文件导致 miniaudio C扩展崩溃闪退）
        if not os.path.exists(temp_mp3) or os.path.getsize(temp_mp3) < 200:
            if os.path.exists(temp_mp3):
                try:
                    os.remove(temp_mp3)
                except OSError:
                    pass
            raise RuntimeError("TTS合成结果文件无效或过小")

        # 变声处理
        if self.config.enable_voice_change:
            self._apply_voice_change(temp_mp3, output_path)
            if os.path.exists(temp_mp3):
                os.remove(temp_mp3)
        else:
            # 不变声，直接转换格式为wav（用pygame解码，避免miniaudio截断一半）
            samples, sample_rate, num_channels, sample_width = self._decode_audio(temp_mp3)
            self._write_wav(output_path, samples, sample_rate, num_channels, sample_width)
            if os.path.exists(temp_mp3):
                os.remove(temp_mp3)

        # 校验输出时长并记录日志（疑似截断时告警，便于排查）
        self._verify_duration(output_path, text)

        # 定期清理旧音频，避免output_audio目录无限膨胀
        self._cleanup_old_audio()

        return output_path

    def play(self, audio_path: str) -> float:
        """播放音频文件，返回时长(秒)"""
        with self._lock:
            if not self._mixer_ready or not os.path.exists(audio_path):
                return 0
            try:
                sound = pygame.mixer.Sound(audio_path)
                sound.set_volume(self.config.volume / 100.0)
                sound.play()
                return sound.get_length()
            except Exception:
                return 0

    def stop(self):
        """停止播放"""
        with self._lock:
            if not self._mixer_ready:
                return
            try:
                pygame.mixer.stop()
            except Exception:
                pass

    def preview_voice(self, voice_id: str, text: str = "你好，欢迎来到直播间！") -> str:
        """预览指定音色"""
        uid = uuid.uuid4().hex[:6]
        temp_path = os.path.join(self._audio_dir, f"_preview_{uid}.mp3")
        out_path = os.path.join(self._audio_dir, f"_preview_{uid}.wav")

        async def _gen():
            comm = edge_tts.Communicate(text, voice=voice_id)
            await comm.save(temp_path)

        self._run_async(_gen(), timeout=20)

        if not os.path.exists(temp_path) or os.path.getsize(temp_path) < 200:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise RuntimeError("试听合成结果无效")

        samples, sample_rate, num_channels, sample_width = self._decode_audio(temp_path)
        self._write_wav(out_path, samples, sample_rate, num_channels, sample_width)
        if os.path.exists(temp_path):
            os.remove(temp_path)

        self.play(out_path)
        return out_path

    def _cleanup_old_audio(self):
        """清理旧音频文件：超过上限时删除最旧的文件，防止目录膨胀"""
        try:
            files = []
            for name in os.listdir(self._audio_dir):
                path = os.path.join(self._audio_dir, name)
                if os.path.isfile(path) and (name.endswith('.wav') or name.endswith('.mp3')):
                    files.append((os.path.getmtime(path), path))
            if len(files) <= MAX_AUDIO_FILES:
                return
            files.sort()  # 按修改时间升序（最旧在前）
            now = time.time()
            excess = len(files) - KEEP_AUDIO_FILES
            removed = 0
            for mtime, path in files:
                if removed >= excess:
                    break
                # 跳过2分钟内生成的文件（可能正在播放）
                if now - mtime < 120:
                    continue
                try:
                    os.remove(path)
                    removed += 1
                except OSError:
                    pass
        except Exception:
            pass

    def cleanup(self):
        """清理资源（须在播报线程退出后调用）"""
        with self._lock:
            # 停止持久事件循环
            if self._loop is not None:
                try:
                    self._loop.call_soon_threadsafe(self._loop.stop)
                except Exception:
                    pass
            if self._loop_thread and self._loop_thread.is_alive():
                self._loop_thread.join(timeout=2)
            if not self._mixer_ready:
                return
            try:
                pygame.mixer.quit()
            except Exception:
                pass
            self._mixer_ready = False
