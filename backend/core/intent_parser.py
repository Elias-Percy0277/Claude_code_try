"""
意图解析器
使用 DeepSeek API 解析用户查询，配合本地关键词检测确保图表类型可靠
"""
import logging
import json
import re
from typing import Dict, List, Any, Optional
import pandas as pd

from backend.agent.llm_client import LLMClient, LLMClientError

logger = logging.getLogger(__name__)


# 支持的分析命令
SUPPORTED_COMMANDS = {
    "overview",      # 数据概览
    "trend",         # 趋势分析
    "distribution",  # 分布分析
    "moving_avg",    # 移动平均
    "comparison",    # 分组对比
    "correlation",   # 相关性分析
    "seasonality",   # 季节性分解
}

# 支持的图表类型
SUPPORTED_CHART_TYPES = {
    "bar", "line", "pie", "scatter", "histogram", "area", "radar", "boxplot",
}

# 图表类型关键词映射（优先级从高到低——先匹配长关键词避免误判）
CHART_TYPE_KEYWORDS = {
    "boxplot": ["箱线图", "箱型图"],
    "histogram": ["直方图", "频数图"],
    "scatter": ["散点图", "点状图", "scatter plot", "散布图", "点图"],
    "pie": ["饼状图", "饼图", "占比图", "扇形图", "pie chart", "展示占比", "各部分占比", "各占比", "百分比图", "百分比"],
    "line": ["折线图", "曲线图", "线形图", "折线", "趋势线", "line chart", "换成折线", "改为折线", "用折线", "线图"],
    "bar": ["柱状图", "条形图", "柱形图", "柱图", "bar chart", "bar图", "换成柱状", "改为柱状", "用柱状"],
    "area": ["面积图", "区域图"],
    "radar": ["雷达图", "spider图", "网状图"],
    "heatmap": ["热力图", "热图", "heatmap", "交叉表热力图"],
}

# 交叉表关键词
CROSSTAB_KEYWORDS = [
    "交叉表", "列联表", "交叉分析", "交叉对比", "crosstab", "cross tab",
    "交叉频次", "交叉频率", "pivot table", "透视表", "数据透视",
    "交叉分布", "两个分类", "分类组合",
]

# 建议类查询关键词
SUGGESTION_KEYWORDS = [
    "进一步分析", "分析建议", "下一步", "还能分析什么", "建议分析",
    "推荐分析", "分析方向", "深入分析", "更多分析", "还有什么可以分析",
    "给我建议", "分析思路", "如何分析", "suggest",
]


def detect_chart_type(query: str) -> Optional[str]:
    """
    从用户查询中本地检测图表类型关键词。
    这是对 LLM 返回 chart_type 的可靠补充/保底。

    Args:
        query: 用户自然语言查询

    Returns:
        检测到的图表类型，未检测到返回 None
    """
    query_lower = query.lower()
    for chart_type, keywords in CHART_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in query_lower:
                return chart_type
    return None


async def parse_intent_async(
    query: str,
    df: pd.DataFrame,
    llm_client: Optional[LLMClient] = None
) -> Dict[str, Any]:
    """
    使用 DeepSeek API 直接解析用户查询为分析命令，
    并用本地关键词检测保底 chart_type。

    Args:
        query: 用户自然语言查询
        df: 数据集 DataFrame
        llm_client: LLM 客户端

    Returns:
        解析结果字典
    """
    if llm_client is None:
        from backend.agent.llm_client import get_llm_client
        llm_client = get_llm_client()

    # 构建数据集信息
    dtypes = {col: str(dtype) for col, dtype in df.dtypes.items()}
    columns_info = "\n".join([f"  - {col}: {dtype}" for col, dtype in dtypes.items()])
    preview = df.head(5).to_string(max_cols=10)
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    datetime_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()
    categorical_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

    # --- 前置检测：建议类查询 ---
    query_lower = query.lower()
    if any(kw in query_lower for kw in SUGGESTION_KEYWORDS):
        logger.info("检测到建议类查询，直接生成建议")
        return _generate_suggestions(query, df, numeric_cols, categorical_cols, datetime_cols)

    # --- 前置检测：相关性查询 ---
    CORRELATION_KEYWORDS = ["相关性", "相关分析", "相关系数", "correlation", "关联分析"]
    if any(kw in query_lower for kw in CORRELATION_KEYWORDS) and len(numeric_cols) >= 2:
        logger.info("检测到相关性查询，本地解析")
        # 从查询中尝试提取用户指定的列
        mentioned_nums = [c for c in numeric_cols if c.lower() in query_lower]
        target = mentioned_nums[:5] if len(mentioned_nums) >= 2 else numeric_cols[:5]
        return {
            "confidence": 0.95,
            "tasks": [{
                "intent": "correlation",
                "target_columns": target,
                "groupby": None,
                "groupby2": None,
                "params": {},
                "chart_type": detect_chart_type(query),
                "reasoning": "用户请求相关性分析"
            }]
        }

    # --- 前置检测：季节性分解查询 ---
    SEASONALITY_KEYWORDS = ["季节性", "季节分解", "周期性", "seasonality", "时序分解", "季节性分解"]
    if any(kw in query_lower for kw in SEASONALITY_KEYWORDS) and datetime_cols and numeric_cols:
        logger.info("检测到季节性分解查询，本地解析")
        return {
            "confidence": 0.95,
            "tasks": [{
                "intent": "seasonality",
                "target_columns": numeric_cols[:1],
                "groupby": None,
                "groupby2": None,
                "params": {},
                "chart_type": detect_chart_type(query),
                "reasoning": "用户请求季节性分解"
            }]
        }

    # --- 前置检测：交叉表查询 ---
    if any(kw in query_lower for kw in CROSSTAB_KEYWORDS):
        logger.info("检测到交叉表查询，本地解析")
        task = _parse_crosstab_intent(query, df, numeric_cols, categorical_cols)
        if task:
            return {"confidence": 0.95, "tasks": [task]}

    dataset_info = f"""
数据集特征：
- 数值列: {numeric_cols if numeric_cols else '无'}
- 日期列: {datetime_cols if datetime_cols else '无'}
- 分类列: {categorical_cols if categorical_cols else '无'}
- 总行数: {len(df)}
"""

    prompt = f"""你是数据分析助手。根据用户问题和数据集信息，选择最合适的分析方法并返回分析命令。

用户问题：{query}

数据集列：
{columns_info}
{dataset_info}

数据预览：
{preview}

可用分析命令：
- overview: 数据概览 - 初次查看或需求不明确
- trend: 趋势分析 - 展示数值数据的变化趋势
- distribution: 分布分析 - 展示数值数据的分布特征
- moving_avg: 移动平均 - 时间序列平滑处理
- comparison: 分组对比 - 按分类变量对比数值差异，包括交叉表/列联表分析（两个分类变量的频次分布）
- correlation: 相关性分析 - 数值列间的相关系数矩阵与散点图
- seasonality: 季节性分解 - 时间序列的趋势、季节和残差分解（需要日期列）

返回 JSON：
{{
  "command": "trend",
  "columns": ["列名1"],
  "groupby": "分组列名（仅 comparison 需要）",
  "groupby2": "第二个分组列名（仅 comparison 多维对比时需要）",
  "params": {{"window": 7}},
  "chart_type": "line",
  "reasoning": "原因"
}}

约束：
1. command 必须是上述之一
2. columns 必须使用数据集的实际列名（即上面"数据集列"中列出的英文名）。如果用户使用中文描述列（如"年龄""收入""性别"），你必须根据语义自动映射到对应的实际英文列名（如"年龄"→"age"、"收入"→"income"、"性别"→"gender"/"sex"）。不要返回中文名称作为列名。
3. chart_type 必须根据用户提到的图表类型设置，支持：line, bar, pie, scatter, histogram, area, radar, boxplot
4. groupby 和 groupby2 同样必须使用实际英文列名，遵循与 columns 相同的中文→英文映射规则
4. 用户提到"饼图/饼状图/占比/百分比/比例" → chart_type: "pie"
5. 用户提到"折线图/线图/曲线" → chart_type: "line"
6. 用户提到"柱状图/条形图" → chart_type: "bar"
7. 用户提到"散点图/点图/点状图" → chart_type: "scatter"
8. 用户提到"面积图" → chart_type: "area"
9. 用户提到"雷达图" → chart_type: "radar"
10. 用户提到"箱线图" → chart_type: "boxplot"
11. 用户提到"直方图" → chart_type: "histogram"
12. 用户说"换成X图/改为X图" → 保持原 command，只改 chart_type
13. "用饼图展示分布" → command: "distribution", chart_type: "pie"
14. "X按Y分组，用饼图" → command: "comparison", chart_type: "pie"
15. 多维对比：当用户同时提到两个分类变量与一个数值变量的关系时（如"age与workclass与native-country的关系"），使用 command: "comparison"，设置 groupby 为主要分组列，groupby2 为第二个分组列
16. 多列趋势：当用户要求同时展示多个数值列的趋势时，columns 包含多个列名
17. 交叉表/列联表：当用户提到"交叉表""列联表""交叉分析""交叉对比""crosstab""pivot table""透视表"等，使用 command: "comparison"，将第一个分类列设为 groupby，第二个分类列（或要统计的列）设为 columns[0]。如果只是两个分类列的频次交叉，columns 设为第二个分类列，groupby 设为第一个分类列
18. 相关性分析：当用户提到"相关性""相关系数""关联""correlation"等，使用 command: "correlation"，columns 设为涉及的数值列
19. 季节性分解：当用户提到"季节性""周期性""季节分解""seasonality"等，使用 command: "seasonality"，columns 设为涉及的数值列

只返回 JSON。"""

    try:
        response = await llm_client.achat(
            messages=[
                {
                    "role": "system",
                    "content": "你是数据分析专家。返回严格的 JSON 格式。必须设置 chart_type 字段。"
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=500
        )

        logger.debug(f"LLM 原始响应: {response[:200]}...")

        # 尝试提取 JSON
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
        if json_match:
            try:
                json_str = json_match.group(0)
                result = json.loads(json_str)

                command = result.get("command", "overview")

                if command not in SUPPORTED_COMMANDS:
                    logger.warning(f"不支持的命令: {command}，替换为 overview")
                    command = "overview"

                # 从 LLM 获取 chart_type
                llm_chart_type = result.get("chart_type")

                # 本地关键词检测作为保底
                local_chart_type = detect_chart_type(query)

                # 决策：LLM 返回了就用 LLM 的，否则用本地检测
                if llm_chart_type and llm_chart_type in SUPPORTED_CHART_TYPES:
                    chart_type = llm_chart_type
                elif local_chart_type:
                    chart_type = local_chart_type
                    logger.info(f"LLM 未返回有效 chart_type，使用本地检测: {chart_type}")
                else:
                    chart_type = None

                task = {
                    "intent": command,
                    "target_columns": result.get("columns", []),
                    "groupby": result.get("groupby"),
                    "groupby2": result.get("groupby2"),
                    "params": result.get("params", {}),
                    "chart_type": chart_type,
                    "reasoning": result.get("reasoning", "")
                }

                # 验证列名
                actual_columns = df.columns.tolist()
                if task["target_columns"]:
                    valid_cols = [col for col in task["target_columns"] if col in actual_columns]
                    invalid_cols = set(task["target_columns"]) - set(valid_cols)
                    if invalid_cols:
                        logger.warning(f"列名不存在: {invalid_cols}")
                        task["target_columns"] = valid_cols
                        if not valid_cols:
                            task["target_columns"] = numeric_cols[:1] if numeric_cols else []
                else:
                    if command in ["trend", "distribution", "moving_avg"]:
                        task["target_columns"] = numeric_cols[:1] if numeric_cols else []

                # 验证 groupby
                if task["groupby"] and task["groupby"] not in actual_columns:
                    logger.warning(f"groupby 列不存在: {task['groupby']}")
                    if categorical_cols:
                        task["groupby"] = categorical_cols[0]
                    else:
                        task["groupby"] = None

                # 验证 groupby2
                if task["groupby2"] and task["groupby2"] not in actual_columns:
                    logger.warning(f"groupby2 列不存在: {task['groupby2']}")
                    cat_without_first = [c for c in categorical_cols if c != task["groupby"]]
                    task["groupby2"] = cat_without_first[0] if cat_without_first else None

                # 本地 fallback：如果 LLM 没返回 groupby2，但查询中提到了多个分类列
                if not task["groupby2"] and command == "comparison" and task["groupby"]:
                    mentioned_cats = [c for c in categorical_cols if c.lower() in query.lower()]
                    # 去掉已作为 groupby 的列，剩下的作为 groupby2
                    remaining_cats = [c for c in mentioned_cats if c != task["groupby"]]
                    if remaining_cats:
                        task["groupby2"] = remaining_cats[0]
                        logger.info(f"本地检测到 groupby2: {task['groupby2']}")

                # moving_avg 默认 window
                if command == "moving_avg" and "window" not in task.get("params", {}):
                    task["params"] = task.get("params", {})
                    task["params"]["window"] = 7

                logger.info(f"意图解析成功: command={command}, columns={task['target_columns']}, chart_type={chart_type}")

                return {
                    "confidence": 0.9,
                    "tasks": [task]
                }

            except json.JSONDecodeError as e:
                logger.warning(f"JSON 解析失败: {e}")

        # JSON 解析失败
        logger.info("无法解析为结构化命令，返回原始 AI 分析")
        return {
            "confidence": 0.5,
            "raw_response": response.strip(),
            "warning": "AI 返回了非结构化响应，直接展示分析内容"
        }

    except LLMClientError as e:
        logger.error(f"LLM API 调用失败: {e}")
        return {
            "confidence": 0.0,
            "tasks": [],
            "error": f"AI 服务暂时不可用: {str(e)}"
        }

    except Exception as e:
        logger.error(f"意图解析异常: {e}")
        return {
            "confidence": 0.0,
            "tasks": [],
            "error": f"解析过程出错: {str(e)}"
        }


def parse_intent(
    query: str,
    df: pd.DataFrame,
    llm_client: Optional[LLMClient] = None
) -> Dict[str, Any]:
    """同步解析用户查询"""
    import asyncio
    return asyncio.run(parse_intent_async(query, df, llm_client))


def _parse_crosstab_intent(
    query: str,
    df: pd.DataFrame,
    numeric_cols: list,
    categorical_cols: list
) -> Optional[Dict[str, Any]]:
    """本地解析交叉表查询意图"""
    if len(categorical_cols) < 1:
        return None

    query_lower = query.lower()
    # 尝试从查询中找出用户提到的分类列
    mentioned_cats = [c for c in categorical_cols if c.lower() in query_lower]
    if len(mentioned_cats) >= 2:
        groupby = mentioned_cats[0]
        target_col = mentioned_cats[1]
    elif len(mentioned_cats) == 1 and len(categorical_cols) >= 2:
        groupby = mentioned_cats[0]
        target_col = [c for c in categorical_cols if c != groupby][0]
    elif len(categorical_cols) >= 2:
        groupby = categorical_cols[0]
        target_col = categorical_cols[1]
    else:
        return None

    return {
        "intent": "comparison",
        "target_columns": [target_col],
        "groupby": groupby,
        "groupby2": None,
        "params": {},
        "chart_type": "bar",
        "reasoning": f"用户请求交叉表分析，{groupby} x {target_col}"
    }


def _generate_suggestions(
    query: str,
    df: pd.DataFrame,
    numeric_cols: list,
    categorical_cols: list,
    datetime_cols: list
) -> Dict[str, Any]:
    """根据数据集特征生成分折建议，不调用 LLM"""
    lines = ["## 数据分析建议\n"]
    lines.append(f"当前数据集有 **{len(df)}** 行、**{len(df.columns)}** 列。\n")

    if numeric_cols:
        lines.append("### 数值列分析")
        for col in numeric_cols[:3]:
            lines.append(f"- **{col}**：可以分析趋势、分布、移动平均、分组对比")
        if len(numeric_cols) >= 2:
            lines.append(f"- **{numeric_cols[0]}** 与 **{numeric_cols[1]}**：相关性分析")
        lines.append("")

    if categorical_cols:
        lines.append("### 分类列分析")
        for col in categorical_cols[:3]:
            n_unique = df[col].nunique()
            lines.append(f"- **{col}**（{n_unique} 个类别）：分组对比、交叉表分析")
        if len(categorical_cols) >= 2:
            lines.append(f"- **{categorical_cols[0]}** × **{categorical_cols[1]}**：交叉表/列联表分析")
        lines.append("")

    if datetime_cols:
        lines.append("### 时间维度分析")
        lines.append("- 时间趋势分析")
        lines.append("- 移动平均平滑")
        lines.append("- 季节性分解")
        lines.append("")

    lines.append("### 推荐查询")
    if numeric_cols:
        lines.append(f"1. `分析 {numeric_cols[0]} 的趋势变化`")
        lines.append(f"2. `查看 {numeric_cols[0]} 的分布`")
    if categorical_cols and numeric_cols:
        lines.append(f"3. `按 {categorical_cols[0]} 对比 {numeric_cols[0]}`")
    if len(categorical_cols) >= 2:
        lines.append(f"4. `{categorical_cols[0]} 和 {categorical_cols[1]} 的交叉表`")
    if numeric_cols and len(numeric_cols) >= 2:
        lines.append(f"5. `{numeric_cols[0]} 和 {numeric_cols[1]} 的相关性`")

    suggestion_text = "\n".join(lines)
    return {
        "confidence": 0.8,
        "raw_response": suggestion_text,
        "warning": None
    }
