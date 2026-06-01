"""
配置管理模块
"""
import json
import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT  # 数据直接存在项目根目录
CONFIG_FILE = PROJECT_ROOT / "config" / "settings.json"
DEFAULT_CONFIG_FILE = PROJECT_ROOT / "config" / "settings.default.json"


class Settings:
    """配置管理类"""

    def __init__(self):
        self._config: dict[str, Any] = {}
        self.load()

    def load(self):
        """加载配置文件"""
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                self._config = json.load(f)
        else:
            self._config = self._get_default_config()
            self.save()

    def save(self):
        """保存配置文件"""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self._config, f, ensure_ascii=False, indent=2)

    def _get_default_config(self) -> dict[str, Any]:
        """获取默认配置"""
        return {
            "web": {
                "host": "127.0.0.1",
                "port": 5001,
                "debug": False
            },
            "ollama": {
                "base_url": "http://localhost:11434",
                "model": "qwen2.5",
                "timeout": 30
            },
            "ai": {
                "max_context_messages": 20,
                "temperature": 0.7,
                "default_system_prompt": "你是一个友好的助手，请用自然的语言回复消息。"
            },
            "wechat": {
                "auto_reply": True,
                "whitelist_only": True
            },
            "logging": {
                "level": "INFO",  # DEBUG, INFO, WARNING, ERROR
                "max_file_size": 10 * 1024 * 1024,  # 10MB
                "backup_count": 5
            },
            "style_learning": {
                "enabled": True,
                "sample_messages": 50  # 从聊天记录中提取的样本数量
            },
            "storage": {
                "max_db_size": 100 * 1024 * 1024,  # 数据库最大 100MB
                "max_messages_per_contact": 1000,  # 每个联系人最多保存 1000 条消息
                "max_context_tokens": 4000,  # AI 上下文最大 token 数估算
                "auto_cleanup": True,  # 自动清理旧数据
                "cleanup_days": 30  # 清理 30 天前的消息
            }
        }

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，支持点号分隔的路径"""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def set(self, key: str, value: Any):
        """设置配置值，支持点号分隔的路径"""
        keys = key.split(".")
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
        self.save()

    def get_all(self) -> dict[str, Any]:
        """获取所有配置"""
        return self._config.copy()

    def update(self, config: dict[str, Any]):
        """更新配置"""
        def deep_update(base: dict, update: dict):
            for k, v in update.items():
                if isinstance(v, dict) and isinstance(base.get(k), dict):
                    deep_update(base[k], v)
                else:
                    base[k] = v

        deep_update(self._config, config)
        self.save()


# 全局配置实例
settings = Settings()
