"""
数据模型定义
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum


class MessageType(str, Enum):
    """消息类型"""
    RECEIVED = "received"
    SENT = "sent"


@dataclass
class Contact:
    """联系人模型"""
    id: Optional[int] = None
    wx_id: str = ""
    name: str = ""
    remark: Optional[str] = None
    is_whitelist: bool = False
    system_prompt: Optional[str] = None
    style_profile: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "wx_id": self.wx_id,
            "name": self.name,
            "remark": self.remark,
            "is_whitelist": self.is_whitelist,
            "system_prompt": self.system_prompt,
            "style_profile": self.style_profile,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class Message:
    """消息模型"""
    id: Optional[int] = None
    contact_id: int = 0
    msg_type: MessageType = MessageType.RECEIVED
    content: str = ""
    timestamp: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "contact_id": self.contact_id,
            "msg_type": self.msg_type.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class ConversationContext:
    """对话上下文模型"""
    contact_id: int = 0
    context_json: str = "{}"
    updated_at: Optional[datetime] = None
