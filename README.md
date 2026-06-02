# 加密货币行情晴雨分析系统

Python 全栈 · 本地常驻后台 · Flask 可视化仪表盘 · 分阶段迭代开发。

## 当前进度：第四步（计分）✅

- [x] 第一步：项目骨架、配置、Flask 页面
- [x] 第二步：后台定时任务
- [x] 第三步：资讯 / 宏观 / 资金数据源
- [x] 第四步：分项计分 + 综合总分（0~100）+ 评级标签
- [ ] 链上数据（Solana / ETH 质押 / Dune）
- [ ] 第五步：前端完善
- [ ] 第六步：局域网与开机自启
- [ ] 第三步：数据源对接
- [ ] 第四步：计分逻辑
- [ ] 第五步：前端数据渲染完善
- [ ] 第六步：局域网访问与开机自启说明

## 目录结构

```
CryptMktBarometer/
├── main.py                 # 程序入口
├── requirements.txt
├── config/
│   ├── config.example.yaml # 配置模板
│   └── config.yaml         # 本地配置（勿提交密钥）
├── app/                    # Flask Web
│   ├── __init__.py
│   ├── routes.py
│   └── templates/
├── core/                   # 配置加载、评级工具
├── collectors/             # 数据采集（第三步）
├── scheduler/
│   └── background_scheduler.py  # APScheduler 后台调度
├── collectors/
│   └── fetch_runner.py          # 每轮拉取编排（第三步扩展）
├── scoring/                # 计分逻辑（第四步）
├── storage/                # CSV 存储（后续）
├── static/css/             # 样式
└── data/logs/              # 历史 CSV 日志目录
```

## 快速启动

```bash
# 1. 进入项目目录
cd CryptMktBarometer

# 2. 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# 3. 安装依赖
pip install -r requirements.txt

# 4. 复制配置（若尚未有 config.yaml）
# copy config\config.example.yaml config\config.yaml

# 5. 启动服务
python main.py
```

浏览器打开：**http://127.0.0.1:5000/**（拉取完成后**刷新**页面查看板块 C）

健康检查：**http://127.0.0.1:5000/health**（含 `scheduler` 字段：拉取次数、最近时间）

每轮拉取记录写入：
- `data/logs/fetch_history.csv` — 拉取摘要
- `data/logs/news_snapshot.csv` — TOP10 资讯
- `data/logs/score_history.csv` — 分项分与综合总分

### 计分规则（第四步）

| 分项 | 权重 | 主要依据 |
|------|------|----------|
| 宏观数据 | 40 | 10Y 美债变动、政策预期、经济日历 |
| 全球监管政策 | 20 | 监管类资讯影响分汇总 |
| 资金链上数据 | 25 | ETF 流向、爆仓、持仓、全球市值变动 |
| ETH/SOL 基本面 | 15 | 生态/质押/安全类资讯 |

综合总分 = 四项之和（0~100）。评级：>70 强利多 · 55~70 偏利多 · 45~55 中性 · 30~45 偏利空 · <30 强利空

计分代码位于 `scoring/` 目录，可按需调整关键词与权重映射。

## 配置说明

编辑 `config/config.yaml`：

| 配置项 | 说明 |
|--------|------|
| `web.host` / `web.port` | 本机访问地址与端口 |
| `scheduler.interval_minutes` | 轮询间隔（分钟），默认 10 |
| `scheduler.enabled` | 定时任务开关（默认 `true`） |
| `api_keys.*` | 各数据源 API 密钥 |
| `data_sources.*` | 各数据源开关 |

首次使用可将 `config.example.yaml` 复制为 `config.yaml` 后修改。

## 页面三大板块（第一步为占位）

- **板块 A**：晴雨计分总表（宏观 40%、监管 20%、资金 25%、基本面 15%）
- **板块 B**：TOP10 重磅资讯列表
- **板块 C**：原始数据抓取日志

## 许可证

私有项目，按需使用。
