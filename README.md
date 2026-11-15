# FinPilot v17 · 看懂期权，再带着依据追问

新增独立的 **期权数据 → chatbot 分析演示**：双击根目录 `start-options-demo.cmd`，或打开运行服务的 `/options-demo`。选择分析引擎后点击「一键演示」，读取六份合成合约、计算指标并解释；「播放下一帧」展示同一样本的变化与报价缺失。配置可用时可真实调用 DeepSeek，离线模式明确显示为本地规则解释。页面始终标注「模拟网关回放 · 非实时行情」，不连接 IBKR、不写入已有聊天。完整操作、三分钟讲稿和故障处理见 [期权数据演示说明](docs/options_data_demo.md)。

先打开 [期权互动学习](http://127.0.0.1:8000/learn)：选择“看跌成交更集中”“价差与入场成本”“下方保护定价”教学情景，先读白话线索，再查看依据和不能推出的结论。无需 IBKR 权限；全部报价、IV、持仓和日期都是明确标注的合成输入，不能用来判断当前市场。

在同页切换买入看涨、买入看跌或看涨借记价差，改变行权价、合约份数、到期标的价和成交假设，立即查看本地计算的到期盈亏曲线、初始成本、盈亏平衡和最大损失。例如默认买入看涨试算支付总额 360 USD，假设到期标的价为 102 USD 时净亏损 160 USD；标的上涨也可能尚未覆盖权利金。图表不提供概率，不计算提前平仓价值，不含费用和实际行权/指派过程。

点击“带着这份演示追问”会保存当前参数并建立专属会话、预填问题；**需要自己点击发送才请求所选模型**。AI 读取已保存试算及本地证据，回复保留合成来源、教学日期、参数与 OIC 知识依据；改变试算不会改写旧报告或旧回答。离线或模型校验失败时提供清楚标注的本地解释，不把降级伪装成模型成功。项目手册新增互动学习教程，问“FinPilot 的期权互动演示怎么用？”即可获取入口、步骤和限制。

首页与工作台以浅白、藏青和低调金色统一入口；工作台先展示学习、精确计算、功能指南三项任务，专业网关采集与历史复盘继续保留。网页形象沿用按上游许可署名的 2D 鲸鱼娘，旧机器人作为明确标注的展示选项。见 [v17 技术与功能说明](docs/options_learning_v17.md) 和 [演示脚本](docs/demo_v17.md)。本轮完善功能、说明与交互，不引入收费或交易执行。

## v16 历史增量：项目使用指南

v16 让助手回答“我们项目的功能怎么用”。在工作台点击「使用指南」，或直接问“期权分析怎么用”“在哪里切换模型”“如何连接桌宠”；也可打开 <http://127.0.0.1:8000/help> 搜索 16 个双语手册主题。回复提供真实入口、步骤、限制、手册版本与实现依据。手册搜索不调用模型或 IBKR；聊天中的所选模型只辅助匹配已审阅的主题，操作文字由本地手册提供，模型不能新增按钮、网址或能力。

教程使用独立的 `project-help` 模式；离线或模型匹配失败仍可阅读手册，实际市场追问和一般问题保持原有路径。即使会话已绑定期权报告，询问操作方法也不会清除绑定、改写旧分析或采集新行情。桌宠内可阅读同一手册，`/demo` 保持独立会话。见 [v16 技术与验证说明](docs/project_help_v16.md)。

## v15 历史增量：鲸鱼娘桌宠与可追溯金融问答
## 虚拟形象元素添加

COMP4431 Artificial Intelligence (2026/27) 课程项目。提供中英双语金融教育问答、可追溯知识检索、DeepSeek 接入、精确财务计算、会话持久化与 JSON 导出，以及依浏览器能力启用的语音输入/朗读。

v15 新增 **Windows 2D 鲸鱼娘桌宠＋网页同款形象＋明确选定会话的共享金融问答**。采用现成角色动作，运行图像约 1.09 MiB；新角色只为 2D，旧机器人 2D/3D 保留。桌宠使用现有金融后端，回复继续保留数据日期、本地证据、专家来源和真实模式；单击互动、连接和同步不会自动调用模型或 IBKR。`/demo` 保持独立会话，不自动加入共享。

启动桌宠：`powershell -NoProfile -ExecutionPolicy Bypass -File .\start-desktop.ps1`。**便携 EXE 仍需要项目 Python 环境和后端，不是无需 Python 的自包含程序。** 本轮仅用于课程与个人非商业演示，角色素材许可单独保留，见 [素材归属](web/companion/licenses/ATTRIBUTION.md)。

详见 [v15 技术与功能报告](docs/desktop_pet_v15.md) 和 [v15 演示脚本](docs/demo_v15.md)。最终服务端 717 项通过；工作台与打包 Electron 渲染器的真实 DeepSeek 两轮通过，共三次生成含一次修正，零新增 IB 请求。原生报告为 `passed_with_manual_hardware_limits`：九项进程 instrumentation 通过，物理拖动、托盘、精确 alpha 命中及多硬件效果仍未认证。完整提交包打出后，以独立 `dist/package_check_v15.json` 的实际结果为准。下面的 v14 及更早记录保留为历史阶段。

收尾时已用启动脚本打开连接 8000 的可见桌宠；最后的 UIA 检查被用户按 Esc 中断，不计作最终人工检查通过。

v14 将专家知识库接入历史复盘与原有快照聊天，并增加独立的三步演示页。14 条 OCC/OIC、Cboe、IBKR 知识块使用 BM25、中文字符 n-gram 与 RRF 检索；针对问题和数据局限补充经过审阅的知识主题。回复分开标注本地数据与专家来源，按段检查已识别的知识主张是否有支持。该检查是有限规则，不是通用语义蕴含验证，也不保证所有回答正确。没有新增 embeddings、向量数据库或 DeepSeek 微调。

**演示入口**：[三步创新演示](http://127.0.0.1:8000/demo)：加载真实历史档案 → 检索专家依据 → 明确点击 AI 解释及连续追问。沿用浅白、藏青与低调金色风格，并复用真实 2D/3D Avatar、模型切换与状态动画。加载档案不会连接 IBKR；发送聊天才请求所选引擎。完整历史工作台仍在 <http://127.0.0.1:8000/workspace?view=history>。见 [v14 技术与功能报告](docs/innovation_rag_v14.md) 和 [演示脚本](docs/demo_v14.md)。

档案来自先前真实网关返回的 AAPL 2026-11-06、09、10 股票与选定 C/P 合约的成交 bars，不能代表当前市场。小时 bars 的时段覆盖未核验完整，成交量变化不满足比较条件；历史 OI 与双边报价保持缺失，不会补造。v13 原始报告与失败验证记录保留用于审计。

v12 修复真实 IBKR 数据采集中漏处理收盘字段和等待窗口过短的问题。网关返回的收盘参考价、最新成交和双边报价分别记录；界面区分实时订阅限制、已收到的延迟资料及缺失字段，不将收盘价当作可成交报价。真实 Edge 页面已完成两次网关采集、聊天刷新和继续追问，两条 DeepSeek 回答均成功。结果为有限数据通过：实际返回延迟资料、双边报价仍为 0/6，实时请求存在订阅限制。真实链路验收与限制见 [v12 技术与功能报告](docs/ibkr_gateway_v12.md)。

复现可用链路：期权分析中显式选择「延迟」建立报告，再点击「针对这批数据追问」，聊天内使用「刷新并解释变化」。刷新会保留原请求模式，不会把实时模式的旧报告悄悄降级成延迟模式。

v11 在聊天快照卡加入「刷新并解释变化」。一次点击重新采集服务器保存的范围，用当前所选模型解释前后变化，保留旧报告与旧回复。前后比较先核验合约、实际行情类型、请求及有效配对范围；不能比较的字段显示原因，缺失值不当作零。聊天内可以展开分析记录回看各版本。功能、技术与验证报告见 `docs/options_refresh_v11.md`。

v10 打通期权报告与聊天：分析后可点击「针对这批数据追问」，开启绑定该快照的专属会话。AI 读取服务器保存的汇总指标与质量信息，用白话解释当前样本；每条回复保留采集时间、实际行情类型、作用范围及可展开的本地数值依据。旧批次不会随新报告变化，追问不自动刷新行情，普通问答和计算器继续可用。功能、技术与验证报告见 `docs/options_chat_v10.md`。

v9 的期权日期从 IBKR 所选标的的实际合约链读取，下拉框仅列出可用到期日，后端在订阅行情前再次校验。批量分析也校验每组日期并保留直接 API 调用中的部分失败。普通科学、写作、编程和生活问题可使用所选模型正常回答，无关的金融参考资料不会作为答案来源展示。实现与验收记录见 `docs/expiry_and_general_chat_v9.md`。

v8 默认以「易懂解读」呈现期权分析，先解释所选样本的数据新旧、哪类合约交易更多、分布是否集中以及线索是否一致。每百份合约的比例图使用实际有效样本计算，并保留缺失和零值的区别。术语说明与专业详情可按需展开，基础解读在本地完成。设计、规则与验证记录见 `docs/options_novice_v8.md`。

v7 将期权功能扩展为实质性的联合分析。每批报告联合解释流动性、行权价成交与持仓集中度、共同样本结构差、IV 形状及支持和冲突的证据。联合模式支持最多四组标的或到期日，保留部分失败并对符合条件的同标的期限 IV 进行比较。现有 DeepSeek 可以生成带证据引用的综合摘要、主要发现、条件情景和局限。模型文本经过结构、引用和数值格式验证，定量值从本地证据读取。使用方法和实测结果见 `docs/options_collective_v7.md`。

v6 在 `/workspace?view=options` 加入 IB Gateway 只读期权分析。支持按到期日批量采集美股与 ETF 期权，区分实际行情类型与覆盖范围，计算成交量比、未平仓量比、约 25Δ IV 差和平值跨式权利金占比。样本通过实时质量检查后，可按需将聚合指标交给现有 DeepSeek API 排序解读。配置、指标和实测结果见 `docs/options_analysis_v6.md`。

v5 以 Coinwise 为视觉参考，采用浅灰白、藏青与低调金色渐变。首页 `/` 使用指定的 6 秒背景视频、视频就绪后启动的 GSAP 入场和 Motion 移动导航。`/workspace` 默认浅色，用户仍可切换主题。设计与验证见 `docs/showcase_design_v5.md` 和 `docs/workspace_design_v5.md`。

v4 将 `/workspace` 实际工作台与首页统一为黑金视觉：聊天、计算器、Avatar 和引擎选择使用同一套金色、石墨色与状态反馈。提供全局暂停动效，尊重系统减少动态设置，保留象牙金浅色模式。交互使用短时 Web Animations API 与 CSS 过渡，消息和数字直接显示；模型切换明确作用于下一条问题。计算器隔离过期请求，聊天请求期间锁定会话、语言和引擎选择；移动导航支持焦点约束与 Escape 关闭。设计、功能与验证范围见 `docs/workspace_design_v4.md`。

v3 增加 React 19 / Tailwind CSS 4 黑金动效首页，使用 GSAP ScrollTrigger、Motion 与原创 Three.js 信号雕塑展示项目功能。首页为 `/`，原有完整工作台保留在 `/workspace`。页面中的知识来源与复利计算使用实际后端，不会自动调用付费模型。设计与动效实现记录见 `docs/showcase_design.md`；既有 PDF 和 v2 PPTX 保留为上一阶段核心功能的说明。

v2 增加原创 2D/3D Avatar、明暗主题、来源展开与本地 Qwen3-0.6B LoRA 实验引擎。DeepSeek 仍是默认云端引擎；本地适配器是否可用由真实训练清单和权重哈希决定。这里的 LoRA 不是对托管 DeepSeek 模型微调，RAG 和提示词也不称为微调。

## 团队信息（提交前必须填写）

| 成员 | 英文姓名 | 学号 | 负责工作 |
| --- | --- | --- | --- |
| 1 | 待填写 | 待填写 | 待团队确认 |
| 2 | 待填写 | 待填写 | 待团队确认 |
| 3（如适用） | 待填写 | 待填写 | 待团队确认 |
| 4（如适用） | 待填写 | 待填写 | 待团队确认 |

课程要求团队 2-4 人。不要将未参与者或虚构身份填入本表。

## 启动

运行环境：Python 3.11 或以上。以下为 Windows PowerShell 命令，在项目根目录执行；无需激活虚拟环境。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item .env.example .env }
```

用文本编辑器打开 `.env`，在 `DEEPSEEK_API_KEY` 填入自己的密钥。`DEEPSEEK_MODEL` 默认 `deepseek-flash`，可根据官方接口与账户权限调整。Tracking ID 不是 API Key。不要将 `.env` 发给他人或加入源码压缩包。没有可用密钥时仍可运行离线模式。

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

在浏览器打开 <http://127.0.0.1:8000>；本地接口文档与请求测试页为 <http://127.0.0.1:8000/docs>，机器可读契约为 `/openapi.json`。如端口被占用，可改用 `--port 8001`。不要用文件方式直接打开 `web/index.html`，前端需要后端接口。

## 验证

v15 证据分层记录于 `docs/desktop_pet_v15.md`：renderer 17 项；工作台/演示页 24 项 × 三视口；桌宠页面 15 项 × 三视口；跨独立 Edge 配置档的真实 SSE/持久化 12 项（提供者输出受控）；构建与宿主契约 4 项；最终服务端 717 项。实际两端 DeepSeek 问答是另一份独立验收，共两轮、三次生成及一次修正。原生九项 instrumentation 含模拟操作，不认证真实鼠标穿透、物理拖动/托盘、多屏或真手机。失败和狭窄来源/否定修正的审计均保留，330 项定向检查也不是金融判断准确率，见 [完整 v15 验收索引](reports/companion_acceptance_v15.json)。

v14 检索评估区分开发集与冻结算法后的 24 问保留集。保留集相关问题 Recall@4 为 0.870370，全部所需来源命中 15/18；无关问题正确拒绝 4/6，仍有误召回。这些是小样本检索指标，不是答案准确率或预测成功率。独立演示页 27 项受控检查在 320、390、1440 三种视口通过；真实模型链路及最终交付结果以 `docs/innovation_rag_v14.md` 和对应报告为准。

最终服务端 649 项测试通过。实际 Edge `/demo` 完成两轮 DeepSeek 连续追问，共四次生成含两次引用修正；原快照 RAG 一轮共两次生成含一次修正。均为已保存真实历史资料的有限数据验收，零新增 IB 请求。失败与首答引用问题保留在 `reports/innovation_acceptance_v14.json`，不宣称模型每次首答正确。

v13 验收：527 项服务端测试通过；历史界面 23 项检查在三种视口通过；生产历史采集及两轮真实 DeepSeek 追问通过有限数据验收。历史时段覆盖、缺失字段及逐句引用精度局限见 `docs/history_rag_v13.md`。

v12 阶段验收：377 项服务端测试通过；诊断界面 17 项检查在三种视口通过；真实 Edge 中两次网关采集与两条 DeepSeek 回复通过有限数据验收。完整实时报价尚未取得，边界和实际前后数据见 `docs/ibkr_gateway_v12.md`。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q --junitxml=reports/tests_v14.xml
.\.venv\Scripts\python.exe scripts/evaluate.py
.\.venv\Scripts\python.exe scripts/check_guided_demo_browser_v14.py
```

v3 阶段为 58 项服务端测试和 24 项实际浏览器展示页检查通过；对应 `reports/tests_v3.xml` 与 `reports/showcase_check.json`。浏览器检查覆盖六种屏宽、暂停/减少动态、3D 与资源失败降级、真实计算以及工作台功能深链，不代表获奖、第三方无障碍认证或所有设备的帧率保证。

v4 工作台可重复验证命令：`.\.venv\Scripts\python.exe scripts/check_workspace_v4.py`；`--skip-live-chat` 可跳过两次实际云端问答以避免 API 费用。浏览器与截图结果保存在 `reports/workspace_check_v4.json` 和 `reports/screenshots/workspace-v4/`。语音事件测试使用受控模拟；实际麦克风、扬声器与移动设备硬件仍取决于浏览器权限和设备。

v5 界面验证可运行 `scripts/check_showcase_v5.py` 和 `scripts/check_workspace_v4.py --theme light`。两套检查连接本地服务，不发起真实模型请求。

v4 历史验收（2026-11-10）：

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 服务端回归 | 58 项通过 | `reports/tests_v4.xml` |
| 黑金工作台 | 33 项通过，12 个中英布局案例，含两次真实 DeepSeek 回答 | `reports/workspace_check_v4.json` |
| 首页回归 | 24 项通过 | `reports/showcase_check_v4.json` |
| Avatar 独立渲染与生命周期 | 12 项通过 | `reports/avatar_gold_check_v4.json` |
| 本地 LoRA 实际工作台集成 | 6 项通过，实际生成、切回云端、保留旧回答模式 | `reports/browser_local_check_v4.json` |

以上浏览器检查使用一台 Windows 的 Edge；移动验收包含响应式视口与触摸仿真，不等同于真实手机硬件验收。本地推理可使用 `.\.venv\Scripts\python.exe scripts/check_browser_local_v4.py` 单独复现，需要训练产物和已缓存的基座；不会发起 DeepSeek 请求。

## 重建动效首页

提交包内已包含 `web/showcase/` 编译产物，只运行 Python 后端即可查看。修改 React 源码时需要 Node.js 22.12 以上（本机使用 24.12），然后执行：

```powershell
Set-Location frontend
npm ci
npm run build
Set-Location ..
```

开发依赖由 `frontend/package-lock.json` 固定。字体、视频和库均以本地资源提供，来源记录及许可位于 `frontend/public/`。资源加载失败时保留静态文字与工作台入口；3D 不可用时回退为 SVG。页面有暂停动效按钮，也遵循系统减少动画设置。

完整浏览器验收（需要已安装 `requirements-ui-tests.txt` 并运行本地服务）：

```powershell
.\.venv\Scripts\python.exe scripts/check_showcase.py
```

固定检索测试集在 `evaluation/cases.json`，评估报告写入 `reports/evaluation.json`。检索指标不是完整问答正确率。真实云端调用与浏览器验收记录见功能报告和 `reports/`。健康接口中的配置状态不能替代实际 API 请求。

v1 基线验证：45 项服务端自动化测试、48 个固定检索验收案例、13 个浏览器交互检查通过；原始证据保存在 `reports/v1_baseline/`。v2 的最新自动化、Avatar、浏览器和微调对比结果分别记录在 `reports/tests_v2.xml`、`reports/avatar_check.json`、`reports/browser_check_v2.json` 与 `reports/finetuning_*.json`。初次生成中发现的 APY 解释错误及修正记录在功能报告与 `reports/rate_regression.json`；因此不能把路径通过率解读为答案完全正确。

如需重新验证真实服务，以下命令会调用 DeepSeek 并按账户规则消耗额度：

```powershell
.\.venv\Scripts\python.exe scripts/check_provider.py
.\.venv\Scripts\python.exe scripts/check_app.py
```

将 `.env` 中的 `FINPILOT_OFFLINE=true` 可强制离线；`DEEPSEEK_TIMEOUT` 为请求超时秒数，默认 45。可用 `FINPILOT_DB` 指定本地数据库路径。变更配置后需重启服务。

## 功能与操作

- 在聊天页选择语言，输入金融问题或使用示例问题；查看回答模式和官方来源。
- 在计算器中进行月复利/定期投入、固定利率等额本息贷款、月度预算计算，核对公式和假设。
- 新建或恢复会话；需要学习记录时导出 JSON；不需要的会话可以删除。
- 浏览器支持且授权时使用语音输入和朗读。语音识别可能依赖浏览器厂商在线服务。
- 离线模式从本地知识库组织回答，不会伪装成成功调用 DeepSeek。

## v2 新功能

- 右侧金融教练由真实 Three.js WebGL2 网格渲染，支持 2D SVG 切换和不支持 WebGL2 时的降级。
- 聆听、思考、朗读和错误状态与实际操作联动；嘴部动作是近似动画，不是精准音素同步。
- 明暗主题、减少动画偏好、可折叠移动助手面板和可展开来源摘要改善阅读与控制。
- 回答采用有限 Markdown 的安全 DOM 渲染，来源编号可直接核对；原始模型 HTML 不执行。
- 模型选择器可切换 DeepSeek 与本地 LoRA 实验引擎；未训练、缺少缓存或推理失败时明确回退到本地知识摘录。

Avatar 独立验收不调用 LLM，也不需要 API Key：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ui-tests.txt
.\.venv\Scripts\python.exe scripts/check_avatar.py
```

## 可选本地 LoRA 环境

主应用无需安装 PyTorch。需要本地实验引擎时，按 `finetuning/README.md` 创建独立 `.venv-ml`，安装固定依赖并显式下载公开基座模型。普通聊天只读取已下载缓存，不自动下载大模型。下载与训练需要额外磁盘空间和时间；训练脚本要求 NVIDIA CUDA GPU。

```powershell
.\.venv-ml\Scripts\python.exe scripts/download_model.py
.\.venv-ml\Scripts\python.exe scripts/train_lora.py
.\.venv-ml\Scripts\python.exe scripts/evaluate_lora.py
```

训练/下载脚本从当前 shell 环境读取缓存路径；若自定义缓存，请先设置 PowerShell 的 `$env:FINPILOT_HF_HOME`，并让后端 `.env` 的同名配置指向同一目录。只修改 `.env` 不会自动改变独立训练脚本的环境。使用 `.env.example` 中的 `FINPILOT_ML_PYTHON`、`FINPILOT_ADAPTER` 和可选 `FINPILOT_HF_HOME` 配置路径后重启后端。不要用主应用的 `.venv` 直接执行训练脚本。适配器与基座是两类文件：提交包中的小型适配器不能替代单独下载的基座权重。

本轮已实际完成 Qwen3-0.6B LoRA：3 轮、108 次优化器更新，适配器约 9.20MB；训练环节约 181.51 秒（不包括环境和下载）。训练与最终对照成绩分别读取 `reports/finetuning_training.json` 与 `reports/finetuning_evaluation.json`。低损失和格式指标不等于金融事实准确率，不能据此声称超过 DeepSeek。 本地应用接口也已真实验证：2 条中英生成和 1 条工具路径通过，见 `reports/local_integration.json`。本次冷/热进程示例分别约 15.06/10.71 秒，属于小模型实验而非低延迟保证。

## 项目结构

```text
app/                  FastAPI 服务、配置、计算、检索与会话存储
data/knowledge.json   人工整理的双语金融知识与来源
web/                  无外部 CDN 的 HTML / CSS / JavaScript 前端
frontend/             React 动效首页源码及固定的构建依赖
tests/                自动化验证
evaluation/cases.json 固定检索问题集
scripts/              评估与报告构建工具
reports/              实际验证输出
docs/                 可编辑技术文档、功能报告、英文演示稿
finetuning/           主题分组数据、训练配置与复现说明
models/finpilot-lora/  本地 LoRA 适配器与训练清单（如已训练）
output/pdf/           v2 排版后的 PDF 报告
```

## 文档

- `docs/technical_documentation.md`：架构、数据流、接口、算法、配置、安全边界与局限。
- `docs/functional_report.md`：功能、验收场景、实际验证结果与课程要求对应。
- `docs/demo_script_en.md`：7 分钟英文演示流程与问答准备。
- `output/pdf/`：可提交和打印的技术文档与功能报告。
- `docs/innovation_upgrade.md`：新增三项功能的技术选择与事实边界。
- `docs/demo_upgrade_en.md`：针对 Avatar、LoRA 与现代 UI 的英文演示稿。
- `output/presentations/FinPilot_Demo_EN_v2.pptx`：新版三项附加功能的英文演示稿。
- `output/presentations/FinPilot_Demo_EN.pptx`：保留的 v1 基础版 8 页演示稿；其中测试数字是历史基线，不能当作 v2 最终结果。

重建 PDF 需要额外安装 `reportlab`，然后执行 `python scripts/build_reports.py`。默认使用 Windows 宋体和黑体；其他系统可用 `FINPILOT_REPORT_FONT` 指定包含中文的 TrueType 字体。PDF 工具不属于应用启动依赖。

## 数据与密钥

在云端模式下，问题和选取的上下文会发送给 DeepSeek。会话保存在本机数据库；本项目没有用户认证或多人数据隔离，应在本机使用，不输入真实账户凭据或敏感金融资料。密钥仅由服务端读取。若密钥曾出现在聊天记录或公开位置，建议轮换。

普通聊天提供教育解释和假设计算。期权分析独立读取本地 IB Gateway，并显示其实际返回的行情类型。情绪线索仅描述该批次的相对成交活跃度及定价，不能推出交易方向。具体法规与保障制度需核对适用地区和官方最新资料。

## 提交核对

填写本 README 的团队信息；打包源码、提示词、知识库、测试和文档；排除 `.env`、`.venv`、缓存与含个人信息的数据库。课程还要求 PPTX 与英文现场演示。原说明内日期星期标注有差异，以 Canvas 与教师通知为准。

```powershell
.\.venv\Scripts\python.exe scripts/package_submission.py
```

该脚本按允许列表生成 `dist/FinPilot_submission_v8.zip`，内含期权易懂解读、联合分析、首页源码、构建产物、视频、验收文档与实际训练的 LoRA 适配器。密钥、会话数据库、虚拟环境和基座缓存均排除。系统提示保存在 `app/service.py` 和 `app/local_prompt.py`，知识库随源码一同提交。

# COMP4431_Project

