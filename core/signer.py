"""抖音直播 wss signature 生成器。

抖音直播弹幕 WebSocket 现在要求 URL 携带 signature 参数，否则握手被拒绝
（返回 200 Invalid response status）。签名算法参照官方 webmssdk：
    1) 从 wss URL 的 query 中按固定参数列表取值，拼成 "k=v,k=v,..." 字符串
    2) 对该字符串取 md5（hex）
    3) 用 webmssdk 的 sign.js 执行 get_sign(md5) 得到 signature

由于 execjs / py_mini_racer 未安装，这里通过本地 Node.js 执行 sign.js。
"""
import os
import hashlib
import subprocess
import urllib.parse
from core import app_logger

# 参与签名的固定参数列表（顺序不可变）
_SIGN_PARAMS = (
    "live_id,aid,version_code,webcast_sdk_version,"
    "room_id,sub_room_id,sub_channel_id,did_rule,"
    "user_unique_id,device_platform,device_type,ac,"
    "identity"
).split(",")

_JS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "js")
_SIGN_RUNNER = os.path.join(_JS_DIR, "sign_runner.js")

# 缓存 node 可执行文件探测结果
_node_exe_cache = None
_node_checked = False


def _find_node():
    """探测本机可用的 node 可执行文件路径，找不到返回 None（结果缓存）。"""
    global _node_exe_cache, _node_checked
    if _node_checked:
        return _node_exe_cache
    _node_checked = True
    for exe in ("node", "node.exe"):
        try:
            r = subprocess.run(
                [exe, "--version"],
                capture_output=True, text=True, timeout=8,
                creationflags=_no_window_flag(),
            )
            if r.returncode == 0:
                _node_exe_cache = exe
                return exe
        except Exception:
            continue
    _node_exe_cache = None
    return None


def _no_window_flag():
    """Windows 下隐藏子进程控制台窗口。"""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _compute_md5_param(wss_url: str) -> str:
    """从 wss URL 提取签名参数并计算 md5(hex)。"""
    query = urllib.parse.urlparse(wss_url).query
    wss_maps = {}
    for pair in query.split("&"):
        if not pair:
            continue
        k, _, v = pair.partition("=")
        wss_maps[k] = v
    tpl = [f"{k}={wss_maps.get(k, '')}" for k in _SIGN_PARAMS]
    param = ",".join(tpl)
    return hashlib.md5(param.encode()).hexdigest()


def generate_signature(wss_url: str) -> str:
    """为给定 wss URL 生成 signature。失败时返回空字符串（调用方可降级）。"""
    node = _find_node()
    if not node:
        app_logger.log_error("未检测到 Node.js，无法生成 wss 签名（请安装 Node.js）")
        return ""
    if not os.path.exists(_SIGN_RUNNER):
        app_logger.log_error("缺少签名脚本 sign_runner.js")
        return ""
    try:
        md5_param = _compute_md5_param(wss_url)
        r = subprocess.run(
            [node, _SIGN_RUNNER, md5_param],
            capture_output=True, text=True, timeout=20,
            creationflags=_no_window_flag(),
        )
        if r.returncode != 0:
            app_logger.log_error("签名脚本执行失败: " + (r.stderr or "").strip())
            return ""
        sig = (r.stdout or "").strip()
        if not sig or sig.lower() == "undefined":
            app_logger.log_error("签名结果为空")
            return ""
        return sig
    except Exception as e:
        app_logger.log_error("生成 wss 签名异常: " + str(e))
        return ""
