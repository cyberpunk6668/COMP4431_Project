# 鲸鱼娘素材归属与修改记录

本项目使用已有社区 Q 版形象，非 DeepSeek 官方产品，不表示获得官方代言。

- 动作图、立绘、多视图与动作采样：**YunYueSama**，项目 https://github.com/YunYueSama/codex-deepseek-pet ，固定版本 `7661c8b304c5400701f91da01b1a643a207331de`。
- 原设「溟月」：**上善无形**，原作者许可声明 https://www.bilibili.com/opus/1231977657712771073 。
- 女仆版设计：**ZipZipPipe**，许可声明 https://www.bilibili.com/opus/1247156596114456581 。
- 原角色采用 **CC BY-NC-SA 4.0**；此版本仅用于课程及个人非商业演示。DeepSeek 名称及标志仍归其权利人。

YunYueSama 对其有权授权的新增贡献使用随附的 `YUNYUESAMA-LICENSE.txt`（自定义署名许可），其完整第三方范围说明见 `UPSTREAM-ASSET_LICENSE.md`。新增贡献的许可不消除底层角色的非商业条件。

FinPilot 修改：从上述固定版本选择动作帧、按原画格坐标重排图集、动画格压缩为 256px WebP、高清待机及静态立绘为 512px WebP。原画身份、衣服和颜色保留，没有重新生成人物；派生图集按底层 CC BY-NC-SA 4.0 条件提供，并同时保留作者新增贡献的署名和许可。每个输入和输出的字节数及 SHA256 见 `../provenance.json`。

现有动作只表示互动或处理状态，不表示金融市场情绪、风险等级或收益保证。朗读时使用既有动作近似表达，不是音素级唇形同步。本轮不包含新的 3D 模型。

Coopanion（https://github.com/Pal-AI-Lab/Coopanion）仅作为桌宠交互设计参考；本目录没有复制其 AGPL 实现或未随代码授权的鲸鱼贴图。应用代码与角色素材分别记录许可，不将整个金融应用代码误标为 CC 素材许可。

构建复现：安装构建依赖 `Pillow==11.3.0` 与 Node.js，然后运行 `python scripts/prepare_companion_assets.py`。运行已交付页面无需 Pillow、Node 或网络下载。原始源文件缓存只位于项目 `tmp/`，不随源码包发布。
