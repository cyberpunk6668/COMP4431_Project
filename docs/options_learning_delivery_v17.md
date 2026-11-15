# v17 期权学习演示交付说明

本轮完善功能、说明和交互。核心入口是 `/learn`：选择合成教学情景，阅读线索与限制，改变策略及到期价格，查看本地公式结果，再保存并进入聊天。进入聊天只预填问题，点击发送才请求所选引擎；原始参数和旧回答各自保留。

当前服务已通过只读运行检查，可打开 <http://127.0.0.1:8000/learn> 或 <http://127.0.0.1:8000/workspace>。已有 FinPilot 服务时直接使用；需要从项目目录全新启动时运行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

合成情景与本地试算不需要 IBKR 或模型。模型密钥继续仅由后端配置读取，未放入源码包。环境安装和配置见项目 README。

本轮交付使用独立文件名，避免与并行任务的通用打包脚本互相覆盖：

| 文件 | 用途 |
| --- | --- |
| `dist/FinPilot_options_learning_v17.zip` | 已冻结源代码、运行资源、报告和既有 v15 桌宠便携程序 |
| `dist/options_learning_submission_manifest_v17.json` | 压缩包大小、SHA-256、原生程序版本与排除规则 |
| `dist/options_learning_source_manifest_v17.json` | 打包时各源文件的 SHA-256；检查写入字节与稳定源集合一致 |
| `dist/package_check_options_learning_v17.json` | 实际解包后、独立数据库中的离线启动与功能检查 |

重新交付时，在其他代码编辑完成后依次运行：

```powershell
.\.venv\Scripts\python.exe scripts/package_options_learning_v17.py
.\.venv\Scripts\python.exe scripts/check_options_learning_package_v17.py
```

打包器检测并发文件变更时会拒绝发布不一致的包。原始网页下载缓存 `data/news_sources/` 不参与应用运行，并从本轮包中排除；原文件仍保留在工作区。其他任务加入的新闻和网关格式回放实现保持原样，它们的模型调用不计入本轮期权学习验证。

验证证据：

- 本轮应用与测试冻结版本：937 项 Python 测试通过。并行功能加入后的兼容性检查：1006 项通过；对应的 `app/`、`tests/` 和公开 JSON 在检查期间稳定，期间另有一个脚本新增，记录在兼容性报告中。
- 学习页在 320／390／1440 视口各通过 17 项检查；实际应用通过 52 项，含保存追问、错误恢复、计算器、手册、CSV／JSON 导入、旧演示连续追问、主题与语言保留、旧 3D 渲染。
- 63 项有限文字／背景颜色检查通过，最低对比度 5.2306:1。这不是全站 WCAG 认证。
- 最终实际 DeepSeek 连续两问通过，两次生成、零修正；整个开发验证累计 16 次请求、含 7 次修正，旧失败及诊断报告保留。独立编码代理进行了有限阅读式复核，未进行外部人类金融认证。

数值例子均为合成教学输入，不证明当前市场状态、实时行情权限或投资回报。桌宠原生宿主沿用 v15，便携包仍需要项目 Python 环境；本轮未重新认证物理拖动、穿透、真实麦克风或多硬件效果。技术细节、验收范围和可用于 PPT 的截图见 [技术与功能说明](options_learning_v17.md)，演示顺序见 [演示脚本](demo_v17.md)。
