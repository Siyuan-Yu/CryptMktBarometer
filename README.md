# 加密货币行情晴雨分析系统

Python 全栈 · 本地常驻后台 · Flask 可视化仪表盘 · 分阶段迭代开发。

## 当前进度：第一步 ✅

- [x] 项目目录结构
- [x] `config/config.yaml` 配置文件（API 密钥、轮询间隔、Web 端口等）
- [x] Flask 基础网页骨架（三大板块布局）
- [ ] 第二步：定时任务模块
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
├── scheduler/              # 定时任务（第二步）
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

浏览器打开：**http://127.0.0.1:5000/**

健康检查：**http://127.0.0.1:5000/health**

## 配置说明

编辑 `config/config.yaml`：

| 配置项 | 说明 |
|--------|------|
| `web.host` / `web.port` | 本机访问地址与端口 |
| `scheduler.interval_minutes` | 轮询间隔（分钟），默认 10 |
| `scheduler.enabled` | 定时任务开关（第二步启用） |
| `api_keys.*` | 各数据源 API 密钥 |
| `data_sources.*` | 各数据源开关 |

首次使用可将 `config.example.yaml` 复制为 `config.yaml` 后修改。

## 页面三大板块（第一步为占位）

- **板块 A**：晴雨计分总表（宏观 40%、监管 20%、资金 25%、基本面 15%）
- **板块 B**：TOP10 重磅资讯列表
- **板块 C**：原始数据抓取日志

## 许可证

私有项目，按需使用。
