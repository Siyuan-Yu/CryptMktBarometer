"""
资讯中文化：纯中文标题、规范摘要、中文关键词胶囊
词典 + 可选在线翻译；剔除中英混杂残留。
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

from collectors.types import NewsItem

logger = logging.getLogger(__name__)

_EN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9'’.-]{1,}")
_LATIN_CHUNK = re.compile(r"[A-Za-z]{4,}")

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
            ("10-year yield", "10年期美债收益率"),
            ("stock market", "美国股市"),
            ("wall street", "华尔街"),
            ("s&p 500", "标普500指数"),
            ("nasdaq", "纳斯达克指数"),
            ("dow jones", "道琼斯指数"),
            ("earnings report", "财报"),
            ("inflation data", "通胀数据"),
            ("pay.sh", "Pay.sh支付"),
            ("solana foundation", "Solana基金会"),
            ("open interest", "持仓量"),
            ("record high", "创历史新高"),
            ("all-time high", "历史新高"),
            ("breaking", "突发"),
            ("approval", "获批"),
            ("approved", "已批准"),
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
            ("regulation", "监管"),
            ("etf", "交易所交易基金"),
            ("inflation", "通货膨胀"),
            ("recession", "经济衰退"),
            ("bullish", "看多"),
            ("bearish", "看空"),
            ("surge", "大涨"),
            ("plunge", "暴跌"),
            ("rally", "反弹"),
            ("crash", "崩盘"),
            ("solana", "索拉纳公链"),
            ("ethereum", "以太坊"),
            ("bitcoin", "比特币"),
            ("crypto", "加密货币"),
            ("cryptocurrency", "加密货币"),
            ("blockchain", "区块链"),
            ("staking", "质押"),
            ("sec", "美国证监会"),
            ("cpi", "消费者物价指数"),
            ("ppi", "生产者物价指数"),
            ("fomc", "美联储议息会议"),
            ("powell", "美联储主席鲍威尔"),
            ("vitalik", "以太坊创始人维塔利克"),
            ("proposes", "提议"),
            ("proposal", "提案"),
            ("announces", "宣布"),
            ("according to", "据报道"),
            ("report", "报告"),
            ("market", "市场"),
            ("markets", "市场"),
            ("trump", "特朗普"),
            ("tariff", "关税"),
            ("tariffs", "关税"),
        ],
        key=lambda x: -len(x[0]),
    )
)

_KEYWORD_CN: dict[str, str] = {
    "BTC": "比特币",
    "ETH": "以太坊",
    "SOL": "索拉纳",
    "ETF": "交易基金",
    "SEC": "美国证监会",
    "CPI": "消费者物价",
    "PPI": "生产者物价",
    "FED": "美联储",
    "FOMC": "议息会议",
    "NFT": "非同质化代币",
    "DEFI": "去中心化金融",
    "L2": "二层网络",
    "NFP": "非农就业",
    "PMI": "采购经理指数",
    "GDP": "国内生产总值",
    "DXY": "美元指数",
}


def _chinese_ratio(text: str) -> float:
    if not text:
        return 0.0
    cn = len(re.findall(r"[\u4e00-\u9fff]", text))
    return cn / max(len(text), 1)


def _is_mainly_chinese(text: str) -> bool:
    if not text:
        return False
    return _chinese_ratio(text) >= 0.45


@lru_cache(maxsize=512)
def _translate_online(text: str) -> str | None:
    if _is_mainly_chinese(text) or len(text) < 2:
        return text
    try:
        from deep_translator import GoogleTranslator

        return GoogleTranslator(source="auto", target="zh-CN").translate(text[:500])
    except Exception:
        return None


def translate_phrases(text: str) -> str:
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


def _strip_latin_fragments(text: str) -> str:
    """删除残留英文字符，保留已有中文与数字标点。"""
    t = re.sub(r"[A-Za-z][A-Za-z0-9'’.-]*", " ", text)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[·•|]{2,}", "·", t)
    t = re.sub(r"^[，。、\s]+|[，。、\s]+$", "", t)
    return t.strip()


def polish_chinese_text(text: str, *, force_full_translate: bool = False) -> str:
    """润色为通顺纯中文，剔除零散英文碎片。"""
    if not text:
        return ""
    raw = text.strip()

    if force_full_translate or not _is_mainly_chinese(raw):
        online = _translate_online(raw)
        if online and online.strip():
            raw = online.strip()
        else:
            raw = translate_phrases(raw)
    else:
        raw = translate_phrases(raw)

    if _EN_TOKEN.search(raw) or _LATIN_CHUNK.search(raw):
        online = _translate_online(text)
        if online and online.strip():
            raw = online.strip()

    raw = _strip_latin_fragments(raw)
    return raw or "市场相关资讯"


def to_pure_chinese_title(title: str) -> str:
    """标题仅输出纯中文。"""
    raw = (title or "").strip()
    if not raw:
        return "暂无标题"
    cn = polish_chinese_text(raw, force_full_translate=True)
    if _EN_TOKEN.search(cn):
        online = _translate_online(title)
        if online:
            cn = _strip_latin_fragments(online)
    return cn or "市场相关资讯"


def localize_keywords(keywords: list[str]) -> list[str]:
    result: list[str] = []
    for kw in keywords:
        k = str(kw).strip()
        if not k:
            continue
        upper = k.upper()
        if upper in _KEYWORD_CN:
            cn = _KEYWORD_CN[upper]
        elif _is_mainly_chinese(k):
            cn = polish_chinese_text(k)
        else:
            cn = polish_chinese_text(translate_phrases(k))
        if cn and cn not in result:
            result.append(cn)
    return result[:5]


def impact_suffix(score: float) -> str:
    s = float(score)
    if s > 0:
        return f"【利多：+{s:.1f}分】"
    if s < 0:
        return f"【利空：{s:.1f}分】"
    return "【中性：0分】"


def generate_summary_cn(
    title_cn: str,
    *,
    impact_score: float,
    logic: str = "",
) -> str:
    """摘要 = 中文简述 + 【利多/利空：xx分】"""
    core = (title_cn or "市场相关资讯")[:100]
    hint = ""
    if logic:
        hint = polish_chinese_text(
            logic.split("；")[0].split(";")[0], force_full_translate=True
        )[:72]
        hint = re.sub(r"社区投票.*", "", hint).strip()
        hint = re.sub(r"标题含.*", "", hint).strip()

    if hint and len(hint) > 6 and hint not in core:
        body = f"{core}。{hint.rstrip('。')}。"
    else:
        body = f"{core}。"

    return body + impact_suffix(impact_score)


def build_display_fields(item: NewsItem) -> dict[str, Any]:
    from collectors.news_categories import classify_news_tag

    title_cn = to_pure_chinese_title(item.title)
    keywords_cn = localize_keywords(item.keywords)
    summary_cn = generate_summary_cn(
        title_cn,
        impact_score=item.impact_score,
        logic=item.logic,
    )
    tag = classify_news_tag(item)
    return {
        "title_cn": title_cn,
        "summary_cn": summary_cn,
        "keywords_cn": keywords_cn,
        "logic_cn": polish_chinese_text(item.logic) if item.logic else "",
        "display_title": title_cn,
        "display_keywords": keywords_cn,
        "category_label": tag,
        "source_tag": tag,
    }
