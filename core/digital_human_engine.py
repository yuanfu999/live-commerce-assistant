"""数字人引擎 - 调用MuseTalk实现实时口型驱动"""
import os
import time
import shutil
import subprocess
import threading
import queue
import tempfile
import numpy as np
from typing import Optional, Callable
from pathlib import Path

from core import app_logger


# MuseTalk 默认配置
MUSETALK_DIR = r"D:\project\MuseTalk"
AI_ENV_PYTHON = r"D:\project\ai-env\Scripts\python.exe"
FFMPEG_PATH = r"D:\ffmpeg\bin\ffmpeg.exe"
FFMPEG_DIR = r"D:\ffmpeg\bin"

# MuseTalk 模型路径（相对于MUSETALK_DIR）
UNET_MODEL_PATH = "./models/musetalk/pytorch_model.bin"
UNET_CONFIG_PATH = "./models/musetalk/musetalk.json"
MUSETALK_VERSION = "v1"


class DigitalHumanEngine:
    """
    数字人引擎
    
    通过MuseTalk实现：
    - 输入：源视频/图片 + 音频 → 输出：口型驱动的视频帧
    - 支持实时模式（虚拟摄像头输出）和离线模式（生成视频文件）
    """

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._running = False
        self._source_video = ""  # 源视频路径
        self._output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "digital_human", "output"
        )
        os.makedirs(self._output_dir, exist_ok=True)

        # 实时模式相关
        self._frame_queue = queue.Queue(maxsize=10)
        self._audio_queue = queue.Queue(maxsize=5)
        self._virtual_cam = None
        self._render_thread: Optional[threading.Thread] = None

        # 配置
        self.resolution = (1280, 720)  # 输出分辨率
        self.fps = 25  # 帧率
        self.use_virtual_camera = True

    @property
    def is_running(self) -> bool:
        """引擎是否在运行"""
        return self._running

    def set_source_video(self, video_path: str):
        """
        设置源视频（真人出镜视频）
        
        Args:
            video_path: 视频文件路径（建议720p，正面，光线均匀）
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"源视频不存在: {video_path}")
        
        # 验证是否为视频文件
        supported_ext = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
        if Path(video_path).suffix.lower() not in supported_ext:
            raise ValueError(f"不支持的视频格式，支持: {supported_ext}")
        
        self._source_video = video_path

    @staticmethod
    def _ensure_ascii_path(file_path: str, tmp_copies: list, prefix: str) -> str:
        """
        确保文件路径为纯ASCII（OpenCV在Windows下无法读取中文路径）。
        若路径含非ASCII字符，复制到临时目录并返回新路径；否则原样返回。
        """
        try:
            file_path.encode("ascii")
            return file_path  # 纯ASCII路径，无需处理
        except UnicodeEncodeError:
            pass
        ext = Path(file_path).suffix
        tmp_dir = tempfile.mkdtemp(prefix="dh_")
        tmp_path = os.path.join(tmp_dir, f"{prefix}_{int(time.time() * 1000)}{ext}")
        shutil.copy2(file_path, tmp_path)
        tmp_copies.append(tmp_path)
        tmp_copies.append(tmp_dir)  # 目录也记录下来以便清理
        return tmp_path

    def generate_video(self, audio_path: str, output_path: str = None,
                       bbox_shift: int = 0) -> str:
        """
        离线模式：音频 + 源视频 → 生成说话视频
        
        Args:
            audio_path: 驱动音频路径（WAV/MP3）
            output_path: 输出视频路径（默认自动生成）
            bbox_shift: 人脸框偏移量（负值向下，正值向上）
            
        Returns:
            生成的视频文件路径
        """
        if not self._source_video:
            raise ValueError("请先设置源视频: set_source_video()")
        
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        if output_path is None:
            output_path = os.path.join(
                self._output_dir,
                f"dh_{int(time.time() * 1000)}.mp4"
            )

        # 创建临时YAML配置文件（MuseTalk使用YAML配置指定输入）
        task_name = f"task_{int(time.time())}"

        # MuseTalk内部使用cv2读取视频，Windows下cv2不支持中文路径，
        # 因此将含非ASCII字符的输入文件复制到纯英文临时路径
        tmp_copies = []  # 记录临时文件以便清理
        video_for_task = self._ensure_ascii_path(self._source_video, tmp_copies, "src_video")
        audio_for_task = self._ensure_ascii_path(audio_path, tmp_copies, "src_audio")

        config_content = f"""{task_name}:
  video_path: "{video_for_task.replace(os.sep, '/')}"
  audio_path: "{audio_for_task.replace(os.sep, '/')}"
  bbox_shift: {bbox_shift}
"""
        # 写入临时配置
        config_dir = os.path.join(MUSETALK_DIR, "configs", "inference")
        os.makedirs(config_dir, exist_ok=True)
        config_file = os.path.join(config_dir, f"_tmp_{task_name}.yaml")
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(config_content)

        # 结果目录
        result_dir = os.path.join(self._output_dir, "musetalk_results")
        os.makedirs(result_dir, exist_ok=True)

        # 构建命令（与验证通过的命令格式一致）
        cmd = [
            AI_ENV_PYTHON, "-m", "scripts.inference",
            "--inference_config", config_file,
            "--result_dir", result_dir,
            "--unet_model_path", UNET_MODEL_PATH,
            "--unet_config", UNET_CONFIG_PATH,
            "--version", MUSETALK_VERSION,
        ]

        # 设置环境变量（确保ffmpeg可用）
        env = os.environ.copy()
        env["PATH"] = FFMPEG_DIR + os.pathsep + env.get("PATH", "")

        try:
            result = subprocess.run(
                cmd,
                cwd=MUSETALK_DIR,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,  # 10分钟超时
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "未知错误"
                app_logger.log_error("MuseTalk推理失败: " + error_msg[-300:])
                raise RuntimeError(f"MuseTalk推理失败:\n{error_msg[-500:]}")

            # 查找生成的视频文件
            # MuseTalk输出格式: result_dir/v1/<video_name>_<audio_name>.mp4
            video_stem = Path(self._source_video).stem
            audio_stem = Path(audio_path).stem
            expected_name = f"{video_stem}_{audio_stem}.mp4"
            expected_path = os.path.join(
                result_dir, MUSETALK_VERSION, expected_name
            )

            if os.path.exists(expected_path):
                # 移动到目标路径
                shutil.move(expected_path, output_path)
                return output_path
            else:
                # 搜索result_dir中的mp4文件
                for root, dirs, files in os.walk(result_dir):
                    for fname in files:
                        if fname.endswith(".mp4") and not fname.startswith("temp_"):
                            found = os.path.join(root, fname)
                            shutil.move(found, output_path)
                            return output_path
                # 推理"成功"但无输出，通常是人脸检测失败
                stdout_tail = (result.stdout or "")[-400:]
                stderr_tail = (result.stderr or "")[-200:]
                app_logger.log_error(
                    "MuseTalk未产出视频。stdout: " + stdout_tail + " stderr: " + stderr_tail
                )
                hint = ""
                if "NoneType" in stdout_tail or "NoneType" in stderr_tail:
                    hint = ("\n\n可能原因：源视频中未检测到人脸。\n"
                            "请确认源视频为正面出镜、光线均匀、人脸清晰可见的视频。")
                raise RuntimeError(
                    f"MuseTalk推理完成但未找到输出视频{hint}\n"
                    f"stdout: {stdout_tail}"
                )

        except subprocess.TimeoutExpired:
            app_logger.log_error("MuseTalk推理超时（600秒）")
            raise RuntimeError("MuseTalk推理超时（视频可能过长）")
        except FileNotFoundError:
            raise RuntimeError(
                f"找不到MuseTalk或Python环境\n"
                f"Python: {AI_ENV_PYTHON}\n"
                f"MuseTalk: {MUSETALK_DIR}"
            )
        finally:
            # 清理临时配置和临时复制的输入文件
            if os.path.exists(config_file):
                os.remove(config_file)
            for tmp_path in tmp_copies:
                try:
                    if os.path.isfile(tmp_path):
                        os.remove(tmp_path)
                    elif os.path.isdir(tmp_path):
                        os.rmdir(tmp_path)
                except OSError:
                    pass

    def start_realtime(self, audio_stream_callback: Callable = None):
        """
        启动实时模式（用于直播）
        
        Args:
            audio_stream_callback: 音频流回调，返回音频chunk
        """
        if self._running:
            return

        if not self._source_video:
            raise ValueError("请先设置源视频")

        self._running = True

        # 启动渲染线程
        self._render_thread = threading.Thread(
            target=self._realtime_render_loop,
            args=(audio_stream_callback,),
            daemon=True
        )
        self._render_thread.start()

    def stop_realtime(self):
        """停止实时模式"""
        self._running = False
        if self._render_thread:
            self._render_thread.join(timeout=5)
            self._render_thread = None
        self._close_virtual_camera()

    def _realtime_render_loop(self, audio_callback):
        """实时渲染循环"""
        try:
            # 初始化虚拟摄像头
            if self.use_virtual_camera:
                self._init_virtual_camera()

            # 使用MuseTalk的实时推理模式 (scripts/realtime_inference.py)
            realtime_script = os.path.join(MUSETALK_DIR, "scripts", "realtime_inference.py")

            if os.path.exists(realtime_script):
                # 创建实时推理配置
                audio_path = self._get_next_audio()
                config_content = (
                    f"avatar_live:\n"
                    f"  preparation: True\n"
                    f"  bbox_shift: 0\n"
                    f'  video_path: "{self._source_video.replace(os.sep, "/")}"\n'
                    f"  audio_clips:\n"
                    f'    audio_0: "{audio_path.replace(os.sep, "/")}"\n'
                )
                config_file = os.path.join(
                    MUSETALK_DIR, "configs", "inference", "_tmp_realtime.yaml"
                )
                with open(config_file, "w", encoding="utf-8") as f:
                    f.write(config_content)

                # 通过子进程运行实时推理
                cmd = [
                    AI_ENV_PYTHON, "-m", "scripts.realtime_inference",
                    "--inference_config", config_file,
                    "--unet_model_path", UNET_MODEL_PATH,
                    "--unet_config", UNET_CONFIG_PATH,
                    "--whisper_dir", "./models/whisper",
                    "--ffmpeg_path", FFMPEG_DIR,
                    "--version", MUSETALK_VERSION,
                    "--fps", str(self.fps),
                    "--batch_size", "10",
                    "--result_dir", os.path.join(self._output_dir, "realtime"),
                ]

                env = os.environ.copy()
                env["PATH"] = FFMPEG_DIR + os.pathsep + env.get("PATH", "")

                self._process = subprocess.Popen(
                    cmd,
                    cwd=MUSETALK_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )

                # 等待进程结束
                while self._running and self._process.poll() is None:
                    time.sleep(0.1)
            else:
                # 降级方案：循环播放源视频 + 音频驱动
                self._fallback_render_loop(audio_callback)

        except Exception as e:
            print(f"实时渲染错误: {e}")
        finally:
            self._running = False

    def _get_next_audio(self) -> str:
        """获取下一个待播放的音频文件"""
        try:
            return self._audio_queue.get(timeout=5)
        except queue.Empty:
            return ""

    def _fallback_render_loop(self, audio_callback):
        """降级渲染方案：使用OpenCV读取源视频帧"""
        try:
            import cv2
            cap = cv2.VideoCapture(self._source_video)
            if not cap.isOpened():
                return

            frame_delay = 1.0 / self.fps
            while self._running:
                ret, frame = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                # 推送到虚拟摄像头
                if self._virtual_cam:
                    self._virtual_cam.send(frame)

                time.sleep(frame_delay)

            cap.release()
        except ImportError:
            pass

    def _init_virtual_camera(self):
        """初始化虚拟摄像头"""
        try:
            import pyvirtualcam
            self._virtual_cam = pyvirtualcam.Camera(
                width=self.resolution[0],
                height=self.resolution[1],
                fps=self.fps,
                device="OBS Virtual Camera",
            )
        except Exception:
            try:
                import pyvirtualcam
                self._virtual_cam = pyvirtualcam.Camera(
                    width=self.resolution[0],
                    height=self.resolution[1],
                    fps=self.fps,
                )
            except Exception as e:
                print(f"虚拟摄像头初始化失败: {e}")
                self._virtual_cam = None

    def _close_virtual_camera(self):
        """关闭虚拟摄像头"""
        if self._virtual_cam:
            try:
                self._virtual_cam.close()
            except Exception:
                pass
            self._virtual_cam = None

    def push_audio_chunk(self, audio_path: str):
        """
        推送一段音频到实时渲染队列
        
        Args:
            audio_path: 音频文件路径
        """
        if self._running:
            self._audio_queue.put(audio_path)

    def get_source_videos(self) -> list:
        """获取已有的源视频列表"""
        source_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "digital_human", "source_video"
        )
        if not os.path.exists(source_dir):
            return []

        supported_ext = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
        videos = []
        for f in os.listdir(source_dir):
            if Path(f).suffix.lower() in supported_ext:
                full_path = os.path.join(source_dir, f)
                videos.append({
                    "name": f,
                    "path": full_path,
                    "size": os.path.getsize(full_path),
                })
        return videos

    def test_environment(self) -> tuple:
        """
        测试环境是否就绪
        
        Returns:
            (success: bool, message: str)
        """
        issues = []

        if not os.path.exists(AI_ENV_PYTHON):
            issues.append(f"Python环境不存在: {AI_ENV_PYTHON}")

        if not os.path.exists(MUSETALK_DIR):
            issues.append(f"MuseTalk目录不存在: {MUSETALK_DIR}")

        if not os.path.exists(FFMPEG_PATH):
            issues.append(f"FFmpeg不存在: {FFMPEG_PATH}")

        if not self._source_video:
            issues.append("未设置源视频")

        if issues:
            return False, "\n".join(issues)
        return True, "环境就绪"

    def cleanup(self):
        """清理资源"""
        self.stop_realtime()
        if self._process and self._process.poll() is None:
            self._process.terminate()
