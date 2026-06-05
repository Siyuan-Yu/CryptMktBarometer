"""
动态权重优化 + 历史回测核心模块

功能：
  1. 根据近 7/30 天消息实际价格冲击，自适应四大模块权重
  2. 记录 TOP 资讯发布后 1h/4h/24h BTC/ETH/SOL 涨跌幅
  3. 历史回测：固定权重 vs 动态权重准确率对比

独立模块，不修改原有 scoring 算法，仅替换权重与总分合成方式。
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from collectors.types import NewsItem
from core.config_loader import PROJECT_ROOT, load_config
from core.market_rating import rating_from_total_score
from scoring.constants import (
    FUNDAMENTALS_KEYWORDS,
    LEGACY_WEIGHT_FUNDAMENTALS,
    LEGACY_WEIGHT_FUNDING,
    LEGACY_WEIGHT_MACRO,
    LEGACY_WEIGHT_REGULATION,
    REGULATION_KEYWORDS,
    WEIGHT_FUNDAMENTALS,
    WEIGHT_FUNDING,
    WEIGHT_MACRO,
    WEIGHT_REGULATION,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 模块键与固定权重（兼容旧版）
# ---------------------------------------------------------------------------
MODULE_MACRO = "macro"
MODULE_REGULATION = "regulation"
MODULE_FUNDING = "funding"
MODULE_FUNDAMENTALS = "fundamentals"

MODULE_ORDER = (MODULE_MACRO, MODULE_REGULATION, MODULE_FUNDING, MODULE_FUNDAMENTALS)

# 回测最优基准权重（当前默认）
STATIC_WEIGHTS: dict[str, int] = {
    MODULE_MACRO: WEIGHT_MACRO,
    MODULE_REGULATION: WEIGHT_REGULATION,
    MODULE_FUNDING: WEIGHT_FUNDING,
    MODULE_FUNDAMENTALS: WEIGHT_FUNDAMENTALS,
}

# 旧版权重（回测对比）
LEGACY_WEIGHTS: dict[str, int] = {
    MODULE_MACRO: LEGACY_WEIGHT_MACRO,
    MODULE_REGULATION: LEGACY_WEIGHT_REGULATION,
    MODULE_FUNDING: LEGACY_WEIGHT_FUNDING,
    MODULE_FUNDAMENTALS: LEGACY_WEIGHT_FUNDAMENTALS,
}

SMOOTH_ALPHA = 0.28

WEIGHT_BOUNDS: dict[str, tuple[int, int]] = {
    MODULE_MACRO: (20, 50),
    MODULE_REGULATION: (10, 30),
    MODULE_FUNDING: (15, 35),
    MODULE_FUNDAMENTALS: (5, 20),
}

CATEGORY_TO_MODULE = {
    "宏观数据": MODULE_MACRO,
    "全球监管政策": MODULE_REGULATION,
    "资金链上数据": MODULE_FUNDING,
    "ETH/SOL 币种基本面": MODULE_FUNDAMENTALS,
}

# 突发事件关键词 → 提升对应模块
EVENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    MODULE_MACRO: (
        "cpi", "ppi", "nonfarm", "nfp", "fed", "fomc", "powell", "rate cut",
        "rate hike", "inflation", "jobs report", "treasury", "降息", "加息", "非农",
    ),
    MODULE_REGULATION: (
        "sec", "etf approval", "lawsuit", "ban", "regulation", "congress",
        "cftc", "approved", "rejected", "诉讼", "监管",
    ),
    MODULE_FUNDING: (
        "etf flow", "liquidation", "爆仓", "open interest", "inflow", "outflow",
        "whale", "funding rate",
    ),
    MODULE_FUNDAMENTALS: (
        "ethereum", "solana", "staking", "hack", "exploit", "mainnet upgrade",
    ),
}

SPIKE_THRESHOLD = 2.5
WEAK_THRESHOLD = 0.35
WEAK_STREAK = 3
EVENT_BOOST_FACTOR = 1.20
EVENT_BOOST_HOURS = 24
IDLE_DECAY_FACTOR = 0.94
WEAK_STREAK_DECAY = 0.90


@dataclass
class DynamicWeights:
    macro: int = WEIGHT_MACRO
    regulation: int = WEIGHT_REGULATION
    funding: int = WEIGHT_FUNDING
    fundamentals: int = WEIGHT_FUNDAMENTALS
    method: str = "static"
    updated_at: str = ""

    def as_dict(self) -> dict[str, int]:
        return {
            MODULE_MACRO: self.macro,
            MODULE_REGULATION: self.regulation,
            MODULE_FUNDING: self.funding,
            MODULE_FUNDAMENTALS: self.fundamentals,
        }

    def as_list_for_ui(self) -> list[dict[str, Any]]:
        from storage import impact_db

        labels = {
            MODULE_MACRO: "宏观数据",
            MODULE_REGULATION: "全球监管政策",
            MODULE_FUNDING: "资金链上数据",
            MODULE_FUNDAMENTALS: "ETH/SOL 币种基本面",
        }
        baseline = STATIC_WEIGHTS
        legacy = LEGACY_WEIGHTS
        rows = []
        for k in MODULE_ORDER:
            w = self.as_dict()[k]
            boosted = impact_db.has_recent_event(k, EVENT_BOOST_HOURS)
            rows.append(
                {
                    "name": labels[k],
                    "module": k,
                    "weight": w,
                    "bar_percent": w,
                    "baseline_weight": baseline[k],
                    "static_weight": legacy[k],
                    "delta": w - baseline[k],
                    "event_boost": boosted,
                }
            )
        return rows


@dataclass
class ModuleInfluence:
    """各模块市场影响力（最近窗口）。"""

    window_days: int
    scores: dict[str, float] = field(default_factory=dict)
    signed_scores: dict[str, float] = field(default_factory=dict)
    sample_counts: dict[str, int] = field(default_factory=dict)

    def as_ui_rows(self, signed: dict[str, float] | None = None) -> list[dict[str, Any]]:
        labels = {
            MODULE_MACRO: "宏观数据",
            MODULE_REGULATION: "全球监管政策",
            MODULE_FUNDING: "资金链上数据",
            MODULE_FUNDAMENTALS: "ETH/SOL 币种基本面",
        }
        signed = signed or {}
        rows = []
        for k in MODULE_ORDER:
            s = float(signed.get(k, 0))
            rows.append(
                {
                    "name": labels[k],
                    "influence": round(self.scores.get(k, 0.0), 2),
                    "signed": round(s, 2),
                    "samples": self.sample_counts.get(k, 0),
                    "color_class": _impact_color_class(s),
                }
            )
        return rows


def _impact_color_class(signed: float) -> str:
    if signed > 0.15:
        return "impact-pos"
    if signed < -0.15:
        return "impact-neg"
    return "impact-neutral"


@dataclass
class BacktestResult:
    start_date: str
    end_date: str
    sample_days: int
    fixed_accuracy: float
    dynamic_accuracy: float
    fixed_correlation: float
    dynamic_correlation: float
    optimal_weights: DynamicWeights
    message: str = ""
    csv_path: str = ""

    def summary_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "sample_days": self.sample_days,
            "fixed_accuracy": f"{self.fixed_accuracy:.1%}",
            "dynamic_accuracy": f"{self.dynamic_accuracy:.1%}",
            "fixed_correlation": round(self.fixed_correlation, 3),
            "dynamic_correlation": round(self.dynamic_correlation, 3),
            "optimal_weights": self.optimal_weights.as_dict(),
            "message": self.message,
            "csv_path": self.csv_path,
        }


# ---------------------------------------------------------------------------
# 分类与事件检测
# ---------------------------------------------------------------------------
def classify_news_module(title: str) -> str:
    lower = title.lower()
    if any(k in lower for k in EVENT_KEYWORDS[MODULE_MACRO]):
        return MODULE_MACRO
    if any(k in lower for k in REGULATION_KEYWORDS):
        return MODULE_REGULATION
    if any(k in lower for k in ("liquidation", "etf", "inflow", "outflow", "open interest")):
        return MODULE_FUNDING
    if any(k in lower for k in FUNDAMENTALS_KEYWORDS):
        return MODULE_FUNDAMENTALS
    return MODULE_REGULATION


def is_breaking_event(title: str, module: str) -> bool:
    lower = title.lower()
    return any(k in lower for k in EVENT_KEYWORDS.get(module, ()))


# ---------------------------------------------------------------------------
# 价格冲击测算
# ---------------------------------------------------------------------------
def _parse_datetime(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        pub = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        return pub
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def measure_pending_impacts() -> int:
    """补全已发布满 24h 的消息的实际冲击值。"""
    from storage import impact_db, price_db

    price_db.init_schema()
    impact_db.init_schema()

    updated = 0
    for row in impact_db.list_pending_measurement():
        pub = _parse_datetime(row["published_at"])
        if pub is None:
            continue
        now = datetime.now(timezone.utc)
        if now < pub + timedelta(hours=24):
            continue

        cfg = load_config()
        syms = cfg.get("weight_optimizer", {}).get("price_symbols", ["BTC", "ETH", "SOL"])

        a1 = price_db.composite_pct_change(pub, 1, syms)
        a4 = price_db.composite_pct_change(pub, 4, syms)
        a24 = price_db.composite_pct_change(pub, 24, syms)
        if a24 is None:
            continue

        impact_db.update_actual_impacts(
            row["id"],
            actual_1h=a1,
            actual_4h=a4,
            actual_24h=a24,
            composite_24h=a24,
        )
        updated += 1
    return updated


def register_top_news(news_items: list[NewsItem], top_display: list[dict]) -> None:
    """将 TOP 资讯写入冲击待测表。"""
    from storage import impact_db

    impact_db.init_schema()
    url_to_item = {n.url: n for n in news_items if n.url}
    for row in top_display:
        item = url_to_item.get(row.get("url", ""))
        title = row.get("title") or (item.title if item else "")
        if not title:
            continue
        mod = classify_news_module(title)
        pred = float(row.get("impact_score") or (item.impact_score if item else 0))
        pub = datetime.now(timezone.utc)
        if item and item.published_at:
            try:
                pub = datetime.fromisoformat(item.published_at.replace("Z", "+00:00"))
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        source_tag = ""
        if item and item.raw:
            source_tag = item.raw.get("source_tag") or ""
        source_label = row.get("source", "") or (item.source if item else "")
        if source_tag:
            source_label = f"{source_label}·{source_tag}"

        impact_db.insert_news_pending(
            title=title,
            source=source_label[:120],
            url=row.get("url", ""),
            module=mod,
            published_at=pub,
            predicted_impact=pred,
            is_event=is_breaking_event(title, mod),
        )


# ---------------------------------------------------------------------------
# 动态权重计算
# ---------------------------------------------------------------------------
def _influence_to_raw_weights(influence_7: dict, influence_30: dict) -> dict[str, float]:
    raw: dict[str, float] = {}
    for mod in MODULE_ORDER:
        s7 = influence_7.get(mod, {})
        s30 = influence_30.get(mod, {})
        v7 = float(s7.get("abs_avg", 0)) + float(s7.get("event_ratio", 0)) * 2
        v30 = float(s30.get("abs_avg", 0))
        raw[mod] = v7 * 0.6 + v30 * 0.4 + 0.5
    return raw


def _apply_event_boost_24h(weights: dict[str, float]) -> dict[str, float]:
    """突发事件：24 小时内相关模块临时 +20%，过期自动恢复（依赖库内 is_event 标记）。"""
    from storage import impact_db

    for mod in MODULE_ORDER:
        if impact_db.has_recent_event(mod, EVENT_BOOST_HOURS):
            weights[mod] *= EVENT_BOOST_FACTOR
    return weights


def _apply_rules(weights: dict[str, float], inf7: dict, inf30: dict) -> dict[str, float]:
    from storage import impact_db

    for mod in MODULE_ORDER:
        s7 = inf7.get(mod, {})
        s30 = inf30.get(mod, {})
        a7 = float(s7.get("abs_avg", 0))
        a30 = float(s30.get("abs_avg", 0))

        if a30 >= 1.2:
            weights[mod] *= 1.0 + min(0.18, a30 / 14.0)
        if impact_db.module_idle_days(mod, 30, threshold=0.15):
            weights[mod] *= IDLE_DECAY_FACTOR
        if impact_db.recent_weak_streak(mod, WEAK_THRESHOLD, WEAK_STREAK):
            weights[mod] *= WEAK_STREAK_DECAY
        if a7 >= SPIKE_THRESHOLD:
            weights[mod] *= 1.15
        if float(s7.get("event_ratio", 0)) >= 0.2:
            weights[mod] *= 1.10
    return weights


def _smooth_with_previous(new_w: DynamicWeights, prev: DynamicWeights | None, alpha: float) -> DynamicWeights:
    if prev is None:
        return new_w
    blended = {
        mod: prev.as_dict()[mod] * (1 - alpha) + new_w.as_dict()[mod] * alpha for mod in MODULE_ORDER
    }
    bounded = _normalize_weights(blended)
    bounded.method = new_w.method + "+smooth"
    bounded.updated_at = new_w.updated_at
    return bounded


def _load_previous_weights() -> DynamicWeights | None:
    from storage import impact_db

    row = impact_db.load_weight_state()
    if not row:
        return None
    return DynamicWeights(
        macro=int(row["macro"]),
        regulation=int(row["regulation"]),
        funding=int(row["funding"]),
        fundamentals=int(row["fundamentals"]),
        method=str(row.get("method") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


def _normalize_weights(raw: dict[str, float]) -> DynamicWeights:
    """在模块上下限内归一化，保证总和恒为 100，避免单点跳变。"""
    bounded: dict[str, float] = {}
    for mod in MODULE_ORDER:
        lo, hi = WEIGHT_BOUNDS[mod]
        bounded[mod] = clamp(raw.get(mod, 1.0), lo, hi)

    for _ in range(64):
        total = sum(bounded.values())
        if total <= 0:
            return _static_weights()
        if abs(total - 100.0) < 0.01:
            break
        for mod in MODULE_ORDER:
            lo, hi = WEIGHT_BOUNDS[mod]
            bounded[mod] = clamp(bounded[mod] * 100.0 / total, lo, hi)

    scaled = {m: bounded[m] / sum(bounded.values()) * 100.0 for m in MODULE_ORDER}
    ints = {m: int(round(scaled[m])) for m in MODULE_ORDER}
    for mod in MODULE_ORDER:
        lo, hi = WEIGHT_BOUNDS[mod]
        ints[mod] = int(clamp(ints[mod], lo, hi))

    guard = 0
    while sum(ints.values()) != 100 and guard < 200:
        guard += 1
        diff = 100 - sum(ints.values())
        adjusted = False
        order = MODULE_ORDER if diff > 0 else list(reversed(MODULE_ORDER))
        for mod in order:
            lo, hi = WEIGHT_BOUNDS[mod]
            if diff > 0 and ints[mod] < hi:
                ints[mod] += 1
                adjusted = True
                break
            if diff < 0 and ints[mod] > lo:
                ints[mod] -= 1
                adjusted = True
                break
        if not adjusted:
            break

    return DynamicWeights(
        macro=ints[MODULE_MACRO],
        regulation=ints[MODULE_REGULATION],
        funding=ints[MODULE_FUNDING],
        fundamentals=ints[MODULE_FUNDAMENTALS],
        method="dynamic",
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def compute_dynamic_weights(cfg: dict | None = None) -> DynamicWeights:
    """根据近 7/30 天实际冲击计算动态权重。"""
    cfg = cfg or load_config()
    opt = cfg.get("weight_optimizer", {})
    if not opt.get("enabled", True):
        return _static_weights()

    from storage import impact_db

    impact_db.init_schema()
    inf7 = impact_db.module_influence_stats(int(opt.get("window_short_days", 7)))
    inf30 = impact_db.module_influence_stats(int(opt.get("window_long_days", 30)))

    total_samples = sum(int(inf7.get(m, {}).get("count", 0)) for m in MODULE_ORDER)
    if total_samples < int(opt.get("min_samples_for_dynamic", 5)):
        w = _static_weights()
        w.method = "static_insufficient_data"
        w.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return w

    raw = _influence_to_raw_weights(inf7, inf30)
    raw = _apply_rules(raw, inf7, inf30)
    raw = _apply_event_boost_24h(raw)
    new_w = _normalize_weights(raw)
    alpha = float(opt.get("smooth_alpha", SMOOTH_ALPHA))
    prev = _load_previous_weights()
    return _smooth_with_previous(new_w, prev, alpha)


def _legacy_weights() -> DynamicWeights:
    return DynamicWeights(
        macro=LEGACY_WEIGHTS[MODULE_MACRO],
        regulation=LEGACY_WEIGHTS[MODULE_REGULATION],
        funding=LEGACY_WEIGHTS[MODULE_FUNDING],
        fundamentals=LEGACY_WEIGHTS[MODULE_FUNDAMENTALS],
        method="legacy_40_20_25_15",
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def _static_weights() -> DynamicWeights:
    return DynamicWeights(
        macro=STATIC_WEIGHTS[MODULE_MACRO],
        regulation=STATIC_WEIGHTS[MODULE_REGULATION],
        funding=STATIC_WEIGHTS[MODULE_FUNDING],
        fundamentals=STATIC_WEIGHTS[MODULE_FUNDAMENTALS],
        method="static",
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def get_module_influence(window_days: int = 30) -> ModuleInfluence:
    from storage import impact_db

    stats = impact_db.module_influence_stats(window_days)
    scores = {m: float(stats.get(m, {}).get("abs_avg", 0)) for m in MODULE_ORDER}
    signed = {m: float(stats.get(m, {}).get("signed_avg", 0)) for m in MODULE_ORDER}
    counts = {m: int(stats.get(m, {}).get("count", 0)) for m in MODULE_ORDER}
    return ModuleInfluence(
        window_days=window_days,
        scores=scores,
        signed_scores=signed,
        sample_counts=counts,
    )


def get_dual_module_influence() -> tuple[ModuleInfluence, ModuleInfluence]:
    return get_module_influence(7), get_module_influence(30)


# ---------------------------------------------------------------------------
# 与计分引擎对接：用动态权重合成总分
# ---------------------------------------------------------------------------
def apply_dynamic_total(
    categories: list[dict[str, Any]],
    weights: DynamicWeights,
) -> tuple[float, list[dict[str, Any]]]:
    """
    将原分项得分（按旧满分计量）归一化后，用动态权重合成总分。
    返回 (total_score, 更新后的 categories)
    """
    static_max = {
        MODULE_MACRO: WEIGHT_MACRO,
        MODULE_REGULATION: WEIGHT_REGULATION,
        MODULE_FUNDING: WEIGHT_FUNDING,
        MODULE_FUNDAMENTALS: WEIGHT_FUNDAMENTALS,
    }
    wmap = weights.as_dict()
    total = 0.0
    updated: list[dict[str, Any]] = []

    for cat in categories:
        mod = CATEGORY_TO_MODULE.get(cat["name"], MODULE_REGULATION)
        old_max = static_max[mod]
        raw_score = float(cat.get("score") or 0)
        norm = raw_score / old_max if old_max else 0.5
        norm = clamp(norm, 0.0, 1.0)
        w = wmap[mod]
        weighted_pts = round(norm * w, 1)
        total += weighted_pts
        new_cat = dict(cat)
        new_cat["weight"] = w
        new_cat["score"] = weighted_pts
        new_cat["norm_ratio"] = round(norm * 100, 1)
        updated.append(new_cat)

    total = round(clamp(total, 0, 100), 1)
    return total, updated


# ---------------------------------------------------------------------------
# 回测
# ---------------------------------------------------------------------------
def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx * dy == 0:
        return 0.0
    return num / (dx * dy)


def _direction_accuracy(pred: list[float], actual: list[float]) -> float:
    if not pred:
        return 0.0
    hits = sum(1 for p, a in zip(pred, actual) if (p >= 0) == (a >= 0))
    return hits / len(pred)


def _grid_search_weights(daily_module: dict[str, dict[str, float]], btc_returns: dict[str, float]) -> DynamicWeights:
    """在权重边界内网格搜索，最大化与 BTC 24h 收益相关性。"""
    best_corr = -2.0
    best = _static_weights()

    macro_range = range(20, 51, 10)
    reg_range = range(10, 31, 10)
    fund_range = range(15, 36, 10)

    days = sorted(btc_returns.keys())
    for ma in macro_range:
        for rg in reg_range:
            for fd in fund_range:
                fu = 100 - ma - rg - fd
                if not (5 <= fu <= 20):
                    continue
                w = DynamicWeights(macro=ma, regulation=rg, funding=fd, fundamentals=fu)
                preds = []
                acts = []
                for d in days:
                    mods = daily_module.get(d, {})
                    if d not in btc_returns:
                        continue
                    score = sum(mods.get(m, 0) * w.as_dict()[m] / 100.0 for m in MODULE_ORDER)
                    preds.append(score)
                    acts.append(btc_returns[d])
                if len(preds) < 5:
                    continue
                corr = _pearson(preds, acts)
                if corr > best_corr:
                    best_corr = corr
                    best = w
    best.method = "backtest_optimal"
    return best


def _build_daily_module_from_prices(start_date: str, end_date: str) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """
    用 BTC/ETH/SOL 日涨跌构造四大模块「代理冲击」（资讯样本不足时的价格回测）。
    """
    from storage import price_db

    btc = price_db.daily_return_series("BTC", start_date, end_date)
    eth = price_db.daily_return_series("ETH", start_date, end_date)
    sol = price_db.daily_return_series("SOL", start_date, end_date)
    days = sorted(btc.keys())

    daily_module: dict[str, dict[str, float]] = {}
    btc_returns: dict[str, float] = {}

    for i, d in enumerate(days):
        b = btc[d]
        e = eth.get(d, b)
        s = sol.get(d, b)
        btc_returns[d] = b

        mom7 = sum(btc.get(days[j], 0) for j in range(max(0, i - 6), i + 1)) / min(7, i + 1)
        vol7 = sum(abs(btc.get(days[j], 0)) for j in range(max(0, i - 6), i + 1)) / min(7, i + 1)

        daily_module[d] = {
            MODULE_MACRO: -mom7 * 0.6,
            MODULE_REGULATION: (e - b) * 0.5,
            MODULE_FUNDING: vol7 * (1 if b >= 0 else -1),
            MODULE_FUNDAMENTALS: (s - b) * 0.8,
        }
    return daily_module, btc_returns


def run_backtest_from_prices(start_date: str, end_date: str, cfg: dict | None = None) -> BacktestResult:
    """基于历史价格的代理回测（资讯样本不足时自动启用）。"""
    cfg = cfg or load_config()
    daily_module, btc_returns = _build_daily_module_from_prices(start_date, end_date)
    days = sorted(daily_module.keys())

    if len(days) < 10:
        return BacktestResult(
            start_date=start_date,
            end_date=end_date,
            sample_days=0,
            fixed_accuracy=0.0,
            dynamic_accuracy=0.0,
            fixed_correlation=0.0,
            dynamic_correlation=0.0,
            optimal_weights=_static_weights(),
            message="价格数据不足，请先执行 --backfill 回填 K 线。",
        )

    fixed_w = _legacy_weights()
    dyn_w = compute_dynamic_weights(cfg)
    fixed_preds, dyn_preds, actuals = [], [], []

    for d in days:
        mods = daily_module[d]
        act = btc_returns[d]
        actuals.append(act)
        fixed_preds.append(sum(mods[m] * fixed_w.as_dict()[m] / 100.0 for m in MODULE_ORDER))
        dyn_preds.append(sum(mods[m] * dyn_w.as_dict()[m] / 100.0 for m in MODULE_ORDER))

    optimal = _grid_search_weights(daily_module, btc_returns)

    result = BacktestResult(
        start_date=start_date,
        end_date=end_date,
        sample_days=len(days),
        fixed_accuracy=_direction_accuracy(fixed_preds, actuals),
        dynamic_accuracy=_direction_accuracy(dyn_preds, actuals),
        fixed_correlation=_pearson(fixed_preds, actuals),
        dynamic_correlation=_pearson(dyn_preds, actuals),
        optimal_weights=optimal,
        message=(
            f"价格代理回测完成（{len(days)} 个交易日）。"
            "本地资讯仅覆盖近期，已用 BTC/ETH/SOL 日涨跌构造模块代理信号；"
            "积累更多 TOP10 资讯后可自动切换为「资讯冲击」回测。"
        ),
    )
    result.csv_path = _save_backtest_csv(result, days, daily_module, fixed_preds, dyn_preds, actuals)
    _save_backtest_summary_json(result)
    return result


def run_backtest(start_date: str, end_date: str, cfg: dict | None = None) -> BacktestResult:
    """
    历史回测：对比固定权重 vs 动态权重。
    优先使用资讯实际冲击；样本不足时自动改用价格代理回测。
    """
    cfg = cfg or load_config()
    from storage import impact_db

    impact_db.init_schema()
    rows = impact_db.list_impacts_between(f"{start_date}T00:00:00", f"{end_date}T23:59:59")

    if len(rows) < int(cfg.get("weight_optimizer", {}).get("backtest_min_samples", 10)):
        return run_backtest_from_prices(start_date, end_date, cfg)

    from storage import price_db

    btc_daily = price_db.daily_return_series("BTC", start_date, end_date)

    daily_module: dict[str, dict[str, float]] = {}
    for r in rows:
        day = r["published_at"][:10]
        mod = r["module"]
        imp = float(r["composite_24h"] or 0)
        daily_module.setdefault(day, {m: 0.0 for m in MODULE_ORDER})
        daily_module[day][mod] = daily_module[day].get(mod, 0) + imp

    days = sorted(daily_module.keys())
    fixed_w = _legacy_weights()
    dyn_w = compute_dynamic_weights(cfg)

    fixed_preds, dyn_preds, actuals = [], [], []
    for d in days:
        mods = daily_module[d]
        act = btc_daily.get(d)
        if act is None:
            act = sum(mods.values()) / len(MODULE_ORDER)
        actuals.append(act)
        fixed_preds.append(sum(mods[m] * fixed_w.as_dict()[m] / 100.0 for m in MODULE_ORDER))
        dyn_preds.append(sum(mods[m] * dyn_w.as_dict()[m] / 100.0 for m in MODULE_ORDER))

    optimal = _grid_search_weights(daily_module, btc_daily)

    acc_lift = _direction_accuracy(dyn_preds, actuals) - _direction_accuracy(fixed_preds, actuals)
    corr_lift = _pearson(dyn_preds, actuals) - _pearson(fixed_preds, actuals)

    result = BacktestResult(
        start_date=start_date,
        end_date=end_date,
        sample_days=len(days),
        fixed_accuracy=_direction_accuracy(fixed_preds, actuals),
        dynamic_accuracy=_direction_accuracy(dyn_preds, actuals),
        fixed_correlation=_pearson(fixed_preds, actuals),
        dynamic_correlation=_pearson(dyn_preds, actuals),
        optimal_weights=optimal,
        message=(
            f"资讯冲击回测：{len(rows)} 条新闻，{len(days)} 个有效日。"
            f"旧版权重40/20/25/15 准确率 {_direction_accuracy(fixed_preds, actuals):.1%}，"
            f"动态权重 { _direction_accuracy(dyn_preds, actuals):.1%}（提升 {acc_lift:+.1%}）；"
            f"相关性提升 {corr_lift:+.3f}。"
        ),
    )

    result.csv_path = _save_backtest_csv(result, days, daily_module, fixed_preds, dyn_preds, actuals)
    _save_backtest_summary_json(result)
    return result


def _log_dir() -> Path:
    cfg = load_config()
    rel = cfg.get("storage", {}).get("log_dir", "data/logs")
    p = Path(rel)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def _save_backtest_csv(
    result: BacktestResult,
    days: list[str],
    daily_module: dict,
    fixed_preds: list[float],
    dyn_preds: list[float],
    actuals: list[float],
) -> str:
    path = _log_dir() / "backtest_detail.csv"
    write_header = not path.exists()
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "date",
                "actual_avg_impact",
                "fixed_pred",
                "dynamic_pred",
                "macro_impact",
                "reg_impact",
                "fund_impact",
                "funda_impact",
            ]
        )
        for i, d in enumerate(days):
            m = daily_module[d]
            w.writerow(
                [
                    d,
                    round(actuals[i], 4),
                    round(fixed_preds[i], 4),
                    round(dyn_preds[i], 4),
                    round(m.get(MODULE_MACRO, 0), 4),
                    round(m.get(MODULE_REGULATION, 0), 4),
                    round(m.get(MODULE_FUNDING, 0), 4),
                    round(m.get(MODULE_FUNDAMENTALS, 0), 4),
                ]
            )
    summary_path = _log_dir() / "backtest_summary.csv"
    write_h = not summary_path.exists()
    with open(summary_path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "run_at",
                "start",
                "end",
                "sample_days",
                "fixed_acc",
                "dynamic_acc",
                "fixed_corr",
                "dynamic_corr",
                "opt_macro",
                "opt_reg",
                "opt_fund",
                "opt_funda",
            ],
        )
        if write_h:
            w.writeheader()
        ow = result.optimal_weights
        w.writerow(
            {
                "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "start": result.start_date,
                "end": result.end_date,
                "sample_days": result.sample_days,
                "fixed_acc": round(result.fixed_accuracy, 4),
                "dynamic_acc": round(result.dynamic_accuracy, 4),
                "fixed_corr": round(result.fixed_correlation, 4),
                "dynamic_corr": round(result.dynamic_correlation, 4),
                "opt_macro": ow.macro,
                "opt_reg": ow.regulation,
                "opt_fund": ow.funding,
                "opt_funda": ow.fundamentals,
            }
        )
    return str(summary_path)


def _save_backtest_summary_json(result: BacktestResult) -> None:
    path = _log_dir() / "backtest_latest.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result.summary_dict(), f, ensure_ascii=False, indent=2)


def load_latest_backtest() -> dict[str, Any]:
    path = _log_dir() / "backtest_latest.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 定时任务入口
# ---------------------------------------------------------------------------
def run_weight_pipeline(cfg: dict | None = None) -> dict[str, Any]:
    """价格同步 + 冲击补全 + 权重重算（每 6 小时调用）。"""
    cfg = cfg or load_config()
    opt = cfg.get("weight_optimizer", {})
    if not opt.get("enabled", True):
        return {"skipped": True}

    from collectors.price_hourly import sync_recent_hours

    syms = opt.get("price_symbols", ["BTC", "ETH", "SOL"])
    hours = int(opt.get("price_sync_hours", 168))
    price_counts = sync_recent_hours(syms, hours=hours)
    measured = measure_pending_impacts()
    weights = compute_dynamic_weights(cfg)
    inf7, inf30 = get_dual_module_influence()

    recalc_h = int(opt.get("recalc_interval_hours", 6))
    next_at = (datetime.now() + timedelta(hours=recalc_h)).strftime("%Y-%m-%d %H:%M:%S")

    from storage import impact_db

    impact_db.save_weight_state(
        weights.macro,
        weights.regulation,
        weights.funding,
        weights.fundamentals,
        method=weights.method,
        next_recalc_at=next_at,
    )

    from storage.csv_logger import append_weight_history

    measured_total = impact_db.count_measured_impacts()
    append_weight_history(
        weights=weights.as_dict(),
        method=weights.method,
        next_recalc_at=next_at,
        impact_samples=measured_total,
    )

    payload = {
        "weights": weights,
        "influence_7": inf7,
        "influence_30": inf30,
        "price_sync": price_counts,
        "impacts_updated": measured,
        "next_recalc_at": next_at,
    }
    _persist_optimizer_state(payload)
    return payload


def backfill_price_linked_events(start_date: str, end_date: str) -> int:
    """
    用 BTC 日涨跌生成「日度市场事件」冲击记录（不删已有数据）。
    当历史资讯标题无法覆盖 2025 全年时，用真实价格变动作为冲击样本。
    """
    from storage import impact_db, price_db

    price_db.init_schema()
    impact_db.init_schema()
    btc = price_db.daily_return_series("BTC", start_date, end_date)
    eth = price_db.daily_return_series("ETH", start_date, end_date)
    sol = price_db.daily_return_series("SOL", start_date, end_date)
    added = 0

    for day in sorted(btc.keys()):
        b = btc[day]
        if abs(b) < 0.25:
            continue
        e = eth.get(day, b)
        s = sol.get(day, b)
        composite = (b + e + s) / 3.0

        if abs(e - b) > abs(s - b):
            mod = MODULE_REGULATION if abs(e - b) > 1 else MODULE_FUNDING
        elif abs(s - b) > 1.2:
            mod = MODULE_FUNDAMENTALS
        elif abs(b) > 2:
            mod = MODULE_MACRO
        else:
            mod = MODULE_FUNDING

        pub = datetime.fromisoformat(day).replace(tzinfo=timezone.utc, hour=12)
        title = f"[日度市场] BTC {b:+.2f}% | ETH {e:+.2f}% | SOL {s:+.2f}%"
        nid = impact_db.insert_news_pending(
            title=title,
            source="PriceEvent",
            url=f"price-event://{day}",
            module=mod,
            published_at=pub,
            predicted_impact=max(-10.0, min(10.0, composite / 2)),
            is_event=abs(b) >= 2.5,
        )
        impact_db.update_actual_impacts(
            nid,
            actual_1h=b * 0.4,
            actual_4h=b * 0.7,
            actual_24h=composite,
            composite_24h=composite,
        )
        added += 1
    return added


def run_full_upgrade_pipeline(cfg: dict | None = None) -> dict[str, Any]:
    """历史资讯抓取 + 冲击测算 + 权重校准 + 回测（一键）。"""
    cfg = cfg or load_config()
    opt = cfg.get("weight_optimizer", {})
    start = opt.get("backtest", {}).get("default_start", "2025-01-01")
    end = datetime.now().strftime("%Y-%m-%d")

    from collectors.news_historical import fetch_historical_news
    from collectors.price_hourly import backfill_history, sync_recent_hours

    syms = opt.get("price_symbols", ["BTC", "ETH", "SOL"])
    hist = fetch_historical_news(cfg)
    backfill_history(syms, start, end)
    sync_recent_hours(syms, hours=int(opt.get("price_sync_hours", 168)))
    price_events = backfill_price_linked_events(start, end)
    measured = measure_pending_impacts()
    rebuild_impacts_from_news_csv()
    weight_payload = run_weight_pipeline(cfg)
    bt = run_backtest(start, end, cfg)

    return {
        "historical": hist,
        "price_events_added": price_events,
        "impacts_measured": measured,
        "weights": weight_payload,
        "backtest": bt.summary_dict(),
    }


def _persist_optimizer_state(payload: dict) -> None:
    from core.state_store import update_state
    from storage import impact_db

    w: DynamicWeights = payload["weights"]
    inf7: ModuleInfluence = payload.get("influence_7") or payload.get("influence")
    inf30: ModuleInfluence = payload.get("influence_30") or inf7
    measured = impact_db.count_measured_impacts()
    total = impact_db.count_total_impacts()
    min_need = int(load_config().get("weight_optimizer", {}).get("min_samples_for_dynamic", 5))

    if measured >= min_need:
        status = "动态权重已生效（真实资讯冲击）"
    elif total > 0:
        status = f"资讯样本积累中（已测算 {measured}/{total} 条，满 {min_need} 条后完全生效）"
    else:
        status = "资讯样本不足，当前使用回测基准权重 30/30/35/5"

    rows_30 = inf30.as_ui_rows(inf30.signed_scores) if inf30 else []
    rows_7 = inf7.as_ui_rows(inf7.signed_scores) if inf7 else []
    combined = []
    for i, r30 in enumerate(rows_30):
        r7 = rows_7[i] if i < len(rows_7) else {}
        combined.append(
            {
                **r30,
                "influence_7": r7.get("influence", 0),
                "signed_7": r7.get("signed", 0),
                "color_7": r7.get("color_class", "impact-neutral"),
                "samples_7": r7.get("samples", 0),
            }
        )

    recalc_h = int(load_config().get("weight_optimizer", {}).get("recalc_interval_hours", 6))

    update_state(
        weight_optimizer={
            "dynamic_weights": w.as_list_for_ui(),
            "weights_method": w.method,
            "weights_updated_at": w.updated_at,
            "next_recalc_at": payload.get("next_recalc_at", "—"),
            "recalc_interval_hours": recalc_h,
            "status_message": status,
            "module_influence": combined,
            "module_influence_7": rows_7,
            "influence_window_days": inf30.window_days if inf30 else 30,
            "impact_samples": measured,
            "impact_total": total,
            "backtest": load_latest_backtest(),
            "price_sync": payload.get("price_sync"),
            "impacts_updated": payload.get("impacts_updated"),
        },
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def rebuild_impacts_from_news_csv() -> int:
    """从 data/logs/news_snapshot.csv 重建待测算记录并尝试补全冲击。"""
    import csv

    from storage import impact_db, price_db

    price_db.init_schema()
    impact_db.init_schema()
    path = _log_dir() / "news_snapshot.csv"
    if not path.exists():
        logger.warning("未找到 %s", path)
        return 0
    n = 0
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get("title", "")
            if not title:
                continue
            mod = classify_news_module(title)
            try:
                pub = datetime.strptime(row["fetch_time"], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pub = datetime.now(timezone.utc)
            pred = float(row.get("impact_score") or 0)
            impact_db.insert_news_pending(
                title=title,
                source=row.get("source", ""),
                url=row.get("url", ""),
                module=mod,
                published_at=pub,
                predicted_impact=pred,
                is_event=is_breaking_event(title, mod),
            )
            n += 1
    return n + measure_pending_impacts()


def main() -> None:
    parser = argparse.ArgumentParser(description="动态权重与回测工具")
    parser.add_argument("--backfill", nargs=2, metavar=("START", "END"), help="回填历史K线 YYYY-MM-DD")
    parser.add_argument("--backtest", nargs=2, metavar=("START", "END"), help="运行回测")
    parser.add_argument("--recalc", action="store_true", help="立即重算动态权重")
    parser.add_argument("--sync-prices", action="store_true", help="同步最近价格")
    parser.add_argument("--rebuild-impacts", action="store_true", help="从 news_snapshot.csv 重建冲击样本")
    parser.add_argument("--fetch-history", action="store_true", help="抓取 2025 至今历史资讯")
    parser.add_argument("--full-pipeline", action="store_true", help="历史资讯+冲击+权重+回测 一键执行")
    args = parser.parse_args()
    cfg = load_config()

    if args.backfill:
        from collectors.price_hourly import backfill_history

        syms = cfg.get("weight_optimizer", {}).get("price_symbols", ["BTC", "ETH", "SOL"])
        print("回填价格…", backfill_history(syms, args.backfill[0], args.backfill[1]))
        return

    if args.sync_prices:
        from collectors.price_hourly import sync_recent_hours

        syms = cfg.get("weight_optimizer", {}).get("price_symbols", ["BTC", "ETH", "SOL"])
        print(sync_recent_hours(syms))
        return

    if args.backtest:
        r = run_backtest(args.backtest[0], args.backtest[1], cfg)
        print(json.dumps(r.summary_dict(), ensure_ascii=False, indent=2))
        return

    if args.recalc:
        print(json.dumps(asdict(run_weight_pipeline(cfg)), default=str, ensure_ascii=False, indent=2))
        return

    if args.rebuild_impacts:
        print(f"已处理/更新冲击记录: {rebuild_impacts_from_news_csv()} 条")
        return

    if getattr(args, "fetch_history", False):
        from collectors.news_historical import fetch_historical_news

        print(json.dumps(fetch_historical_news(cfg), ensure_ascii=False, indent=2))
        print("冲击测算…", measure_pending_impacts())
        return

    if getattr(args, "full_pipeline", False):
        print(json.dumps(run_full_upgrade_pipeline(cfg), default=str, ensure_ascii=False, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
