"""
DEEPSEEK API 客户端
提供意图解析、结果润色、流式文本生成功能
"""
import os
import json
import logging
from typing import AsyncIterator, Optional, Dict, Any
import httpx
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

logger = logging.getLogger(__name__)


# 从环境变量获取 API Key
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_KEY_2 = os.getenv("DEEPSEEK_API_KEY_2", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"


class LLMClientError(Exception):
    """LLM 客户端错误"""
    pass


class LLMClient:
    """DEEPSEEK API 客户端"""

    def __init__(self, api_key: str = ""):
        """
        初始化 LLM 客户端

        Args:
            api_key: DEEPSEEK API Key，如果不提供则从环境变量读取
        """
        self.api_key = api_key or DEEPSEEK_API_KEY
        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY 未设置，LLM 功能将不可用")

    def _is_available(self) -> bool:
        """检查 API 是否可用"""
        return bool(self.api_key)

    async def achat(
        self,
        messages: list,
        model: str = "deepseek-chat",
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """
        异步聊天请求

        Args:
            messages: 消息列表
            model: 模型名称
            stream: 是否流式返回
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            响应文本

        Raises:
            LLMClientError: API 调用失败
        """
        if not self._is_available():
            raise LLMClientError("DEEPSEEK_API_KEY 未配置")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    DEEPSEEK_API_URL,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()

                data = response.json()
                return data["choices"][0]["message"]["content"]

        except httpx.HTTPStatusError as e:
            logger.error(f"DEEPSEEK API HTTP 错误: {e.response.status_code}")
            raise LLMClientError(f"API 调用失败: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"DEEPSEEK API 请求错误: {e}")
            raise LLMClientError(f"网络请求失败: {e}")
        except (KeyError, IndexError) as e:
            logger.error(f"DEEPSEEK API 响应解析失败: {e}")
            raise LLMClientError("API 响应格式错误")

    async def achat_stream(
        self,
        messages: list,
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> AsyncIterator[str]:
        """
        异步流式聊天请求

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数

        Yields:
            文本片段

        Raises:
            LLMClientError: API 调用失败
        """
        if not self._is_available():
            raise LLMClientError("DEEPSEEK_API_KEY 未配置")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    DEEPSEEK_API_URL,
                    headers=headers,
                    json=payload
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue

                        data_str = line[6:]  # 去掉 "data: " 前缀

                        if data_str == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue

        except httpx.HTTPStatusError as e:
            logger.error(f"DEEPSEEK API HTTP 错误: {e.response.status_code}")
            raise LLMClientError(f"API 调用失败: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"DEEPSEEK API 请求错误: {e}")
            raise LLMClientError(f"网络请求失败: {e}")

    def chat(
        self,
        messages: list,
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """
        同步聊天请求（兼容异步环境）

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            响应文本
        """
        import asyncio

        try:
            # 尝试获取现有事件循环
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果循环正在运行，创建新任务并等待
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.achat(messages, model, False, temperature, max_tokens)
                    )
                    return future.result()
            else:
                # 循环未运行，直接使用
                return loop.run_until_complete(
                    self.achat(messages, model, False, temperature, max_tokens)
                )
        except RuntimeError:
            # 没有事件循环，创建新的
            return asyncio.run(
                self.achat(messages, model, False, temperature, max_tokens)
            )


# 全局单例客户端
_planner_client: Optional[LLMClient] = None
_advisor_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """获取全局 LLM 客户端单例（兼容旧代码，等同 get_planner_client）"""
    return get_planner_client()


def get_planner_client() -> LLMClient:
    """获取 Agent1（规划调度器）专用的 LLM 客户端"""
    global _planner_client
    if _planner_client is None:
        _planner_client = LLMClient(DEEPSEEK_API_KEY)
    return _planner_client


def get_advisor_client() -> LLMClient:
    """获取 Agent2（分析顾问）专用的 LLM 客户端"""
    global _advisor_client
    if _advisor_client is None:
        key = DEEPSEEK_API_KEY_2 or DEEPSEEK_API_KEY
        if not DEEPSEEK_API_KEY_2:
            logger.warning("DEEPSEEK_API_KEY_2 未设置，Agent2 将回退使用 DEEPSEEK_API_KEY")
        _advisor_client = LLMClient(key)
    return _advisor_client
