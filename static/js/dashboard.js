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

    function renderNewsTable(tbodyId, items) {
        const tbody = $(tbodyId);
        if (!tbody) return;
        if (!items || !items.length) {
            tbody.innerHTML =
                '<tr><td colspan="7" class="empty-row">暂无该类资讯</td></tr>';
            return;
        }
        tbody.innerHTML = items
            .map((item, i) => {
                const score = Number(item.impact_score) || 0;
                const ic =
                    score > 0 ? "impact-pos" : score < 0 ? "impact-neg" : "";
                const kw = (
                    item.keywords_cn ||
                    item.display_keywords ||
                    item.keywords ||
                    []
                ).join(" · ");
                const title =
                    item.title_cn ||
                    item.display_title ||
                    item.title ||
                    "";
                const summary = item.summary_cn || "—";
                const link = item.url
                    ? `<a href="${esc(item.url)}" target="_blank" rel="noopener">查看</a>`
                    : "—";
                const sign = score > 0 ? "+" : "";
                return `<tr>
          <td>${i + 1}</td>
          <td class="title-cell">${esc(title)}</td>
          <td class="summary-cell">${esc(summary)}</td>
          <td class="keywords-cell">${esc(kw || "—")}</td>
          <td class="impact-cell ${ic}">${sign}${score}</td>
          <td>${esc(item.source || "")}</td>
          <td>${link}</td>
        </tr>`;
            })
            .join("");
    }

    function renderPrices(data) {
        const tickers = (data && data.tickers) || {};
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
                    chgEl.className = "price-change";
                } else {
                    const sign = chg >= 0 ? "+" : "";
                    chgEl.textContent = `24h ${sign}${Number(chg).toFixed(2)}%`;
                    chgEl.className =
                        "price-change " + (chg >= 0 ? "chg-up" : "chg-down");
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
      <dt>回测区间</dt><dd>${esc(bt.start_date)} ~ ${esc(bt.end_date)}（${bt.sample_days} 日）</dd>
      <dt>方向准确率</dt><dd>固定 ${esc(bt.fixed_accuracy)} · 动态 <strong class="impact-pos">${esc(bt.dynamic_accuracy)}</strong></dd>
      <dt>BTC 相关性</dt><dd>${bt.fixed_correlation} / ${bt.dynamic_correlation}</dd>
      <dt>最优权重</dt><dd>宏观${ow.macro} 监管${ow.regulation} 资金${ow.funding} 币${ow.fundamentals}</dd>
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
            ratingEl.textContent = `当前市场评级：${ratingLabel || "待计算"}`;
            ratingEl.className = `rating-tag ${ratingClass || "rating-neutral"}`;
        }
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

            renderScore(
                data.categories,
                data.total_score,
                data.rating_label,
                data.rating_class
            );
            renderNewsTable("news-tbody", data.top_news);
            renderNewsTable("sol-news-tbody", data.sol_news);
            renderNewsTable("eth-news-tbody", data.eth_news);
            renderNewsTable("macro-news-tbody", data.macro_news);
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

    document.addEventListener("DOMContentLoaded", () => {
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
