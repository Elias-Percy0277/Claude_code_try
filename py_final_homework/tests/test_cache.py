"""
缓存管理器模块测试
"""
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.cache.cache import (
    CacheManager,
    get_cache_manager,
    calculate_file_hash,
    template_polish,
    cache_analysis_result
)


def test_cache_basic_operations():
    """测试缓存基本操作"""
    print("\n=== 测试缓存基本操作 ===")

    cache = CacheManager(max_size=5, ttl_seconds=60)

    # 测试设置和获取
    cache.set("session1", "分析销售额", "abc123", {"result": "success"})
    result = cache.get("session1", "分析销售额", "abc123")

    if result and result["result"] == "success":
        print("[OK] 缓存设置和获取成功")
    else:
        print("[FAIL] 缓存设置和获取失败")

    # 测试缓存未命中
    result = cache.get("session1", "其他查询", "abc123")
    if result is None:
        print("[OK] 缓存未命中正确返回 None")
    else:
        print("[FAIL] 缓存未命中应该返回 None")

    # 测试不同的 file_hash
    result = cache.get("session1", "分析销售额", "def456")
    if result is None:
        print("[OK] 不同 file_hash 正确返回 None")
    else:
        print("[FAIL] 不同 file_hash 应该返回 None")


def test_cache_lru():
    """测试 LRU 淘汰"""
    print("\n=== 测试 LRU 淘汰 ===")

    cache = CacheManager(max_size=3, ttl_seconds=60)

    # 填满缓存
    cache.set("s1", "q1", "h1", {"data": 1})
    cache.set("s2", "q2", "h2", {"data": 2})
    cache.set("s3", "q3", "h3", {"data": 3})

    # 访问第一个条目（更新 LRU）
    cache.get("s1", "q1", "h1")

    # 添加第 4 个条目，应该淘汰最旧的（s2）
    cache.set("s4", "q4", "h4", {"data": 4})

    # 验证
    if cache.get("s1", "q1", "h1") is not None:
        print("[OK] s1 仍在缓存中")
    else:
        print("[FAIL] s1 应该仍在缓存中")

    if cache.get("s2", "q2", "h2") is None:
        print("[OK] s2 已被 LRU 淘汰")
    else:
        print("[FAIL] s2 应该被淘汰")

    if cache.get("s3", "q3", "h3") is not None:
        print("[OK] s3 仍在缓存中")
    else:
        print("[FAIL] s3 应该仍在缓存中")


def test_cache_expiration():
    """测试缓存过期"""
    print("\n=== 测试缓存过期 ===")

    cache = CacheManager(max_size=10, ttl_seconds=1)  # 1 秒过期

    cache.set("s1", "q1", "h1", {"data": 1})

    # 立即获取应该成功
    if cache.get("s1", "q1", "h1") is not None:
        print("[OK] 新缓存可以获取")
    else:
        print("[FAIL] 新缓存应该可以获取")

    # 等待过期
    time.sleep(1.5)

    # 获取应该失败（已过期）
    if cache.get("s1", "q1", "h1") is None:
        print("[OK] 过期缓存正确返回 None")
    else:
        print("[FAIL] 过期缓存应该返回 None")


def test_cache_stats():
    """测试缓存统计"""
    print("\n=== 测试缓存统计 ===")

    cache = CacheManager(max_size=10, ttl_seconds=60)

    cache.set("s1", "q1", "h1", {"data": 1})
    cache.set("s2", "q2", "h2", {"data": 2})

    # 命中
    cache.get("s1", "q1", "h1")
    cache.get("s1", "q1", "h1")

    # 未命中
    cache.get("s1", "q2", "h1")
    cache.get("s2", "q1", "h1")

    stats = cache.get_stats()
    print(f"[OK] 缓存统计:")
    print(f"  大小: {stats['size']}/{stats['max_size']}")
    print(f"  命中: {stats['hits']}")
    print(f"  未命中: {stats['misses']}")
    print(f"  命中率: {stats['hit_rate']:.2%}")


def test_cache_delete_session():
    """测试删除会话缓存"""
    print("\n=== 测试删除会话缓存 ===")

    cache = CacheManager(max_size=10, ttl_seconds=60)

    cache.set("s1", "q1", "h1", {"data": 1})
    cache.set("s1", "q2", "h1", {"data": 2})
    cache.set("s2", "q1", "h1", {"data": 3})

    count = cache.delete("s1")

    if count == 2:
        print("[OK] 正确删除了 2 条缓存")
    else:
        print(f"[FAIL] 应该删除 2 条缓存，实际删除了 {count}")

    # 验证
    if cache.get("s1", "q1", "h1") is None and cache.get("s1", "q2", "h1") is None:
        print("[OK] s1 的缓存已全部删除")
    else:
        print("[FAIL] s1 的缓存应该全部被删除")

    if cache.get("s2", "q1", "h1") is not None:
        print("[OK] s2 的缓存仍然存在")
    else:
        print("[FAIL] s2 的缓存不应该被删除")


def test_file_hash():
    """测试文件哈希计算"""
    print("\n=== 测试文件哈希计算 ===")

    content1 = b"hello world"
    content2 = b"hello world"
    content3 = b"hello"

    hash1 = calculate_file_hash(content1)
    hash2 = calculate_file_hash(content2)
    hash3 = calculate_file_hash(content3)

    if hash1 == hash2:
        print(f"[OK] 相同内容产生相同哈希: {hash1}")
    else:
        print("[FAIL] 相同内容应该产生相同哈希")

    if hash1 != hash3:
        print(f"[OK] 不同内容产生不同哈希: {hash1} vs {hash3}")
    else:
        print("[FAIL] 不同内容应该产生不同哈希")


def test_template_polish():
    """测试模板化结果润色"""
    print("\n=== 测试模板化结果润色 ===")

    # 测试概览模板
    overview_result = {
        "row_count": 100,
        "column_count": 5,
        "columns": {
            "销售额": {"dtype": "int64", "null_count": 0, "null_ratio": 0.0},
            "利润": {"dtype": "int64", "null_count": 5, "null_ratio": 0.05}
        }
    }
    text = template_polish(overview_result, "overview")
    if "数据概览" in text and "100 行" in text:
        print("[OK] 概览模板生成成功")
    else:
        print("[FAIL] 概览模板生成失败")

    # 测试趋势模板
    trend_result = {
        "direction": "上升",
        "change_rate": 25.5,
        "r_squared": 0.85
    }
    text = template_polish(trend_result, "trend")
    if "上升" in text and "25.5%" in text:
        print("[OK] 趋势模板生成成功")
    else:
        print("[FAIL] 趋势模板生成失败")

    # 测试相关性模板
    corr_result = {
        "method": "pearson",
        "pairs": [
            {"x": "销售额", "y": "利润", "value": 0.85}
        ]
    }
    text = template_polish(corr_result, "correlation")
    if "相关" in text and "0.85" in text:
        print("[OK] 相关性模板生成成功")
    else:
        print("[FAIL] 相关性模板生成失败")


def test_global_cache_manager():
    """测试全局缓存管理器"""
    print("\n=== 测试全局缓存管理器 ===")

    manager1 = get_cache_manager()
    manager2 = get_cache_manager()

    if manager1 is manager2:
        print("[OK] 全局缓存管理器是单例")
    else:
        print("[FAIL] 全局缓存管理器应该是单例")


if __name__ == "__main__":
    print("=" * 50)
    print("缓存管理器模块测试")
    print("=" * 50)

    test_cache_basic_operations()
    test_cache_lru()
    test_cache_expiration()
    test_cache_stats()
    test_cache_delete_session()
    test_file_hash()
    test_template_polish()
    test_global_cache_manager()

    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)
