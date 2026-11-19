# FinPilot · 金融学习与期权风险解读

COMP4431 Artificial Intelligence（2026/27）课程项目。FinPilot 将可追溯的知识检索、本地公式计算和模型解释放在同一个工作台中，支持中英双语问答、期权风险解读、到期盈亏试算、历史复盘，以及共享指定会话的 Windows 桌宠。

**当前应用版本：17.0.0。** 已验证的主要运行环境为 Windows x64、Python 3.11 和 Edge。项目用于金融教育与课程展示，分析结果需结合数据来源、日期和适用范围核对。

[快速启动](#快速启动) · [页面与功能](#页面与功能) · [模型与配置](#模型与配置) · [开发与验证](#开发与验证) · [文档与历史版本](#文档与历史版本) · [团队与提交](#团队与提交)

## 团队与提交

### 团队信息

| 成员 | 英文姓名 | 学号 | 贡献比例 |
| --- | --- | --- | --- |
| 1 | Li Hengxian | 24118129d | 25% |
| 2 | Liang Zishen | 24099982d | 25% |
| 3 | Wu Peihang | 24108869d | 25% |
| 4 | Wang Xuxin | 24110796d | 25% |

## 项目特点

- **先计算，再解释**：复利、贷款、预算与期权到期盈亏由本地代码计算；模型读取结果及证据，帮助理解含义。
- **来源可追溯**：金融知识、期权快照、历史报告和使用手册分别保留来源、时间及适用范围，旧回答继续关联原有依据。
- **明确区分模式**：真实模型生成、本地规则、本地知识摘录及模型失败降级都有标识；合成数据与真实历史资料分开展示。
- **逐步学习**：从风险解读、互动试算进入带依据的追问；专业 IBKR 采集、历史复盘和联合分析保留在完整工作台。
- **本机持久化**：会话保存到 SQLite，支持恢复与 JSON 导出；桌宠仅共享用户明确选定的会话。

## 快速启动

### 1. 安装运行环境

先安装 Python 3.11 或以上版本。以下命令在**项目根目录的 Windows PowerShell** 中执行，无需激活虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt tzdata==2025.3
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
```

Windows 通常没有系统 IANA 时区数据库；运行依赖已包含 `tzdata==2025.3`，供纽约交易日判断、互动学习及历史复盘使用。首次安装需要网络。

### 2. 选择运行模式

不填 API Key 也能使用本地知识摘录、计算器、合成期权分析、互动学习和使用手册。

需要 DeepSeek 时，用文本编辑器打开 `.env`，填写自己的 `DEEPSEEK_API_KEY`，并确认 `FINPILOT_OFFLINE=false`。项目默认模型名为 `deepseek-flash`，实际可用性取决于服务端接口与账户权限。不要将密钥填入聊天或演示页面。

需要固定的离线彩排时，将 `.env` 的 `FINPILOT_OFFLINE` 设为 `true`。这会关闭 DeepSeek 云端路径；工作台显式选择的本地 LoRA 仍可进行本地推理。

### 3. 启动服务

双击根目录 **`start-finpilot.bat`**，或运行：

```powershell
.\start-finpilot.bat
```

启动器检查或创建 `.venv`、补装缺失的核心依赖、准备 `.env`，随后启动后端、悬浮 2D 对话助手和浏览器。默认使用 8000–8010 中第一个可用端口，**以启动窗口显示的地址为准**。缺少桌宠运行依赖时自动下载锁定版本的 Node/Electron；依赖和桌宠偏好缓存于 `%LOCALAPPDATA%\FinPilot\runtimes\full-<项目路径摘要>\`，后续复用。

**启动窗口需保持打开。关闭该窗口、按 `Ctrl+C` 或双击 `stop-finpilot.cmd`，会同时结束本次项目后端和助手。** 后端异常退出也会关闭助手；关闭浏览器页面不会停止项目。同一项目重复启动会复用现有运行实例，不重复创建助手；修改配置、代码或切换 `-NoDesktop` 模式时，请先停止再重启。独立运行的旧服务不会被接管或结束。

```powershell
# 指定端口，不打开浏览器，仍启动助手
.\start-finpilot.bat -Port 8001 -NoBrowser

# 仅使用网页，不启动桌面助手
.\start-finpilot.bat -NoDesktop

# 停止本项目通过启动器开启的服务与助手
.\stop-finpilot.cmd

# 重新安装核心依赖
.\start-finpilot.bat -Install
```

仅运行已编译的网页（`-NoDesktop`）不需要 Node.js。直接执行 `uvicorn` 供后端开发使用，不会自动创建桌面助手。不要直接打开 `web/index.html`，页面需要后端接口。浏览器语音、3D 和实际网关采集另有环境要求，见后文。

### 单独启动期权风险解读

准备好上述 Python 环境后，双击 **`start-options-demo.cmd`**，默认打开：

<http://127.0.0.1:8018/options-demo>

此启动器使用独立数据库，禁用实际 IBKR 访问。页面加载不会请求模型；选择引擎后点击「一键分析」或明确发送问题才运行对应模式。数据始终是固定的合成样本。

```powershell
# 完全本地的规则分析彩排
.\start-options-demo.cmd -Offline

# 使用其他端口；不自动打开浏览器
.\start-options-demo.cmd -Port 8019 -Offline -NoBrowser

# 停止本启动器拥有的对应服务
.\start-options-demo.cmd -Port 8019 -Stop
```

切换离线设置，或修改 `.env` 后，先用对应端口的 `-Stop` 停止已有独立服务，再重新启动。启动器不会停止其他程序占用的端口。进程记录和独立数据库位于 `tmp/options-demo/`，日志位于 `output/options-demo/`。

## 页面与功能

下表使用主服务默认端口 8000；若启动器选择了其他端口，请相应替换。独立期权服务的默认端口为 8018。

| 入口 | 用途 | 数据与依赖 |
| --- | --- | --- |
| [首页](http://127.0.0.1:8000/) | 项目介绍与功能导航 | 本地资源和编译后的 React 页面 |
| [期权风险解读](http://127.0.0.1:8000/options-demo) | 一键解释波动定价、两翼 IV 差和跨式成本 | 固定合成样本；本地规则或可选 DeepSeek，不连接 IBKR |
| [期权互动学习](http://127.0.0.1:8000/learn) | 三种情景、到期盈亏试算、保存后追问 | 合成教学数据；计算与保存不请求模型 |
| [完整工作台](http://127.0.0.1:8000/workspace) | 双语聊天、财务计算器、知识来源、会话管理 | 可离线使用；云端问答需有效配置 |
| [专业期权分析](http://127.0.0.1:8000/workspace?view=options) | 单组或联合采集、质量检查、指标与报告追问 | 真实采集需本地 IB Gateway、可选依赖及行情权限 |
| [历史复盘](http://127.0.0.1:8000/workspace?view=history) | 导入 CSV/JSON、回放历史档案、检索专家依据 | 区分自有文件、合成示例和已保存的真实历史资料 |
| [三步历史演示](http://127.0.0.1:8000/demo) | 加载历史档案 → 检索依据 → 明确请求 AI 解释 | 独立会话；加载档案不采集新行情 |
| [使用指南](http://127.0.0.1:8000/help) | 搜索当前 17 个双语手册主题 | 手册版本 17.0；页面搜索不请求模型或 IBKR |
| [网页桌宠](http://127.0.0.1:8000/pet) | 查看角色与指定会话的聊天界面 | 主启动器默认同时启动原生悬浮窗口 |
| [API 文档](http://127.0.0.1:8000/docs) | 本地接口说明与请求测试 | 机器可读契约为 `/openapi.json` |

### 推荐体验流程

1. 打开「期权风险解读」，核对「模拟数据 · 非实时行情」标识与引擎，点击一次「一键分析」，阅读概览和回答，再按需展开数值依据。
2. 打开「期权互动学习」，选择看跌活动、报价价差或下方保护情景，切换买入看涨、买入看跌或看涨借记价差，改变到期价格并更新试算。
3. 点击「带着这份演示追问」，保存当前试算并建立专属会话。系统只预填草稿，**需要自己点击发送**才请求所选回答引擎。
4. 在回答中核对来源、数据日期、模式和局限；改变试算不会改写已保存的报告或旧回答。

默认买入看涨试算支付总额为 360 USD；假设到期标的价格为 102 USD，整组净盈亏为 −160 USD。这说明标的上涨也可能尚未覆盖权利金。盈亏图仅计算到期结果，不包含提前平仓估值、费用、税费及实际行权或指派过程。

### 专业采集与历史资料

真实 IBKR 采集为可选功能：安装依赖，登录本地 IB Gateway，启用 socket API 和 Read-Only API，再按实际环境配置端口、client ID 与行情权限。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-options.txt
```

在 `.env` 中设 `IBKR_ENABLED=true` 后重启主服务，再从工作台明确发起采集。示例端口 4002 需以实际 Gateway 配置为准。返回延迟数据、TCP 端口可达或健康接口正常，都不能单独证明实时行情权限已通过。

联合分析支持最多四组标的或到期日；报告追问绑定已保存的快照，普通追问不会自动刷新行情。「刷新并解释变化」会按原范围和请求模式重新采集，并保留旧报告与旧回答。历史报告保持固定，需导入或获取另一份资料才能改变复盘范围。详细流程见 [网关与权限说明](docs/ibkr_gateway_v12.md)、[刷新说明](docs/options_refresh_v11.md) 和 [历史复盘说明](docs/history_rag_v13.md)。

### Windows 桌宠

主启动器默认自动打开桌宠。只需要后端与桌宠、不打开浏览器时，也可运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-desktop.ps1

# 首次启动时选择端口；同一项目已有实例时复用现有实例
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-desktop.ps1 -Port 8001
```

单击播放本地互动，双击或按 Enter 打开聊天；在工作台点击「连接当前会话」后，桌宠可继续该会话。连接、同步和动画不会自动调用模型或采集行情。关闭项目启动窗口会结束后台与助手；通过托盘「退出桌宠」则只关闭助手，后台保留到项目停止。

默认启动器运行当前宿主源码，以包含最新生命周期修复；旧的 v15 Portable EXE 是历史构建，不用于本次联动启动。**Portable EXE 未内置 Python 后端、基座模型或 API Key。** 开发与重建见 [桌宠说明](desktop/README.md)。鲸鱼娘使用 2D 动作素材，原有机器人支持 2D/3D 展示。

## 模型与配置

### 三种容易混淆的模式

| 模式 | 实际执行内容 | 需要什么 |
| --- | --- | --- |
| DeepSeek | 向配置的云端 API 发送问题和选定上下文 | 有效密钥、网络及可用额度；可能产生费用 |
| 期权风险页「本地规则」 | 用确定性计算和规则解释合成样本 | 主 Python 环境；没有语言模型请求 |
| 工作台「本地 LoRA」 | 用 Qwen3-0.6B 基座和已训练适配器进行本地推理 | 独立 ML 环境、已缓存基座、有效训练产物 |

工作台的离线知识摘录是另一种降级结果，会明确标注模式和原因。模型配置状态只表示配置存在，不能替代实际调用验证。调用 DeepSeek 成功也不会把合成样本变成真实行情。

### 主要配置项

将 `.env.example` 复制为 `.env` 后修改。**已有终端或系统中的同名环境变量优先于 `.env`；修改配置后需要重启对应服务。**

| 配置项 | 项目默认值 | 作用 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 空 | 云端密钥；留空时可走离线路径 |
| `DEEPSEEK_MODEL` | `deepseek-flash` | 请求的模型名称 |
| `DEEPSEEK_TIMEOUT` | `45` | 云端请求超时秒数；部分功能还有更短的请求上限 |
| `FINPILOT_OFFLINE` | `false` | `true` 时禁用 DeepSeek 云端路径 |
| `FINPILOT_DB` | `data/finpilot.sqlite3` | 普通会话及报告数据库路径 |
| `IBKR_ENABLED` | `false` | 是否启用实际网关采集 |
| `IBKR_HOST` / `IBKR_PORT` | `127.0.0.1` / `4002` | 本地 Gateway 地址与示例端口 |
| `IBKR_CLIENT_ID` | `67` | 需避免与其他客户端冲突 |
| `IBKR_MARKET_DATA_TYPE` | `1` | 默认请求类型；实际类型以返回数据为准 |
| `FINPILOT_ADAPTER` | `models/finpilot-lora` | 本地适配器目录 |
| `FINPILOT_ML_PYTHON` | `.venv-ml/Scripts/python.exe`（Windows） | 独立推理环境的解释器 |
| `FINPILOT_HF_HOME` | 未设置 | 可选的 Hugging Face 基座缓存路径 |

本地模型的复现、依赖与硬件要求见 [LoRA 实验说明](finetuning/README.md)。已有适配器可复用，但需要另行下载基座；普通聊天不会自动下载大模型。训练脚本要求 NVIDIA CUDA GPU。独立下载和训练脚本读取当前 shell 环境，自定义缓存时须同步设置 shell 中的 `FINPILOT_HF_HOME` 与后端配置。

本项目的微调对象是 Qwen3-0.6B 的 LoRA 适配器；知识检索和提示词不等于微调，也不声称微调了托管 DeepSeek 模型。训练及对照结果见 [训练报告](reports/finetuning_training.json) 与 [评估报告](reports/finetuning_evaluation.json)，格式或引用指标不能视为金融事实准确率。

## 开发与验证

### 技术结构

后端使用 FastAPI，SQLite 保存会话与报告；普通金融问答结合本地双语知识库，期权与历史解释读取保存的数据及专家依据。专家检索采用 BM25、中文字符 n-gram 和 RRF；引用与输出格式检查是有限规则，不是通用语义正确性验证。

首页源码采用 React、TypeScript、Vite、Tailwind CSS、GSAP、Motion 与 Three.js。工作台及独立功能页位于 `web/`，Windows 桌宠由 Electron 承载。

```text
app/                    API、配置、计算、检索、模型与持久化
  main.py               路由与本机访问约束
  finance.py            财务计算与显式计算命令
  options_demo.py        合成样本的波动与风险解读
  options_lab.py         互动学习及到期盈亏试算
  options_*.py           网关、质量分析、历史、刷新及证据处理
data/                   已审阅知识、手册和教学情景
web/                    工作台、功能页、角色及编译后的首页
frontend/               React 首页源码与依赖锁文件
desktop/                Electron 宿主、测试及构建入口
finetuning/             LoRA 数据、训练与复现说明
models/finpilot-lora/    适配器及训练清单；不含基座
tests/                  Python 单元、API 及回归测试
evaluation/             检索评估案例
scripts/                浏览器验证、评估、报告与打包工具
docs/                   功能说明、技术文档与英文演示稿
reports/                各次验证的结果及截图
dist/                   本机生成的提交包与校验结果
```

### 运行检查

基础测试与检索评估：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/evaluate.py
```

需要避免读取日常 `.env` 和会话数据库时，使用已有的隔离回归入口：

```powershell
.\.venv\Scripts\python.exe scripts/run_python_regression_v17.py
```

真实 Edge 的离线界面检查需要额外依赖，并在当前环境安装 Microsoft Edge。下列脚本自行创建私有测试服务，无需先启动 8000 端口；云端或错误状态采用受控响应，不计作真实模型验收。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ui-tests.txt
.\.venv\Scripts\python.exe scripts/check_experience_ui_v17.py
.\.venv\Scripts\python.exe scripts/check_options_demo_browser.py
.\.venv\Scripts\python.exe scripts/check_options_demo_language.py
.\.venv\Scripts\python.exe scripts/check_storage_resilience.py
```

实际 DeepSeek 检查需显式加 `--live`，会使用账户额度；下面只对选定样本发起一轮英文分析，仍使用合成数据且不连接 IBKR：

```powershell
.\.venv\Scripts\python.exe scripts/check_options_demo_live.py --live --frame 0 --language en
```

### 最近一次完整审查

下表记录 **2026-11-19** 的实际检查结果；历史版本文档中的旧测试数字仅对应当时阶段。

| 检查范围 | 结果 | 证据 |
| --- | --- | --- |
| Python 回归 | 1097 项通过，本轮新增 34 项边界回归 | [JUnit](reports/tests_v17-20261119T084146122933Z.xml) |
| 完整体验 | Edge 320 / 390 / 1440 三种宽度通过 | [界面报告](reports/experience_ui_v17-20261119T083229312909Z.json) |
| 期权风险页与双语 | 主流程、损坏响应保护、语言切换通过 | [流程报告](reports/options_demo_browser_20261119T083229Z.json)、[语言报告](reports/options_demo_language_20261119T084146699638Z.json) |
| 浏览器存储异常 | 禁用存储、容量不足两种故障注入通过 | [存储报告](reports/storage_resilience_20261118T003802012664Z.json) |
| 前端与桌宠构建 | TypeScript/Vite 通过；桌宠 4 项 Node 测试通过，ASAR 与源码一致 | [审查汇总](reports/project_audit_20261119.json)、[桌宠构建](reports/desktop_build_bug_audit_20261118.json) |
| 独立启动与提交包 | 启动、复用、停止及提交包独立解压验证通过 | [启动器报告](reports/launcher_audit_20261118.json)；包验证生成于 `dist/package_check_v17.json` |

本轮实际完成一次缓存本地 LoRA 离线生成；未重新调用真实 DeepSeek 或 IBKR，也未认证物理拖动、托盘、语音、透明区域命中或多屏硬件行为。测试通过不保证绝对没有 bug、模型首答正确或金融判断可靠。更早的真实模型和网关验收保留在对应版本文档及报告中。

### 重建首页和桌宠

只在修改相应源码时需要安装 Node.js。首页原有环境说明使用 Node.js 22.12 以上；项目已有锁文件，使用 `npm ci` 安装对应依赖。

```powershell
Push-Location frontend
npm ci
npm run build
Pop-Location

Push-Location desktop
npm ci
npm test
npm run dist
Pop-Location
```

首页产物写入 `web/showcase/`；桌宠产物写入 `desktop/artifacts/`。重建桌宠后，提交打包器会核对允许的 EXE 大小和 SHA-256；需要先完成构建审查，再更新打包器中的允许值，不能仅因哈希不匹配而跳过检查。

### 常见问题

| 现象 | 排查方式 |
| --- | --- |
| 页面无法打开或接口失败 | 确认 Python 服务仍在运行，查看终端实际端口；使用 HTTP 地址访问，避免直接打开 HTML 文件 |
| PowerShell 阻止脚本运行 | 使用本文展示的 `powershell -NoProfile -ExecutionPolicy Bypass -File ...` 方式运行对应脚本 |
| 提示 `ZoneInfoNotFoundError` | 执行 `.\.venv\Scripts\python.exe -m pip install tzdata==2025.3`，再重启服务 |
| DeepSeek 不可用或显示本地降级 | 核对密钥、模型名、网络、额度、离线设置及同名环境变量；以实际调用和回答模式为准 |
| 风险页提示旧后端或参数无效 | 使用当前项目启动器；先停止它拥有的旧服务再启动，随后刷新页面，不强行复用其他程序的端口 |
| IBKR 返回延迟、缺失报价或权限错误 | 核对 Gateway 登录、API 设置、client ID 和标的权限；保留缺失值，按实际行情类型解读 |
| 本地 LoRA 不可选 | 核对独立环境、已下载基座、训练清单和适配器哈希；参考微调目录说明 |
| 桌宠找不到后端或连错端口 | 为 `start-desktop.ps1` 指定主服务实际使用的 `-Port`，再明确连接目标会话 |

## 数据、使用范围与素材

- 云端模式会把问题和选定上下文发送给 DeepSeek；密钥由服务端读取。不要把 `.env`、账户凭据或私人聊天加入公开仓库、演示投屏及提交包。
- 项目没有用户认证或多人数据隔离，应按本机应用使用，保持回环地址访问。普通数据默认保存在 `data/finpilot.sqlite3`；独立期权启动器使用自己的数据库。
- `/options-demo` 和 `/learn` 的数据为合成输入。历史档案保留原有日期，不能代表当前市场；真实 IBKR 返回数据还须核对权限、字段覆盖和行情类型。
- 成交量不是投资者人数，局部 IV 差和跨式成本不能单独推出涨跌概率、新闻原因或整个市场情绪。项目不提供交易执行或买卖信号。
- 网页语音依赖浏览器能力、权限及设备；识别可能使用浏览器厂商在线服务。浏览器存储不可用时，界面可降级运行，但部分跨刷新偏好无法保留。
- 角色、视频、字体和第三方库分别遵循各自许可。当前角色素材用于课程与个人非商业演示，见 [素材署名与来源](web/companion/licenses/ATTRIBUTION.md)、[角色上游许可](web/companion/licenses/UPSTREAM-ASSET_LICENSE.md) 和 [首页资源记录](web/showcase/asset-provenance.json)。仓库当前未提供统一的项目 LICENSE，不应将第三方素材视为可任意商用。

## 文档与历史版本

| 主题 | 文档 |
| --- | --- |
| 当前期权风险解读、启动、英文短讲稿 | [期权数据分析说明](docs/options_data_demo.md) |
| v17 互动学习与演示 | [技术及功能说明](docs/options_learning_v17.md)、[演示脚本](docs/demo_v17.md) |
| 使用手册与桌宠 | [v16 手册设计](docs/project_help_v16.md)、[v15 桌宠说明](docs/desktop_pet_v15.md)、[桌宠开发](desktop/README.md) |
| 历史复盘、专家检索与依据校验 | [v13 历史复盘](docs/history_rag_v13.md)、[v14 专家检索](docs/innovation_rag_v14.md) |
| 专业期权分析的历史增量 | [v6 采集与指标](docs/options_analysis_v6.md)、[v7 联合分析](docs/options_collective_v7.md)、[v8 易懂解读](docs/options_novice_v8.md)、[v9 到期日](docs/expiry_and_general_chat_v9.md)、[v10 报告追问](docs/options_chat_v10.md)、[v11 刷新](docs/options_refresh_v11.md)、[v12 实际网关](docs/ibkr_gateway_v12.md) |
| 早期架构、设计与本地模型 | [技术文档](docs/technical_documentation.md)、[功能报告](docs/functional_report.md)、[v5 首页](docs/showcase_design_v5.md)、[v5 工作台](docs/workspace_design_v5.md)、[LoRA 实验](finetuning/README.md) |

`output/pdf/` 和 `FinPilot_Demo_EN*.pptx` 保留早期阶段的报告与演示材料，不能视为已经覆盖当前全部功能或最新测试结果。当前展示应结合上表对应功能文档；课程原说明见 [项目要求 PDF](COMP4431_GroupProject2027-1.pdf)，时间安排以教师及 Canvas 通知为准。



### 生成与校验提交包

```powershell
.\.venv\Scripts\python.exe scripts/package_submission.py
.\.venv\Scripts\python.exe scripts/check_package.py
```

输出主包为 **`dist/FinPilot_submission_v17.zip`**，清单为 `dist/submission_manifest_v17.json`，独立解压检查结果为 `dist/package_check_v17.json`。检查使用当前电脑已安装的 Python 依赖，不代表已在完全没有 Python 的电脑上运行通过。

打包器按允许范围收录源码、已审阅知识库、启动脚本、课程说明、构建产物、文档、测试及 LoRA 适配器；排除 `.env`、会话数据库、虚拟环境、已安装 Node 依赖、基座缓存及原始网页下载缓存。系统提示主要位于 `app/service.py`、`app/local_prompt.py` 和各分析模块，随源码提交。

提交前补齐团队信息，核对课程要求的 PPTX 与英文演示，重新生成并验证主包。`dist/` 中较早的 ZIP 和验收记录属于历史产物，修改源码或 README 后需重新打包，避免提交旧副本。
