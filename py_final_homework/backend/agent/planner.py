"""
Agent1 — 规划调度器
接收用户请求，结合会话上下文，输出 JSON 格式的任务计划。
将任务分解为 operation（数据操作）和 consultation（分析咨询）两类。
"""
import json
import logging
import re
from typing import Any, Dict, Optional

from backend.agent.llm_client import LLMClient, LLMClientError, get_planner_client
from backend.core.operations import OPERATION_NAMES
from backend.models.session_context import SessionContext

logger = logging.getLogger(__name__)

# 建议类关键词（模糊需求直接路由到 consultation）
SUGGESTION_KEYWORDS = [
    "进一步分析", "分析建议", "下一步", "还能分析什么", "建议分析",
    "推荐分析", "分析方向", "深入分析", "更多分析", "还有什么可以分析",
    "给我建议", "分析思路", "如何分析", "suggest", "接下来", "怎么分析",
    "还能做什么", "还有什么", "帮我看看",
]

# 具体操作关键词（有明确操作意图）
OPERATION_KEYWORDS = {
    "overview": ["概览", "总览", "概况", "数据集信息", "基本信息"],
    "trend": ["趋势", "变化", "增长", "下降", "走势"],
    "distribution": ["分布", "直方图", "箱线图", "频率", "频次"],
    "comparison": ["对比", "比较", "分组", "交叉表", "列联表", "差异", "按.*分组"],
    "correlation": ["相关性", "相关分析", "相关系数", "关联", "correlation"],
    "moving_avg": ["移动平均", "平滑", "均线", "sma", "ema"],
    "seasonality": ["季节性", "周期性", "季节分解", "时序分解"],
}

PLANNER_SYSTEM_PROMPT = """你是数据分析系统的任务规划器。用户会提出各种数据分析需求，你的职责是将需求拆解为明确的原子任务计划，并判断每个任务是"数据操作"还是"分析咨询"。

## 可用操作能力
你可以调度以下后端操作：
{available_operations_descriptions}

## 当前数据上下文
{data_profile_summary}

## 历史分析步骤
{analysis_history_summary}

## 上一次操作结果（如有）
{last_operation_result}

## 任务类型定义
1. **数据操作（operation）**：用户要求对数据执行具体计算、统计、绘图等。这类任务必须生成一个包含 operation 和 parameters 的可执行指令。
2. **分析咨询（consultation）**：用户要求给出分析建议、解读、或下一步方案，例如"接下来怎么分析"、"为什么金牌会员消费高"。这类任务不能直接执行操作，必须路由给分析师Agent。

## 输出格式
你必须输出一个严格的JSON计划，格式如下：
{{
  "plan": [
    {{"type": "operation", "operation": "correlation", "parameters": {{"columns": ["age", "fnlwgt"]}}}},
    {{"type": "consultation", "context": "用户希望基于上一步结果进一步分析"}}
  ]
}}

## 规则
- 如果用户需求混合了操作和分析，应分解为多个步骤，操作步骤在咨询步骤之前。
- 对于模糊需求（如"进一步分析"、"接下来怎么做"），若没有具体的操作关键词，一律视为 consultation。
- 永远不要自行生成分析见解或结论，那不是你的职责。
- 确保 operation 中的参数完全来自数据上下文中的列名。
- 如果用户需求无法用现有操作完成，在 plan 中加入一个 type 为 "error" 的步骤，解释原因。
- 图表类型由用户提及的关键词决定（折线图=line, 柱状图=bar, 饼图=pie, 散点图=scatter, 直方图=histogram, 面积图=area, 雷达图=radar, 箱线图=boxplot）。

只返回JSON。"""


async def plan(
    query: str,
    context: SessionContext,
    llm_client: Optional[LLMClient] = None,
) -> Dict[str, Any]:
    """
    Agent1：规划调度

    Args:
        query: 用户查询
        context: 会话上下文
        llm_client: LLM 客户端

    Returns:
        {"plan": [{"type": "operation"|"consultation"|"error", ...}]}
    """
    if llm_client is None:
        llm_client = get_planner_client()

    query_lower = query.lower()

    # ---- 快速路径：纯模糊需求 → 直接 consultation ----
    if _is_pure_vague_query(query_lower, context):
        logger.info("检测到纯模糊需求，直接路由到 consultation")
        return {
            "plan": [{
                "type": "consultation",
                "context": query,
            }]
        }

    # ---- 快速路径：本地关键词匹配具体操作 ----
    local_operation = _detect_operation(query_lower, context)
    if local_operation:
        logger.info(f"本地关键词匹配到操作: {local_operation['operation']}")
        return {"plan": [local_operation]}

    # ---- LLM 路径：复杂需求由 LLM 解析 ----
    try:
        prompt_dict = context.to_prompt_dict()
        system_prompt = PLANNER_SYSTEM_PROMPT.format(
            available_operations_descriptions=prompt_dict["available_operations"],
            data_profile_summary=prompt_dict["data_profile"],
            analysis_history_summary=prompt_dict["analysis_history"],
            last_operation_result=prompt_dict["last_operation_result"],
        )

        response = await llm_client.achat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"用户问题：{query}\n\n请输出任务计划JSON。"},
            ],
            temperature=0.1,
            max_tokens=800,
        )

        logger.debug(f"Agent1 原始响应: {response[:300]}...")

        # 提取 JSON
        plan = _extract_plan(response)
        if plan:
            return _validate_plan(plan, context)

        logger.warning("Agent1 JSON 解析失败，降级为 consultation")
        return {
            "plan": [{
                "type": "consultation",
                "context": query,
            }]
        }

    except LLMClientError as e:
        logger.error(f"Agent1 LLM 调用失败: {e}")
        return {
            "plan": [{
                "type": "consultation",
                "context": query,
            }]
        }
    except Exception as e:
        logger.error(f"Agent1 异常: {e}")
        return {
            "plan": [{
                "type": "error",
                "message": f"规划失败: {str(e)}",
            }]
        }


def _is_pure_vague_query(query_lower: str, context: SessionContext) -> bool:
    """判断是否为纯模糊需求（无任何具体操作意图）"""
    has_suggestion_kw = any(kw in query_lower for kw in SUGGESTION_KEYWORDS)

    # 检查是否有具体操作关键词
    has_operation_kw = False
    for op_name, keywords in OPERATION_KEYWORDS.items():
        for kw in keywords:
            if kw in query_lower:
                has_operation_kw = True
                break
        if has_operation_kw:
            break

    # 检查是否提到了具体列名
    has_column_ref = any(col.lower() in query_lower for col in context.data_profile.columns)

    if has_suggestion_kw and not has_operation_kw and not has_column_ref:
        return True

    return False


def _detect_operation(query_lower: str, context: SessionContext) -> Optional[Dict[str, Any]]:
    """本地关键词检测具体操作"""
    from backend.core.operations import validate_operation

    # 检测相关性
    correlation_kws = ["相关性", "相关分析", "相关系数", "correlation", "关联分析"]
    if any(kw in query_lower for kw in correlation_kws):
        if len(context.data_profile.numeric_columns) >= 2:
            mentioned = [c for c in context.data_profile.numeric_columns if c.lower() in query_lower]
            cols = mentioned[:5] if len(mentioned) >= 2 else context.data_profile.numeric_columns[:5]
            return {
                "type": "operation",
                "operation": "correlation",
                "parameters": {"columns": cols, "chart_type": _detect_chart_type(query_lower)},
            }

    # 检测交叉表
    crosstab_kws = ["交叉表", "列联表", "交叉分析", "交叉对比", "crosstab", "透视表"]
    if any(kw in query_lower for kw in crosstab_kws):
        cat_cols = context.data_profile.categorical_columns
        num_cols = context.data_profile.numeric_columns
        if cat_cols and num_cols:
            return {
                "type": "operation",
                "operation": "comparison",
                "parameters": {
                    "target_columns": [num_cols[0]],
                    "groupby": cat_cols[0],
                    "chart_type": _detect_chart_type(query_lower),
                },
            }
        elif len(cat_cols) >= 2:
            return {
                "type": "operation",
                "operation": "comparison",
                "parameters": {
                    "target_columns": [cat_cols[1]],
                    "groupby": cat_cols[0],
                    "chart_type": "bar",
                },
            }

    # 检测季节性
    seasonality_kws = ["季节性", "季节分解", "周期性", "seasonality", "时序分解"]
    if any(kw in query_lower for kw in seasonality_kws):
        if context.data_profile.datetime_columns and context.data_profile.numeric_columns:
            return {
                "type": "operation",
                "operation": "seasonality",
                "parameters": {
                    "column": context.data_profile.numeric_columns[0],
                    "chart_type": _detect_chart_type(query_lower),
                },
            }

    return None


def _detect_chart_type(query_lower: str) -> Optional[str]:
    """从查询中检测图表类型"""
    chart_map = {
        "boxplot": ["箱线图", "箱型图"],
        "histogram": ["直方图", "频数图"],
        "scatter": ["散点图", "点状图", "scatter"],
        "pie": ["饼状图", "饼图", "占比图", "扇形图"],
        "line": ["折线图", "曲线图", "线形图", "折线"],
        "bar": ["柱状图", "条形图", "柱形图"],
        "area": ["面积图", "区域图"],
        "radar": ["雷达图"],
    }
    for chart_type, keywords in chart_map.items():
        for kw in keywords:
            if kw in query_lower:
                return chart_type
    return None


def _extract_plan(response: str) -> Optional[Dict[str, Any]]:
    """从 LLM 响应中提取 JSON 计划"""
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _validate_plan(plan: Dict[str, Any], context: SessionContext) -> Dict[str, Any]:
    """验证并修正计划中的操作参数"""
    steps = plan.get("plan", [])
    if not steps:
        return {"plan": [{"type": "consultation", "context": "无法解析具体操作意图"}]}

    for step in steps:
        if step.get("type") != "operation":
            continue

        op_name = step.get("operation", "")
        if op_name not in OPERATION_NAMES:
            logger.warning(f"未知操作: {op_name}，转为 consultation")
            step["type"] = "consultation"
            step["context"] = f"用户请求的操作 '{op_name}' 暂不支持"
            continue

        # 验证参数中的列名
        params = step.get("parameters", {})
        actual_cols = set(context.data_profile.columns)
        for key in ("columns", "target_columns"):
            if key in params and isinstance(params[key], list):
                params[key] = [c for c in params[key] if c in actual_cols]

        if "column" in params and params["column"] not in actual_cols:
            if context.data_profile.numeric_columns:
                params["column"] = context.data_profile.numeric_columns[0]

        if "groupby" in params and params["groupby"] not in actual_cols:
            if context.data_profile.categorical_columns:
                params["groupby"] = context.data_profile.categorical_columns[0]
            else:
                params["groupby"] = None

    return plan
