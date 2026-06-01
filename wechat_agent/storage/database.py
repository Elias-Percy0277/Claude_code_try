"""
数据库操作模块
"""
import aiosqlite
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from storage.models import Contact, Message, ConversationContext, MessageType
from utils.logger import logger


class Database:
    """数据库操作类"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            # 数据库直接放在项目根目录
            db_path = Path(__file__).parent.parent / "database.db"
        self.db_path = db_path
        self._init_sync()

    def _init_sync(self):
        """同步初始化数据库（用于表创建）"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            self._create_tables(conn)

    def _create_tables(self, conn):
        """创建数据表"""
        # 联系人表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wx_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                remark TEXT,
                is_whitelist BOOLEAN DEFAULT 0,
                system_prompt TEXT,
                style_profile TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 消息记录表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                msg_type TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contact_id) REFERENCES contacts(id)
            )
        """)

        # 对话上下文表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_context (
                contact_id INTEGER PRIMARY KEY,
                context_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contact_id) REFERENCES contacts(id)
            )
        """)

        # 全局配置表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # 创建索引
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_contact
            ON messages(contact_id, timestamp DESC)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp
            ON messages(timestamp DESC)
        """)

        conn.commit()

    async def get_contact_by_wx_id(self, wx_id: str) -> Optional[Contact]:
        """根据微信 ID 获取联系人"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM contacts WHERE wx_id = ?",
                (wx_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return Contact(
                        id=row["id"],
                        wx_id=row["wx_id"],
                        name=row["name"],
                        remark=row["remark"],
                        is_whitelist=bool(row["is_whitelist"]),
                        system_prompt=row["system_prompt"],
                        style_profile=row["style_profile"],
                        created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                        updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
                    )
        return None

    async def create_or_update_contact(self, contact: Contact) -> Contact:
        """创建或更新联系人"""
        async with aiosqlite.connect(self.db_path) as db:
            now = datetime.now().isoformat()
            existing = await self.get_contact_by_wx_id(contact.wx_id)

            if existing:
                # 更新
                async with db.execute("""
                    UPDATE contacts
                    SET name = ?, remark = ?, is_whitelist = ?,
                        system_prompt = ?, style_profile = ?, updated_at = ?
                    WHERE wx_id = ?
                """, (contact.name, contact.remark, contact.is_whitelist,
                      contact.system_prompt, contact.style_profile, now, contact.wx_id)):
                    pass
                contact.id = existing.id
                contact.created_at = existing.created_at
            else:
                # 创建
                cursor = await db.execute("""
                    INSERT INTO contacts (wx_id, name, remark, is_whitelist, system_prompt, style_profile, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (contact.wx_id, contact.name, contact.remark, contact.is_whitelist,
                      contact.system_prompt, contact.style_profile, now, now))
                contact.id = cursor.lastrowid
                contact.created_at = datetime.fromisoformat(now)

            await db.commit()
            return contact

    async def get_all_contacts(self, whitelist_only: bool = False) -> List[Contact]:
        """获取所有联系人"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM contacts"
            if whitelist_only:
                query += " WHERE is_whitelist = 1"
            query += " ORDER BY updated_at DESC"

            contacts = []
            async with db.execute(query) as cursor:
                async for row in cursor:
                    contacts.append(Contact(
                        id=row["id"],
                        wx_id=row["wx_id"],
                        name=row["name"],
                        remark=row["remark"],
                        is_whitelist=bool(row["is_whitelist"]),
                        system_prompt=row["system_prompt"],
                        style_profile=row["style_profile"],
                        created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                        updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
                    ))
            return contacts

    async def save_message(self, message: Message) -> Message:
        """保存消息"""
        async with aiosqlite.connect(self.db_path) as db:
            now = datetime.now().isoformat()
            cursor = await db.execute("""
                INSERT INTO messages (contact_id, msg_type, content, timestamp)
                VALUES (?, ?, ?, ?)
            """, (message.contact_id, message.msg_type.value, message.content, now))
            message.id = cursor.lastrowid
            message.timestamp = datetime.fromisoformat(now)
            await db.commit()
            return message

    async def get_messages(
        self,
        contact_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> List[Message]:
        """获取联系人的消息记录"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            messages = []
            async with db.execute("""
                SELECT * FROM messages
                WHERE contact_id = ?
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """, (contact_id, limit, offset)) as cursor:
                async for row in cursor:
                    messages.append(Message(
                        id=row["id"],
                        contact_id=row["contact_id"],
                        msg_type=MessageType(row["msg_type"]),
                        content=row["content"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                    ))
            return list(reversed(messages))

    async def get_conversation_context(self, contact_id: int) -> ConversationContext:
        """获取对话上下文"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM conversation_context WHERE contact_id = ?",
                (contact_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return ConversationContext(
                        contact_id=row["contact_id"],
                        context_json=row["context_json"],
                        updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
                    )
        # 不存在则返回空的
        return ConversationContext(contact_id=contact_id, context_json="[]")

    async def save_conversation_context(
        self,
        contact_id: int,
        context: List[dict]
    ) -> None:
        """保存对话上下文"""
        async with aiosqlite.connect(self.db_path) as db:
            now = datetime.now().isoformat()
            context_json = json.dumps(context, ensure_ascii=False)
            await db.execute("""
                INSERT OR REPLACE INTO conversation_context (contact_id, context_json, updated_at)
                VALUES (?, ?, ?)
            """, (contact_id, context_json, now))
            await db.commit()

    async def delete_contact(self, contact_id: int) -> bool:
        """删除联系人"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM messages WHERE contact_id = ?", (contact_id,))
            await db.execute("DELETE FROM conversation_context WHERE contact_id = ?", (contact_id,))
            await db.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
            await db.commit()
            return True

    async def get_stats(self) -> dict:
        """获取统计信息"""
        async with aiosqlite.connect(self.db_path) as db:
            # 总联系人数
            async with db.execute("SELECT COUNT(*) FROM contacts") as cursor:
                total_contacts = (await cursor.fetchone())[0]

            # 白名单联系人数
            async with db.execute("SELECT COUNT(*) FROM contacts WHERE is_whitelist = 1") as cursor:
                whitelist_contacts = (await cursor.fetchone())[0]

            # 总消息数
            async with db.execute("SELECT COUNT(*) FROM messages") as cursor:
                total_messages = (await cursor.fetchone())[0]

            # 今日消息数
            async with db.execute("""
                SELECT COUNT(*) FROM messages
                WHERE DATE(timestamp) = DATE('now')
            """) as cursor:
                today_messages = (await cursor.fetchone())[0]

            return {
                "total_contacts": total_contacts,
                "whitelist_contacts": whitelist_contacts,
                "total_messages": total_messages,
                "today_messages": today_messages,
            }

    async def cleanup_old_messages(self, days: int = 30, max_per_contact: int = 1000) -> dict:
        """清理旧消息，防止数据库过大"""
        async with aiosqlite.connect(self.db_path) as db:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

            # 删除超过天数限制的消息
            await db.execute(
                "DELETE FROM messages WHERE timestamp < ?",
                (cutoff_date,)
            )
            old_deleted = db.total_changes

            # 获取每个联系人的消息数
            async with db.execute("""
                SELECT contact_id, COUNT(*) as count
                FROM messages
                GROUP BY contact_id
            """) as cursor:
                contacts_over_limit = []
                async for row in cursor:
                    if row[1] > max_per_contact:
                        contacts_over_limit.append((row[0], row[1]))

            # 对超过单联系人限制的消息进行删除（保留最新的）
            for contact_id, count in contacts_over_limit:
                await db.execute("""
                    DELETE FROM messages
                    WHERE contact_id = ?
                    AND id NOT IN (
                        SELECT id FROM messages
                        WHERE contact_id = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    )
                """, (contact_id, contact_id, max_per_contact))

            limit_deleted = db.total_changes - old_deleted

            # 清理孤立的上下文（联系人已删除）
            await db.execute("""
                DELETE FROM conversation_context
                WHERE contact_id NOT IN (SELECT id FROM contacts)
            """)

            await db.commit()

            logger.info(f"清理完成: 删除 {old_deleted} 条旧消息, {limit_deleted} 条超限消息")

            return {
                "old_deleted": old_deleted,
                "limit_deleted": limit_deleted,
                "total_deleted": old_deleted + limit_deleted
            }

    async def get_db_size(self) -> dict:
        """获取数据库大小信息"""
        db_file = Path(self.db_path)
        if db_file.exists():
            size = db_file.stat().st_size
            return {
                "size_bytes": size,
                "size_mb": round(size / (1024 * 1024), 2),
                "path": str(db_file)
            }
        return {"size_bytes": 0, "size_mb": 0, "path": str(db_file)}


# 全局数据库实例
db = Database()


# 同步版本的数据库操作（用于 Flask 路由）
import threading

class DatabaseSync:
    """纯同步数据库操作类（用于 Flask）"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            # 数据库直接放在项目根目录
            db_path = Path(__file__).parent.parent / "database.db"
        self.db_path = db_path
        # 确保表存在
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            self._create_tables(conn)

    def _create_tables(self, conn):
        """创建数据表"""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wx_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                remark TEXT,
                is_whitelist BOOLEAN DEFAULT 0,
                system_prompt TEXT,
                style_profile TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                msg_type TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contact_id) REFERENCES contacts(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_context (
                contact_id INTEGER PRIMARY KEY,
                context_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contact_id) REFERENCES contacts(id)
            )
        """)
        conn.commit()

    def get_stats_sync(self) -> dict:
        """获取统计信息"""
        with sqlite3.connect(self.db_path) as conn:
            total_contacts = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
            whitelist_contacts = conn.execute("SELECT COUNT(*) FROM contacts WHERE is_whitelist = 1").fetchone()[0]
            total_messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            today_messages = conn.execute("""
                SELECT COUNT(*) FROM messages
                WHERE DATE(timestamp) = DATE('now')
            """).fetchone()[0]
            return {
                "total_contacts": total_contacts,
                "whitelist_contacts": whitelist_contacts,
                "total_messages": total_messages,
                "today_messages": today_messages,
            }

    async def cleanup_old_messages(self, days: int = 30, max_per_contact: int = 1000) -> dict:
        """清理旧消息，防止数据库过大"""
        async with aiosqlite.connect(self.db_path) as db:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

            # 删除超过天数限制的消息
            await db.execute(
                "DELETE FROM messages WHERE timestamp < ?",
                (cutoff_date,)
            )
            old_deleted = db.total_changes

            # 获取每个联系人的消息数
            async with db.execute("""
                SELECT contact_id, COUNT(*) as count
                FROM messages
                GROUP BY contact_id
            """) as cursor:
                contacts_over_limit = []
                async for row in cursor:
                    if row[1] > max_per_contact:
                        contacts_over_limit.append((row[0], row[1]))

            # 对超过单联系人限制的消息进行删除（保留最新的）
            for contact_id, count in contacts_over_limit:
                await db.execute("""
                    DELETE FROM messages
                    WHERE contact_id = ?
                    AND id NOT IN (
                        SELECT id FROM messages
                        WHERE contact_id = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    )
                """, (contact_id, contact_id, max_per_contact))

            limit_deleted = db.total_changes - old_deleted

            # 清理孤立的上下文（联系人已删除）
            await db.execute("""
                DELETE FROM conversation_context
                WHERE contact_id NOT IN (SELECT id FROM contacts)
            """)

            await db.commit()

            logger.info(f"清理完成: 删除 {old_deleted} 条旧消息, {limit_deleted} 条超限消息")

            return {
                "old_deleted": old_deleted,
                "limit_deleted": limit_deleted,
                "total_deleted": old_deleted + limit_deleted
            }

    async def get_db_size(self) -> dict:
        """获取数据库大小信息"""
        db_file = Path(self.db_path)
        if db_file.exists():
            size = db_file.stat().st_size
            return {
                "size_bytes": size,
                "size_mb": round(size / (1024 * 1024), 2),
                "path": str(db_file)
            }
        return {"size_bytes": 0, "size_mb": 0, "path": str(db_file)}

    def get_all_contacts_sync(self, whitelist_only: bool = False) -> List[Contact]:
        """获取所有联系人"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM contacts"
            if whitelist_only:
                query += " WHERE is_whitelist = 1"
            query += " ORDER BY updated_at DESC"

            contacts = []
            for row in conn.execute(query):
                contacts.append(Contact(
                    id=row["id"],
                    wx_id=row["wx_id"],
                    name=row["name"],
                    remark=row["remark"],
                    is_whitelist=bool(row["is_whitelist"]),
                    system_prompt=row["system_prompt"],
                    style_profile=row["style_profile"],
                    created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                    updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
                ))
            return contacts

    def create_or_update_contact_sync(self, contact: Contact) -> Contact:
        """创建或更新联系人"""
        with sqlite3.connect(self.db_path) as conn:
            now = datetime.now().isoformat()
            existing = conn.execute("SELECT * FROM contacts WHERE wx_id = ?", (contact.wx_id,)).fetchone()

            if existing:
                conn.execute("""
                    UPDATE contacts
                    SET name = ?, remark = ?, is_whitelist = ?,
                        system_prompt = ?, style_profile = ?, updated_at = ?
                    WHERE wx_id = ?
                """, (contact.name, contact.remark, contact.is_whitelist,
                      contact.system_prompt, contact.style_profile, now, contact.wx_id))
            else:
                conn.execute("""
                    INSERT INTO contacts (wx_id, name, remark, is_whitelist, system_prompt, style_profile, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (contact.wx_id, contact.name, contact.remark, contact.is_whitelist,
                      contact.system_prompt, contact.style_profile, now, now))
            conn.commit()

            # 获取更新后的记录
            row = conn.execute("SELECT * FROM contacts WHERE wx_id = ?", (contact.wx_id,)).fetchone()
            contact.id = row[0]
            return contact

    def get_messages_sync(self, contact_id: int, limit: int = 50) -> List[Message]:
        """获取消息记录"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            messages = []
            for row in conn.execute("""
                SELECT * FROM messages
                WHERE contact_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (contact_id, limit)):
                messages.append(Message(
                    id=row["id"],
                    contact_id=row["contact_id"],
                    msg_type=MessageType(row["msg_type"]),
                    content=row["content"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                ))
            return list(reversed(messages))

    def get_conversation_context_sync(self, contact_id: int) -> dict:
        """获取对话上下文"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM conversation_context WHERE contact_id = ?",
                (contact_id,)
            ).fetchone()
            if row:
                return {
                    "contact_id": row["contact_id"],
                    "context_json": row["context_json"],
                    "updated_at": row["updated_at"]
                }
            # 不存在则返回空的
            return {
                "contact_id": contact_id,
                "context_json": "[]",
                "updated_at": None
            }

    def delete_contact_sync(self, contact_id: int) -> bool:
        """删除联系人"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM messages WHERE contact_id = ?", (contact_id,))
            conn.execute("DELETE FROM conversation_context WHERE contact_id = ?", (contact_id,))
            conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
            conn.commit()
            return True


# 全局同步数据库实例
db_sync = DatabaseSync()
