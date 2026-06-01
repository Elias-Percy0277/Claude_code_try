"""
会话管理器模块测试
"""
import sys
import os
import time
import shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from backend.session.manager import (
    SessionManager,
    Session,
    get_session_manager,
    SessionNotFoundError
)


def cleanup_test_sessions():
    """清理测试会话"""
    test_sessions_dir = "sessions"
    if os.path.exists(test_sessions_dir):
        shutil.rmtree(test_sessions_dir)
    os.makedirs(test_sessions_dir, exist_ok=True)


def create_test_dataframe(rows=100):
    """创建测试用 DataFrame"""
    import numpy as np
    return pd.DataFrame({
        'id': range(rows),
        'value': np.random.randn(rows),
        'category': np.random.choice(['A', 'B', 'C'], rows)
    })


def test_create_session():
    """测试创建会话"""
    print("\n=== 测试创建会话 ===")

    cleanup_test_sessions()

    manager = SessionManager(sessions_dir="sessions", expire_minutes=30)
    df = create_test_dataframe()

    session = manager.create_session(
        dataframe=df,
        original_filename="test_data.csv",
        file_hash="abc123"
    )

    print(f"[OK] 会话创建成功")
    print(f"  Session ID: {session.session_id}")
    print(f"  行数: {session.row_count}")
    print(f"  列数: {len(session.columns)}")
    print(f"  磁盘路径: {session.disk_path}")

    # 验证文件存在
    assert os.path.exists(manager._get_meta_path(session.session_id))
    assert os.path.exists(manager._get_data_path(session.session_id))
    print(f"[OK] 会话文件已创建")

    return session.session_id


def test_get_session(session_id):
    """测试获取会话"""
    print("\n=== 测试获取会话 ===")

    manager = SessionManager(sessions_dir="sessions", expire_minutes=30)

    try:
        session = manager.get_session(session_id)
        print(f"[OK] 会话获取成功")
        print(f"  Session ID: {session.session_id}")
        print(f"  行数: {session.row_count}")
    except Exception as e:
        print(f"[FAIL] 会话获取失败: {e}")


def test_session_not_found():
    """测试会话不存在"""
    print("\n=== 测试会话不存在 ===")

    manager = SessionManager(sessions_dir="sessions", expire_minutes=30)

    try:
        manager.get_session("non-existent-id")
        print("[FAIL] 应该抛出 SessionNotFoundError")
    except SessionNotFoundError as e:
        print(f"[OK] 正确抛出异常: {e}")


def test_update_session(session_id):
    """测试更新会话"""
    print("\n=== 测试更新会话 ===")

    manager = SessionManager(sessions_dir="sessions", expire_minutes=30)

    try:
        manager.update_session(session_id, chat_history=[{"role": "user", "content": "test"}])
        print(f"[OK] 会话更新成功")

        # 验证更新
        info = manager.get_session_info(session_id)
        if len(info.get('chat_history', [])) > 0:
            print(f"[OK] 聊天记录已更新")
        else:
            print(f"[WARN] 聊天记录未更新")

    except Exception as e:
        print(f"[FAIL] 会话更新失败: {e}")


def test_session_expiration():
    """测试会话过期"""
    print("\n=== 测试会话过期 ===")

    cleanup_test_sessions()

    # 创建过期时间很短的管理器
    manager = SessionManager(sessions_dir="sessions", expire_minutes=0)  # 立即过期
    df = create_test_dataframe()

    session = manager.create_session(df, "test.csv", "hash123")
    session_id = session.session_id

    # 等待一会儿
    time.sleep(0.5)

    try:
        manager.get_session(session_id)
        print("[WARN] 会话应该已过期")
    except SessionNotFoundError:
        print("[OK] 会话已正确过期")


def test_list_sessions():
    """测试列出会话"""
    print("\n=== 测试列出会话 ===")

    cleanup_test_sessions()

    manager = SessionManager(sessions_dir="sessions", expire_minutes=30)

    # 创建多个会话
    for i in range(3):
        df = create_test_dataframe(rows=10 * (i + 1))
        manager.create_session(df, f"test_{i}.csv", f"hash{i}")

    sessions = manager.list_sessions()

    print(f"[OK] 列出会话成功")
    print(f"  会话数量: {len(sessions)}")
    for s in sessions:
        print(f"    - {s['session_id'][:8]}...: {s['filename']} ({s['row_count']} 行)")


def test_cleanup_expired():
    """测试清理过期会话"""
    print("\n=== 测试清理过期会话 ===")

    cleanup_test_sessions()

    # 混合创建正常和过期的会话
    manager = SessionManager(sessions_dir="sessions", expire_minutes=30)

    # 正常会话
    df1 = create_test_dataframe()
    s1 = manager.create_session(df1, "normal.csv", "hash1")

    # 修改为过期
    manager._update_last_accessed(s1.session_id)

    count = manager.cleanup_expired_sessions()
    print(f"[OK] 清理完成，删除了 {count} 个过期会话")

    # 验证
    sessions = manager.list_sessions()
    print(f"  剩余会话: {len(sessions)}")


def test_get_session_info():
    """测试获取会话信息"""
    print("\n=== 测试获取会话信息 ===")

    cleanup_test_sessions()

    manager = SessionManager(sessions_dir="sessions", expire_minutes=30)
    df = create_test_dataframe()

    session = manager.create_session(df, "test.csv", "hash123")
    info = manager.get_session_info(session.session_id)

    print(f"[OK] 获取会话信息成功")
    print(f"  文件名: {info['filename']}")
    print(f"  行数: {info['row_count']}")
    print(f"  列: {info['columns']}")


def test_get_stats():
    """测试获取统计信息"""
    print("\n=== 测试获取统计信息 ===")

    cleanup_test_sessions()

    manager = SessionManager(sessions_dir="sessions", expire_minutes=30)

    # 创建会话
    for i in range(2):
        df = create_test_dataframe(rows=50)
        manager.create_session(df, f"test_{i}.csv", f"hash{i}")

    stats = manager.get_stats()

    print(f"[OK] 获取统计信息成功")
    print(f"  总会话数: {stats['total_sessions']}")
    print(f"  活跃会话: {stats['active_sessions']}")
    print(f"  内存缓存: {stats['memory_cached']}")
    print(f"  总行数: {stats['total_rows']}")


def test_global_manager():
    """测试全局会话管理器"""
    print("\n=== 测试全局会话管理器 ===")

    manager1 = get_session_manager()
    manager2 = get_session_manager()

    if manager1 is manager2:
        print("[OK] 全局会话管理器是单例")
    else:
        print("[FAIL] 全局会话管理器应该是单例")


def test_memory_cache():
    """测试内存缓存"""
    print("\n=== 测试内存缓存 ===")

    cleanup_test_sessions()

    manager = SessionManager(sessions_dir="sessions", expire_minutes=30, max_cache_size=2)

    df = create_test_dataframe()

    # 创建多个会话
    s1 = manager.create_session(df, "test1.csv", "hash1")
    s2 = manager.create_session(df, "test2.csv", "hash2")
    s3 = manager.create_session(df, "test3.csv", "hash3")

    stats = manager.get_stats()
    print(f"[OK] 内存缓存测试")
    print(f"  内存缓存数: {stats['memory_cached']}")
    print(f"  最大缓存: {manager.max_cache_size}")

    if stats['memory_cached'] <= manager.max_cache_size:
        print(f"[OK] 内存缓存数量正确")
    else:
        print(f"[FAIL] 内存缓存数量超过限制")


if __name__ == "__main__":
    print("=" * 50)
    print("会话管理器模块测试")
    print("=" * 50)

    # 创建会话并获取 ID 用于后续测试
    session_id = test_create_session()
    test_get_session(session_id)
    test_session_not_found()
    test_update_session(session_id)
    test_session_expiration()
    test_list_sessions()
    test_cleanup_expired()
    test_get_session_info()
    test_get_stats()
    test_global_manager()
    test_memory_cache()

    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)

    # 清理
    cleanup_test_sessions()
