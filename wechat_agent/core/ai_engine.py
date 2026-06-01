"""
AI 引擎模块 - 封装 Ollama API
"""
import json
import time
from typing import List, Optional, Generator

import requests

from config.settings import settings
from utils.logger import logger


class MessageRole:
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class AIEngine:
    """AI 引擎类"""

    def __init__(self):
        self.base_url = settings.get("ollama.base_url", "http://localhost:11434")
        self.model = settings.get("ollama.model", "qwen2.5")
        self.timeout = settings.get("ollama.timeout", 30)
        self.max_context = settings.get("ai.max_context_messages", 20)
        self.temperature = settings.get("ai.temperature", 0.7)
        self._check_connection()

    def _check_connection(self):
        """检查 Ollama 连接"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                logger.info(f"Ollama 连接成功，可用模型: {model_names}")
                if self.model not in model_names:
                    logger.warning(f"配置的模型 {self.model} 不在可用列表中")
            else:
                logger.warning(f"Ollama 响应异常: {response.status_code}")
        except Exception as e:
            logger.error(f"Ollama 连接失败: {e}")

    def _build_messages(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        context: Optional[List[dict]] = None
    ) -> List[dict]:
        """构建消息列表"""
        messages = []

        # 系统提示词
        if system_prompt:
            messages.append({
                "role": MessageRole.SYSTEM,
                "content": system_prompt
            })

        # 历史上下文（限制数量）
        if context:
            # 取最近的 max_context 条消息
            recent_context = context[-self.max_context:] if len(context) > self.max_context else context
            for msg in recent_context:
                if msg.get("role") in [MessageRole.USER, MessageRole.ASSISTANT]:
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })

        # 当前用户消息
        messages.append({
            "role": MessageRole.USER,
            "content": user_message
        })

        return messages

    def generate(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        context: Optional[List[dict]] = None,
        stream: bool = False
    ) -> str:
        """生成 AI 回复"""
        default_prompt = settings.get("ai.default_system_prompt", "你是一个友好的助手。")
        system_prompt = system_prompt or default_prompt

        messages = self._build_messages(message, system_prompt, context)

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": self.temperature,
            }
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
                stream=stream
            )

            if response.status_code == 200:
                if stream:
                    # 流式响应
                    def generate_stream():
                        for line in response.iter_lines():
                            if line:
                                try:
                                    data = json.loads(line)
                                    if "message" in data:
                                        content = data["message"].get("content", "")
                                        if content:
                                            yield content
                                    if data.get("done", False):
                                        break
                                except json.JSONDecodeError:
                                    continue
                    return generate_stream()
                else:
                    # 非流式响应
                    result = response.json()
                    return result.get("message", {}).get("content", "")
            else:
                logger.error(f"Ollama API 错误: {response.status_code}")
                return "抱歉，AI 服务暂时不可用。"

        except requests.Timeout:
            logger.error("Ollama 请求超时")
            return "抱歉，AI 响应超时。"
        except Exception as e:
            logger.error(f"Ollama 请求异常: {e}")
            return "抱歉，AI 服务出现错误。"

    def generate_stream(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        context: Optional[List[dict]] = None
    ) -> Generator[str, None, None]:
        """生成流式 AI 回复"""
        default_prompt = settings.get("ai.default_system_prompt", "你是一个友好的助手。")
        system_prompt = system_prompt or default_prompt

        messages = self._build_messages(message, system_prompt, context)

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": self.temperature,
            }
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
                stream=True
            )

            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if "message" in data:
                                content = data["message"].get("content", "")
                                if content:
                                    yield content
                            if data.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue
            else:
                logger.error(f"Ollama API 错误: {response.status_code}")
                yield "抱歉，AI 服务暂时不可用。"

        except requests.Timeout:
            logger.error("Ollama 请求超时")
            yield "抱歉，AI 响应超时。"
        except Exception as e:
            logger.error(f"Ollama 请求异常: {e}")
            yield "抱歉，AI 服务出现错误。"

    def set_model(self, model: str):
        """设置使用的模型"""
        self.model = model
        logger.info(f"切换模型为: {model}")

    def get_models(self) -> List[str]:
        """获取可用模型列表"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                return [m.get("name", "") for m in models]
        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
        return []

    def test_connection(self) -> bool:
        """测试连接"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False


# 全局 AI 引擎实例
ai_engine = AIEngine()
