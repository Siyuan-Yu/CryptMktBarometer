/**
 * 仪表盘无刷新更新
 * - 价格：默认每 5 秒（/api/prices）
 * - 行情/资讯/评分/权重：默认每 30 秒（/api/dashboard）
 */
(function () {
    const cfg = window.DASHBOARD_CONFIG || {};
    const dashMs = Math.max(10, (cfg.refreshSeconds || 30)) * 1000;
    const priceMs = Math.max(3, (cfg.priceRefreshSeconds || 5)) * 1000;

    function $(id) {
        return document.getElementById(id);
    }

    function esc(s) {
        return String(s ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function fmtSigned(v) {
        const n = Number(v);
        if (Number.isNaN(n)) return "—";
        return (n > 0 ? "+" : "") + n.toFixed(2);
    }

    function fmtPrice(n) {
        const v = Number(n);
        if (Number.isNaN(v)) return "—";
        if (v >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
        if (v >= 1) return v.toLocaleString("en-US", { maximumFractionDigits: 2 });
        return v.toLocaleString("en-US", { maximumFractionDigits: 4 });
    }

    function parseTime(s) {
        if (!s || s === "—") return null;
        const t = new Date(s.replace(" ", "T"));
        return Number.isNaN(t.getTime()) ? null : t;
    }

    function formatPublishedAt(item) {
        const raw =
            (item && (item.published_at || item.published)) ||
            (item && item.raw && (item.raw.published || item.raw.published_at)) ||
            "";
        if (!raw || raw === "—") return "—";
        const t = parseTime(String(raw).replace("Z", ""));
        if (t) {
            const y = t.getFullYear();
            const m = String(t.getMonth() + 1).padStart(2, "0");
            const d = String(t.getDate()).padStart(2, "0");
            const h = String(t.getHours()).padStart(2, "0");
            const min = String(t.getMinutes()).padStart(2, "0");
            return `${y}-${m}-${d} ${h}:${min}`;
        }
        const s = String(raw).replace("T", " ").trim();
        return s.length >= 16 ? s.slice(0, 16) : s || "—";
    }

    const ASSET_META = {
        btc: {
            label: "BTC",
            kicker: "☀ BTC 晴雨",
            newsTitle: "📰 BTC 专属资讯",
            newsHint:
                "比特币现货 ETF · 灰度 · SEC · 矿工 · 链上 · 减半 · 机构持仓",
        },
        eth: {
            label: "ETH",
            kicker: "☀ ETH 晴雨",
            newsTitle: "📰 ETH 专属资讯",
            newsHint: "以太坊 · L2 · 质押 · ETF · SEC · 生态升级",
        },
        sol: {
            label: "SOL",
            kicker: "☀ SOL 晴雨",
            newsTitle: "📰 SOL 专属资讯",
            newsHint: "Solana 公链 · DeFi · 基金会 · 生态项目",
        },
        us: {
            label: "美股大盘",
            kicker: "☀ 美股晴雨",
            newsTitle: "📰 美股 / 宏观资讯",
            newsHint: "CPI · 美联储 · 美股 · 国债收益率 · 非农",
        },
    };

    const WEIGHT_NUDGE = {
        btc: {},
        eth: { "ETH/SOL 币种基本面": 6, "资金链上数据": -4 },
        sol: { "ETH/SOL 币种基本面": 8, "宏观数据": -4 },
        us: {
            "宏观数据": 12,
            "全球监管政策": 3,
            "资金链上数据": -8,
            "ETH/SOL 币种基本面": -7,
        },
    };

    let activeAsset = "btc";
    let scoreChart = null;

    function chartTitleFor(assetId) {
        const meta = ASSET_META[assetId] || ASSET_META.btc;
        return `📈 ${meta.label} · 分数历史走势`;
    }

    function initScoreChart() {
        if (typeof ScoreChart === "undefined") return;
        scoreChart = ScoreChart.create("score-chart-root");
        if (scoreChart) scoreChart.setAsset(activeAsset);
    }

    async function refreshScoreHistory() {
        if (!scoreChart) return;
        const since = cfg.scoreHistorySince || "2026-01-01";
        try {
            const res = await fetch(
                `/api/score-history?since=${encodeURIComponent(since)}`,
                { cache: "no-store" }
            );
            if (!res.ok) return;
            const data = await res.json();
            scoreChart.setSeries(data.series || {});
            scoreChart.setAsset(activeAsset);
        } catch (e) {
            console.warn("score history load failed", e);
        }
    }

    function deepClone(obj) {
        return JSON.parse(JSON.stringify(obj || null));
    }

    function clamp(n, lo, hi) {
        return Math.max(lo, Math.min(hi, n));
    }

    function avgImpact(items) {
        if (!items || !items.length) return 0;
        const sum = items.reduce(
            (s, it) => s + (Number(it.impact_score) || 0),
            0
        );
        return sum / items.length;
    }

    function nudgeWeights(rows, nudges) {
        const out = deepClone(rows || []);
        if (!out.length) return out;
        out.forEach((r) => {
            if (nudges[r.name]) r.weight = (Number(r.weight) || 0) + nudges[r.name];
        });
        let sum = out.reduce((s, r) => s + (Number(r.weight) || 0), 0);
        if (sum <= 0) return out;
        out.forEach((r) => {
            r.weight = Math.round(((Number(r.weight) || 0) * 100) / sum);
            r.bar_percent = r.weight;
        });
        const fix = 100 - out.reduce((s, r) => s + r.weight, 0);
        if (fix && out[0]) out[0].weight += fix;
        return out;
    }

    function adjustCategoriesForAsset(categories, assetId, data) {
        const cats = deepClone(categories || []);
        const ethAvg = avgImpact(data.eth_news);
        const solAvg = avgImpact(data.sol_news);
        const macroAvg = avgImpact(data.macro_news);
        const btcAvg = avgImpact(data.btc_news);

        const nudge = (idx, delta, summary) => {
            if (!cats[idx] || cats[idx].score == null) return;
            cats[idx].score = clamp(Number(cats[idx].score) + delta, 0, 100);
            if (summary) cats[idx].summary = summary;
        };

        if (assetId === "eth" && cats[3]) {
            nudge(
                3,
                ethAvg * 2.5,
                `ETH 专属 ${(data.eth_news || []).length} 条 · 均冲击 ${ethAvg.toFixed(1)}`
            );
        } else if (assetId === "sol" && cats[3]) {
            nudge(
                3,
                solAvg * 2.5,
                `SOL 专属 ${(data.sol_news || []).length} 条 · 均冲击 ${solAvg.toFixed(1)}`
            );
        } else if (assetId === "us") {
            nudge(
                0,
                macroAvg * 2.2,
                `宏观/美股 ${(data.macro_news || []).length} 条 · 均冲击 ${macroAvg.toFixed(1)}`
            );
            nudge(1, macroAvg * 0.8);
            if (cats[2]) cats[2].score = clamp(Number(cats[2].score) - 2, 0, 100);
        } else if (assetId === "btc" && cats[2]) {
            nudge(
                2,
                btcAvg * 1.2,
                `BTC 专属 ${(data.btc_news || []).length} 条 · 均冲击 ${btcAvg.toFixed(1)}`
            );
        }
        return cats;
    }

    function calcWeightedTotal(categories, weights) {
        const wm = {};
        (weights || []).forEach((w) => {
            if (w.name) wm[w.name] = Number(w.weight);
        });
        let sum = 0;
        let tw = 0;
        (categories || []).forEach((c) => {
            const w = wm[c.name] ?? Number(c.weight) ?? 25;
            if (c.score == null) return;
            sum += Number(c.score) * w;
            tw += w;
        });
        return tw > 0 ? sum / tw : null;
    }

    function ratingLabelFromScore(total) {
        const s = Number(total);
        if (Number.isNaN(s)) return "待计算";
        if (s > 70) return "强利多";
        if (s >= 55) return "偏利多";
        if (s >= 45) return "中性";
        if (s >= 30) return "偏利空";
        return "强利空";
    }

    function ratingClassFromScore(total) {
        const s = Number(total);
        if (Number.isNaN(s)) return "rating-neutral";
        if (s > 70) return "rating-bull-strong";
        if (s >= 55) return "rating-bull";
        if (s >= 45) return "rating-neutral";
        if (s >= 30) return "rating-bear";
        return "rating-bear-strong";
    }

    function newsForAsset(assetId, data) {
        switch (assetId) {
            case "eth":
                return data.eth_news || [];
            case "sol":
                return data.sol_news || [];
            case "us":
                return data.macro_news || [];
            default:
                return data.btc_news || data.top_news || [];
        }
    }

    function buildAssetView(assetId, data) {
        const news = newsForAsset(assetId, data);
        if (assetId === "btc") {
            return {
                categories: data.categories,
                weights: (data.weight_optimizer || {}).dynamic_weights,
                total_score: data.total_score,
                rating_label: data.rating_label,
                rating_class: data.rating_class,
                news,
            };
        }
        const weights = nudgeWeights(
            (data.weight_optimizer || {}).dynamic_weights,
            WEIGHT_NUDGE[assetId] || {}
        );
        const categories = adjustCategoriesForAsset(
            data.categories,
            assetId,
            data
        );
        const total = calcWeightedTotal(categories, weights);
        return {
            categories,
            weights,
            total_score: total,
            rating_label:
                total != null ? ratingLabelFromScore(total) : data.rating_label,
            rating_class:
                total != null ? ratingClassFromScore(total) : data.rating_class,
            news,
        };
    }

    function updateAssetChrome(assetId) {
        const meta = ASSET_META[assetId] || ASSET_META.btc;
        const kicker = $("gauge-kicker");
        if (kicker) kicker.textContent = meta.kicker;
        const nt = $("asset-news-panel-title");
        if (nt) nt.textContent = meta.newsTitle;
        const nh = $("asset-news-panel-hint");
        if (nh) nh.textContent = meta.newsHint;
        const ct = $("score-chart-title");
        if (ct) ct.textContent = chartTitleFor(assetId);
        document.querySelectorAll(".asset-pill").forEach((btn) => {
            const on = btn.getAttribute("data-asset") === assetId;
            btn.classList.toggle("is-active", on);
            btn.setAttribute("aria-selected", on ? "true" : "false");
        });
    }

    function applyAssetView(assetId) {
        const data = window.__dashboardRaw;
        if (!data) return;
        activeAsset = assetId;
        try {
            localStorage.setItem("barometer_asset", assetId);
        } catch (e) {
            /* ignore */
        }
        const view = buildAssetView(assetId, data);
        updateAssetChrome(assetId);
        renderScore(
            view.categories,
            view.total_score,
            view.rating_label,
            view.rating_class
        );
        renderWeightScoreStrip(view.categories, view.weights);
        renderNewsTable("asset-news-tbody", view.news);
        renderNewsTicker((window.__dashboardRaw || {}).top_news);
        if (scoreChart) scoreChart.setAsset(assetId);
        updateCoinFearVisibility(assetId);
    }

    function bindAssetSwitcher() {
        try {
            const saved = localStorage.getItem("barometer_asset");
            if (saved && ASSET_META[saved]) activeAsset = saved;
        } catch (e) {
            /* ignore */
        }
        document.addEventListener("click", (e) => {
            const btn = e.target.closest(".asset-pill");
            if (!btn) return;
            const nav = btn.closest(".asset-switcher, .asset-switcher-dock");
            if (!nav) return;
            const id = btn.getAttribute("data-asset");
            if (!id || !ASSET_META[id]) return;
            applyAssetView(id);
        });
    }

    function updateCountdown(nextAt, el) {
        if (!el) return;
        const target = parseTime(nextAt);
        if (!target) {
            el.textContent = "—";
            return;
        }
        const sec = Math.max(0, Math.floor((target - Date.now()) / 1000));
        const h = Math.floor(sec / 3600);
        const m = Math.floor((sec % 3600) / 60);
        const s = sec % 60;
        el.textContent = `${h}时${m}分${s}秒`;
    }

    window.__topNewsList = [];
    window.__newsTables = {};

    function tagClass(label) {
        const map = {
            "BTC生态": "tag-btc",
            "SOL生态": "tag-sol",
            "ETH生态": "tag-eth",
            美股宏观: "tag-macro",
            全市场加密: "tag-crypto",
        };
        return map[label] || "tag-crypto";
    }

    function keywordPillsHtml(item) {
        const kws =
            item.keywords_cn ||
            item.display_keywords ||
            item.keywords ||
            [];
        if (!kws.length) return '<span class="muted">—</span>';
        return `<div class="kw-pills">${kws
            .map((k) => `<span class="kw-pill">${esc(k)}</span>`)
            .join("")}</div>`;
    }

    function tickerChipHtml(item, rank) {
        const score = Number(item.impact_score) || 0;
        const ic =
            score > 0 ? "impact-pos" : score < 0 ? "impact-neg" : "";
        const title =
            item.title_cn || item.display_title || item.title || "—";
        const label =
            item.category_label || item.source_tag || "全市场加密";
        const sign = score > 0 ? "+" : "";
        const pub = formatPublishedAt(item);
        return `<button type="button" class="ticker-chip" data-news-open="${rank - 1}" aria-label="查看资讯详情">
        <span class="cat-tag ${tagClass(label)}">${esc(label)}</span>
        <span class="ticker-chip-rank">#${rank}</span>
        <span class="ticker-chip-title">${esc(title)}</span>
        <span class="ticker-chip-time">${esc(pub)}</span>
        <span class="ticker-chip-score ${ic}">${sign}${score}分</span>
      </button>`;
    }

    function openNewsModal(item) {
        if (!item) return;
        const modal = $("news-modal");
        if (!modal) return;
        const label =
            item.category_label || item.source_tag || "全市场加密";
        const score = Number(item.impact_score) || 0;
        const sign = score > 0 ? "+" : "";
        const tagEl = $("news-modal-tag");
        const titleEl = $("news-modal-title");
        const sumEl = $("news-modal-summary");
        const kwEl = $("news-modal-keywords");
        const scoreEl = $("news-modal-score");
        const srcEl = $("news-modal-source");
        const linkEl = $("news-modal-link");

        if (tagEl) {
            tagEl.textContent = label;
            tagEl.className = `cat-tag ${tagClass(label)}`;
        }
        if (titleEl)
            titleEl.textContent =
                item.title_cn || item.display_title || item.title || "—";
        if (sumEl) sumEl.textContent = item.summary_cn || "暂无摘要";
        if (kwEl) kwEl.innerHTML = keywordPillsHtml(item);
        if (scoreEl) {
            scoreEl.textContent = `${sign}${score} 分`;
            scoreEl.className =
                score > 0
                    ? "impact-pos"
                    : score < 0
                      ? "impact-neg"
                      : "";
        }
        if (srcEl) srcEl.textContent = item.source || "—";
        const pubEl = $("news-modal-published");
        if (pubEl) pubEl.textContent = formatPublishedAt(item);
        if (linkEl) {
            if (item.url) {
                linkEl.innerHTML = `<a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.url)}</a>`;
            } else {
                linkEl.textContent = "—";
            }
        }
        modal.hidden = false;
        modal.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden";
    }

    function closeNewsModal() {
        const modal = $("news-modal");
        if (!modal) return;
        modal.hidden = true;
        modal.setAttribute("aria-hidden", "true");
        document.body.style.overflow = "";
    }

    function renderNewsTicker(items) {
        const track = $("news-ticker-track");
        if (!track) return;
        window.__topNewsList = items || [];

        if (!items || !items.length) {
            track.innerHTML =
                '<span class="ticker-chip ticker-chip-empty">等待定时任务抓取 TOP10 资讯…</span>';
            return;
        }

        const chips = items.map((item, i) => tickerChipHtml(item, i + 1)).join("");
        track.innerHTML = chips + chips;
        const duration = Math.max(40, items.length * 6);
        track.style.animationDuration = `${duration}s`;
    }

    function renderNewsTable(tbodyId, items) {
        const tbody = $(tbodyId);
        if (!tbody) return;
        window.__newsTables = window.__newsTables || {};
        window.__newsTables[tbodyId] = items || [];

        if (!items || !items.length) {
            tbody.innerHTML =
                '<tr><td colspan="6" class="empty-row">暂无该类资讯，等待定时任务抓取…</td></tr>';
            return;
        }
        tbody.innerHTML = items
            .map((item, i) => {
                const score = Number(item.impact_score) || 0;
                const ic =
                    score > 0 ? "impact-pos" : score < 0 ? "impact-neg" : "";
                const title =
                    item.title_cn ||
                    item.display_title ||
                    item.title ||
                    "";
                const summary = item.summary_cn || "—";
                const link = item.url
                    ? `<a href="${esc(item.url)}" target="_blank" rel="noopener" class="meta-link" onclick="event.stopPropagation()">原文</a>`
                    : "";
                const sign = score > 0 ? "+" : "";
                const pub = formatPublishedAt(item);
                return `<tr class="news-row-clickable" data-news-table="${esc(tbodyId)}" data-news-index="${i}" tabindex="0" role="button">
          <td class="col-idx">${i + 1}</td>
          <td class="title-cell">${esc(title)}</td>
          <td class="summary-cell">${esc(summary)}</td>
          <td class="keywords-cell">${keywordPillsHtml(item)}</td>
          <td class="time-cell">${esc(pub)}</td>
          <td class="meta-cell"><div class="meta-stack meta-stack-row">
            <span class="impact-cell ${ic}">${sign}${score}</span>
            <span class="meta-source">${esc(item.source || "")}</span>
            ${link}
          </div></td>
        </tr>`;
            })
            .join("");
    }

    function renderWeightScoreStrip(categories, dynamicWeights) {
        const strip = $("weight-score-strip");
        if (!strip) return;
        const weightMap = {};
        (dynamicWeights || []).forEach((r) => {
            if (r.name) weightMap[r.name] = r.weight;
        });
        strip.querySelectorAll(".wsc-card").forEach((card, i) => {
            const cat = (categories || [])[i];
            if (!cat) return;
            const wEl = card.querySelector("[data-wsc-weight]");
            const sEl = card.querySelector("[data-wsc-score]");
            const w = weightMap[cat.name];
            if (wEl)
                wEl.textContent =
                    w != null ? `${w}%` : cat.weight != null ? `${cat.weight}%` : "—";
            if (sEl)
                sEl.textContent =
                    cat.score != null ? Number(cat.score).toFixed(1) : "—";
        });
    }

    const RING_LEN = 1017.88;

    function ratingToState(label, score) {
        const s = Number(score);
        if (!Number.isNaN(s)) {
            if (s > 70) return "bull-strong";
            if (s >= 55) return "bull";
            if (s >= 45) return "neutral";
            if (s >= 30) return "bear";
            return "bear-strong";
        }
        const map = {
            强利多: "bull-strong",
            偏利多: "bull",
            利多: "bull",
            中性: "neutral",
            偏利空: "bear",
            利空: "bear",
            强利空: "bear-strong",
        };
        return map[label] || "neutral";
    }

    function scoreGradient(score) {
        const s = Number(score);
        if (Number.isNaN(s)) return ["#a8d8ff", "#c4b0ff", "#ffb8d8"];
        if (s > 70) return ["#8ef0c0", "#5ecf9a", "#a8ffe0"];
        if (s >= 55) return ["#a8f0e8", "#6dd4c8", "#c8fff0"];
        if (s >= 45) return ["#e8e0ff", "#c4b8e8", "#f0ecff"];
        if (s >= 30) return ["#ffe8c8", "#ffc896", "#fff0d8"];
        return ["#ffd8dc", "#ffabab", "#ffe8ec"];
    }

    function renderCentralGauge(totalScore, ratingLabel, ratingClass) {
        const gauge = $("firefly-gauge");
        const scoreEl = $("gauge-score");
        const ratingEl = $("gauge-rating");
        const ring = $("gauge-ring-progress");
        if (!gauge) return;

        const score =
            totalScore != null && !Number.isNaN(Number(totalScore))
                ? Number(totalScore)
                : null;
        const label = ratingLabel || "待计算";
        const state = ratingToState(label, score);

        gauge.dataset.activeState = state;
        gauge.dataset.ratingClass = ratingClass || "rating-neutral";
        gauge.style.setProperty(
            "--score-pct",
            score != null ? String(score / 100) : "0"
        );

        if (scoreEl) {
            scoreEl.textContent =
                score != null ? String(Math.round(score)) : "—";
        }
        if (ratingEl) {
            ratingEl.textContent = label;
            ratingEl.className = `gauge-rating ${ratingClass || "rating-neutral"}`;
        }
        if (ring) {
            const pct = score != null ? Math.min(100, Math.max(0, score)) : 0;
            ring.style.strokeDashoffset = String(
                RING_LEN * (1 - pct / 100)
            );
            const [a, b, c] = scoreGradient(score);
            const sa = $("grad-stop-a");
            const sb = $("grad-stop-b");
            const sc = $("grad-stop-c");
            if (sa) sa.setAttribute("stop-color", a);
            if (sb) sb.setAttribute("stop-color", b);
            if (sc) sc.setAttribute("stop-color", c);
        }
    }

    const FG_ZONE_CLASS = [
        "fg-extreme-fear",
        "fg-fear",
        "fg-neutral",
        "fg-greed",
        "fg-extreme-greed",
        "fg-unknown",
    ];

    const FG_ICON = {
        "fg-extreme-fear": "😱",
        "fg-fear": "😰",
        "fg-neutral": "😐",
        "fg-greed": "😊",
        "fg-extreme-greed": "🤑",
        "fg-unknown": "◎",
    };

    function renderCoinFear(coinFear) {
        const map = coinFear || {};
        document.querySelectorAll("[data-coin-fear]").forEach((chip) => {
            const sym = chip.getAttribute("data-coin-fear");
            const row = map[sym] || {};
            const zone = row.zone || "fg-unknown";
            FG_ZONE_CLASS.forEach((c) => chip.classList.remove(c));
            chip.classList.add(zone);
            if (row.value == null) {
                chip.textContent = "币种情绪 —";
            } else {
                chip.textContent = `币种情绪 ${Math.round(Number(row.value))}｜${row.label || "—"}`;
            }
        });
        updateCoinFearVisibility(activeAsset);
    }

    function updateCoinFearVisibility(assetId) {
        const show = assetId === "btc" || assetId === "eth" || assetId === "sol";
        const sym = show ? ASSET_META[assetId].label : "";
        document.querySelectorAll("[data-coin-fear]").forEach((chip) => {
            const on = show && chip.getAttribute("data-coin-fear") === sym;
            chip.hidden = !on;
        });
    }

    function renderFearGreed(fg) {
        const widget = $("fear-greed-widget");
        const valEl = $("fg-value");
        const labelEl = $("fg-label");
        const iconEl = $("fg-icon");
        if (!widget) return;

        FG_ZONE_CLASS.forEach((c) => widget.classList.remove(c));

        if (!fg || fg.value == null) {
            widget.classList.add("fg-unknown");
            if (valEl) valEl.textContent = "—";
            if (labelEl) labelEl.textContent = fg && fg.error ? "暂不可用" : "—";
            if (iconEl) iconEl.textContent = FG_ICON["fg-unknown"];
            return;
        }

        const zone = fg.zone || "fg-unknown";
        widget.classList.add(zone);
        if (valEl) valEl.textContent = String(Math.round(Number(fg.value)));
        if (labelEl) labelEl.textContent = fg.label || "—";
        if (iconEl) iconEl.textContent = FG_ICON[zone] || FG_ICON["fg-unknown"];
    }

    function renderPrices(data) {
        const tickers = (data && data.tickers) || {};
        renderFearGreed(data && data.fear_greed);
        renderCoinFear(data && data.coin_fear);
        ["BTC", "ETH", "SOL"].forEach((sym) => {
            const card = $(`price-${sym.toLowerCase()}`);
            if (!card) return;
            const t = tickers[sym] || {};
            const valEl = card.querySelector("[data-price-value]");
            const chgEl = card.querySelector("[data-price-change]");
            const price = t.price;
            const chg = t.change_24h_pct;
            if (valEl) {
                valEl.textContent =
                    price != null ? `$${fmtPrice(price)}` : "—";
            }
            if (chgEl) {
                if (chg == null) {
                    chgEl.textContent = "24h —";
                    chgEl.className = "price-hero-chg";
                } else {
                    const sign = chg >= 0 ? "+" : "";
                    chgEl.textContent = `24h ${sign}${Number(chg).toFixed(2)}%`;
                    chgEl.className =
                        "price-hero-chg " + (chg >= 0 ? "chg-up" : "chg-down");
                }
            }
        });
        if ($("price-source"))
            $("price-source").textContent = data.source || "—";
        if ($("price-updated"))
            $("price-updated").textContent = data.fetched_at || "—";
    }

    async function refreshPrices() {
        try {
            const res = await fetch("/api/prices", { cache: "no-store" });
            if (!res.ok) return;
            renderPrices(await res.json());
        } catch (e) {
            console.warn("price refresh failed", e);
        }
    }

    function renderWeights(rows) {
        const tbody = $("weights-tbody");
        if (!tbody) return;
        if (!rows || !rows.length) {
            tbody.innerHTML =
                '<tr><td colspan="5" class="empty-row">等待权重计算</td></tr>';
            return;
        }
        tbody.innerHTML = rows
            .map((r) => {
                const delta = r.delta || 0;
                const deltaCls =
                    delta > 0 ? "impact-pos" : delta < 0 ? "impact-neg" : "";
                const boost = r.event_boost
                    ? '<span class="boost-tag">突发+20%</span>'
                    : "";
                return `<tr>
          <td>${esc(r.name)} ${boost}</td>
          <td><div class="weight-bar-wrap"><div class="weight-bar" style="width:${r.bar_percent || r.weight}%"></div></div>
              <strong>${r.weight}%</strong></td>
          <td>${r.baseline_weight}%</td>
          <td>${r.static_weight}%</td>
          <td class="${deltaCls}">${delta > 0 ? "+" : ""}${delta}</td>
        </tr>`;
            })
            .join("");
    }

    function renderInfluence(rows) {
        const tbody = $("influence-tbody");
        if (!tbody) return;
        if (!rows || !rows.length) {
            tbody.innerHTML =
                '<tr><td colspan="5" class="empty-row">等待冲击样本</td></tr>';
            return;
        }
        tbody.innerHTML = rows
            .map(
                (r) => `<tr>
          <td>${esc(r.name)}</td>
          <td class="${r.color_7 || "impact-neutral"}">${fmtSigned(r.signed_7)}</td>
          <td>${r.samples_7 || 0}</td>
          <td class="${r.color_class || "impact-neutral"}">${fmtSigned(r.signed)}</td>
          <td>${r.samples || 0}</td>
        </tr>`
            )
            .join("");
    }

    function renderBacktest(bt) {
        const box = $("backtest-box");
        if (!box) return;
        if (!bt || !bt.start_date) {
            box.innerHTML =
                '<p class="panel-hint">点击按钮运行回测，结果自动保存。</p>';
            return;
        }
        const ow = bt.optimal_weights || {};
        box.innerHTML = `<dl class="log-dl">
      <dt>回测区间</dt><dd>${esc(bt.start_date)} ~ ${esc(bt.end_date)}（${bt.sample_days} 个有效日）</dd>
      <dt>方向准确率</dt><dd>旧版固定 ${esc(bt.fixed_accuracy)} · 动态 <strong class="impact-pos">${esc(bt.dynamic_accuracy)}</strong></dd>
      <dt>与 BTC 日涨跌相关性</dt><dd>旧版 ${bt.fixed_correlation} · 动态 ${bt.dynamic_correlation}</dd>
      <dt>网格搜索最优权重</dt><dd>宏观 ${ow.macro} · 监管 ${ow.regulation} · 资金 ${ow.funding} · 币种 ${ow.fundamentals}</dd>
      ${bt.message ? `<dt>说明</dt><dd>${esc(bt.message)}</dd>` : ""}
      ${bt.csv_path ? `<dt>CSV</dt><dd><code>${esc(bt.csv_path)}</code></dd>` : ""}
    </dl>`;
    }

    function renderScore(categories, totalScore, ratingLabel, ratingClass) {
        const tbody = $("score-tbody");
        if (tbody && categories) {
            tbody.innerHTML = categories
                .map(
                    (c) => `<tr>
          <td>${esc(c.name)}</td>
          <td>${c.weight}%</td>
          <td class="score-cell">${c.score != null ? Number(c.score).toFixed(1) : "—"}</td>
          <td class="summary-cell">${esc(c.summary || "")}</td>
        </tr>`
                )
                .join("");
        }
        const totalEl = $("total-score");
        const ratingEl = $("rating-tag");
        if (totalEl) {
            totalEl.innerHTML =
                totalScore != null
                    ? `<strong>${Number(totalScore).toFixed(1)}</strong> / 100`
                    : "<strong>—</strong>";
        }
        if (ratingEl) {
            ratingEl.textContent = ratingLabel || "待计算";
            ratingEl.className = `rating-tag ${ratingClass || "rating-neutral"}`;
        }
        renderCentralGauge(totalScore, ratingLabel, ratingClass);
    }

    async function refreshDashboard() {
        try {
            const res = await fetch("/api/dashboard", { cache: "no-store" });
            if (!res.ok) return;
            const data = await res.json();
            const wo = data.weight_optimizer || {};

            window.__lastWeightNext = wo.next_recalc_at;

            if ($("live-last-fetch"))
                $("live-last-fetch").textContent = data.last_fetch_time || "—";
            if ($("live-weights-updated"))
                $("live-weights-updated").textContent =
                    wo.weights_updated_at || "—";
            if ($("live-page-updated"))
                $("live-page-updated").textContent = new Date().toLocaleString(
                    "zh-CN"
                );
            updateCountdown(wo.next_recalc_at, $("live-weight-countdown"));
            if (wo.status_message && $("weight-status"))
                $("weight-status").textContent = wo.status_message;

            window.__dashboardRaw = data;
            applyAssetView(activeAsset);
            await refreshScoreHistory();
            renderWeights(wo.dynamic_weights);
            renderInfluence(wo.module_influence);
            renderBacktest(wo.backtest);

            const logTime = $("log-fetch-time");
            if (logTime && data.fetch_log)
                logTime.textContent = data.fetch_log.fetch_time || "—";
        } catch (e) {
            console.warn("dashboard refresh failed", e);
        }
    }

    async function runBacktest() {
        const btn = $("btn-backtest");
        const status = $("backtest-run-status");
        if (!btn) return;
        btn.disabled = true;
        if (status) status.textContent = "回测运行中，请稍候…";
        const end = new Date().toISOString().slice(0, 10);
        const start = cfg.backtestStart || "2025-01-01";
        try {
            const res = await fetch(
                `/api/backtest?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`,
                { method: "POST" }
            );
            const data = await res.json();
            if (!res.ok || data.ok === false)
                throw new Error(data.error || "回测失败");
            renderBacktest(data);
            if (status)
                status.textContent = `完成：${data.start_date} ~ ${data.end_date}`;
            await refreshDashboard();
        } catch (e) {
            if (status) status.textContent = "回测失败：" + e.message;
        } finally {
            btn.disabled = false;
        }
    }

    function bindNewsModal() {
        document.addEventListener("click", (e) => {
            const openBtn = e.target.closest("[data-news-open]");
            if (openBtn) {
                const idx = parseInt(openBtn.getAttribute("data-news-open"), 10);
                openNewsModal(window.__topNewsList[idx]);
                return;
            }
            const row = e.target.closest("[data-news-table]");
            if (row) {
                const tid = row.getAttribute("data-news-table");
                const idx = parseInt(row.getAttribute("data-news-index"), 10);
                const list = (window.__newsTables || {})[tid];
                if (list && list[idx]) openNewsModal(list[idx]);
                return;
            }
            if (e.target.closest("[data-news-close]")) closeNewsModal();
        });
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape") closeNewsModal();
            const row = e.target.closest("[data-news-table]");
            if (row && (e.key === "Enter" || e.key === " ")) {
                e.preventDefault();
                row.click();
            }
        });
    }

    document.addEventListener("DOMContentLoaded", () => {
        bindAssetSwitcher();
        initScoreChart();
        refreshScoreHistory();
        bindNewsModal();
        refreshPrices();
        refreshDashboard();
        setInterval(refreshPrices, priceMs);
        setInterval(refreshDashboard, dashMs);
        setInterval(() => {
            updateCountdown(window.__lastWeightNext, $("live-weight-countdown"));
        }, 1000);
        const btn = $("btn-backtest");
        if (btn) btn.addEventListener("click", runBacktest);
    });
})();
