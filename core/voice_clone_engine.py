"""声音复刻引擎 - 调用GPT-SoVITS本地API"""
import os
import time
import json
import wave
import subprocess
import threading
import requests
from typing import Optional
from pathlib import Path

from core import app_logger


# GPT-SoVITS 默认配置
GPTSOVITS_DIR = r"D:\project\GPT-SoVITS"
GPTSOVITS_API_PORT = 9880
GPTSOVITS_API_URL = f"http://127.0.0.1:{GPTSOVITS_API_PORT}"
AI_ENV_PYTHON = r"D:\project\ai-env\Scripts\python.exe"


class VoiceCloneEngine:
    """
    声音复刻引擎
    
    通过GPT-SoVITS的HTTP API实现：
    - zero-shot语音克隆（参考音频+目标文字→克隆音色音频）
    - 管理GPT-SoVITS服务进程
    """

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._running = False
        self._ref_audio_path = ""  # 参考音频路径
        self._ref_text = ""  # 参考音频对应文字
        self._output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "output_audio", "cloned"
        )
        os.makedirs(self._output_dir, exist_ok=True)

    @property
    def is_running(self) -> bool:
        """GPT-SoVITS服务是否在运行"""
        if self._process is None:
            return False
        return self._process.poll() is None

    @property
    def has_reference(self) -> bool:
        """是否已设置有效的参考音频"""
        return bool(self._ref_audio_path) and os.path.exists(self._ref_audio_path)

    def start_service(self) -> bool:
        """
        启动GPT-SoVITS API服务
        
        Returns:
            是否启动成功
        """
        if self.is_running:
            return True

        api_script = os.path.join(GPTSOVITS_DIR, "api_v2.py")
        if not os.path.exists(api_script):
            # 尝试旧版API
            api_script = os.path.join(GPTSOVITS_DIR, "api.py")

        if not os.path.exists(api_script):
            raise FileNotFoundError(
                f"找不到GPT-SoVITS API脚本: {api_script}\n"
                f"请确认GPT-SoVITS已正确安装到 {GPTSOVITS_DIR}"
            )

        try:
            # 使用ai-env虚拟环境启动
            cmd = [
                AI_ENV_PYTHON,
                api_script,
                "-a", "127.0.0.1",
                "-p", str(GPTSOVITS_API_PORT),
            ]

            self._process = subprocess.Popen(
                cmd,
                cwd=GPTSOVITS_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            # 等待服务启动
            for _ in range(30):
                time.sleep(1)
                if self._check_service():
                    self._running = True
                    return True
                if self._process.poll() is not None:
                    break

            return False

        except Exception as e:
            raise RuntimeError(f"启动GPT-SoVITS服务失败: {str(e)}")

    def stop_service(self):
        """停止GPT-SoVITS服务"""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None
        self._running = False

    def _check_service(self) -> bool:
        """检查服务是否可用"""
        try:
            resp = requests.get(f"{GPTSOVITS_API_URL}/", timeout=2)
            # 任何响应（包括404）都说明服务在运行
            return True
        except requests.exceptions.ConnectionError:
            return False
        except Exception:
            return False

    def set_reference_audio(self, audio_path: str, ref_text: str = ""):
        """
        设置参考音频（用于声音克隆）
        
        Args:
            audio_path: 参考音频文件路径（WAV/MP3，3-10秒）
            ref_text: 参考音频中说的文字（可选，提高克隆质量）
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"参考音频不存在: {audio_path}")

        # 校验音频时长（GPT-SoVITS要求参考音频在3~10秒之间）
        duration = self._get_audio_duration(audio_path)
        if duration is not None:
            if duration < 3:
                raise ValueError(
                    f"参考音频时长仅{duration:.1f}秒，太短了。\n"
                    f"GPT-SoVITS要求参考音频在3~10秒之间，请重新录制5-10秒的清晰语音。"
                )
            if duration > 15:
                raise ValueError(
                    f"参考音频时长{duration:.1f}秒，太长了。\n"
                    f"GPT-SoVITS要求参考音频在3~10秒之间，请截取其中5-10秒的清晰片段。"
                )

        self._ref_audio_path = audio_path
        self._ref_text = ref_text

    @staticmethod
    def _get_audio_duration(audio_path: str):
        """获取音频时长（秒），无法解析时返回None"""
        ext = Path(audio_path).suffix.lower()
        if ext == ".wav":
            try:
                with wave.open(audio_path) as wf:
                    return wf.getnframes() / wf.getframerate()
            except Exception:
                pass
        try:
            import miniaudio
            info = miniaudio.get_file_info(audio_path)
            return info.duration
        except Exception:
            return None

    def synthesize(self, text: str, output_path: str = None,
                   speed: float = 1.0, language: str = "zh") -> str:
        """
        使用克隆音色合成语音
        
        Args:
            text: 要合成的文字
            output_path: 输出文件路径（默认自动生成）
            speed: 语速（1.0为正常）
            language: 语言（zh/en/ja）
            
        Returns:
            生成的音频文件路径
        """
        if not self._ref_audio_path:
            raise ValueError("请先设置参考音频: set_reference_audio()")

        if not self.is_running:
            if not self.start_service():
                raise RuntimeError("GPT-SoVITS服务未启动")

        if output_path is None:
            output_path = os.path.join(
                self._output_dir,
                f"clone_{int(time.time() * 1000)}.wav"
            )

        # 调用GPT-SoVITS API
        payload = {
            "text": text,
            "text_lang": language,
            "ref_audio_path": self._ref_audio_path,
            "prompt_text": self._ref_text,
            "prompt_lang": language,
            "speed_factor": speed,
            "streaming_mode": False,
        }

        try:
            resp = requests.post(
                f"{GPTSOVITS_API_URL}/tts",
                json=payload,
                timeout=60,
            )

            if resp.status_code == 200:
                # 返回的是音频数据
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                return output_path
            else:
                error_msg = resp.text
                app_logger.log_error("GPT-SoVITS合成失败: " + error_msg[:200])
                # 解析常见错误，给出友好提示
                hint = ""
                if "参考音频" in error_msg or "3~" in error_msg or "3s" in error_msg.lower():
                    hint = "\n\n可能原因：参考音频时长不符合要求（3~10秒），请重新录制。"
                raise RuntimeError(f"GPT-SoVITS合成失败: {error_msg}{hint}")

        except requests.exceptions.ConnectionError:
            raise RuntimeError("无法连接GPT-SoVITS服务，请确认服务已启动")
        except requests.exceptions.Timeout:
            raise RuntimeError("GPT-SoVITS合成超时（文本可能过长）")

    def synthesize_to_file(self, text: str, output_path: str = None) -> str:
        """简化接口：文字→克隆音频文件"""
        return self.synthesize(text, output_path)

    def test_connection(self) -> tuple:
        """
        测试服务连接
        
        Returns:
            (success: bool, message: str)
        """
        if not os.path.exists(GPTSOVITS_DIR):
            return False, f"GPT-SoVITS目录不存在: {GPTSOVITS_DIR}"

        if self.is_running:
            if self._check_service():
                return True, "服务运行中"
            else:
                return False, "进程存在但API无响应"
        else:
            return False, "服务未启动"

    def get_voice_samples(self) -> list:
        """获取已有的声音样本列表"""
        samples_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "voice_samples"
        )
        if not os.path.exists(samples_dir):
            return []

        supported_ext = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
        samples = []
        for f in os.listdir(samples_dir):
            if Path(f).suffix.lower() in supported_ext:
                samples.append({
                    "name": f,
                    "path": os.path.join(samples_dir, f),
                    "size": os.path.getsize(os.path.join(samples_dir, f)),
                })
        return samples

    def cleanup(self):
        """清理资源"""
        self.stop_service()
