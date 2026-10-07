"""
可视化生成器
使用 pyecharts 生成 ECharts JSON 配置

模块职责：
- 将统计分析 / 机器学习的结果（DataFrame、列表、字典）转换为 ECharts 前端可消费的 option JSON。
- 集中维护各类图表（折线、柱状、饼图、热力图、散点图、箱线图、雷达图、ROC、混淆矩阵、公平性审计等）的配置生成逻辑。
- 提供统一的基础配置（标题、提示框、图例）辅助函数，保证各图表风格一致。
- 兼容 pyecharts 缺失场景：未安装时降级并记录告警，不影响其他模块导入。
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


# AI-assisted: 使用 Claude 生成统一标题配置函数，人工校验后保留默认样式
def _create_base_title(title: str, subtitle: str = "") -> Dict:
    """创建基础标题配置

    生成 ECharts title 配置，统一控制标题居中显示与字号。

    Args:
        title: 主标题文本
        subtitle: 副标题文本（可选，用于补充说明如 AUC、差异值等）

    Returns:
        Dict: ECharts title 配置字典
    """
    return {
        "text": title,
        "subtext": subtitle,
        "left": "center",
        "textStyle": {"fontSize": 16}
    }


# AI-assisted: 使用 Claude 生成统一 tooltip 配置函数，人工校验后保留十字准星样式
def _create_base_tooltip() -> Dict:
    """创建基础提示框配置

    返回 axis 触发、十字准星指针的通用 tooltip 配置。

    Returns:
        Dict: ECharts tooltip 配置字典
    """
    return {
        "trigger": "axis",
        "axisPointer": {"type": "cross"}
    }


# AI-assisted: 使用 Claude 生成统一图例配置函数，人工校验后保留滚动式布局
def _create_base_legend(data: Optional[List[str]] = None) -> Dict:
    """创建基础图例配置

    生成顶部滚动式图例配置，可选地注入系列名称。

    Args:
        data: 系列名称列表；为空则不写入 data 字段，交由 ECharts 自动推断

    Returns:
        Dict: ECharts legend 配置字典
    """
    config = {
        "top": "8%",
        "type": "scroll"
    }
    if data:
        config["data"] = data
    return config


# AI-assisted: 使用 Claude 生成折线图配置，未做大幅修改
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

    基于 DataFrame 生成支持多系列的折线图 ECharts option。

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


# AI-assisted: 使用 Claude 生成移动平均图表配置，人工调整了平滑曲线与原始数据的透明度对比
def create_moving_average_chart(
    original_data: List,
    smoothed_data: List,
    title: str = "移动平均",
    x_name: str = "序号",
    y_name: str = "数值"
) -> Dict[str, Any]:
    """
    创建移动平均图表

    将原始序列与平滑序列叠加展示，便于观察趋势走向。

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


# AI-assisted: 使用 Claude 生成相关性热力图配置，手动调整了蓝-红渐变配色区间
def create_correlation_heatmap(
    corr_matrix: Dict[str, Dict[str, float]],
    columns: List[str],
    title: str = "相关性热力图"
) -> Dict[str, Any]:
    """
    创建相关性热力图

    将相关系数矩阵展开为 [x, y, value] 三元组并映射到 [-1, 1] 色阶。

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


# AI-assisted: 使用 Claude 生成散点图配置，人工调整了点尺寸与透明度
def create_scatter_plot(
    x_data: List,
    y_data: List,
    x_name: str = "X",
    y_name: str = "Y",
    title: str = "散点图"
) -> Dict[str, Any]:
    """
    创建散点图（用于相关性分析）

    将成对的 X、Y 数据合并为坐标点并配置提示框格式化函数。

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


# AI-assisted: 使用 Claude 生成柱状图配置，人工调整了线性渐变配色方向
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

    根据 horizontal 参数切换垂直 / 水平方向，并应用统一的线性渐变柱体样式。

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


# AI-assisted: 使用 Claude 生成分组柱状图配置，手动指定了多系列配色循环
def create_grouped_bar_chart(
    groups: List[str],
    series_data: List[Dict[str, Any]],
    title: str = "分组柱状图",
    x_name: str = "",
    y_name: str = ""
) -> Dict[str, Any]:
    """
    创建分组柱状图（用于多组对比）

    将多组系列数据并排渲染为柱状图，按预设色板循环着色。

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


# AI-assisted: 使用 Claude 生成分组折线图配置，人工校验了分组数据到单条折线的转换逻辑
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


# AI-assisted: 使用 Claude 生成分布直方图配置，人工校验了分箱中点计算
def create_histogram_chart(
    bin_edges: List[float],
    counts: List[int],
    title: str = "分布直方图",
    x_name: str = "数值",
    y_name: str = "频数"
) -> Dict[str, Any]:
    """
    创建直方图（用于分布分析）

    以分箱中点为 X 轴、频数为 Y 轴，并配置区间 tooltip 格式化。

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


# AI-assisted: 使用 Claude 生成箱线图配置，人工调整了箱体边框与填充配色
def create_box_plot(
    categories: List[str],
    box_data: List[List[float]],
    title: str = "箱线图"
) -> Dict[str, Any]:
    """
    创建箱线图（用于分布分析）

    接收 [min, Q1, median, Q3, max] 五元组列表，渲染分组分布对比。

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


# AI-assisted: 使用 Claude 生成饼图配置，人工支持了环形图半径切换
def create_pie_chart(
    data: List[Dict[str, Any]],
    title: str = "饼图",
    donut: bool = False
) -> Dict[str, Any]:
    """
    创建饼图

    根据是否环形调整半径，并展示名称与百分比标签。

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


# AI-assisted: 使用 Claude 生成季节性分解图表配置，人工调整了趋势/季节序列的颜色与线型
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

    将原始、趋势、季节三条序列叠加在同一坐标系，直观呈现时间序列分解结果。

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
# AI-assisted: 使用 Claude 生成热力图 tooltip 的 JS 格式化函数，未做大幅修改
def function_formatter_heatmap() -> str:
    """热力图 tooltip 格式化函数

    返回一段 ECharts 可执行的 JavaScript，将单元格数值保留 4 位小数后展示。

    Returns:
        str: JavaScript 格式化函数字符串
    """
    return "function(params) { return params.value[2].toFixed(4); }"


# AI-assisted: 使用 Claude 生成散点图 tooltip 的 JS 格式化函数，人工校验了标签注入
def function_formatter_scatter(x_name: str, y_name: str) -> str:
    """散点图 tooltip 格式化函数

    返回一段 ECharts 可执行的 JavaScript，展示 X、Y 轴名称及其数值（保留 2 位小数）。

    Args:
        x_name: X 轴名称
        y_name: Y 轴名称

    Returns:
        str: JavaScript 格式化函数字符串
    """
    return f"function(params) {{ return '{x_name}: ' + params.value[0].toFixed(2) + '<br/>{y_name}: ' + params.value[1].toFixed(2); }}"


# AI-assisted: 使用 Claude 生成直方图 tooltip 的 JS 格式化函数，人工校验了区间边界拼接
def function_formatter_histogram(bin_edges: List[float]) -> str:
    """直方图 tooltip 格式化函数

    将分箱边界嵌入返回的 JavaScript，使 tooltip 显示当前数据点所属的左闭右开区间及频数。

    Args:
        bin_edges: 分箱边界列表

    Returns:
        str: JavaScript 格式化函数字符串
    """
    edges_str = str(bin_edges)
    return f"function(params) {{ const edges = {edges_str}; return '区间: [' + edges[params.dataIndex].toFixed(2) + ', ' + edges[params.dataIndex + 1].toFixed(2) + ')<br/>频数: ' + params.value; }}"


# AI-assisted: 使用 Claude 生成分组饼图配置，手动扩充了多类目配色色板
def create_grouped_pie_chart(
    groups: List[str],
    series_data: List[Dict[str, Any]],
    title: str = "分组饼图"
) -> Dict[str, Any]:
    """
    创建分组饼图（用于展示占比）

    将分组对比结果转换为环形饼图，直观比较各组占比。

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


# AI-assisted: 使用 Claude 生成面积图配置，人工调整了垂直方向渐变填充
def create_area_chart(
    categories: List[str],
    series_data: List[Dict[str, Any]],
    title: str = "面积图",
    x_name: str = "",
    y_name: str = ""
) -> Dict[str, Any]:
    """
    创建面积图（用于展示趋势和占比）

    将分组首项数据渲染为带渐变填充的平滑折线，突出整体走势。

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


# AI-assisted: 使用 Claude 生成雷达图配置，人工校验了指示器最大值的 1.2 倍系数
def create_radar_chart(
    groups: List[str],
    series_data: List[Dict[str, Any]],
    title: str = "雷达图"
) -> Dict[str, Any]:
    """
    创建雷达图（用于多维度对比）

    根据分组名称构建各维度指示器，并将首项数据映射为单个雷达数据点。

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


# AI-assisted: 使用 Claude 生成分组散点图配置，人工调整了 X 轴标签旋转角度与点尺寸
def create_grouped_scatter_chart(
    groups: List[str],
    series_data: List[Dict[str, Any]],
    title: str = "分组散点图",
    x_name: str = "",
    y_name: str = ""
) -> Dict[str, Any]:
    """
    创建分组散点图（用于展示分组数据分布）

    以分组索引为 X 坐标、首项数值为 Y 坐标生成散点，便于横向比较各组取值。

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


# AI-assisted: 使用 Claude 生成混淆矩阵热力图配置，人工校验了行列与实际/预测的映射顺序
def create_confusion_matrix_chart(
    cm_data: dict,
    title: str = "混淆矩阵"
) -> Dict[str, Any]:
    """
    创建混淆矩阵热力图

    将二分类结果（tn/fp/fn/tp）展开为 2x2 热力图，并附带带标签的 tooltip。

    Args:
        cm_data: 包含 tn, fp, fn, tp 的字典
        title: 图表标题

    Returns:
        Dict[str, Any]: ECharts option JSON
    """
    tn = cm_data["tn"]
    fp = cm_data["fp"]
    fn = cm_data["fn"]
    tp = cm_data["tp"]

    data = [[tn, fp], [fn, tp]]
    flat_data = []
    for i in range(2):
        for j in range(2):
            flat_data.append([j, i, data[i][j]])

    return {
        "chart_type": "heatmap",
        "option": {
            "title": _create_base_title(title),
            "tooltip": {"formatter": "function(p){ return ['<=50K','>50K'][p.data[1]] + ' 预测为 ' + ['<=50K','>50K'][p.data[0]] + ': ' + p.data[2]; }"},
            "grid": {"left": "15%", "right": "15%", "bottom": "15%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": ["预测 <=50K", "预测 >50K"],
                "splitArea": {"show": True}
            },
            "yAxis": {
                "type": "category",
                "data": ["实际 <=50K", "实际 >50K"],
                "splitArea": {"show": True}
            },
            "visualMap": {
                "min": 0,
                "max": max(tn + fp, fn + tp),
                "calculable": True,
                "orient": "horizontal",
                "left": "center",
                "bottom": "0%"
            },
            "series": [{
                "type": "heatmap",
                "data": flat_data,
                "label": {"show": True, "fontSize": 16, "fontWeight": "bold"},
                "emphasis": {"itemStyle": {"shadowBlur": 10, "shadowColor": "rgba(0, 0, 0, 0.5)"}}
            }]
        }
    }


# AI-assisted: 使用 Claude 生成 ROC 曲线图配置，人工添加了对角基线参考与 AUC 副标题
def create_roc_curve_chart(
    fpr: list,
    tpr: list,
    auc_score: float,
    title: str = "ROC 曲线"
) -> Dict[str, Any]:
    """
    创建 ROC 曲线图

    将 FPR/TPR 点序列绘制为折线，并叠加随机基线、以 AUC 作为副标题。

    Args:
        fpr: 假阳性率序列
        tpr: 真阳性率序列
        auc_score: AUC 分数，展示在副标题
        title: 图表标题

    Returns:
        Dict[str, Any]: ECharts option JSON
    """
    roc_points = [[float(f), float(t)] for f, t in zip(fpr, tpr)]
    diagonal = [[0, 0], [1, 1]]

    return {
        "chart_type": "line",
        "option": {
            "title": _create_base_title(title, f"AUC = {auc_score:.4f}"),
            "tooltip": {"trigger": "item"},
            "grid": {"left": "10%", "right": "10%", "bottom": "15%", "containLabel": True},
            "xAxis": {
                "type": "value",
                "name": "假阳性率 (FPR)",
                "min": 0, "max": 1,
                "nameLocation": "middle", "nameGap": 30
            },
            "yAxis": {
                "type": "value",
                "name": "真阳性率 (TPR)",
                "min": 0, "max": 1,
                "nameLocation": "end"
            },
            "series": [
                {
                    "name": "随机基线",
                    "type": "line",
                    "data": diagonal,
                    "lineStyle": {"type": "dashed", "color": "#999"},
                    "symbol": "none",
                    "itemStyle": {"color": "#999"}
                },
                {
                    "name": f"ROC (AUC={auc_score:.4f})",
                    "type": "line",
                    "data": roc_points,
                    "smooth": False,
                    "lineStyle": {"width": 2, "color": "#5470c6"},
                    "symbol": "none",
                    "areaStyle": {"opacity": 0.15, "color": "#5470c6"},
                    "itemStyle": {"color": "#5470c6"}
                }
            ]
        }
    }


# AI-assisted: 使用 Claude 生成特征重要性水平柱状图配置，人工调整了 top_n 截断与右侧标签
def create_feature_importance_chart(
    features: list,
    title: str = "特征重要性",
    top_n: int = 15
) -> Dict[str, Any]:
    """
    创建特征重要性水平柱状图

    截取前 top_n 个特征并倒序排列，使重要性最高的特征显示在顶部。

    Args:
        features: 特征列表，每个元素含 {feature, importance}
        title: 图表标题
        top_n: 展示的特征数量上限

    Returns:
        Dict[str, Any]: ECharts option JSON
    """
    features = features[:top_n]
    features.reverse()

    names = [f["feature"] for f in features]
    values = [round(f["importance"] * 100, 2) for f in features]

    return {
        "chart_type": "bar",
        "option": {
            "title": _create_base_title(title),
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "grid": {"left": "30%", "right": "10%", "bottom": "5%", "top": "15%", "containLabel": True},
            "xAxis": {
                "type": "value",
                "name": "重要性 (%)",
                "nameLocation": "end"
            },
            "yAxis": {
                "type": "category",
                "data": names,
                "axisLabel": {"fontSize": 11}
            },
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
                },
                "label": {"show": True, "position": "right", "formatter": "{c}%"}
            }]
        }
    }


# AI-assisted: 使用 Claude 生成公平性审计对比柱状图配置，人工调整了 TPR/FPR 双系列配色
def create_fairness_chart(
    fairness_result: dict,
    title: str = "公平性审计"
) -> list:
    """
    创建公平性审计对比柱状图（每个敏感属性一张图）

    遍历所有敏感属性，为每个属性生成一张并列对比 TPR 与 FPR 的柱状图。

    Args:
        fairness_result: 公平性审计结果，含 sensitive_attributes 子结构
        title: 图表标题（仅作占位，实际标题按属性名生成）

    Returns:
        list: 各敏感属性对应的图表配置列表
    """
    charts = []

    for attr_name, attr_data in fairness_result.get("sensitive_attributes", {}).items():
        groups = attr_data["groups"]
        group_names = [g["group"] for g in groups]
        tpr_values = [g["tpr"] for g in groups]
        fpr_values = [g["fpr"] for g in groups]

        charts.append({
            "chart_type": "bar",
            "option": {
                "title": _create_base_title(
                    f"公平性审计 - {attr_name}",
                    f"TPR 差异: {attr_data['tpr_gap']:.4f}, FPR 差异: {attr_data['fpr_gap']:.4f}"
                ),
                "tooltip": {"trigger": "axis"},
                "legend": {"data": ["TPR (真正率)", "FPR (假阳性率)"], "top": "12%"},
                "grid": {"left": "10%", "right": "10%", "bottom": "15%", "top": "25%", "containLabel": True},
                "xAxis": {
                    "type": "category",
                    "data": group_names,
                    "axisLabel": {"rotate": 30}
                },
                "yAxis": {"type": "value", "name": "比率", "min": 0, "max": 1},
                "series": [
                    {
                        "name": "TPR (真正率)",
                        "type": "bar",
                        "data": tpr_values,
                        "itemStyle": {"color": "#5470c6"},
                        "label": {"show": True, "position": "top", "formatter": "{c}"}
                    },
                    {
                        "name": "FPR (假阳性率)",
                        "type": "bar",
                        "data": fpr_values,
                        "itemStyle": {"color": "#ee6666"},
                        "label": {"show": True, "position": "top", "formatter": "{c}"}
                    }
                ]
            }
        })

    return charts
