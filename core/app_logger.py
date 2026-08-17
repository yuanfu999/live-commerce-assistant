"""全局运行日志 - 写入文件（自动轮转）+ 内存缓冲，供日志面板查看/导出"""
import os
import logging
from logging.handlers import RotatingFileHandler
from collections import deque
from datetime import datetime

# 日志目录（项目根目录/logs）
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(APP_DIR, "logs")
LOG_PATH = os.path.join(LOG_DIR, "app.log")
ERROR_LOG_PATH = os.path.join(LOG_DIR, "error.log")  # 仅错误日志，便于快速排查问题

# 内存缓冲（最近2000条，供日志面板实时显示）
_memory_buffer = deque(maxlen=2000)

_logger = None


def setup_logger() -> logging.Logger:
    """初始化全局日志器（只执行一次）"""
    global _logger
    if _logger is not None:
        return _logger

    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger("live_assistant")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 文件输出（单个最大2MB，保留3个备份，防止无限膨胀）
    try:
        file_handler = RotatingFileHandler(
            LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except Exception:
        pass  # 文件不可写时仅用内存缓冲

    # 错误专用日志文件（仅记录ERROR及以上级别，出问题时可优先查看）
    try:
        error_handler = RotatingFileHandler(
            ERROR_LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(fmt)
        logger.addHandler(error_handler)
    except Exception:
        pass

    _logger = logger
    return logger


def _record(level: str, msg: str):
    """记录一条日志到文件+内存缓冲"""
    logger = setup_logger()
    line = f"{datetime.now().strftime('%H:%M:%S')} [{level}] {msg}"
    _memory_buffer.append(line)
    try:
        if level == "ERROR":
            logger.error(msg)
        elif level == "WARN":
            logger.warning(msg)
        else:
            logger.info(msg)
    except Exception:
        pass


def log_info(msg: str):
    _record("INFO", msg)


def log_warn(msg: str):
    _record("WARN", msg)


def log_error(msg: str):
    _record("ERROR", msg)


def get_recent_logs(limit: int = 500) -> list:
    """获取最近的日志行（内存缓冲）"""
    return list(_memory_buffer)[-limit:]


def get_log_file_path() -> str:
    """日志文件路径（用于导出）"""
    return LOG_PATH


def get_error_log_file_path() -> str:
    """错误日志文件路径（用于导出）"""
    return ERROR_LOG_PATH
