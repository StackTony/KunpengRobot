"""LLM 接入层: OpenAI 兼容 API 流式调用; 未配置时降级为纯规则总结."""
import logging
from typing import AsyncIterator

from openai import AsyncOpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def llm_enabled() -> bool:
    return bool(settings.LLM_API_BASE and settings.LLM_API_KEY)


def get_client() -> AsyncOpenAI:
    return AsyncOpenAI(base_url=settings.LLM_API_BASE, api_key=settings.LLM_API_KEY)


async def stream_summary(context: str) -> AsyncIterator[str]:
    """将规则命中结果 + 关键日志片段送入 LLM, 流式产出总结 token.

    调用方将每个 token 通过 EventBus 发布, 前端呈现打字机效果.
    """
    if not llm_enabled():
        yield "(LLM 未配置, 降级为纯规则报告)"
        return

    client = get_client()
    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": (
                "你是资深运维专家。根据提供的日志规则命中结果与关键日志片段，"
                "给出：1) 故障根因分析 2) 处置建议。简洁、分点、中文。")},
            {"role": "user", "content": context[:32000]},
        ],
        stream=True,
    )
    async for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def rule_only_summary(findings: list[dict]) -> str:
    """纯规则总结 (LLM 不可用时的降级输出)."""
    if not findings:
        return "未发现异常。"
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    lines = [f"共命中 {len(findings)} 条规则: " + ", ".join(f"{k}×{v}" for k, v in counts.items())]
    for f in findings[:20]:
        lines.append(f"[{f['severity']}] {f['rule_name']}: {f.get('matched_text', '')[:120]}")
    return "\n".join(lines)
