"""
日志工具模块
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Windows 控制台 UTF-8 设置
if sys.platform == "win32":
    import ctypes
    try:
        # 设置控制台代码页为 UTF-8 (65001)
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except:
        pass

from config.settings import settings


class Logger:
    """日志管理类"""

    _loggers = {}

    @classmethod
    def get_logger(cls, name: str = "wechat_custody") -> logging.Logger:
        """获取日志记录器"""
        if name in cls._loggers:
            return cls._loggers[name]

        logger = logging.getLogger(name)
        logger.setLevel(settings.get("logging.level", "INFO"))

        # 清除已有的处理器
        logger.handlers.clear()

        # 日志格式
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # 控制台处理器 - 修复 Windows 中文乱码
        # 重新配置 stdout 使用 UTF-8 编码
        if sys.platform == "win32":
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 文件处理器 - 日志保存在项目根目录
        log_dir = Path(__file__).parent.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{name}.log"

        max_bytes = settings.get("logging.max_file_size", 10 * 1024 * 1024)
        backup_count = settings.get("logging.backup_count", 5)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        cls._loggers[name] = logger
        return logger


# 默认日志记录器
logger = Logger.get_logger()
