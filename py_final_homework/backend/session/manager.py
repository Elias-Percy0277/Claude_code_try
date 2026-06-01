"""
会话管理器
管理用户会话和数据隔离，支持服务重启恢复
"""
import os
import json
import uuid
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import logging

import pandas as pd

from backend.models.session_context import SessionContext, DataProfile, OperationResult
from backend.core.operations import build_data_profile

logger = logging.getLogger(__name__)

# 会话配置
SESSIONS_DIR = "sessions"
SESSION_EXPIRE_MINUTES = 30
MAX_CACHE_SIZE = 10  # 内存中最多缓存 10 个 DataFrame


class SessionNotFoundError(Exception):
    """会话不存在错误"""
    pass


class Dataset:
    """单个数据集类"""

    def __init__(
        self,
        dataset_id: str,
        dataframe: pd.DataFrame,
        original_filename: str,
        file_hash: str,
        dataset_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.dataset_id = dataset_id
        self.dataframe = dataframe
        self.original_filename = original_filename
        self.file_hash = file_hash
        self.dataset_name = dataset_name or original_filename
        self.metadata = metadata or {}

    @property
    def row_count(self) -> int:
        return len(self.dataframe)

    @property
    def columns(self) -> List[str]:
        return self.dataframe.columns.tolist()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "dataset_id": self.dataset_id,
            "dataset_name": self.dataset_name,
            "original_filename": self.original_filename,
            "file_hash": self.file_hash,
            "row_count": self.row_count,
            "columns": self.columns,
            "metadata": self.metadata
        }


class Session:
    """会话数据类（支持多数据集）"""

    def __init__(
        self,
        session_id: str,
        datasets: Dict[str, Dataset],
        created_at: Optional[datetime] = None,
        last_accessed: Optional[datetime] = None,
        disk_path: Optional[str] = None,
        context: Optional[SessionContext] = None
    ):
        self.session_id = session_id
        self.datasets = datasets  # dataset_id -> Dataset
        self.created_at = created_at or datetime.now()
        self.last_accessed = last_accessed or datetime.now()
        self.disk_path = disk_path or os.path.join(SESSIONS_DIR, session_id)
        self.context = context or SessionContext()

    @property
    def primary_dataset(self) -> Optional[Dataset]:
        """获取主数据集（第一个添加的数据集）"""
        if self.datasets:
            return next(iter(self.datasets.values()))
        return None

    @property
    def row_count(self) -> int:
        """主数据集的行数（向后兼容）"""
        if self.primary_dataset:
            return self.primary_dataset.row_count
        return 0

    @property
    def columns(self) -> List[str]:
        """主数据集的列名（向后兼容）"""
        if self.primary_dataset:
            return self.primary_dataset.columns
        return []

    @property
    def total_rows(self) -> int:
        """所有数据集的总行数"""
        return sum(ds.row_count for ds in self.datasets.values())

    @property
    def dataset_count(self) -> int:
        """数据集数量"""
        return len(self.datasets)

    def add_dataset(self, dataset: Dataset) -> None:
        """添加数据集"""
        self.datasets[dataset.dataset_id] = dataset

    def remove_dataset(self, dataset_id: str) -> bool:
        """移除数据集"""
        if dataset_id in self.datasets:
            del self.datasets[dataset_id]
            return True
        return False

    def get_dataset(self, dataset_id: str) -> Optional[Dataset]:
        """获取指定数据集"""
        return self.datasets.get(dataset_id)

    def get_all_dataframes(self) -> Dict[str, pd.DataFrame]:
        """获取所有数据集的 DataFrame"""
        return {ds.dataset_id: ds.dataframe for ds in self.datasets.values()}

    def init_context(self, data_id: str, df: pd.DataFrame):
        """基于 DataFrame 初始化会话上下文"""
        profile_dict = build_data_profile(df)
        self.context = SessionContext(
            data_id=data_id,
            data_profile=DataProfile(**profile_dict),
        )

    def update_context(self, result: OperationResult):
        """操作完成后更新上下文"""
        self.context.update_with_result(result)

    def get_context(self) -> SessionContext:
        """获取会话上下文"""
        return self.context

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "datasets": [ds.to_dict() for ds in self.datasets.values()],
            "dataset_count": self.dataset_count,
            "total_rows": self.total_rows
        }


class SessionManager:
    """
    会话管理器

    功能：
    - 创建会话并持久化到磁盘
    - 从内存或磁盘加载会话
    - 清理过期会话
    - LRU 内存管理
    """

    def __init__(
        self,
        sessions_dir: str = SESSIONS_DIR,
        expire_minutes: int = SESSION_EXPIRE_MINUTES,
        max_cache_size: int = MAX_CACHE_SIZE
    ):
        """
        初始化会话管理器

        Args:
            sessions_dir: 会话存储目录
            expire_minutes: 会话过期时间（分钟）
            max_cache_size: 内存中最大缓存 DataFrame 数量
        """
        self.sessions_dir = sessions_dir
        self.expire_minutes = expire_minutes
        self.max_cache_size = max_cache_size

        # 内存缓存 (LRU)
        self._memory_cache: Dict[str, Session] = {}

        # 确保会话目录存在
        os.makedirs(self.sessions_dir, exist_ok=True)

        logger.info(f"会话管理器初始化完成: 目录={sessions_dir}, 过期={expire_minutes}分钟")

    def _get_session_dir(self, session_id: str) -> str:
        """获取会话目录路径"""
        return os.path.join(self.sessions_dir, session_id)

    def _get_meta_path(self, session_id: str) -> str:
        """获取元数据文件路径"""
        return os.path.join(self._get_session_dir(session_id), "meta.json")

    def _get_data_path(self, session_id: str, dataset_id: str) -> str:
        """获取数据文件路径"""
        return os.path.join(self._get_session_dir(session_id), f"{dataset_id}.parquet")

    def _get_cache_path(self, session_id: str) -> str:
        """获取缓存文件路径"""
        return os.path.join(self._get_session_dir(session_id), "cache.json")

    def _analyze_columns(self, df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        """分析列信息"""
        result = {}
        for col in df.columns:
            info = {
                "dtype": str(df[col].dtype),
                "nullable": bool(df[col].isna().any()),
                "nunique": None
            }

            nunique = df[col].nunique()
            if nunique < 100:
                info["nunique"] = int(nunique)
            else:
                info["nunique"] = "high"

            if info["nullable"]:
                info["null_ratio"] = round(df[col].isna().sum() / len(df), 4)

            result[col] = info
        return result

    def create_session(
        self,
        dataframe: pd.DataFrame,
        original_filename: str,
        file_hash: str,
        dataset_name: Optional[str] = None
    ) -> Session:
        """
        创建新会话

        Args:
            dataframe: 数据集
            original_filename: 原始文件名
            file_hash: 文件哈希
            dataset_name: 数据集名称（可选）

        Returns:
            Session 对象
        """
        session_id = str(uuid.uuid4())
        dataset_id = str(uuid.uuid4())
        now = datetime.now()

        # 创建会话目录
        session_dir = self._get_session_dir(session_id)
        os.makedirs(session_dir, exist_ok=True)

        # 创建数据集对象
        dataset = Dataset(
            dataset_id=dataset_id,
            dataframe=dataframe,
            original_filename=original_filename,
            file_hash=file_hash,
            dataset_name=dataset_name or original_filename
        )

        # 保存数据到磁盘
        data_path = self._get_data_path(session_id, dataset_id)
        dataframe.to_parquet(data_path, index=False)
        logger.info(f"数据已保存到: {data_path}")

        # 创建元数据
        meta = {
            "session_id": session_id,
            "created_at": now.isoformat(),
            "last_accessed": now.isoformat(),
            "datasets": {
                dataset_id: {
                    "dataset_id": dataset_id,
                    "dataset_name": dataset.dataset_name,
                    "original_filename": original_filename,
                    "file_hash": file_hash,
                    "columns_info": self._analyze_columns(dataframe),
                    "row_count": len(dataframe)
                }
            },
            "chat_history": []
        }

        # 创建会话对象
        session = Session(
            session_id=session_id,
            datasets={dataset_id: dataset},
            created_at=now,
            last_accessed=now,
            disk_path=session_dir
        )

        # 初始化会话上下文
        session.init_context(dataset_id, dataframe)

        # 持久化上下文
        meta["context"] = session.context.to_dict()

        # 保存元数据
        meta_path = self._get_meta_path(session_id)
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        logger.info(f"元数据已保存到: {meta_path}")

        # 内存缓存管理（LRU）
        self._add_to_memory_cache(session)

        logger.info(f"会话创建成功: {session_id} ({original_filename}, {len(dataframe)} 行)")

        return session

    def get_session(self, session_id: str) -> Session:
        """
        获取会话

        Args:
            session_id: 会话 ID

        Returns:
            Session 对象

        Raises:
            SessionNotFoundError: 会话不存在
        """
        # 先查内存缓存
        if session_id in self._memory_cache:
            session = self._memory_cache[session_id]
            session.last_accessed = datetime.now()
            logger.debug(f"从内存缓存加载会话: {session_id}")
            return session

        # 内存未命中，从磁盘加载
        meta_path = self._get_meta_path(session_id)
        if not os.path.exists(meta_path):
            raise SessionNotFoundError(f"会话不存在或已过期: {session_id}")

        # 加载元数据
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        # 检查是否过期
        last_accessed = datetime.fromisoformat(meta['last_accessed'])
        if datetime.now() - last_accessed > timedelta(minutes=self.expire_minutes):
            # 过期，删除并抛出异常
            self.delete_session(session_id)
            raise SessionNotFoundError(f"会话已过期: {session_id}")

        # 加载所有数据集
        datasets = {}
        for dataset_id, dataset_meta in meta.get('datasets', {}).items():
            data_path = self._get_data_path(session_id, dataset_id)
            if os.path.exists(data_path):
                dataframe = pd.read_parquet(data_path)
                datasets[dataset_id] = Dataset(
                    dataset_id=dataset_id,
                    dataframe=dataframe,
                    original_filename=dataset_meta['original_filename'],
                    file_hash=dataset_meta['file_hash'],
                    dataset_name=dataset_meta.get('dataset_name', dataset_meta['original_filename'])
                )

        # 创建会话对象
        session = Session(
            session_id=session_id,
            datasets=datasets,
            created_at=datetime.fromisoformat(meta['created_at']),
            last_accessed=datetime.now(),
            disk_path=self._get_session_dir(session_id)
        )

        # 恢复上下文
        if 'context' in meta and meta['context']:
            try:
                session.context = SessionContext.from_dict(meta['context'])
            except Exception as e:
                logger.warning(f"恢复上下文失败: {e}，重新初始化")
                primary = session.primary_dataset
                if primary:
                    session.init_context(
                        next(iter(datasets.keys())),
                        primary.dataframe
                    )
        elif datasets:
            primary = session.primary_dataset
            if primary:
                session.init_context(
                    next(iter(datasets.keys())),
                    primary.dataframe
                )

        # 更新访问时间
        self._update_last_accessed(session_id)

        # 加入内存缓存
        self._add_to_memory_cache(session)

        logger.info(f"从磁盘加载会话: {session_id} ({len(datasets)} 个数据集)")

        return session

    def _add_to_memory_cache(self, session: Session) -> None:
        """
        添加会话到内存缓存（LRU 淘汰）

        Args:
            session: 会话对象
        """
        # 如果已存在，更新
        if session.session_id in self._memory_cache:
            return

        # 检查缓存大小
        if len(self._memory_cache) >= self.max_cache_size:
            # 删除最旧的（第一个）
            oldest_id = next(iter(self._memory_cache))
            del self._memory_cache[oldest_id]
            logger.debug(f"LRU 淘汰内存缓存: {oldest_id}")

        # 添加新会话
        self._memory_cache[session.session_id] = session

    def add_dataset_to_session(
        self,
        session_id: str,
        dataframe: pd.DataFrame,
        original_filename: str,
        file_hash: str,
        dataset_name: Optional[str] = None
    ) -> Dataset:
        """
        向现有会话添加数据集

        Args:
            session_id: 会话 ID
            dataframe: 数据集
            original_filename: 原始文件名
            file_hash: 文件哈希
            dataset_name: 数据集名称（可选）

        Returns:
            Dataset 对象

        Raises:
            SessionNotFoundError: 会话不存在
        """
        # 检查会话是否存在
        meta_path = self._get_meta_path(session_id)
        if not os.path.exists(meta_path):
            raise SessionNotFoundError(f"会话不存在: {session_id}")

        dataset_id = str(uuid.uuid4())
        now = datetime.now()

        # 创建数据集对象
        dataset = Dataset(
            dataset_id=dataset_id,
            dataframe=dataframe,
            original_filename=original_filename,
            file_hash=file_hash,
            dataset_name=dataset_name or original_filename
        )

        # 保存数据到磁盘
        data_path = self._get_data_path(session_id, dataset_id)
        dataframe.to_parquet(data_path, index=False)
        logger.info(f"数据已保存到: {data_path}")

        # 更新元数据
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        meta['datasets'][dataset_id] = {
            "dataset_id": dataset_id,
            "dataset_name": dataset.dataset_name,
            "original_filename": original_filename,
            "file_hash": file_hash,
            "columns_info": self._analyze_columns(dataframe),
            "row_count": len(dataframe)
        }
        meta['last_accessed'] = now.isoformat()

        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        # 更新内存缓存中的会话
        if session_id in self._memory_cache:
            self._memory_cache[session_id].add_dataset(dataset)

        logger.info(f"数据集已添加到会话: {session_id} ({original_filename}, {len(dataframe)} 行)")

        return dataset

    def _update_last_accessed(self, session_id: str) -> None:
        """更新会话最后访问时间"""
        meta_path = self._get_meta_path(session_id)
        if os.path.exists(meta_path):
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)

            meta['last_accessed'] = datetime.now().isoformat()

            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

    def update_session(self, session_id: str, **updates) -> None:
        """
        更新会话元数据

        Args:
            session_id: 会话 ID
            **updates: 要更新的字段
        """
        meta_path = self._get_meta_path(session_id)
        if not os.path.exists(meta_path):
            raise SessionNotFoundError(f"会话不存在: {session_id}")

        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        # 更新字段
        meta.update(updates)
        meta['last_accessed'] = datetime.now().isoformat()

        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        logger.info(f"会话元数据已更新: {session_id}")

    def rename_session(self, session_id: str, new_name: str) -> None:
        """重命名会话"""
        meta_path = self._get_meta_path(session_id)
        if not os.path.exists(meta_path):
            raise SessionNotFoundError(f"会话不存在: {session_id}")

        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        meta['session_name'] = new_name.strip()

        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        logger.info(f"会话已重命名: {session_id} -> {new_name}")

    def delete_session(self, session_id: str) -> None:
        """
        删除会话

        Args:
            session_id: 会话 ID
        """
        # 从内存缓存删除
        if session_id in self._memory_cache:
            del self._memory_cache[session_id]

        # 删除磁盘文件（会话目录下的所有文件）
        session_dir = self._get_session_dir(session_id)
        if os.path.exists(session_dir):
            shutil.rmtree(session_dir)
            logger.info(f"会话已删除: {session_id}")

    def remove_dataset_from_session(self, session_id: str, dataset_id: str) -> bool:
        """
        从会话中移除数据集

        Args:
            session_id: 会话 ID
            dataset_id: 数据集 ID

        Returns:
            是否成功移除
        """
        meta_path = self._get_meta_path(session_id)
        if not os.path.exists(meta_path):
            raise SessionNotFoundError(f"会话不存在: {session_id}")

        # 加载元数据
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        if dataset_id not in meta.get('datasets', {}):
            return False

        # 删除数据文件
        data_path = self._get_data_path(session_id, dataset_id)
        if os.path.exists(data_path):
            os.remove(data_path)

        # 更新元数据
        del meta['datasets'][dataset_id]
        meta['last_accessed'] = datetime.now().isoformat()

        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        # 更新内存缓存
        if session_id in self._memory_cache:
            self._memory_cache[session_id].remove_dataset(dataset_id)

        logger.info(f"数据集已从会话移除: {session_id}/{dataset_id}")
        return True

    def cleanup_expired_sessions(self) -> int:
        """
        清理过期会话

        Returns:
            清理的会话数量
        """
        now = datetime.now()
        expire_threshold = now - timedelta(minutes=self.expire_minutes)
        count = 0

        sessions_dir = Path(self.sessions_dir)
        if not sessions_dir.exists():
            return 0

        for session_dir in sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue

            meta_path = session_dir / "meta.json"
            if not meta_path.exists():
                # 元文件损坏，直接删除目录
                shutil.rmtree(session_dir)
                count += 1
                logger.warning(f"删除损坏的会话目录: {session_dir.name}")
                continue

            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)

                last_accessed = datetime.fromisoformat(meta['last_accessed'])

                if last_accessed < expire_threshold:
                    # 过期，删除会话
                    session_id = meta['session_id']
                    self.delete_session(session_id)
                    count += 1
                    logger.info(f"清理过期会话: {session_id} (最后访问: {last_accessed})")

            except Exception as e:
                logger.error(f"清理会话失败 {session_dir}: {e}")

        return count

    def get_session_info(self, session_id: str) -> Dict[str, Any]:
        """
        获取会话信息（不加载完整数据）

        Args:
            session_id: 会话 ID

        Returns:
            会话信息字典
        """
        meta_path = self._get_meta_path(session_id)
        if not os.path.exists(meta_path):
            raise SessionNotFoundError(f"会话不存在: {session_id}")

        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        datasets = []
        total_rows = 0
        for ds_id, ds_meta in meta.get('datasets', {}).items():
            datasets.append({
                "dataset_id": ds_id,
                "dataset_name": ds_meta.get('dataset_name', ds_meta['original_filename']),
                "original_filename": ds_meta['original_filename'],
                "row_count": ds_meta['row_count'],
                "columns": list(ds_meta.get('columns_info', {}).keys())
            })
            total_rows += ds_meta['row_count']

        return {
            "session_id": meta['session_id'],
            "valid": True,
            "created_at": meta['created_at'],
            "last_accessed": meta['last_accessed'],
            "session_name": meta.get('session_name', ''),
            "datasets": datasets,
            "dataset_count": len(datasets),
            "total_rows": total_rows
        }

    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        列出所有会话

        Returns:
            会话信息列表
        """
        sessions = []
        sessions_dir = Path(self.sessions_dir)

        if not sessions_dir.exists():
            return sessions

        for session_dir in sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue

            meta_path = session_dir / "meta.json"
            if not meta_path.exists():
                continue

            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)

                datasets = meta.get('datasets', {})
                primary_dataset = next(iter(datasets.values())) if datasets else {}

                sessions.append({
                    "session_id": meta['session_id'],
                    "filename": primary_dataset.get('original_filename', ''),
                    "session_name": meta.get('session_name', ''),
                    "created_at": meta['created_at'],
                    "last_accessed": meta['last_accessed'],
                    "row_count": primary_dataset.get('row_count', 0),
                    "dataset_count": len(datasets),
                    "is_expired": (datetime.now() - datetime.fromisoformat(meta['last_accessed'])).total_seconds() > self.expire_minutes * 60
                })
            except Exception as e:
                logger.error(f"读取会话信息失败 {session_dir}: {e}")

        # 按创建时间排序
        sessions.sort(key=lambda x: x['created_at'], reverse=True)
        return sessions

    def add_chat_entry(self, session_id: str, role: str, content: str, charts: list = None) -> None:
        """
        向会话的聊天历史添加条目

        Args:
            session_id: 会话 ID
            role: 消息角色 (user/assistant/system)
            content: 消息内容
            charts: 图表数据列表（可选）
        """
        meta_path = self._get_meta_path(session_id)
        if not os.path.exists(meta_path):
            raise SessionNotFoundError(f"会话不存在: {session_id}")

        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        if 'chat_history' not in meta:
            meta['chat_history'] = []

        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        if charts:
            entry["charts"] = charts

        meta['chat_history'].append(entry)
        meta['last_accessed'] = datetime.now().isoformat()

        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        logger.info(f"聊天历史条目已添加到会话: {session_id}")

    def save_context(self, session_id: str) -> None:
        """持久化内存中的上下文到磁盘"""
        meta_path = self._get_meta_path(session_id)
        if not os.path.exists(meta_path):
            raise SessionNotFoundError(f"会话不存在: {session_id}")

        if session_id not in self._memory_cache:
            return

        session = self._memory_cache[session_id]
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        meta['context'] = session.context.to_dict()
        meta['last_accessed'] = datetime.now().isoformat()

        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def get_chat_history(self, session_id: str) -> list:
        """
        获取会话的聊天历史

        Args:
            session_id: 会话 ID

        Returns:
            聊天历史条目列表
        """
        meta_path = self._get_meta_path(session_id)
        if not os.path.exists(meta_path):
            raise SessionNotFoundError(f"会话不存在: {session_id}")

        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        return meta.get('chat_history', [])

    def get_stats(self) -> Dict[str, Any]:
        """
        获取会话管理器统计信息

        Returns:
            统计信息字典
        """
        sessions = self.list_sessions()

        now = datetime.now()
        active_count = sum(
            1 for s in sessions
            if not s['is_expired']
        )
        expired_count = len(sessions) - active_count

        total_rows = sum(s['row_count'] for s in sessions)
        total_datasets = sum(s.get('dataset_count', 1) for s in sessions)

        return {
            "total_sessions": len(sessions),
            "active_sessions": active_count,
            "expired_sessions": expired_count,
            "memory_cached": len(self._memory_cache),
            "total_rows": total_rows,
            "total_datasets": total_datasets,
            "sessions_dir": self.sessions_dir,
            "expire_minutes": self.expire_minutes,
            "max_cache_size": self.max_cache_size
        }


# 全局单例
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """获取全局会话管理器单例"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
