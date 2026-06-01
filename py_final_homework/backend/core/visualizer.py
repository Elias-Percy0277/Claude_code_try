"""
可视化生成器
使用 pyecharts 生成 ECharts JSON 配置
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

# 可选导入 pyecharts
try:
    from pyecharts.charts import (
        Line, Bar, Pie, Scatter, HeatMap,
        Timeline, Grid
    )
    from pyecharts import options as opts
    from pyecharts.globals import ThemeType
    HAS_PYECHARTS = True
except ImportError:
    HAS_PYECHARTS = False
    logger.warning("pyecharts 未安装，可视化功能将不可用")


class VisualizationError(Exception):
    """可视化错误"""
    pass


def _create_base_title(title: str, subtitle: str = "") -> Dict:
    """创建基础标题配置"""
    return {
        "text": title,
        "subtext": subtitle,
        "left": "center",
        "textStyle": {"fontSize": 16}
    }


def _create_base_tooltip() -> Dict:
    """创建基础提示框配置"""
    return {
        "trigger": "axis",
        "axisPointer": {"type": "cross"}
    }


def _create_base_legend(data: Optional[List[str]] = None) -> Dict:
    """创建基础图例配置"""
    config = {
        "top": "8%",
        "type": "scroll"
    }
    if data:
        config["data"] = data
    return config


def create_line_chart(
    df: pd.DataFrame,
    x_column: str,
    y_columns: List[str],
    title: str = "折线图",
    smooth: bool = False,
    x_name: str = "",
    y_name: str = ""
) -> Dict[str, Any]:
    """
    创建折线图（用于趋势分析）

    Args:
        df: 数据集
        x_column: X 轴列名
        y_columns: Y 轴列名列表
        title: 图表标题
        smooth: 是否平滑曲线
        x_name: X 轴标签
        y_name: Y 轴标签

    Returns:
        ECharts option JSON
    """
    # 准备数据
    x_data = df[x_column].tolist()
    series = []

    for col in y_columns:
        if col in df.columns:
            series.append({
                "name": col,
                "type": "line",
                "data": df[col].tolist(),
                "smooth": smooth,
                "symbol": "circle",
                "symbolSize": 6
            })

    y_label = y_name or (y_columns[0] if len(y_columns) == 1 else "")
    return {
        "chart_type": "line",
        "option": {
            "title": _create_base_title(title),
            "tooltip": _create_base_tooltip(),
            "legend": _create_base_legend(y_columns),
            "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": x_data,
                "boundaryGap": False,
                "name": x_name or x_column,
                "nameLocation": "middle",
                "nameGap": 30
            },
            "yAxis": {"type": "value", "name": y_label, "nameLocation": "end"},
            "series": series
        }
    }


def create_moving_average_chart(
    original_data: List,
    smoothed_data: List,
    title: str = "移动平均",
    x_name: str = "序号",
    y_name: str = "数值"
) -> Dict[str, Any]:
    """
    创建移动平均图表

    Args:
        original_data: 原始数据
        smoothed_data: 平滑后数据
        title: 图表标题
        x_name: X 轴标签
        y_name: Y 轴标签

    Returns:
        ECharts option JSON
    """
    x_data = list(range(len(original_data)))

    return {
        "chart_type": "line",
        "option": {
            "title": _create_base_title(title),
            "tooltip": _create_base_tooltip(),
            "legend": _create_base_legend(["原始数据", "移动平均"]),
            "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": x_data,
                "boundaryGap": False,
                "name": x_name,
                "nameLocation": "middle",
                "nameGap": 30
            },
            "yAxis": {"type": "value", "name": y_name, "nameLocation": "end"},
            "series": [
                {
                    "name": "原始数据",
                    "type": "line",
                    "data": original_data,
                    "symbol": "circle",
                    "symbolSize": 4,
                    "itemStyle": {"opacity": 0.6},
                    "lineStyle": {"opacity": 0.6}
                },
                {
                    "name": "移动平均",
                    "type": "line",
                    "data": smoothed_data,
                    "smooth": True,
                    "lineStyle": {"width": 3},
                    "itemStyle": {"color": "#ff6b6b"}
                }
            ]
        }
    }


def create_correlation_heatmap(
    corr_matrix: Dict[str, Dict[str, float]],
    columns: List[str],
    title: str = "相关性热力图"
) -> Dict[str, Any]:
    """
    创建相关性热力图

    Args:
        corr_matrix: 相关系数矩阵
        columns: 列名列表
        title: 图表标题

    Returns:
        ECharts option JSON
    """
    # 准备热力图数据
    heatmap_data = []
    for i, col1 in enumerate(columns):
        for j, col2 in enumerate(columns):
            value = corr_matrix.get(col1, {}).get(col2, 0)
            heatmap_data.append([j, i, round(value, 4)])

    return {
        "chart_type": "heatmap",
        "option": {
            "title": _create_base_title(title),
            "tooltip": {
                "trigger": "item",
                "formatter": function_formatter_heatmap()
            },
            "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": columns,
                "splitArea": {"show": True}
            },
            "yAxis": {
                "type": "category",
                "data": columns,
                "splitArea": {"show": True}
            },
            "visualMap": {
                "min": -1,
                "max": 1,
                "calculable": True,
                "orient": "horizontal",
                "left": "center",
                "bottom": "5%",
                "inRange": {
                    "color": ["#313695", "#4575b4", "#74add1", "#abd9e9",
                              "#e0f3f8", "#fee090", "#fdae61", "#f46d43",
                              "#d73027", "#a50026"]
                }
            },
            "series": [{
                "type": "heatmap",
                "data": heatmap_data,
                "label": {"show": True},
                "emphasis": {
                    "itemStyle": {
                        "shadowBlur": 10,
                        "shadowColor": "rgba(0, 0, 0, 0.5)"
                    }
                }
            }]
        }
    }


def create_scatter_plot(
    x_data: List,
    y_data: List,
    x_name: str = "X",
    y_name: str = "Y",
    title: str = "散点图"
) -> Dict[str, Any]:
    """
    创建散点图（用于相关性分析）

    Args:
        x_data: X 轴数据
        y_data: Y 轴数据
        x_name: X 轴名称
        y_name: Y 轴名称
        title: 图表标题

    Returns:
        ECharts option JSON
    """
    # 合并数据
    scatter_data = [[x, y] for x, y in zip(x_data, y_data)]

    return {
        "chart_type": "scatter",
        "option": {
            "title": _create_base_title(title),
            "tooltip": {
                "trigger": "item",
                "formatter": function_formatter_scatter(x_name, y_name)
            },
            "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
            "xAxis": {
                "type": "value",
                "name": x_name,
                "nameLocation": "middle",
                "nameGap": 30
            },
            "yAxis": {
                "type": "value",
                "name": y_name,
                "nameLocation": "middle",
                "nameGap": 30
            },
            "series": [{
                "type": "scatter",
                "data": scatter_data,
                "symbolSize": 8,
                "itemStyle": {
                    "color": "#5470c6",
                    "opacity": 0.7
                }
            }]
        }
    }


def create_bar_chart(
    categories: List[str],
    values: List[float],
    title: str = "柱状图",
    horizontal: bool = False,
    x_name: str = "",
    y_name: str = ""
) -> Dict[str, Any]:
    """
    创建柱状图（用于分组对比）

    Args:
        categories: 类别列表
        values: 数值列表
        title: 图表标题
        horizontal: 是否水平柱状图
        x_name: X 轴标签
        y_name: Y 轴标签

    Returns:
        ECharts option JSON
    """
    if horizontal:
        return {
            "chart_type": "bar",
            "option": {
                "title": _create_base_title(title),
                "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
                "xAxis": {"type": "value", "name": x_name, "nameLocation": "end"},
                "yAxis": {"type": "category", "data": categories, "name": y_name, "nameLocation": "end"},
                "series": [{
                    "type": "bar",
                    "data": values,
                    "itemStyle": {
                        "color": {
                            "type": "linear",
                            "x": 0, "y": 0, "x2": 1, "y2": 0,
                            "colorStops": [
                                {"offset": 0, "color": "#5470c6"},
                                {"offset": 1, "color": "#91cc75"}
                            ]
                        }
                    }
                }]
            }
        }
    else:
        return {
            "chart_type": "bar",
            "option": {
                "title": _create_base_title(title),
                "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
                "xAxis": {"type": "category", "data": categories, "name": x_name, "nameLocation": "middle", "nameGap": 30},
                "yAxis": {"type": "value", "name": y_name, "nameLocation": "end"},
                "series": [{
                    "type": "bar",
                    "data": values,
                    "itemStyle": {
                        "color": {
                            "type": "linear",
                            "x": 0, "y": 1, "x2": 0, "y2": 0,
                            "colorStops": [
                                {"offset": 0, "color": "#5470c6"},
                                {"offset": 1, "color": "#91cc75"}
                            ]
                        }
                    }
                }]
            }
        }


def create_grouped_bar_chart(
    groups: List[str],
    series_data: List[Dict[str, Any]],
    title: str = "分组柱状图",
    x_name: str = "",
    y_name: str = ""
) -> Dict[str, Any]:
    """
    创建分组柱状图（用于多组对比）

    Args:
        groups: 分组名称列表
        series_data: 系列数据列表，每个元素包含 {name, data}
        title: 图表标题
        x_name: X 轴标签
        y_name: Y 轴标签

    Returns:
        ECharts option JSON
    """
    series = []
    colors = ["#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de", "#3ba272"]

    for i, item in enumerate(series_data):
        series.append({
            "name": item["name"],
            "type": "bar",
            "data": item["data"],
            "itemStyle": {"color": colors[i % len(colors)]}
        })

    y_label = y_name or "均值"
    return {
        "chart_type": "bar",
        "option": {
            "title": _create_base_title(title),
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "legend": _create_base_legend([s["name"] for s in series_data]),
            "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
            "xAxis": {"type": "category", "data": groups, "name": x_name, "nameLocation": "middle", "nameGap": 30},
            "yAxis": {"type": "value", "name": y_label, "nameLocation": "end"},
            "series": series
        }
    }


def create_grouped_line_chart(
    groups: List[str],
    series_data: List[Dict[str, Any]],
    title: str = "分组折线图",
    x_name: str = "",
    y_name: str = ""
) -> Dict[str, Any]:
    """
    创建分组折线图（用于多组对比）
    将分组对比数据转换为折线图展示，X轴为分组，Y轴为数值

    Args:
        groups: 分组名称列表（X轴）
        series_data: 系列数据列表，每个元素包含 {name, data}
        title: 图表标题

    Returns:
        ECharts option JSON
    """
    # 对于分组对比，将所有组的均值作为一条折线的数据点
    # series_data 格式: [{"name": "group1", "data": [value1]}, {"name": "group2", "data": [value2]}, ...]
    # 需要转换为: [{"name": "均值", "data": [value1, value2, ...]}]

    line_data = []
    for item in series_data:
        if item["data"] and len(item["data"]) > 0:
            line_data.append(item["data"][0])

    series = [{
        "name": title,
        "type": "line",
        "data": line_data,
        "smooth": True,
        "symbol": "circle",
        "symbolSize": 8,
        "itemStyle": {"color": "#5470c6"},
        "lineStyle": {"width": 3}
    }]

    y_label = y_name or "均值"
    return {
        "chart_type": "line",
        "option": {
            "title": _create_base_title(title),
            "tooltip": _create_base_tooltip(),
            "legend": _create_base_legend([title]),
            "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": groups,
                "boundaryGap": False,
                "name": x_name,
                "nameLocation": "middle",
                "nameGap": 30
            },
            "yAxis": {"type": "value", "name": y_label, "nameLocation": "end"},
            "series": series
        }
    }


def create_histogram_chart(
    bin_edges: List[float],
    counts: List[int],
    title: str = "分布直方图",
    x_name: str = "数值",
    y_name: str = "频数"
) -> Dict[str, Any]:
    """
    创建直方图（用于分布分析）

    Args:
        bin_edges: 分箱边界
        counts: 计数值
        title: 图表标题
        x_name: X 轴标签
        y_name: Y 轴标签

    Returns:
        ECharts option JSON
    """
    # 使用区间中点作为 x 轴
    x_data = [(bin_edges[i] + bin_edges[i + 1]) / 2 for i in range(len(bin_edges) - 1)]

    return {
        "chart_type": "bar",
        "option": {
            "title": _create_base_title(title),
            "tooltip": {
                "trigger": "axis",
                "formatter": function_formatter_histogram(bin_edges)
            },
            "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": x_data,
                "name": x_name,
                "nameLocation": "middle",
                "nameGap": 30
            },
            "yAxis": {"type": "value", "name": y_name, "nameLocation": "end"},
            "series": [{
                "type": "bar",
                "data": counts,
                "barWidth": "80%",
                "itemStyle": {"color": "#5470c6"}
            }]
        }
    }


def create_box_plot(
    categories: List[str],
    box_data: List[List[float]],
    title: str = "箱线图"
) -> Dict[str, Any]:
    """
    创建箱线图（用于分布分析）

    Args:
        categories: 类别列表
        box_data: 箱线图数据 [min, Q1, median, Q3, max]
        title: 图表标题

    Returns:
        ECharts option JSON
    """
    return {
        "chart_type": "boxplot",
        "option": {
            "title": _create_base_title(title),
            "tooltip": {"trigger": "item"},
            "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
            "xAxis": {"type": "category", "data": categories},
            "yAxis": {"type": "value", "name": "数值"},
            "series": [{
                "type": "boxplot",
                "data": box_data,
                "itemStyle": {
                    "borderColor": "#5470c6",
                    "color": "#c0d1ea"
                }
            }]
        }
    }


def create_pie_chart(
    data: List[Dict[str, Any]],
    title: str = "饼图",
    donut: bool = False
) -> Dict[str, Any]:
    """
    创建饼图

    Args:
        data: 数据列表 [{name, value}, ...]
        title: 图表标题
        donut: 是否环形图

    Returns:
        ECharts option JSON
    """
    return {
        "chart_type": "pie",
        "option": {
            "title": _create_base_title(title),
            "tooltip": {"trigger": "item"},
            "legend": {"top": "8%", "type": "scroll"},
            "series": [{
                "type": "pie",
                "radius": ["40%", "70%"] if donut else "70%",
                "data": data,
                "emphasis": {
                    "itemStyle": {
                        "shadowBlur": 10,
                        "shadowOffsetX": 0,
                        "shadowColor": "rgba(0, 0, 0, 0.5)"
                    }
                },
                "label": {"show": True, "formatter": "{b}: {d}%"}
            }]
        }
    }


def create_seasonal_chart(
    dates: List[str],
    original: List[float],
    trend: List[float],
    seasonal: List[float],
    title: str = "季节性分解",
    x_name: str = "日期",
    y_name: str = "数值"
) -> Dict[str, Any]:
    """
    创建季节性分解图表

    Args:
        dates: 日期列表
        original: 原始数据
        trend: 趋势数据
        seasonal: 季节数据
        title: 图表标题
        x_name: X 轴标签
        y_name: Y 轴标签

    Returns:
        ECharts option JSON
    """
    return {
        "chart_type": "line",
        "option": {
            "title": _create_base_title(title),
            "tooltip": {"trigger": "axis"},
            "legend": _create_base_legend(["原始", "趋势", "季节"]),
            "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": dates,
                "name": x_name,
                "nameLocation": "middle",
                "nameGap": 30
            },
            "yAxis": {"type": "value", "name": y_name, "nameLocation": "end"},
            "series": [
                {
                    "name": "原始",
                    "type": "line",
                    "data": original,
                    "itemStyle": {"opacity": 0.5}
                },
                {
                    "name": "趋势",
                    "type": "line",
                    "data": trend,
                    "lineStyle": {"width": 3},
                    "itemStyle": {"color": "#ff6b6b"}
                },
                {
                    "name": "季节",
                    "type": "line",
                    "data": seasonal,
                    "lineStyle": {"width": 2, "type": "dashed"},
                    "itemStyle": {"color": "#4ecdc4"}
                }
            ]
        }
    }


# JavaScript 格式化函数
def function_formatter_heatmap() -> str:
    """热力图 tooltip 格式化函数"""
    return "function(params) { return params.value[2].toFixed(4); }"


def function_formatter_scatter(x_name: str, y_name: str) -> str:
    """散点图 tooltip 格式化函数"""
    return f"function(params) {{ return '{x_name}: ' + params.value[0].toFixed(2) + '<br/>{y_name}: ' + params.value[1].toFixed(2); }}"


def function_formatter_histogram(bin_edges: List[float]) -> str:
    """直方图 tooltip 格式化函数"""
    edges_str = str(bin_edges)
    return f"function(params) {{ const edges = {edges_str}; return '区间: [' + edges[params.dataIndex].toFixed(2) + ', ' + edges[params.dataIndex + 1].toFixed(2) + ')<br/>频数: ' + params.value; }}"


def create_grouped_pie_chart(
    groups: List[str],
    series_data: List[Dict[str, Any]],
    title: str = "分组饼图"
) -> Dict[str, Any]:
    """
    创建分组饼图（用于展示占比）

    Args:
        groups: 分组名称列表
        series_data: 系列数据列表，每个元素包含 {name, data}
        title: 图表标题

    Returns:
        ECharts option JSON
    """
    # 将分组数据转换为饼图格式
    pie_data = []
    colors = ["#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de", "#3ba272",
              "#fc8452", "#9a60b4", "#ea7ccc", "#5470c6", "#91cc75", "#fac858"]

    for i, item in enumerate(series_data):
        if item["data"] and len(item["data"]) > 0:
            pie_data.append({
                "name": item["name"],
                "value": item["data"][0],
                "itemStyle": {"color": colors[i % len(colors)]}
            })

    return {
        "chart_type": "pie",
        "option": {
            "title": _create_base_title(title),
            "tooltip": {
                "trigger": "item",
                "formatter": "{a} <br/>{b}: {c} ({d}%)"
            },
            "legend": {
                "top": "8%",
                "type": "scroll",
                "orient": "horizontal"
            },
            "series": [{
                "type": "pie",
                "radius": ["40%", "70%"],
                "center": ["50%", "55%"],
                "data": pie_data,
                "emphasis": {
                    "itemStyle": {
                        "shadowBlur": 10,
                        "shadowOffsetX": 0,
                        "shadowColor": "rgba(0, 0, 0, 0.5)"
                    }
                },
                "label": {
                    "show": True,
                    "formatter": "{b}: {d}%"
                }
            }]
        }
    }


def create_area_chart(
    categories: List[str],
    series_data: List[Dict[str, Any]],
    title: str = "面积图",
    x_name: str = "",
    y_name: str = ""
) -> Dict[str, Any]:
    """
    创建面积图（用于展示趋势和占比）

    Args:
        categories: 类别列表（X轴）
        series_data: 系列数据列表，每个元素包含 {name, data}
        title: 图表标题
        x_name: X 轴标签
        y_name: Y 轴标签

    Returns:
        ECharts option JSON
    """
    # 提取数据
    area_data = []
    for item in series_data:
        if item["data"] and len(item["data"]) > 0:
            area_data.append(item["data"][0])

    return {
        "chart_type": "area",
        "option": {
            "title": _create_base_title(title),
            "tooltip": _create_base_tooltip(),
            "legend": _create_base_legend([title]),
            "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": categories,
                "boundaryGap": False,
                "name": x_name,
                "nameLocation": "middle",
                "nameGap": 30
            },
            "yAxis": {"type": "value", "name": y_name, "nameLocation": "end"},
            "series": [{
                "type": "line",
                "name": title,
                "data": area_data,
                "smooth": True,
                "symbol": "circle",
                "symbolSize": 6,
                "lineStyle": {"width": 2},
                "areaStyle": {
                    "opacity": 0.3,
                    "color": {
                        "type": "linear",
                        "x": 0, "y": 0, "x2": 0, "y2": 1,
                        "colorStops": [
                            {"offset": 0, "color": "#5470c6"},
                            {"offset": 1, "color": "#91cc75"}
                        ]
                    }
                }
            }]
        }
    }


def create_radar_chart(
    groups: List[str],
    series_data: List[Dict[str, Any]],
    title: str = "雷达图"
) -> Dict[str, Any]:
    """
    创建雷达图（用于多维度对比）

    Args:
        groups: 分组名称列表（维度）
        series_data: 系列数据列表，每个元素包含 {name, data}
        title: 图表标题

    Returns:
        ECharts option JSON
    """
    # 提取数据
    radar_data = []
    max_value = 0
    for item in series_data:
        if item["data"] and len(item["data"]) > 0:
            value = item["data"][0]
            radar_data.append(value)
            if value > max_value:
                max_value = value

    # 设置指示器
    indicators = []
    for group in groups:
        indicators.append({
            "name": group,
            "max": max_value * 1.2
        })

    return {
        "chart_type": "radar",
        "option": {
            "title": _create_base_title(title),
            "tooltip": {
                "trigger": "item"
            },
            "legend": _create_base_legend([title]),
            "radar": {
                "indicator": indicators,
                "radius": "65%",
                "splitNumber": 4
            },
            "series": [{
                "type": "radar",
                "name": title,
                "data": [{
                    "value": radar_data,
                    "name": title
                }],
                "areaStyle": {
                    "opacity": 0.3
                }
            }]
        }
    }


def create_grouped_scatter_chart(
    groups: List[str],
    series_data: List[Dict[str, Any]],
    title: str = "分组散点图",
    x_name: str = "",
    y_name: str = ""
) -> Dict[str, Any]:
    """
    创建分组散点图（用于展示分组数据分布）

    Args:
        groups: 分组名称列表（作为X轴类别）
        series_data: 系列数据列表，每个元素包含 {name, data}
        title: 图表标题
        x_name: X 轴标签
        y_name: Y 轴标签

    Returns:
        ECharts option JSON
    """
    # 将类别转换为数值位置，创建散点数据
    scatter_data = []
    for i, item in enumerate(series_data):
        if item["data"] and len(item["data"]) > 0:
            scatter_data.append([i, item["data"][0]])

    y_label = y_name or "均值"
    return {
        "chart_type": "scatter",
        "option": {
            "title": _create_base_title(title),
            "tooltip": {
                "trigger": "item",
                "formatter": "function(params) { return params.name + ': ' + params.value[1]; }"
            },
            "grid": {"left": "10%", "right": "10%", "bottom": "10%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": groups,
                "axisLabel": {"rotate": 45},
                "name": x_name,
                "nameLocation": "middle",
                "nameGap": 50
            },
            "yAxis": {"type": "value", "name": y_label, "nameLocation": "end"},
            "series": [{
                "type": "scatter",
                "data": scatter_data,
                "symbolSize": 20,
                "itemStyle": {
                    "color": "#5470c6",
                    "opacity": 0.7
                }
            }]
        }
    }
