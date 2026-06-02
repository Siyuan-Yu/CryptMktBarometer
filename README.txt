================================================================================
  加密货币行情晴雨表 (CryptMktBarometer) — Windows 桌面版 EXE 使用说明
================================================================================

一、如何打包（生成单个 exe）
--------------------------------------------------------------------------------
前提：已安装 Python 3.11+，项目内已有 venv 且能正常运行 python main.py

方式 A — 一键脚本（推荐）
  1. 【重要】先完全退出正在运行的 CryptMktBarometer.exe
       - 托盘右键 → 退出程序
       - 或任务管理器结束 CryptMktBarometer.exe
     （否则打包会报错：PermissionError 拒绝访问 dist\...\CryptMktBarometer.exe）
  2. 双击或在 cmd 中运行：
       packaging\build_exe.bat
     脚本会自动尝试结束旧进程并删除旧 exe。
  3. 等待完成后，产物路径：
       dist\CryptMktBarometer.exe

方式 B — 手动命令（在项目根目录）
  1. 激活虚拟环境：
       venv\Scripts\activate
  2. 安装运行依赖 + 打包依赖：
       pip install -r requirements.txt
       pip install -r requirements-build.txt
  3. 生成托盘/程序图标：
       python packaging\generate_icon.py
  4. 打包（单文件、无黑色命令行窗口）：
       pyinstaller packaging\CryptMktBarometer.spec --noconfirm --clean
  5. 得到：
       dist\CryptMktBarometer.exe

说明：
  - 打包不会修改、删除你现有的源码、网页、CSV、数据库。
  - 开发调试仍用：python main.py
  - 桌面版入口为独立文件：desktop_launcher.py（仅打包时使用）


二、如何双击运行
--------------------------------------------------------------------------------
  1. 将 dist\CryptMktBarometer.exe 复制到你希望长期存放的文件夹
     （建议单独建一个目录，例如 D:\CryptMktBarometer\）
  2. 双击 CryptMktBarometer.exe
  3. 程序将自动：
       - 后台启动 Flask 服务（无黑色 CMD 窗口）
       - 打开默认浏览器进入晴雨表网页
       - 在任务栏右下角托盘区显示图标（蓝色「晴」）
  4. 首次运行会在 exe 同目录自动创建：
       config\config.yaml      （从示例复制，可编辑）
       data\logs\              （CSV 日志）
       data\market.db          （运行后产生，SQLite）
       app\templates\          （网页模板，仅首次从包内释放）
       static\                 （CSS/JS，仅首次释放）

局域网手机访问：
  用记事本打开 exe 同目录下 config\config.yaml
  将 web.host 改为：0.0.0.0
  保存后退出托盘程序再重新双击 exe
  手机浏览器访问：http://你的电脑局域网IP:5000


三、如何退出（完全关闭后台）
--------------------------------------------------------------------------------
  1. 点击任务栏托盘区（右下角 ^）的晴雨表图标
  2. 右键 → 选择「退出程序」
  3. 服务、定时抓取、托盘将一并关闭

注意：直接关闭浏览器标签页不会停止后台，必须从托盘退出。


四、数据保存在哪里
--------------------------------------------------------------------------------
  全部在 CryptMktBarometer.exe 所在目录（与 exe 同级），例如：

    config\config.yaml          运行配置（端口、API 密钥、抓取间隔等）
    data\logs\fetch_history.csv     抓取日志
    data\logs\news_snapshot.csv     资讯快照
    data\logs\score_history.csv     评分历史
    data\logs\weight_history.csv    权重学习记录
    data\logs\backtest_*.csv/json   回测结果
    data\market.db                  价格与冲击数据库
    data\logs\desktop.log           桌面版运行日志

  备份：复制整个文件夹即可保留全部历史数据。


五、如何更新
--------------------------------------------------------------------------------
  方式 1 — 只换程序、保留数据（推荐）
    1. 用新版本重新打包得到新的 CryptMktBarometer.exe
    2. 退出旧版托盘程序
    3. 用新 exe 覆盖旧 exe（不要删除 config\ 和 data\ 文件夹）
    4. 重新双击运行

  方式 2 — 仍用 Python 源码开发版
    git pull 或替换源码后：pip install -r requirements.txt
    继续 python main.py，与 exe 共用同一套 config / data 目录结构

  配置项说明：与网页版相同
    - 后台抓取：默认每 10 分钟（config.yaml → scheduler）
    - 页面价格刷新：每 5 秒
    - 行情/资讯刷新：每 30 秒
    - 动态权重：每 6 小时


六、功能清单（与网页版一致）
--------------------------------------------------------------------------------
  [x] 10 分钟自动抓取
  [x] BTC/ETH/SOL 实时价格（约 5 秒刷新）
  [x] TOP10 资讯 + SOL / ETH / 宏观分类资讯
  [x] 中文标题、摘要、关键词
  [x] 晴雨表评分、动态权重、历史回测
  [x] 托盘打开面板 / 完全退出
  [x] 桌面悬浮小仪表盘（半透明置顶，可拖动）

七、桌面悬浮小窗（QQ 宠物风格）
--------------------------------------------------------------------------------
  启动 CryptMktBarometer.exe 后会自动出现小悬浮窗，显示：
    - 晴雨表总分（大号）
    - 市场评级（强利多/偏利多/中性/偏利空/强利空）
    - BTC ETH SOL 价格（约 5 秒刷新，涨绿跌红）

  操作：
    - 左键单击（未拖动时）→ 打开浏览器完整面板
    - 按住拖动 → 移动位置
    - 右键 →「退出悬浮窗」仅关闭小窗，后台与托盘继续运行
    - 托盘「退出程序」→ 同时关闭悬浮窗 + Flask + 托盘

  仅单独开悬浮窗（Flask 需已运行）：
    python floating_dashboard.py

  重新打包 exe 后悬浮窗才会编入程序：
    packaging\build_exe.bat

遇到问题：查看 data\logs\desktop.log

================================================================================
