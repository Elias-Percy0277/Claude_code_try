"""
意图解析模块测试
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from backend.core.data_loader import load_data
from backend.core.intent_parser import (
    parse_intent_fallback, _levenshtein_distance,
    _validate_and_fix_columns, SUPPORTED_INTENTS
)


def create_test_dataframe():
    """创建测试用的 DataFrame"""
    return pd.DataFrame({
        '日期': pd.date_range('2024-01-01', periods=30),
        '销售额': [1000 + i * 50 + (i % 7) * 100 for i in range(30)],
        '利润': [200 + i * 10 for i in range(30)],
        '地区': ['北京', '上海', '广州', '深圳'] * 7 + ['北京', '上海'],
        '产品类别': ['电子产品', '家居用品'] * 15,
    })


def test_fallback_parser():
    """测试规则引擎降级方案"""
    print("\n=== 测试规则引擎解析器 ===")

    df = create_test_dataframe()

    # 测试各种查询
    test_queries = [
        ("看看数据概览", "overview"),
        ("分析销售额趋势", "trend"),
        ("销售额和利润的相关性", "correlation"),
        ("各地区的销售额对比", "comparison"),
        ("销售额的分布情况", "distribution"),
        ("计算销售额的移动平均", "moving_avg"),
    ]

    for query, expected_intent in test_queries:
        try:
            result = parse_intent_fallback(query, df)
            intent = result["tasks"][0]["intent"]
            status = "[OK]" if intent == expected_intent else "[WARN]"
            print(f"{status} 查询: '{query}' -> 意图: {intent} (期望: {expected_intent})")
        except Exception as e:
            print(f"[FAIL] 查询: '{query}' -> 错误: {e}")


def test_levenshtein_distance():
    """测试编辑距离计算"""
    print("\n=== 测试编辑距离计算 ===")

    test_cases = [
        ("销售额", "销售额", 0),
        ("销售额", "销售", 2),
        ("销售额", "销额", 1),
        ("销售额", "利润", 4),
        ("销售额", "sales", 7),
    ]

    for s1, s2, expected in test_cases:
        distance = _levenshtein_distance(s1, s2)
        status = "[OK]" if distance == expected else "[WARN]"
        print(f"{status} '{s1}' vs '{s2}': {distance} (期望: {expected})")


def test_column_validation():
    """测试列名校验和修复"""
    print("\n=== 测试列名校验和修复 ===")

    actual_columns = ['日期', '销售额', '利润', '地区', '产品类别']

    test_cases = [
        # 测试精确匹配
        (
            [{"intent": "trend", "target_columns": ["销售额"]}],
            [{"intent": "trend", "target_columns": ["销售额"]}]
        ),
        # 测试模糊匹配
        (
            [{"intent": "trend", "target_columns": ["销售"]}],  # 错误列名
            [{"intent": "trend", "target_columns": ["销售额"]}]  # 修复后
        ),
        # 测试多个列
        (
            [{"intent": "correlation", "target_columns": ["销售额", "利润"]}],
            [{"intent": "correlation", "target_columns": ["销售额", "利润"]}]
        ),
    ]

    for tasks, expected in test_cases:
        try:
            result = _validate_and_fix_columns(tasks, actual_columns)
            if result == expected:
                print(f"[OK] 列名校验通过: {tasks[0]['target_columns']}")
            else:
                print(f"[WARN] 列名校验结果: {result}, 期望: {expected}")
        except Exception as e:
            print(f"[FAIL] 列名校验失败: {e}")


def test_supported_intents():
    """测试支持的意图类型"""
    print("\n=== 测试支持的意图类型 ===")

    print(f"支持的意图类型 ({len(SUPPORTED_INTENTS)} 个):")
    for intent in sorted(SUPPORTED_INTENTS):
        print(f"  - {intent}")


def test_data_types_detection():
    """测试数据类型检测"""
    print("\n=== 测试数据类型检测 ===")

    df = create_test_dataframe()

    print(f"数据集形状: {df.shape}")
    print(f"数值列: {df.select_dtypes(include=['number']).columns.tolist()}")
    print(f"日期列: {df.select_dtypes(include=['datetime64']).columns.tolist()}")
    print(f"分类型列: {df.select_dtypes(include=['object']).columns.tolist()}")


if __name__ == "__main__":
    print("=" * 50)
    print("意图解析模块测试")
    print("=" * 50)

    test_supported_intents()
    test_data_types_detection()
    test_fallback_parser()
    test_levenshtein_distance()
    test_column_validation()

    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)
