"""
消息处理器 - 处理消息接收、AI 回复、上下文管理

回复模式:
- auto_send: 自动发送消息
- copy_only: 仅复制到剪贴板，由用户手动粘贴
"""
import asyncio
import json
import pyperclip
from typing import Optional, List, Dict
from datetime import datetime

from config.settings import settings
from core.ai_engine import ai_engine, MessageRole
from core.wechat_client import wechat_client
from core.personality import style_learning
from storage.database import db
from storage.models import Contact, Message, MessageType as MsgType
from utils.logger import logger


class ReplyMode:
    """回复模式"""
    AUTO_SEND = "auto_send"    # 自动发送（搜索联系人+粘贴+回车）
    COPY_ONLY = "copy_only"    # 仅复制到剪贴板（手动操作）
    COPY_PASTE = "copy_paste"  # 复制+自动粘贴（等待用户按回车发送）
    AUTO_PASTE = "auto_paste"  # 复制+自动粘贴+自动发送


class MessageHandler:
    """消息处理器类"""

    def __init__(self):
        self._paused = False
        self._processing = set()  # 正在处理的联系人

    async def handle_message(self, message_data: dict):
        """处理收到的消息"""
        if self._paused:
            logger.debug("消息处理已暂停，忽略消息")
            return

        contact_name = message_data.get("contact_name", "")
        content = message_data.get("content", "").strip()

        if not contact_name or not content:
            return

        # 防止重复处理
        if contact_name in self._processing:
            logger.debug(f"联系人 {contact_name} 的消息正在处理中，跳过")
            return

        self._processing.add(contact_name)

        try:
            # 检查是否启用回复（仅复制或自动发送）
            auto_reply = settings.get("wechat.auto_reply", False)
            reply_mode = settings.get("wechat.reply_mode", ReplyMode.COPY_ONLY)

            # 如果完全禁用且不是仅复制模式，则跳过
            if not auto_reply and reply_mode != ReplyMode.COPY_ONLY:
                logger.debug("自动回复已禁用")
                return

            # 获取或创建联系人
            contact = await db.get_contact_by_wx_id(contact_name)
            if not contact:
                contact = Contact(
                    wx_id=contact_name,
                    name=contact_name,
                    is_whitelist=False
                )
                contact = await db.create_or_update_contact(contact)

            # 白名单检查
            if settings.get("wechat.whitelist_only", True):
                if not contact.is_whitelist:
                    logger.info(f"联系人 {contact_name} 不在白名单中，不回复")
                    return

            # 保存收到的消息
            await db.save_message(Message(
                contact_id=contact.id,
                msg_type=MsgType.RECEIVED,
                content=content,
                timestamp=datetime.now()
            ))

            # 生成回复
            reply = await self._generate_reply(contact, content)

            if reply:
                # 发送回复
                self._send_reply(contact_name, reply)

                # 保存发送的消息
                await db.save_message(Message(
                    contact_id=contact.id,
                    msg_type=MsgType.SENT,
                    content=reply,
                    timestamp=datetime.now()
                ))

                # 更新对话上下文
                await self._update_context(contact, content, reply)

        except Exception as e:
            logger.error(f"处理消息异常: {e}")
        finally:
            self._processing.discard(contact_name)

    async def _generate_reply(self, contact: Contact, user_message: str) -> Optional[str]:
        """生成 AI 回复"""
        try:
            # 获取对话上下文
            context_data = await db.get_conversation_context(contact.id)
            context = json.loads(context_data.context_json) if context_data.context_json else []

            # 获取系统提示词
            system_prompt = contact.system_prompt

            # 如果有风格档案，生成提示词
            if contact.style_profile:
                try:
                    style_profile = json.loads(contact.style_profile)
                    base_prompt = system_prompt or settings.get("ai.default_system_prompt", "")
                    system_prompt = style_learning.generate_system_prompt(
                        style_profile,
                        base_name=contact.name
                    )
                except:
                    pass

            # 调用 AI 生成回复
            reply = ai_engine.generate(
                message=user_message,
                system_prompt=system_prompt,
                context=context,
                stream=False
            )

            if reply:
                logger.info(f"AI 回复 {contact.name}: {reply[:50]}...")
            else:
                logger.warning(f"AI 未生成回复给 {contact.name}")

            return reply

        except Exception as e:
            logger.error(f"生成回复异常: {e}")
            return None

    def _send_reply(self, contact_name: str, content: str) -> bool:
        """
        发送回复

        根据 reply_mode 配置决定行为:
        - auto_send: 搜索联系人+粘贴+回车（完全自动）
        - copy_only: 仅复制到剪贴板
        - copy_paste: 复制+自动粘贴（用户按回车发送）
        - auto_paste: 复制+自动粘贴+自动回车
        """
        try:
            reply_mode = settings.get("wechat.reply_mode", ReplyMode.COPY_PASTE)

            if reply_mode == ReplyMode.COPY_ONLY:
                # 仅复制模式
                pyperclip.copy(content)
                logger.info(f"[仅复制] 已复制到剪贴板")
                logger.info(f"  联系人: {contact_name}")
                return True

            elif reply_mode == ReplyMode.COPY_PASTE:
                # 复制+自动粘贴模式
                import pyautogui
                import win32gui
                import win32con
                import time
                pyperclip.copy(content)
                time.sleep(0.1)

                # 只有当微信是前台窗口时才自动粘贴
                foreground_wnd = win32gui.GetForegroundWindow()
                if foreground_wnd == wechat_client.wx_hwnd:
                    # 微信在前台，可以安全粘贴
                    try:
                        # 点击输入框区域（微信窗口内部）
                        if wechat_client.wx_rect:
                            left, top, right, bottom = wechat_client.wx_rect
                            input_x = int((left + right) / 2)
                            input_y = int(bottom - 50)
                            pyautogui.click(input_x, input_y)
                            time.sleep(0.1)
                        pyautogui.hotkey('ctrl', 'v')
                        logger.info(f"[自动粘贴] 已粘贴 AI 回复")
                        logger.info(f"  联系人: {contact_name}")
                    except Exception as e:
                        logger.warning(f"自动粘贴失败: {e}")
                else:
                    # 微信不在前台，只复制
                    logger.info(f"[仅复制] 微信不在前台，仅复制到剪贴板")

                logger.info(f"  联系人: {contact_name}")
                logger.info(f"  内容: {content[:50]}...")
                return True

            elif reply_mode == ReplyMode.AUTO_PASTE:
                # 复制+自动粘贴+自动回车
                import pyautogui
                import win32gui
                import win32con
                import time
                pyperclip.copy(content)
                time.sleep(0.1)

                # 只有当微信是前台窗口时才自动操作
                foreground_wnd = win32gui.GetForegroundWindow()
                if foreground_wnd == wechat_client.wx_hwnd:
                    try:
                        if wechat_client.wx_rect:
                            left, top, right, bottom = wechat_client.wx_rect
                            input_x = int((left + right) / 2)
                            input_y = int(bottom - 50)
                            pyautogui.click(input_x, input_y)
                            time.sleep(0.1)
                        pyautogui.hotkey('ctrl', 'v')
                        time.sleep(0.2)
                        pyautogui.press('enter')
                        logger.info(f"[自动粘贴+发送] 已发送 AI 回复")
                    except Exception as e:
                        logger.warning(f"自动发送失败: {e}")
                else:
                    logger.info(f"[仅复制] 微信不在前台，仅复制到剪贴板")

                logger.info(f"  联系人: {contact_name}")
                logger.info(f"  内容: {content[:50]}...")
                return True

            else:  # AUTO_SEND
                # 完全自动发送模式
                return wechat_client.send_message(contact_name, content)

        except Exception as e:
            logger.error(f"发送回复异常: {e}")
            return False

    async def _update_context(self, contact: Contact, user_message: str, reply: str):
        """更新对话上下文"""
        try:
            # 获取当前上下文
            context_data = await db.get_conversation_context(contact.id)
            context = json.loads(context_data.context_json) if context_data.context_json else []

            # 添加新的对话
            context.append({
                "role": MessageRole.USER,
                "content": user_message
            })
            context.append({
                "role": MessageRole.ASSISTANT,
                "content": reply
            })

            # 限制上下文长度
            max_context = settings.get("ai.max_context_messages", 20)
            if len(context) > max_context * 2:  # 每条消息包含 user 和 assistant
                context = context[-max_context * 2:]

            # 保存
            await db.save_conversation_context(contact.id, context)

        except Exception as e:
            logger.error(f"更新上下文异常: {e}")

    def pause(self):
        """暂停自动回复"""
        self._paused = True
        # 同步暂停微信客户端的消息监听
        wechat_client.pause()
        logger.info("自动回复已暂停")

    def resume(self):
        """恢复自动回复"""
        self._paused = False
        # 同步恢复微信客户端的消息监听
        wechat_client.resume()
        logger.info("自动回复已恢复")

    def is_paused(self) -> bool:
        """检查是否暂停"""
        return self._paused

    async def clear_context(self, contact_id: int):
        """清空对话上下文"""
        await db.save_conversation_context(contact_id, [])
        logger.info(f"已清空联系人 {contact_id} 的对话上下文")

    async def get_conversation_history(self, contact_id: int, limit: int = 50) -> List[dict]:
        """获取对话历史"""
        messages = await db.get_messages(contact_id, limit=limit)
        return [msg.to_dict() for msg in messages]


# 全局消息处理器实例
message_handler = MessageHandler()
