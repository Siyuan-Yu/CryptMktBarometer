/**
 * 分数历史折线图 · 萤火虫车机风
 * 柔和渐变曲线 · 半透明磨砂 · 干净治愈
 */
(function (global) {
    const ZONE = {
        bullStrong: {
            line: "#7ae8b8",
            soft: "#a8f5d4",
            fill: "rgba(122, 232, 184, 0.07)",
            label: "强利多",
        },
        bull: {
            line: "#88e8dc",
            soft: "#b8f5ee",
            fill: "rgba(136, 232, 220, 0.06)",
            label: "偏利多",
        },
        neutral: {
            line: "#c8c0f0",
            soft: "#ddd8f8",
            fill: "rgba(200, 192, 240, 0.08)",
            label: "中性",
        },
        bear: {
            line: "#ffd0c8",
            soft: "#ffe4de",
            fill: "rgba(255, 208, 200, 0.06)",
            label: "偏利空",
        },
        bearStrong: {
            line: "#ffc8c8",
            soft: "#ffe0e0",
            fill: "rgba(255, 200, 200, 0.07)",
            label: "强利空",
        },
    };

    function scoreZone(score) {
        const s = Number(score);
        if (Number.isNaN(s)) return "neutral";
        if (s > 70) return "bullStrong";
        if (s >= 55) return "bull";
        if (s >= 45) return "neutral";
        if (s >= 30) return "bear";
        return "bearStrong";
    }

    function zoneOf(score) {
        return ZONE[scoreZone(score)] || ZONE.neutral;
    }

    function parseTs(s) {
        if (!s) return null;
        const t = new Date(String(s).replace(" ", "T"));
        return Number.isNaN(t.getTime()) ? null : t;
    }

    function bucketPoints(raw, sinceMs, untilMs) {
        const spanDays = (untilMs - sinceMs) / 86400000;
        if (!raw.length) return [];

        if (spanDays <= 2 || raw.length <= 48) {
            return raw.map((p) => ({
                t: parseTs(p.time).getTime(),
                score: p.score,
                label: p.time.slice(0, 16),
            }));
        }

        const bucketMs = spanDays > 14 ? 86400000 : 4 * 3600000;
        const buckets = new Map();

        raw.forEach((p) => {
            const t = parseTs(p.time);
            if (!t) return;
            const ms = t.getTime();
            const key = Math.floor(ms / bucketMs) * bucketMs;
            const arr = buckets.get(key) || [];
            arr.push(p.score);
            buckets.set(key, arr);
        });

        return Array.from(buckets.entries())
            .sort((a, b) => a[0] - b[0])
            .map(([key, scores]) => {
                const avg =
                    scores.reduce((s, v) => s + v, 0) / scores.length;
                const d = new Date(key);
                const label =
                    bucketMs >= 86400000
                        ? `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
                        : `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:00`;
                return { t: key, score: Math.round(avg * 10) / 10, label };
            });
    }

    /** Catmull-Rom 转三次贝塞尔 · 柔和曲线 */
    function smoothLinePath(coords) {
        if (!coords.length) return "";
        if (coords.length === 1) {
            return `M${coords[0][0].toFixed(1)},${coords[0][1].toFixed(1)}`;
        }
        if (coords.length === 2) {
            return `M${coords[0][0].toFixed(1)},${coords[0][1].toFixed(1)} L${coords[1][0].toFixed(1)},${coords[1][1].toFixed(1)}`;
        }

        let d = `M${coords[0][0].toFixed(1)},${coords[0][1].toFixed(1)}`;
        for (let i = 0; i < coords.length - 1; i++) {
            const p0 = coords[Math.max(0, i - 1)];
            const p1 = coords[i];
            const p2 = coords[i + 1];
            const p3 = coords[Math.min(coords.length - 1, i + 2)];
            const cp1x = p1[0] + (p2[0] - p0[0]) / 6;
            const cp1y = p1[1] + (p2[1] - p0[1]) / 6;
            const cp2x = p2[0] - (p3[0] - p1[0]) / 6;
            const cp2y = p2[1] - (p3[1] - p1[1]) / 6;
            d += ` C${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
        }
        return d;
    }

    function buildZoneBands(pad, W, ih, yScale) {
        const bands = [
            { lo: 70, hi: 100, zone: "bullStrong" },
            { lo: 55, hi: 70, zone: "bull" },
            { lo: 45, hi: 55, zone: "neutral" },
            { lo: 30, hi: 45, zone: "bear" },
            { lo: 0, hi: 30, zone: "bearStrong" },
        ];
        return bands
            .map(({ lo, hi, zone }) => {
                const yTop = yScale(hi);
                const yBot = yScale(lo);
                const h = Math.max(0, yBot - yTop);
                const z = ZONE[zone];
                return `<rect class="chart-zone-band" x="${pad.l}" y="${yTop}" width="${W - pad.l - pad.r}" height="${h}" fill="${z.fill}" rx="8"/>`;
            })
            .join("");
    }

    function buildLineGradient(id, coords, pad, W) {
        if (!coords.length) return "";
        const n = coords.length;
        const stops = coords
            .map(([x, , p], i) => {
                const pct = n <= 1 ? 0 : (i / (n - 1)) * 100;
                const z = zoneOf(p.score);
                return `<stop offset="${pct.toFixed(1)}%" stop-color="${z.line}"/>`;
            })
            .join("");
        return `<linearGradient id="${id}" gradientUnits="userSpaceOnUse" x1="${pad.l}" y1="0" x2="${W - pad.r}" y2="0">${stops}</linearGradient>`;
    }

    function buildAreaGradient(id, pad, H) {
        return `<linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#b8d8ff" stop-opacity="0.28"/>
        <stop offset="45%" stop-color="#d8c8ff" stop-opacity="0.18"/>
        <stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
      </linearGradient>`;
    }

    function ScoreChart(container) {
        this.root = container;
        this.asset = "btc";
        this.rawSeries = {};
        this.points = [];
        this._uid = Math.random().toString(36).slice(2, 8);
        this._onResize = () => this.render();
        window.addEventListener("resize", this._onResize);
    }

    ScoreChart.prototype.setSeries = function (seriesByAsset) {
        this.rawSeries = seriesByAsset || {};
        this.render();
    };

    ScoreChart.prototype.setAsset = function (assetId) {
        this.asset = assetId || "btc";
        this.render();
    };

    ScoreChart.prototype.render = function () {
        if (!this.root) return;
        const raw = (this.rawSeries[this.asset] || []).slice();
        if (!raw.length) {
            this.root.innerHTML =
                '<p class="score-chart-empty">暂无历史分数数据（2026 年初至今），等待定时任务写入 score_history.csv…</p>';
            return;
        }

        const parsed = raw
            .map((p) => ({ ...p, ms: parseTs(p.time)?.getTime() }))
            .filter((p) => p.ms != null);
        if (!parsed.length) {
            this.root.innerHTML =
                '<p class="score-chart-empty">历史时间格式无法解析</p>';
            return;
        }

        const sinceMs = parseTs("2026-01-01 00:00:00").getTime();
        const untilMs = parsed[parsed.length - 1].ms;
        this.points = bucketPoints(raw, sinceMs, untilMs);

        const W = Math.max(320, this.root.clientWidth || 480);
        const H = 260;
        const pad = { t: 32, r: 22, b: 44, l: 46 };
        const iw = W - pad.l - pad.r;
        const ih = H - pad.t - pad.b;

        const tMin = sinceMs;
        const tMax = Math.max(untilMs, tMin + 3600000);
        const xScale = (t) => pad.l + ((t - tMin) / (tMax - tMin)) * iw;
        const yScale = (s) =>
            pad.t + ih - (Math.min(100, Math.max(0, s)) / 100) * ih;

        const uid = this._uid;
        const lineGradId = `lineGrad-${uid}`;
        const areaGradId = `areaGrad-${uid}`;
        const glowId = `glow-${uid}`;

        const coords = this.points.map((p) => [xScale(p.t), yScale(p.score), p]);
        const linePath = smoothLinePath(coords);
        const baseY = pad.t + ih;
        const areaPath =
            linePath +
            ` L${coords[coords.length - 1][0].toFixed(1)},${baseY.toFixed(1)}` +
            ` L${coords[0][0].toFixed(1)},${baseY.toFixed(1)} Z`;

        const zoneBands = buildZoneBands(pad, W, ih, yScale);
        const lineGrad = buildLineGradient(lineGradId, coords, pad, W);
        const areaGrad = buildAreaGradient(areaGradId, pad, H);

        const gridLines = [0, 25, 50, 75, 100]
            .map((v) => {
                const y = yScale(v);
                return `<line class="chart-grid" x1="${pad.l}" y1="${y}" x2="${W - pad.r}" y2="${y}"/>
            <text class="chart-axis-y" x="${pad.l - 10}" y="${y + 4}" text-anchor="end">${v}</text>`;
            })
            .join("");

        const tickN = Math.min(5, this.points.length);
        const xLabels = [];
        if (tickN > 0) {
            for (let i = 0; i < tickN; i++) {
                const idx = Math.round(
                    (i / (tickN - 1 || 1)) * (this.points.length - 1)
                );
                const p = this.points[idx];
                const x = xScale(p.t);
                xLabels.push(
                    `<text class="chart-axis-x" x="${x}" y="${H - 10}" text-anchor="middle">${p.label}</text>`
                );
            }
        }

        const dots = coords
            .map(([x, y, p], i) => {
                const z = zoneOf(p.score);
                return `<g class="chart-dot-group" data-idx="${i}">
          <circle class="chart-dot-halo" cx="${x}" cy="${y}" r="10" fill="${z.soft}" opacity="0.45"/>
          <circle class="chart-dot" cx="${x}" cy="${y}" r="4" fill="#fff" stroke="${z.line}" stroke-width="2" data-idx="${i}" tabindex="0" aria-label="${p.label} ${z.label} ${p.score}分"/>
        </g>`;
            })
            .join("");

        const legend = Object.entries(ZONE)
            .map(
                ([key, z]) =>
                    `<span class="chart-legend-item"><i style="background:linear-gradient(135deg,${z.line},${z.soft})"></i>${z.label}</span>`
            )
            .join("");

        this.root.innerHTML = `
      <div class="score-chart-wrap">
        <div class="score-chart-glass-bg" aria-hidden="true"></div>
        <div class="chart-legend">${legend}</div>
        <svg class="score-chart-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="分数历史走势图">
          <defs>
            ${lineGrad}
            ${areaGrad}
            <filter id="${glowId}" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur in="SourceGraphic" stdDeviation="2.5" result="blur"/>
              <feMerge>
                <feMergeNode in="blur"/>
                <feMergeNode in="SourceGraphic"/>
              </feMerge>
            </filter>
          </defs>
          ${zoneBands}
          ${gridLines}
          <path class="chart-area" d="${areaPath}" fill="url(#${areaGradId})"/>
          <path class="chart-line-glow" d="${linePath}" fill="none" stroke="url(#${lineGradId})" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" opacity="0.35"/>
          <path class="chart-line-main" d="${linePath}" fill="none" stroke="url(#${lineGradId})" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" filter="url(#${glowId})"/>
          ${dots}
          ${xLabels.join("")}
        </svg>
        <div class="score-chart-tooltip" id="score-chart-tooltip" hidden></div>
      </div>`;

        this._bindTooltip();
    };

    ScoreChart.prototype._bindTooltip = function () {
        const svg = this.root.querySelector(".score-chart-svg");
        const tip = this.root.querySelector("#score-chart-tooltip");
        if (!svg || !tip) return;

        const show = (idx, clientX, clientY) => {
            const p = this.points[idx];
            if (!p) return;
            const z = zoneOf(p.score);
            tip.hidden = false;
            tip.className = `score-chart-tooltip chart-tip-${scoreZone(p.score)}`;
            tip.innerHTML = `<strong>${p.score}</strong> 分 · ${z.label}<br><span>${p.label}</span>`;
            const wrap = this.root.querySelector(".score-chart-wrap");
            const rect = wrap.getBoundingClientRect();
            tip.style.left = `${clientX - rect.left + 12}px`;
            tip.style.top = `${clientY - rect.top - 10}px`;
            svg.querySelectorAll(".chart-dot-group").forEach((g, i) => {
                g.classList.toggle("is-active", i === idx);
            });
        };
        const hide = () => {
            tip.hidden = true;
            svg.querySelectorAll(".chart-dot-group").forEach((g) =>
                g.classList.remove("is-active")
            );
        };

        svg.querySelectorAll(".chart-dot").forEach((dot) => {
            const idx = +dot.getAttribute("data-idx");
            dot.addEventListener("mouseenter", (e) =>
                show(idx, e.clientX, e.clientY)
            );
            dot.addEventListener("mousemove", (e) =>
                show(idx, e.clientX, e.clientY)
            );
            dot.addEventListener("mouseleave", hide);
            dot.addEventListener("focus", () => {
                const r = dot.getBoundingClientRect();
                show(idx, r.left + r.width / 2, r.top);
            });
            dot.addEventListener("blur", hide);
        });
    };

    ScoreChart.prototype.destroy = function () {
        window.removeEventListener("resize", this._onResize);
    };

    global.ScoreChart = {
        create(containerId) {
            const el = document.getElementById(containerId);
            if (!el) return null;
            return new ScoreChart(el);
        },
    };
})(window);
