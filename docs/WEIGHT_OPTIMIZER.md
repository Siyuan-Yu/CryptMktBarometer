# 动态权重与历史回测 — 使用说明

## 功能概览

- **动态权重**：根据近 7/30 天资讯发布后的真实价格冲击（BTC/ETH/SOL 1h/4h/24h），自动调整四大模块权重（总和恒为 100）。
- **回测**：对比「固定 40/20/25/15」与「动态权重」的方向准确率与相关性，并输出网格搜索最优权重。

## 快速开始（回测）

### 1. 安装依赖并启动主程序（日常运行）

```powershell
cd f:\CryptMktBarometer\CryptMktBarometer
.\venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

主程序每 10 分钟拉取资讯，并记录 TOP10 待测冲击；满 24 小时后自动补全实际涨跌幅。

### 2. 回填历史价格（回测前必做）

```powershell
python weight_optimizer.py --backfill 2024-01-01 2025-05-31
```

从 Binance 公开接口拉取 BTC/ETH/SOL 小时 K 线，写入 `data/market.db`。

### 3. 从资讯日志重建冲击样本（可选）

若已运行过一段时间，有 `data/logs/news_snapshot.csv`：

```powershell
python weight_optimizer.py --rebuild-impacts
```

会尝试用历史 K 线为 CSV 中的资讯补算 24h 冲击。

### 4. 运行回测

```powershell
python weight_optimizer.py --backtest 2024-01-01 2025-05-31
```

或在浏览器（主程序运行时）打开：

```
http://127.0.0.1:5000/api/backtest?start=2024-01-01&end=2025-05-31
```

### 5. 查看结果

- 网页 **板块 F**（历史回测摘要）
- `data/logs/backtest_summary.csv` — 每次回测一行汇总
- `data/logs/backtest_detail.csv` — 按日明细
- `data/logs/backtest_latest.json` — 最近一次结果（供页面展示）

## 其它命令

| 命令 | 说明 |
|------|------|
| `python weight_optimizer.py --sync-prices` | 仅同步最近 168 小时价格 |
| `python weight_optimizer.py --recalc` | 立即重算动态权重 |

## 配置项 `config/config.yaml`

```yaml
weight_optimizer:
  enabled: true
  use_dynamic_weights: true    # 是否用动态权重算总分
  recalc_interval_hours: 6
  window_short_days: 7
  window_long_days: 30
```

## 权重边界

| 模块 | 范围 |
|------|------|
| 宏观 | 20 ~ 50 |
| 监管 | 10 ~ 30 |
| 资金 | 15 ~ 35 |
| 币种 | 5 ~ 20 |

## 样本不足时

回测若提示「样本不足」，说明 `news_impacts` 表里带 `composite_24h` 的记录太少。请：

1. 多运行几天主程序积累 TOP10；或  
2. 执行 `--rebuild-impacts`；或  
3. 缩短回测区间到有数据的日期。

## 核心文件

- `weight_optimizer.py` — 动态权重与回测核心（独立模块）
- `storage/price_db.py` — 小时价格库
- `storage/impact_db.py` — 消息冲击库
- `collectors/price_hourly.py` — Binance K 线抓取
