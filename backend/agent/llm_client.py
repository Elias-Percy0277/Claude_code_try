"""
DEEPSEEK API 客户端

模块职责：
- 封装与 DeepSeek（兼容 OpenAI Chat Completions 协议）的 HTTP 通信。
- 提供同步 chat、异步 achat 与异步流式 achat_stream 三种调用方式。
- 统一处理 API Key 读取、请求构造、错误转换与超时控制。
- 暴露全局单例 get_llm_client() 供业务层复用。
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
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"


# AI-assisted: 使用 Claude 定义 LLM 客户端异常类型，未做大幅修改
class LLMClientError(Exception):
    """LLM 客户端错误（API 调用失败、网络异常、响应解析失败的统一异常）"""
    pass


# AI-assisted: 使用 Claude 封装 DeepSeek 客户端，人工校验后保留超时与错误转换逻辑
class LLMClient:
    """DEEPSEEK API 客户端，提供同步/异步/流式聊天接口"""

    def __init__(self, api_key: str = ""):
        """
        初始化 LLM 客户端

        Args:
            api_key: DEEPSEEK API Key，如果不提供则从环境变量 DEEPSEEK_API_KEY 读取
        """
        self.api_key = api_key or DEEPSEEK_API_KEY
        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY 未设置，LLM 功能将不可用")

    def _is_available(self) -> bool:
        """检查 API 是否可用（依据 api_key 是否已配置）

        Returns:
            True 表示已配置 Key，可发起请求
        """
        return bool(self.api_key)

    # AI-assisted: 使用 Claude 实现异步非流式聊天请求，手动调整了超时时间与异常分支映射
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

    # AI-assisted: 使用 Claude 封装 DeepSeek 流式调用，人工校验后保留 SSE 解析与逐片段 yield 逻辑
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

    # AI-assisted: 使用 Claude 实现兼容异步环境的同步聊天请求，手动调整了事件循环判断分支
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
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """获取全局 LLM 客户端单例（首次调用时惰性创建）

    Returns:
        全局共享的 LLMClient 实例
    """
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
