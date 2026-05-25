"""
可视化模块测试
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import json
from backend.core.visualizer import (
    create_line_chart,
    create_moving_average_chart,
    create_correlation_heatmap,
    create_scatter_plot,
    create_bar_chart,
    create_grouped_bar_chart,
    create_histogram_chart,
    create_box_plot,
    create_pie_chart,
    create_seasonal_chart,
    VisualizationError
)


def test_line_chart():
    """测试折线图"""
    print("\n=== 测试折线图 ===")

    df = pd.DataFrame({
        '日期': pd.date_range('2024-01-01', periods=10),
        '销售额': [100, 120, 115, 130, 145, 140, 155, 160, 150, 170],
        '利润': [20, 25, 23, 28, 30, 28, 35, 36, 32, 40]
    })

    try:
        result = create_line_chart(df, '日期', ['销售额', '利润'], '销售额与利润趋势')
        print(f"[OK] 折线图创建成功")
        print(f"  图表类型: {result['chart_type']}")
        print(f"  系列数量: {len(result['option']['series'])}")
        print(f"  数据点数量: {len(result['option']['xAxis']['data'])}")
    except Exception as e:
        print(f"[FAIL] 折线图创建失败: {e}")


def test_moving_average_chart():
    """测试移动平均图表"""
    print("\n=== 测试移动平均图表 ===")

    original = [100, 105, 102, 110, 115, 112, 120, 125, 122, 130]
    smoothed = [None, None, 102.3, 105.7, 109.0, 112.3, 115.7, 119.0, 122.3, 125.7]

    try:
        result = create_moving_average_chart(original, smoothed, '7天移动平均')
        print(f"[OK] 移动平均图表创建成功")
        print(f"  图表类型: {result['chart_type']}")
        print(f"  系列数量: {len(result['option']['series'])}")
    except Exception as e:
        print(f"[FAIL] 移动平均图表创建失败: {e}")


def test_correlation_heatmap():
    """测试相关性热力图"""
    print("\n=== 测试相关性热力图 ===")

    corr_matrix = {
        '销售额': {'销售额': 1.0, '利润': 0.85, '成本': 0.72},
        '利润': {'销售额': 0.85, '利润': 1.0, '成本': 0.65},
        '成本': {'销售额': 0.72, '利润': 0.65, '成本': 1.0}
    }
    columns = ['销售额', '利润', '成本']

    try:
        result = create_correlation_heatmap(corr_matrix, columns, '变量相关性分析')
        print(f"[OK] 相关性热力图创建成功")
        print(f"  图表类型: {result['chart_type']}")
        print(f"  热力图数据点: {len(result['option']['series'][0]['data'])}")
    except Exception as e:
        print(f"[FAIL] 相关性热力图创建失败: {e}")


def test_scatter_plot():
    """测试散点图"""
    print("\n=== 测试散点图 ===")

    x_data = np.random.randn(100) * 10 + 50
    y_data = x_data * 0.8 + np.random.randn(100) * 5 + 20

    try:
        result = create_scatter_plot(x_data.tolist(), y_data.tolist(), 'X', 'Y', '散点图示例')
        print(f"[OK] 散点图创建成功")
        print(f"  图表类型: {result['chart_type']}")
        print(f"  数据点数量: {len(result['option']['series'][0]['data'])}")
    except Exception as e:
        print(f"[FAIL] 散点图创建失败: {e}")


def test_bar_chart():
    """测试柱状图"""
    print("\n=== 测试柱状图 ===")

    categories = ['北京', '上海', '广州', '深圳']
    values = [120, 150, 90, 135]

    try:
        result = create_bar_chart(categories, values, '各地区销售额')
        print(f"[OK] 柱状图创建成功")
        print(f"  图表类型: {result['chart_type']}")
        print(f"  类别数量: {len(categories)}")
    except Exception as e:
        print(f"[FAIL] 柱状图创建失败: {e}")


def test_grouped_bar_chart():
    """测试分组柱状图"""
    print("\n=== 测试分组柱状图 ===")

    groups = ['北京', '上海', '广州']
    series_data = [
        {'name': 'Q1', 'data': [100, 120, 80]},
        {'name': 'Q2', 'data': [110, 130, 85]},
        {'name': 'Q3', 'data': [120, 140, 90]}
    ]

    try:
        result = create_grouped_bar_chart(groups, series_data, '季度销售额对比')
        print(f"[OK] 分组柱状图创建成功")
        print(f"  图表类型: {result['chart_type']}")
        print(f"  系列数量: {len(result['option']['series'])}")
    except Exception as e:
        print(f"[FAIL] 分组柱状图创建失败: {e}")


def test_histogram():
    """测试直方图"""
    print("\n=== 测试直方图 ===")

    bin_edges = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    counts = [5, 12, 25, 40, 35, 28, 18, 10, 5, 2]

    try:
        result = create_histogram_chart(bin_edges, counts, '数值分布')
        print(f"[OK] 直方图创建成功")
        print(f"  图表类型: {result['chart_type']}")
        print(f"  分箱数量: {len(counts)}")
    except Exception as e:
        print(f"[FAIL] 直方图创建失败: {e}")


def test_pie_chart():
    """测试饼图"""
    print("\n=== 测试饼图 ===")

    data = [
        {'name': '电子产品', 'value': 450},
        {'name': '家居用品', 'value': 300},
        {'name': '服装', 'value': 200},
        {'name': '食品', 'value': 150}
    ]

    try:
        result = create_pie_chart(data, '产品类别占比', donut=True)
        print(f"[OK] 饼图创建成功")
        print(f"  图表类型: {result['chart_type']}")
        print(f"  数据项数量: {len(data)}")
    except Exception as e:
        print(f"[FAIL] 饼图创建失败: {e}")


def test_seasonal_chart():
    """测试季节性分解图表"""
    print("\n=== 测试季节性分解图表 ===")

    dates = pd.date_range('2024-01-01', periods=30).strftime('%Y-%m-%d').tolist()
    original = [100 + i * 2 + 5 * np.sin(i * 0.5) for i in range(30)]
    trend = [100 + i * 2 for i in range(30)]
    seasonal = [5 * np.sin(i * 0.5) for i in range(30)]

    try:
        result = create_seasonal_chart(dates, original, trend, seasonal, '销售数据季节性分解')
        print(f"[OK] 季节性分解图表创建成功")
        print(f"  图表类型: {result['chart_type']}")
        print(f"  系列数量: {len(result['option']['series'])}")
    except Exception as e:
        print(f"[FAIL] 季节性分解图表创建失败: {e}")


def test_json_serialization():
    """测试 JSON 序列化"""
    print("\n=== 测试 JSON 序列化 ===")

    df = pd.DataFrame({
        'x': range(5),
        'y': [10, 20, 15, 25, 30]
    })

    try:
        chart = create_line_chart(df, 'x', ['y'], '测试图表')
        json_str = json.dumps(chart, ensure_ascii=False)
        print(f"[OK] JSON 序列化成功")
        print(f"  JSON 长度: {len(json_str)} 字符")

        # 验证可以反序列化
        parsed = json.loads(json_str)
        assert parsed['chart_type'] == 'line'
        print(f"[OK] JSON 反序列化验证通过")
    except Exception as e:
        print(f"[FAIL] JSON 序列化失败: {e}")


if __name__ == "__main__":
    print("=" * 50)
    print("可视化模块测试")
    print("=" * 50)

    test_line_chart()
    test_moving_average_chart()
    test_correlation_heatmap()
    test_scatter_plot()
    test_bar_chart()
    test_grouped_bar_chart()
    test_histogram()
    test_pie_chart()
    test_seasonal_chart()
    test_json_serialization()

    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)
