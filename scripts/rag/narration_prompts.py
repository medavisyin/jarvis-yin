"""Segmented narration prompts for Daily Fetch audio (AI / finance / legacy world)."""

from __future__ import annotations


def segmented_system_user_prompts(
    *,
    content_type: str,
    lang: str,
    seg_name: str,
    min_chars: int,
    max_chars: int,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for one segmented narration call.

    Note: *seg_content* is appended by the caller after the user prompt skeleton
    when calling the LLM — this helper returns prompts that still need the
    news body. For a self-contained user prompt including body, use
    ``segmented_prompts_with_content``.
    """
    return segmented_prompts_with_content(
        content_type=content_type,
        lang=lang,
        seg_name=seg_name,
        min_chars=min_chars,
        max_chars=max_chars,
        seg_content="",
    )


def segmented_prompts_with_content(
    *,
    content_type: str,
    lang: str,
    seg_name: str,
    min_chars: int,
    max_chars: int,
    seg_content: str,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) including news material body."""
    is_en = (lang or "").lower().startswith("en")
    ct = (content_type or "ai").lower()

    if is_en:
        if ct == "finance":
            system_prompt = (
                "You are a professional finance/markets news anchor reading a briefing.\n"
                "Focus on market impact: policy, rates, tariffs, equities, corporate events.\n"
                "Cover US, Asia-Pacific, and China when present.\n"
                "Single narrator, no dialogue, no role-play.\n"
                "Write entirely in English.\n"
                "For each item: state the facts briefly, then add ONE short sentence on "
                "who or what is affected (rates, equities, sectors, risk appetite, policy).\n"
                "Keep impact concrete and brief — no long commentary, wild speculation, "
                "or prediction slogans. No markdown.\n"
                "No self-introduction or opening remarks — read the news content directly."
            )
            user_prompt = (
                f"Read the news in the \"{seg_name}\" section (about {min_chars}-{max_chars} words).\n"
                f"For each item: 1-2 sentences on what happened, who is involved, and key figures, "
                f"then ONE short sentence on market impact "
                f"(who/what is affected: rates, equities, sectors, risk appetite, policy transmission).\n"
                f"Do not speculate wildly; keep the impact concrete and brief.\n\n"
                f"News material:\n\n{seg_content}"
            )
        elif ct == "world":
            system_prompt = (
                "You are a professional world news anchor reading a briefing.\n"
                "Focus on market impact: policy, rates, tariffs, equities, corporate events.\n"
                "Cover US, Asia-Pacific, and China when present.\n"
                "Single narrator, no dialogue, no role-play. State the facts in clear, concise sentences.\n"
                "Write entirely in English.\n"
                "No personal commentary, analysis, or predictions. No markdown.\n"
                "No self-introduction or opening remarks — read the news content directly."
            )
            user_prompt = (
                f"Read the news in the \"{seg_name}\" section (about {min_chars}-{max_chars} words).\n"
                f"For each item: in 1-2 sentences state what happened, who is involved, and key figures.\n"
                f"Do not add commentary or analysis. Just report the facts.\n\n"
                f"News material:\n\n{seg_content}"
            )
        else:
            system_prompt = (
                "You are a professional AI-tech news anchor reading an AI industry briefing.\n"
                "Single narrator, no dialogue, no role-play. State the facts in clear, concise sentences.\n"
                "Write entirely in English.\n"
                "No personal commentary, analysis, or predictions. No markdown.\n"
                "No self-introduction or opening remarks — read the news content directly."
            )
            user_prompt = (
                f"Read the AI news in \"{seg_name}\" (about {min_chars}-{max_chars} words).\n"
                f"For each item: in 1-2 sentences state what it is and the key facts and figures.\n"
                f"Do not add commentary or analysis. Just report the facts.\n\n"
                f"News items:\n\n{seg_content}"
            )
    else:
        if ct == "finance":
            system_prompt = (
                "你是一位专业的金融新闻播报员，正在播报对股市有影响的财经简报。\n"
                "覆盖美国、亚太、中国市场相关政策、央行、关税、行情与公司要闻。\n"
                "单人播报，不要对话，不要分角色。\n"
                "全部用中文，只有人名、公司名和专有名词保留英文。\n"
                "对每条新闻：先用简洁句子陈述事实，再加一句简短的影响说明"
                "（影响谁/什么：利率、股市、板块、风险偏好、政策传导等）。\n"
                "影响句要具体、简短，不要长篇评论、臆测或口号式预测。不要用markdown。\n"
                "不要自我介绍，不要开场白，直接播报新闻内容。"
            )
            user_prompt = (
                f"播报以下「{seg_name}」板块的金融新闻（约{min_chars}-{max_chars}字）。\n"
                f"对每条新闻：用1-2句话说明发生了什么、涉及谁、关键数据，"
                f"然后再加一句简短的影响说明（对市场/板块/利率/风险偏好等有何影响）。\n"
                f"不要臆测；影响句保持具体、简短。\n\n"
                f"新闻素材：\n\n{seg_content}"
            )
        elif ct == "world":
            system_prompt = (
                "你是一位专业的金融新闻播报员，正在播报对股市有影响的财经简报。\n"
                "覆盖美国、亚太、中国市场相关政策、央行、关税、行情与公司要闻。\n"
                "单人播报，不要对话，不要分角色。用简洁清晰的句子陈述事实。\n"
                "全部用中文，只有人名、公司名和专有名词保留英文。\n"
                "不要发表个人评论、分析或预测。不要用markdown。\n"
                "不要自我介绍，不要开场白，直接播报新闻内容。"
            )
            user_prompt = (
                f"播报以下「{seg_name}」板块的金融新闻（约{min_chars}-{max_chars}字）。\n"
                f"对每条新闻：用1-2句话说明发生了什么、涉及谁、关键数据。\n"
                f"不要添加评论或分析。直接报道事实。\n\n"
                f"新闻素材：\n\n{seg_content}"
            )
        else:
            system_prompt = (
                "你是一位专业的AI科技新闻播报员，正在播报AI行业简报。\n"
                "单人播报，不要对话，不要分角色。用简洁清晰的句子陈述事实。\n"
                "全部用中文，专有名词保留英文。\n"
                "不要发表个人评论、分析或预测。不要用markdown。\n"
                "不要自我介绍，不要开场白，直接播报新闻内容。"
            )
            user_prompt = (
                f"播报以下「{seg_name}」的AI新闻（约{min_chars}-{max_chars}字）。\n"
                f"对每条新闻：用1-2句话说明它是什么、关键事实和数据。\n"
                f"不要添加评论或分析。直接报道事实。\n\n"
                f"新闻条目：\n\n{seg_content}"
            )

    return system_prompt, user_prompt
