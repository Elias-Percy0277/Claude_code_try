"""
Agent2 — 分析方案顾问
基于数据画像、历史操作和当前结果，提供结构化的下一步分析建议。
绝对不调用任何数据操作，只基于给定信息提供可执行的分析方案。
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from backend.agent.llm_client import LLMClient, LLMClientError, get_advisor_client
from backend.core.operations import get_operations_description, OPERATION_NAMES
from backend.models.session_context import SessionContext

logger = logging.getLogger(__name__)

ADVISOR_SYSTEM_PROMPT = """你是一位资深数据分析顾问，你的唯一职责是基于现有的数据画像、分析历史和操作结果，向用户提供清晰、可执行的下一步分析方案。你绝对不能请求或执行任何数据操作。

## 当前数据概况
{data_profile_json}

## 你可以建议使用的操作清单
{available_operations_with_descriptions}

## 已经完成的分析步骤
{analysis_history_text}

## 最近一次操作的具体结果
{last_operation_result_json}

## 任务
1. 如果用户问"接下来怎么分析"、"还能做什么"等，你需要根据数据特征和已完成的分析，规划2-3个有逻辑的后续分析步骤。
2. 如果用户要求解读结果（如"这个交叉表说明了什么"），你需要基于统计结果和业务常识给出合理的解读。
3. 你的所有建议必须引用具体的列名和操作名，确保后端可以直接执行。
4. 方案输出格式必须为结构化JSON，以便前端渲染为"一键执行"按钮。

## 输出格式
你必须输出以下JSON：
{{
  "suggestions": [
    {{
      "title": "分析建议标题",
      "rationale": "为什么要做这个分析",
      "operation": "correlation",
      "parameters": {{"columns": ["age", "fnlwgt"]}},
      "expected_insight": "预期可以揭示的关系"
    }}
  ],
  "interpretation": "对当前结果的解读文字，如果用户未要求解读则为null"
}}

## 严格约束
- 你的输出只能基于提供的数据列和可用操作，绝不允许建议未注册的操作。
- 你无权访问原始数据，不能自己计算，所有方案都由后端执行。
- 如果没有任何信息可以生成建议，请将 suggestions 设为空数组并在 interpretation 中说明原因。

只返回JSON。"""


async def consult(
    context: SessionContext,
    user_query: str = "",
    llm_client: Optional[LLMClient] = None,
) -> Dict[str, Any]:
    """
    Agent2：分析方案顾问

    Args:
        context: 会话上下文
        user_query: 用户原始查询（用于理解上下文）
        llm_client: LLM 客户端

    Returns:
        {"suggestions": [...], "interpretation": "..."}
    """
    if llm_client is None:
        llm_client = get_advisor_client()

    try:
        prompt_dict = context.to_prompt_dict()

        system_prompt = ADVISOR_SYSTEM_PROMPT.format(
            data_profile_json=prompt_dict["data_profile"],
            available_operations_with_descriptions=prompt_dict["available_operations"],
            analysis_history_text=prompt_dict["analysis_history"],
            last_operation_result_json=prompt_dict["last_operation_result"],
        )

        user_message = f"用户问题：{user_query}" if user_query else "请给出下一步分析建议。"

        response = await llm_client.achat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.5,
            max_tokens=1500,
        )

        logger.debug(f"Agent2 原始响应: {response[:300]}...")

        result = _extract_suggestions(response)
        if result:
            return _validate_suggestions(result, context)

        logger.warning("Agent2 JSON 解析失败，降级为模板建议")
        return _fallback_suggestions(context)

    except LLMClientError as e:
        logger.error(f"Agent2 LLM 调用失败: {e}")
        return _fallback_suggestions(context)
    except Exception as e:
        logger.error(f"Agent2 异常: {e}")
        return {
            "suggestions": [],
            "interpretation": f"分析建议生成失败: {str(e)}",
        }


def _extract_suggestions(response: str) -> Optional[Dict[str, Any]]:
    """从 LLM 响应中提取建议 JSON"""
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _validate_suggestions(result: Dict[str, Any], context: SessionContext) -> Dict[str, Any]:
    """验证建议中的操作名和参数"""
    suggestions = result.get("suggestions", [])
    valid_suggestions = []

    for s in suggestions:
        op = s.get("operation", "")
        if op not in OPERATION_NAMES:
            logger.warning(f"Agent2 建议了未注册的操作: {op}，跳过")
            continue

        # 验证参数中的列名
        params = s.get("parameters", {})
        actual_cols = set(context.data_profile.columns)
        for key in ("columns", "target_columns"):
            if key in params and isinstance(params[key], list):
                params[key] = [c for c in params[key] if c in actual_cols]

        valid_suggestions.append(s)

    return {
        "suggestions": valid_suggestions,
        "interpretation": result.get("interpretation"),
    }


def _fallback_suggestions(context: SessionContext) -> Dict[str, Any]:
    """LLM 失败时基于数据画像生成模板建议"""
    suggestions = []
    num_cols = context.data_profile.numeric_columns
    cat_cols = context.data_profile.categorical_columns
    dt_cols = context.data_profile.datetime_columns
    history_ops = {step.operation for step in context.analysis_history}

    if num_cols and "overview" not in history_ops:
        suggestions.append({
            "title": "数据概览",
            "rationale": "先了解数据的基本分布和统计特征",
            "operation": "overview",
            "parameters": {},
            "expected_insight": "了解数据集的整体情况、缺失值和基本统计量",
        })

    if num_cols and "distribution" not in history_ops:
        col = num_cols[0]
        suggestions.append({
            "title": f"{col} 的分布分析",
            "rationale": "了解核心数值列的分布特征和异常值",
            "operation": "distribution",
            "parameters": {"column": col},
            "expected_insight": f"揭示 {col} 的集中趋势、离散程度和异常值",
        })

    if len(num_cols) >= 2 and "correlation" not in history_ops:
        suggestions.append({
            "title": "数值列相关性分析",
            "rationale": "发现数值变量之间的线性关联",
            "operation": "correlation",
            "parameters": {"columns": num_cols[:5]},
            "expected_insight": "找出高度相关的变量对",
        })

    if cat_cols and num_cols and "comparison" not in history_ops:
        suggestions.append({
            "title": f"按 {cat_cols[0]} 对比 {num_cols[0]}",
            "rationale": "发现不同分组间的差异",
            "operation": "comparison",
            "parameters": {"target_columns": [num_cols[0]], "groupby": cat_cols[0]},
            "expected_insight": f"揭示不同 {cat_cols[0]} 分组下 {num_cols[0]} 的差异",
        })

    if dt_cols and num_cols and "trend" not in history_ops:
        suggestions.append({
            "title": f"{num_cols[0]} 趋势分析",
            "rationale": "观察数值随时间的变化趋势",
            "operation": "trend",
            "parameters": {"columns": [num_cols[0]]},
            "expected_insight": f"揭示 {num_cols[0]} 的时间变化规律",
        })

    # 最多返回 4 条
    return {
        "suggestions": suggestions[:4],
        "interpretation": "基于数据特征推荐以下分析方向，点击即可执行。",
    }
