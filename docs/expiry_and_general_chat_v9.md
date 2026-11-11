# FinPilot v9：实际到期日与一般问答

本次修复两个用户可见问题：期权表单允许选择没有对应合约的普通日期；普通问题因没有金融知识库匹配而无法进入模型回答。

## 日期的含义

界面使用「合约到期日」。现有 IBKR 接口提供合约的 expiration，不提供资金到账日或交割完成日；这几种日期不能混用。应用目前支持美股和 ETF 的标准 SMART 期权链。

可选日期来自 IBKR `reqSecDefOptParams` 返回的指定标的合约链，按纽约交易日期保留当天及未来日期、去重并排序。不会推算每周五、每月第三个周五或一般工作日，因此保留真实挂牌的非周五到期日，也能处理交易所实际返回的假期调整日期。[IBKR 官方期权链说明](https://www.interactivebrokers.com/docs/tws-api/doc/contracts/option-chains)

IBKR 的到期日集合和行权价集合独立返回，某个行权价与到期日的组合仍可能不存在。具体合约请求继续使用原来的合约识别和缺失处理，日期有效本身不代表每个合约都有行情或账户已经获得行情权限。当天到期日仍会显示，列表本身不判断盘中是否已停止交易。

## 日期功能与实现

| 环节 | 当前行为 |
| --- | --- |
| 单组选择 | 以实际列表的下拉框替代任意日期输入；空值表示最近可用到期日 |
| 更换标的 | 清除旧标的选择；旧响应不能覆盖新标的的列表 |
| 日期列表 | 从网关读取合约元数据，不订阅标的或期权行情；成功结果在当前页面缓存最多 60 秒，可手动重新读取 |
| 读取失败 | 显示网关错误，不能手填任意日期；可保留自动选择，由后端在分析时查询真实到期日 |
| 批量输入 | 逐个标的检查显式日期；同标的共用一次读取，无效日期阻止表单提交并显示可用日期 |
| 服务端校验 | 单组和批量的每组请求均在任何行情订阅之前按最新链校验；不能通过绕过前端提交不存在的日期 |
| 直接 API 批量请求 | 正确组保留结果，无效组记录错误及可用日期，不终止整批报告 |

新增 `GET /api/options/expirations?symbol=AAPL`，成功响应包含 `source`、`symbol`、`expirations`、`trading_class`、`currency`、`date_kind`、`timezone` 和 `as_of`。`date_kind` 固定为 `expiration`，日期字符串采用 `YYYY-MM-DD`，前端直接显示，避免在浏览器时区转换时产生前后一天偏移。接口响应使用 `Cache-Control: no-store`。

无效日期返回 `ibkr_expiration_unavailable`；单组 API 使用 HTTP 404，错误的 `available_expirations` 提供实际备选值。网关关闭、连接失败、忙碌和链不可用等错误继续区分。元数据和行情采集共享一个连接锁与清理流程，页面按顺序读取列表，避免同客户端 ID 的并发冲突。

主要代码：`app/options_ibkr.py`、`app/options_service.py`、`app/main.py`、`web/options.js`、`web/options.css` 和 `web/index.html`。

## 一般问答功能与实现

普通科学、写作、翻译、编程和生活问题进入用户选择的 DeepSeek 或本地 LoRA。没有匹配金融资料时，使用一般问答提示词正常生成；独立的一般问题不会因为前面讨论过金融而被强行绑定到旧金融资料。真正的简短追问仍可以沿用上一条用户问题的检索上下文。

金融问题继续检索知识库，模型仅在资料相关时引用。界面只展示回答实际引用过的有效来源；一般回答显示实际引擎名称，不显示「+ 检索」或虚构金融来源。输入提示也明确支持一般问题。

原先过宽的关键词拦截已经收窄。例如「应该买什么电脑」「解释内幕交易的定义」「微积分的当前变化率」能够正常进入模型；具体实时价格查询仍明确告知通用聊天没有实时行情上下文，期权行情使用期权分析。确定性计算、密钥过滤和金融交易边界保持原有职责。

模型离线或请求失败时如实说明服务不可用，金融知识摘录及计算器仍可使用。普通问题没有本地资料时不会假装完成模型生成。小型本地 LoRA 可以接收一般问题，但其实际能力受基座和训练范围限制；本次真实云端验证使用默认 DeepSeek。

主要代码：`app/service.py` 和 `web/app.js`。

## 验证与复现

```powershell
.\.venv\Scripts\python.exe -m pytest -q --junitxml=reports/tests_v9.xml
.\.venv\Scripts\python.exe scripts/check_option_expirations_browser_v9.py
.\.venv\Scripts\python.exe scripts/check_option_expirations_live_v9.py
.\.venv\Scripts\python.exe scripts/check_general_chat_v9.py --live
.\.venv\Scripts\python.exe scripts/package_submission.py
.\.venv\Scripts\python.exe scripts/check_package.py
```

浏览器脚本需要本地服务与 Edge。日期界面检查使用受控 API 响应；`--live` 问答检查会发起两次实际 DeepSeek 请求，并只清理自己创建的会话。真实网关检查读取合约元数据，不读取账户资产，也不发起交易或模型请求。

本次服务端回归通过 168 项，涵盖实际链选择、非周五有效日期、无效日期订阅前拒绝、接口规范、批量部分失败、普通问答、上下文跟随、编程下标保留、金融引用与离线状态。报告：`reports/tests_v9.xml`。

实际本地 IB Gateway 返回 AAPL 的 24 个可用到期日；用未列出的 `2026-11-12` 请求分析时，在任何行情订阅前返回不可用到期日错误，返回列表与查询结果一致。报告：`reports/expirations_gateway_v9.json`。这是检查时点的真实结果，挂牌列表随时间变化。

Edge 的受控响应界面检查在 320、390、1440 像素视口通过 19 类检查，覆盖完整 40 项列表、非周五日期、没有任意日期输入、失败和空链、批量错误阻断、60 秒缓存失效、旧标的竞态、顺序读取，以及易懂／专业报告切换。报告：`reports/options_expirations_browser_v9.json`。

桌面 1440 和移动 390 视口还分别通过真实 HTTP 从网关读取 AAPL 日期，两次各返回 24 项，与下拉框逐项一致。两端都验证了选择、自动项和关闭重开，没有页面错误或横向溢出，没有发起分析、行情或 LLM 请求。报告：`reports/options_expirations_live_v9.json`。

实际 DeepSeek 一般问答在桌面 1440 中文和移动 390 英文各通过一次。中文问题正确回答「太阳系最大的行星是木星」；英文请求返回正常的请假邮件。两端均为实际 `deepseek` 模式，没有服务警告或金融来源卡片，输入框恢复可用，刷新后回答与模式保留，未重复调用模型，没有页面错误或横向溢出。两个测试会话已清理，原有用户会话未修改。报告：`reports/general_chat_live_v9.json`；受控回答的界面回归另见 `reports/general_chat_fixture_v9.json`。

移动检查使用桌面 Edge 的响应式视口及触摸仿真，不代表所有手机硬件的验证；两次正常问答也不是通用知识准确率基准。最终提交包及隔离启动检查位于 `dist/FinPilot_submission_v9.zip` 和 `dist/package_check_v9.json`。提交包排除本地密钥、数据库和运行日志。
