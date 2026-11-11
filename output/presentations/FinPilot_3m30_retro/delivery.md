# FinPilot presentation delivery

六页英文 16:9 演示文稿，采用指定 GitHub 技能的复古扁平插画风。四人总目标 3 分 30 秒，英文讲稿 383 词；具体时长需按团队语速排练。此段不包含课程要求的 live demo 和 Q&A。

## 使用文件

- `FinPilot_3m30_retro.pptx`：六页正式演示文稿，每页含相应英文演讲者备注。
- `speaker_guide.md`：合并讲稿、中文理解提示、分工、换页、发音及答辩准备。
- `speaker_1.md` 至 `speaker_4.md`：每人独立讲稿。
- `speech.md`：六页英文口述正文，与 PPT 备注一致。
- `preview.png`：整套视觉预览。
- `origin_image/`：六页原始 PNG。
- `source_audit.md`：技术事实及验收边界。
- `character_licenses/`：保留角色归属、原始许可和衍生条件。

## 分工

| Speaker | 内容 | 页码 | 时间 |
|---|---|---|---|
| 1 | 总述 | 1 | 40 秒 |
| 2 | RAG 技术集成与挑战 | 2–3 | 60 秒 |
| 3 | 前端设计与挑战 | 4 | 55 秒 |
| 4 | 虚拟助手实现、跨端同步与收尾 | 5–6 | 55 秒 |

Speaker 编号可由团队自行对应成员，不虚构姓名、学号或开发分工。

## 生成与检查记录

主技能：[ningzimu/codex-ppt-skill](https://github.com/ningzimu/codex-ppt-skill)，固定读取版本 `941dcafe2f23ea4ae61de99e9b22fb0ef3d9e06c`。

- 图片后端：内置 `image_gen`。没有切换 API/CLI，没有用本地绘图或文字叠加制作正式页面。
- 第 2 页为内部风格基准；用户明确授权跳过后续确认，因此不再等待样张批准。
- 其余五页分别由单页子代理生成，均用技能原生 `record_slide_result.py` 记录。`slide_jobs.json` 中五页为 recorded，第 2 页为 accepted。
- 第 6 页通过同一内置图片工具编辑连接方向，明确网页和桌面都能继续会话。
- 使用技能原生 `assemble_ppt.py` 组装，六页英文讲稿写入备注。
- 已逐页查看图片、核对文字与架构、检查 PPTX 包结构、全幅图片几何和备注一致性。详细结构报告在 `validation.json` 及 `build/`。
- 没有声称已在 PowerPoint 原生应用中打开，没有新增金融模型或 IBKR 调用。

## 制作源文件位置

项目目录：`F:/桌面/COMP4431_Project/output/presentations/FinPilot_3m30_retro/`

PPT：`F:/桌面/COMP4431_Project/output/presentations/FinPilot_3m30_retro/FinPilot_3m30_retro.pptx`

幻灯片图片：`F:/桌面/COMP4431_Project/output/presentations/FinPilot_3m30_retro/origin_image/`

大纲：`F:/桌面/COMP4431_Project/output/presentations/FinPilot_3m30_retro/outline.md`

演讲正文：`F:/桌面/COMP4431_Project/output/presentations/FinPilot_3m30_retro/speech.md`

生成状态：`F:/桌面/COMP4431_Project/output/presentations/FinPilot_3m30_retro/slide_jobs.json`

## 实际使用限制

这是整页图片式 PPT，页内文本与插画不能作为独立对象编辑。文字需要修改时应修改对应提示词，重新生成该页再组装。备注可以在 PowerPoint 中正常编辑。

RAG 的规则校验不保证回答正确；检索指标不等于答案准确率。当前 v15 原生物理交互和真实云端跨端链路仍有未完整验收的部分，演示内容聚焦已实现机制，不宣称全部验收成功。

第 5 页使用项目已有 2D 角色，保留 YunYueSama、上善无形、ZipZipPipe 归属与许可。作品用于本次课程演示，完整素材条件见随包许可。
