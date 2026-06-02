"""
资讯中文化：标题翻译、关键词翻译、1~2 句中文摘要
优先规则词典 + 可选在线翻译（失败时回退），不依赖外部付费 API。
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

from collectors.types import NewsItem

logger = logging.getLogger(__name__)

# 英文短语 → 中文（长词优先匹配）
_PHRASE_MAP: tuple[tuple[str, str], ...] = tuple(
    sorted(
        [
            ("federal reserve", "美联储"),
            ("rate cut", "降息"),
            ("rate hike", "加息"),
            ("interest rate", "利率"),
            ("nonfarm payroll", "非农就业"),
            ("jobs report", "就业报告"),
            ("treasury yield", "国债收益率"),
            ("10-year yield", "10年期收益率"),
            ("stock market", "股市"),
            ("wall street", "华尔街"),
            ("s&p 500", "标普500"),
            ("nasdaq", "纳斯达克"),
            ("dow jones", "道琼斯"),
            ("open interest", "持仓量"),
            ("price change", "价格变动"),
            ("record high", "创历史新高"),
            ("all-time high", "历史新高"),
            ("all time high", "历史新高"),
            ("breaking", "突发"),
            ("approval", "获批"),
            ("approved", "已批准"),
            ("rejected", "遭否决"),
            ("lawsuit", "诉讼"),
            ("investigation", "调查"),
            ("liquidation", "爆仓清算"),
            ("inflow", "资金流入"),
            ("outflow", "资金流出"),
            ("partnership", "合作"),
            ("adoption", "采用"),
            ("upgrade", "升级"),
            ("launch", "上线"),
            ("listing", "上市"),
            ("delist", "下架"),
            ("hack", "黑客攻击"),
            ("exploit", "漏洞利用"),
            ("vulnerability", "安全漏洞"),
            ("bankrupt", "破产"),
            ("sanction", "制裁"),
            ("regulation", "监管"),
            ("etf", "ETF"),
            ("inflation", "通胀"),
            ("deflation", "通缩"),
            ("recession", "衰退"),
            ("bullish", "看多"),
            ("bearish", "看空"),
            ("surge", "大涨"),
            ("plunge", "暴跌"),
            ("rally", "反弹"),
            ("crash", "崩盘"),
            ("breakout", "突破"),
            ("solana", "Solana"),
            ("ethereum", "以太坊"),
            ("bitcoin", "比特币"),
            ("crypto", "加密"),
            ("cryptocurrency", "加密货币"),
            ("blockchain", "区块链"),
            ("staking", "质押"),
            ("sec", "美国证监会"),
            ("cpi", "CPI消费者物价"),
            ("ppi", "PPI生产者物价"),
            ("fomc", "FOMC议息会议"),
            ("powell", "鲍威尔"),
            ("fed", "美联储"),
            ("holds rates", "维持利率不变"),
            ("holds", "维持"),
            ("rates", "利率"),
            ("rally", "上涨"),
            ("tumble", "下跌"),
            ("markets", "市场"),
            ("market", "市场"),
            ("completes", "完成"),
            ("upgrade", "升级"),
            ("record", "创新高"),
            ("hits", "触及"),
        ],
        key=lambda x: -len(x[0]),
    )
)

_KEYWORD_CN: dict[str, str] = {
    "BTC": "比特币",
    "ETH": "以太坊",
    "SOL": "Solana",
    "ETF": "ETF",
    "SEC": "证监会",
    "CPI": "CPI",
    "FED": "美联储",
    "FOMC": "FOMC",
    "NFT": "NFT",
    "DeFi": "DeFi",
    "L2": "二层网络",
}


def _is_mainly_chinese(text: str) -> bool:
    if not text:
        return False
    cn = len(re.findall(r"[\u4e00-\u9fff]", text))
    return cn >= max(4, len(text) * 0.25)


@lru_cache(maxsize=512)
def _translate_online(text: str) -> str | None:
    """可选：deep-translator 在线翻译（未安装或失败返回 None）。"""
    if _is_mainly_chinese(text) or len(text) < 3:
        return text
    try:
        from deep_translator import GoogleTranslator

        return GoogleTranslator(source="auto", target="zh-CN").translate(text[:500])
    except Exception:
        return None


def translate_phrases(text: str) -> str:
    """词典替换 + 可选在线补全。"""
    if not text:
        return ""
    if _is_mainly_chinese(text):
        return text.strip()

    out = text.strip()
    for en, zh in _PHRASE_MAP:
        out = re.sub(re.escape(en), zh, out, flags=re.IGNORECASE)

    online = _translate_online(out if out != text else text)
    if online and online.strip():
        return online.strip()
    return out.strip()


def localize_keywords(keywords: list[str]) -> list[str]:
    result: list[str] = []
    for kw in keywords:
        k = str(kw).strip()
        if not k:
            continue
        upper = k.upper()
        if upper in _KEYWORD_CN:
            result.append(_KEYWORD_CN[upper])
        elif _is_mainly_chinese(k):
            result.append(k)
        else:
            result.append(translate_phrases(k))
    return list(dict.fromkeys(result))[:5]


def market_bias_label(score: float) -> str:
    if score >= 2:
        return "偏多（利多）"
    if score <= -2:
        return "偏空（利空）"
    return "中性"


def generate_summary_cn(
    title_cn: str,
    *,
    impact_score: float,
    logic: str = "",
) -> str:
    """生成 1~2 句中文核心摘要。"""
    bias = market_bias_label(impact_score)
    core = title_cn[:120] if title_cn else "市场相关资讯"

    if logic and _is_mainly_chinese(logic):
        hint = logic.split("；")[0][:80]
        return f"{core}。{hint}，对市场{bias}。"
    if logic:
        logic_cn = translate_phrases(logic.split("；")[0])[:80]
        return f"{core}。{logic_cn}，对市场{bias}。"

    if impact_score >= 2:
        return f"{core}。该消息短期利好风险资产，对市场{bias}。"
    if impact_score <= -2:
        return f"{core}。该消息可能引发抛压或避险情绪，对市场{bias}。"
    return f"{core}。影响有限，当前评估为{bias}。"


def build_display_fields(item: NewsItem) -> dict[str, Any]:
    """为展示字典追加中文字段（不修改原始 title）。"""
    title_cn = translate_phrases(item.title)
    keywords_cn = localize_keywords(item.keywords)
    logic_cn = translate_phrases(item.logic) if item.logic else ""
    summary_cn = generate_summary_cn(
        title_cn,
        impact_score=item.impact_score,
        logic=item.logic,
    )
    return {
        "title_cn": title_cn,
        "summary_cn": summary_cn,
        "keywords_cn": keywords_cn,
        "logic_cn": logic_cn,
        "display_title": title_cn,
        "display_keywords": keywords_cn,
    }
