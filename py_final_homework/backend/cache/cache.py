"""
缓存管理器
减少重复 LLM 调用，提升响应速度
"""
import hashlib
import json
import time
import logging
from typing import Dict, Any, Optional
from functools import lru_cache
from collections import OrderedDict

logger = logging.getLogger(__name__)


class CacheManager:
    """
    请求缓存管理器

    缓存键设计: session_id + query + file_hash
    """

    def __init__(
        self,
        max_size: int = 100,
        ttl_seconds: int = 3600
    ):
        """
        初始化缓存管理器

        Args:
            max_size: 最大缓存条目数
            ttl_seconds: 缓存过期时间（秒）
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def _generate_key(
        self,
        session_id: str,
        query: str,
        file_hash: str
    ) -> str:
        """
        生成缓存键

        Args:
            session_id: 会话 ID
            query: 用户查询
            file_hash: 文件哈希

        Returns:
            缓存键字符串
        """
        # 组合键
        key_parts = f"{session_id}:{query}:{file_hash}"
        # 使用 MD5 哈希
        return hashlib.md5(key_parts.encode('utf-8')).hexdigest()

    def get(
        self,
        session_id: str,
        query: str,
        file_hash: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取缓存

        Args:
            session_id: 会话 ID
            query: 用户查询
            file_hash: 文件哈希

        Returns:
            缓存结果，如果不存在或已过期则返回 None
        """
        key = self._generate_key(session_id, query, file_hash)

        if key not in self._cache:
            self._misses += 1
            logger.debug(f"缓存未命中: {key[:8]}...")
            return None

        entry = self._cache[key]

        # 检查是否过期
        if time.time() - entry["created_at"] > self.ttl_seconds:
            # 删除过期条目
            del self._cache[key]
            self._misses += 1
            logger.debug(f"缓存已过期: {key[:8]}...")
            return None

        # 更新访问时间（LRU）
        self._cache.move_to_end(key)
        entry["last_accessed"] = time.time()
        entry["hit_count"] += 1
        self._hits += 1

        logger.info(f"缓存命中: {key[:8]}... (命中次数: {entry['hit_count']})")
        return entry["result"]

    def set(
        self,
        session_id: str,
        query: str,
        file_hash: str,
        result: Dict[str, Any]
    ) -> None:
        """
        设置缓存

        Args:
            session_id: 会话 ID
            query: 用户查询
            file_hash: 文件哈希
            result: 要缓存的结果
        """
        key = self._generate_key(session_id, query, file_hash)

        # 检查缓存大小，执行 LRU 淘汰
        if len(self._cache) >= self.max_size and key not in self._cache:
            # 删除最旧的条目
            oldest_key, oldest_entry = self._cache.popitem(last=False)
            logger.debug(f"LRU 淘汰缓存: {oldest_key[:8]}... (存在时间: {time.time() - oldest_entry['created_at']:.1f}s)")

        entry = {
            "result": result,
            "created_at": time.time(),
            "last_accessed": time.time(),
            "hit_count": 0,
            "session_id": session_id,
            "query": query,
            "file_hash": file_hash
        }

        self._cache[key] = entry
        logger.info(f"缓存已设置: {key[:8]}... (当前缓存数: {len(self._cache)})")

    def delete(self, session_id: str) -> int:
        """
        删除会话的所有缓存

        Args:
            session_id: 会话 ID

        Returns:
            删除的条目数
        """
        count = 0
        keys_to_delete = []

        for key, entry in self._cache.items():
            if entry.get("session_id") == session_id:
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del self._cache[key]
            count += 1

        if count > 0:
            logger.info(f"删除会话 {session_id} 的缓存: {count} 条")

        return count

    def clear(self) -> None:
        """清空所有缓存"""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"清空所有缓存: {count} 条")

    def cleanup_expired(self) -> int:
        """
        清理过期缓存

        Returns:
            清理的条目数
        """
        now = time.time()
        keys_to_delete = []

        for key, entry in self._cache.items():
            if now - entry["created_at"] > self.ttl_seconds:
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del self._cache[key]

        if keys_to_delete:
            logger.info(f"清理过期缓存: {len(keys_to_delete)} 条")

        return len(keys_to_delete)

    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            统计信息字典
        """
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0

        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 4),
            "entries": [
                {
                    "key": key[:16] + "...",
                    "session_id": entry["session_id"],
                    "query": entry["query"][:50] + "..." if len(entry["query"]) > 50 else entry["query"],
                    "created_at": entry["created_at"],
                    "last_accessed": entry["last_accessed"],
                    "hit_count": entry["hit_count"]
                }
                for key, entry in list(self._cache.items())[:10]  # 只返回前 10 条
            ]
        }

    def get_session_cache_keys(self, session_id: str) -> list:
        """
        获取会话的所有缓存键

        Args:
            session_id: 会话 ID

        Returns:
            缓存键列表
        """
        keys = []
        for key, entry in self._cache.items():
            if entry.get("session_id") == session_id:
                keys.append(key)
        return keys


# 全局单例缓存管理器
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器单例"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager(
            max_size=100,
            ttl_seconds=3600
        )
    return _cache_manager


def calculate_file_hash(file_content: bytes) -> str:
    """
    计算文件内容的哈希值

    Args:
        file_content: 文件内容（字节）

    Returns:
        MD5 哈希值（前 8 位）
    """
    return hashlib.md5(file_content).hexdigest()[:8]


# 装饰器：缓存分析结果
def cache_analysis_result(func):
    """
    缓存分析结果的装饰器

    使用方法:
    @cache_analysis_result
    async def analyze_data(session_id: str, query: str, df: pd.DataFrame):
        ...
    """
    async def wrapper(session_id: str, query: str, file_hash: str, *args, **kwargs):
        cache_manager = get_cache_manager()

        # 尝试从缓存获取
        cached_result = cache_manager.get(session_id, query, file_hash)
        if cached_result is not None:
            logger.info(f"使用缓存结果: {query[:50]}...")
            return cached_result

        # 调用原函数
        result = await func(session_id, query, file_hash, *args, **kwargs)

        # 缓存结果
        cache_manager.set(session_id, query, file_hash, result)

        return result

    return wrapper


# 简单结果润色（模板化，不调用 LLM）
def template_polish(result: Dict[str, Any], intent: str = "overview") -> str:
    """
    使用模板生成分析结果描述（短路机制）

    Args:
        result: 分析结果
        intent: 意图类型

    Returns:
        分析描述文本
    """
    if intent == "overview":
        return _template_overview(result)
    elif intent == "trend":
        return _template_trend(result)
    elif intent == "correlation":
        return _template_correlation(result)
    elif intent == "distribution":
        return _template_distribution(result)
    elif intent == "comparison":
        return _template_comparison(result)
    elif intent == "moving_avg":
        return _template_moving_avg(result)
    else:
        return _template_default(result)


def _template_overview(result: Dict[str, Any]) -> str:
    """概览模板"""
    lines = ["## 数据概览", ""]
    lines.append(f"数据集包含 {result.get('row_count', 0)} 行和 {result.get('column_count', 0)} 列。")
    lines.append("")
    lines.append("### 列信息")
    for col, info in result.get('columns', {}).items():
        dtype = info.get('dtype', 'unknown')
        null_count = info.get('null_count', 0)
        null_ratio = info.get('null_ratio', 0)
        lines.append(f"- **{col}**: 类型 {dtype}, 缺失 {null_count} 个 ({null_ratio:.1%})")
    return "\n".join(lines)


def _template_trend(result: Dict[str, Any]) -> str:
    """趋势模板"""
    direction = result.get('direction', '未知')
    change_rate = result.get('change_rate', 0)
    r_squared = result.get('r_squared', 0)

    lines = ["## 趋势分析", ""]
    lines.append(f"数据呈现 **{direction}** 趋势，")
    if change_rate > 0:
        lines.append(f"整体增长了约 {abs(change_rate):.1f}%。")
    elif change_rate < 0:
        lines.append(f"整体下降了约 {abs(change_rate):.1f}%。")
    else:
        lines.append("整体保持平稳。")

    lines.append("")
    lines.append(f"拟合优度 (R²) 为 {r_squared:.4f}，")

    if r_squared > 0.8:
        lines.append("说明趋势较为明显。")
    elif r_squared > 0.5:
        lines.append("说明趋势中等。")
    else:
        lines.append("说明趋势较弱。")

    return "\n".join(lines)


def _template_correlation(result: Dict[str, Any]) -> str:
    """相关性模板"""
    method = result.get('method', 'pearson')
    pairs = result.get('pairs', [])

    lines = ["## 相关性分析", ""]
    lines.append(f"使用 **{method}** 相关系数进行分析。")
    lines.append("")

    if not pairs:
        lines.append("未发现显著相关性。")
        return "\n".join(lines)

    lines.append("### 变量关系")
    for pair in pairs[:5]:  # 最多显示 5 对
        x, y = pair['x'], pair['y']
        value = pair['value']

        if abs(value) > 0.8:
            strength = "强"
        elif abs(value) > 0.5:
            strength = "中等"
        elif abs(value) > 0.3:
            strength = "弱"
        else:
            strength = "极弱"

        direction = "正相关" if value > 0 else "负相关"
        lines.append(f"- **{x}** 与 **{y}**: {strength}{direction} (r={value:.4f})")

    return "\n".join(lines)


def _template_distribution(result: Dict[str, Any]) -> str:
    """分布模板"""
    lines = ["## 分布分析", ""]
    lines.append(f"数据均值为 **{result.get('mean', 0):.2f}**，")
    lines.append(f"中位数为 **{result.get('median', 0):.2f}**，")
    lines.append(f"标准差为 **{result.get('std', 0):.2f}**。")
    lines.append("")

    outlier_count = result.get('outlier_count', 0)
    if outlier_count > 0:
        lines.append(f"检测到 **{outlier_count}** 个异常值。")
    else:
        lines.append("未检测到异常值。")

    return "\n".join(lines)


def _template_comparison(result: Dict[str, Any]) -> str:
    """分组对比模板"""
    lines = ["## 分组对比分析", ""]

    stats = result.get('statistics', [])
    if not stats:
        lines.append("无法进行分组对比。")
        return "\n".join(lines)

    lines.append("### 各组统计")
    for item in stats:
        group = item.get('group', 'unknown')
        mean = item.get('mean', 0)
        count = item.get('count', 0)
        lines.append(f"- **{group}**: 均值 {mean:.2f} (n={count})")

    # ANOVA 结果
    anova = result.get('anova')
    if anova:
        p_value = anova.get('p_value', 1)
        significant = anova.get('significant', False)
        lines.append("")
        if significant:
            lines.append(f"方差分析显示各组间存在 **显著差异** (p={p_value:.4f})。")
        else:
            lines.append(f"方差分析显示各组间 **无显著差异** (p={p_value:.4f})。")

    return "\n".join(lines)


def _template_moving_avg(result: Dict[str, Any]) -> str:
    """移动平均模板"""
    method = result.get('method', 'simple')
    window = result.get('window', 7)

    lines = ["## 移动平均分析", ""]
    lines.append(f"使用 **{window}** 期 **{method}** 移动平均进行平滑处理。")
    lines.append("")
    lines.append("移动平均可以有效平滑短期波动，")
    lines.append("帮助识别数据的长期趋势方向。")

    return "\n".join(lines)


def _template_default(result: Dict[str, Any]) -> str:
    """默认模板"""
    return "分析已完成，请查看图表了解详情。"
