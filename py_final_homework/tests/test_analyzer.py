"""
分析引擎模块测试
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from backend.core.analyzer import (
    calculate_statistics,
    analyze_correlation,
    analyze_trend,
    calculate_moving_average,
    analyze_distribution,
    analyze_comparison,
    analyze_overview,
    safe_seasonal_decompose,
    AnalysisError
)


def create_test_dataframe():
    """创建测试用的 DataFrame"""
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    np.random.seed(42)

    # 创建带趋势和季节性的数据
    trend = np.linspace(100, 200, 100)
    seasonal = 10 * np.sin(np.arange(100) * 2 * np.pi / 7)  # 7天周期
    noise = np.random.normal(0, 5, 100)

    return pd.DataFrame({
        '日期': dates,
        '销售额': trend + seasonal + noise,
        '利润': trend * 0.2 + seasonal * 0.5 + noise * 0.5,
        '地区': np.random.choice(['北京', '上海', '广州', '深圳'], 100),
        '产品类别': np.random.choice(['电子产品', '家居用品', '服装'], 100),
    })


def test_calculate_statistics():
    """测试统计计算"""
    print("\n=== 测试统计计算 ===")

    df = create_test_dataframe()

    try:
        result = calculate_statistics(df)
        print(f"[OK] 统计计算成功，分析了 {len(result)} 个数值列")
        for col, stats in result.items():
            print(f"  {col}: mean={stats['mean']:.2f}, std={stats['std']:.2f}")
    except Exception as e:
        print(f"[FAIL] 统计计算失败: {e}")


def test_analyze_correlation():
    """测试相关性分析"""
    print("\n=== 测试相关性分析 ===")

    df = create_test_dataframe()

    try:
        result = analyze_correlation(df, method='pearson')
        print(f"[OK] 相关性分析成功，分析了 {len(result['columns'])} 个列")
        print(f"  相关系数对: {len(result['pairs'])} 个")
        for pair in result['pairs'][:3]:
            print(f"    {pair['x']} vs {pair['y']}: {pair['value']:.4f}")
    except Exception as e:
        print(f"[FAIL] 相关性分析失败: {e}")


def test_analyze_trend():
    """测试趋势分析"""
    print("\n=== 测试趋势分析 ===")

    df = create_test_dataframe()

    try:
        result = analyze_trend(df, '销售额', '日期')
        print(f"[OK] 趋势分析成功")
        print(f"  方向: {result['direction']}")
        print(f"  斜率: {result['slope']:.4f}")
        print(f"  R方: {result['r_squared']:.4f}")
        print(f"  变化率: {result['change_rate']:.2f}%")
    except Exception as e:
        print(f"[FAIL] 趋势分析失败: {e}")


def test_moving_average():
    """测试移动平均"""
    print("\n=== 测试移动平均 ===")

    df = create_test_dataframe()

    try:
        result = calculate_moving_average(df, '销售额', window=7, method='simple')
        print(f"[OK] 移动平均计算成功")
        print(f"  方法: {result['method']}")
        print(f"  窗口: {result['window']}")
        print(f"  数据点: {len(result['data'])}")
        # 显示前几个值
        print(f"  前5个值:")
        for i, point in enumerate(result['data'][:5]):
            if point['smoothed'] is not None:
                print(f"    [{i}] original={point['original']:.2f}, smoothed={point['smoothed']:.2f}")
    except Exception as e:
        print(f"[FAIL] 移动平均计算失败: {e}")


def test_seasonal_decompose():
    """测试季节性分解"""
    print("\n=== 测试季节性分解 ===")

    df = create_test_dataframe()

    try:
        result = safe_seasonal_decompose(df, '日期', '销售额')
        if result['success']:
            print(f"[OK] 季节性分解成功")
            print(f"  周期: {result['period']}")
            print(f"  趋势点数: {len(result['trend'])}")
            print(f"  季节点数: {len(result['seasonal'])}")
        else:
            print(f"[WARN] 季节性分解失败: {result['reason']}")
            print(f"  降级方案: {result['fallback']}")
    except Exception as e:
        print(f"[FAIL] 季节性分解测试失败: {e}")


def test_analyze_distribution():
    """测试分布分析"""
    print("\n=== 测试分布分析 ===")

    df = create_test_dataframe()

    try:
        result = analyze_distribution(df, '销售额')
        print(f"[OK] 分布分析成功")
        print(f"  均值: {result['mean']:.2f}")
        print(f"  中位数: {result['median']:.2f}")
        print(f"  标准差: {result['std']:.2f}")
        print(f"  异常值数量: {result['outlier_count']}")
        print(f"  直方图箱数: {len(result['histogram'])}")
    except Exception as e:
        print(f"[FAIL] 分布分析失败: {e}")


def test_analyze_comparison():
    """测试分组对比分析"""
    print("\n=== 测试分组对比分析 ===")

    df = create_test_dataframe()

    try:
        result = analyze_comparison(df, '销售额', '地区')
        print(f"[OK] 分组对比分析成功")
        print(f"  分组数量: {len(result['groups'])}")
        print(f"  分组: {result['groups']}")
        if 'anova' in result:
            print(f"  ANOVA F统计量: {result['anova']['f_statistic']:.4f}")
            print(f"  ANOVA p值: {result['anova']['p_value']:.4f}")
            print(f"  显著差异: {'是' if result['anova']['significant'] else '否'}")
    except Exception as e:
        print(f"[FAIL] 分组对比分析失败: {e}")


def test_analyze_overview():
    """测试数据概览"""
    print("\n=== 测试数据概览 ===")

    df = create_test_dataframe()

    try:
        result = analyze_overview(df)
        print(f"[OK] 数据概览成功")
        print(f"  行数: {result['shape']['rows']}")
        print(f"  列数: {result['shape']['columns']}")
        print(f"  内存使用: {result['memory_usage']}")
        print(f"  列信息:")
        for col, info in result['columns'].items():
            print(f"    {col}: {info['dtype']}, 缺失={info['null_count']}")
    except Exception as e:
        print(f"[FAIL] 数据概览失败: {e}")


def test_error_handling():
    """测试错误处理"""
    print("\n=== 测试错误处理 ===")

    df = create_test_dataframe()

    # 测试不存在的列
    try:
        calculate_statistics(df, columns=['不存在的列'])
        print("[WARN] 应该抛出 AnalysisError")
    except AnalysisError as e:
        print(f"[OK] 正确捕获错误: {e}")

    # 测试数据不足
    try:
        small_df = df.head(1)
        analyze_correlation(small_df)
        print("[WARN] 应该抛出 AnalysisError")
    except AnalysisError as e:
        print(f"[OK] 正确捕获错误: {e}")


if __name__ == "__main__":
    print("=" * 50)
    print("分析引擎模块测试")
    print("=" * 50)

    test_analyze_overview()
    test_calculate_statistics()
    test_analyze_correlation()
    test_analyze_trend()
    test_moving_average()
    test_seasonal_decompose()
    test_analyze_distribution()
    test_analyze_comparison()
    test_error_handling()

    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)
