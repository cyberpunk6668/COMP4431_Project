# FinPilot · Four speakers · 3 minutes 30 seconds

状态：用户已确认六页大纲与素材安排，并明确授权跳过后续确认、直接生成整套 PPT 和四人讲稿。

## 制作约束

- 主技能：https://github.com/ningzimu/codex-ppt-skill ，使用其中的“复古扁平插画风”。
- 输出为六页 16:9 图片式 PPTX，整页内容不可作为独立文本框编辑。
- 课程要求英文 presentation，因此幻灯片与正式讲稿使用英文，另附中文理解提示。
- 四位成员分别负责总述、RAG、前端、虚拟形象助手。用 Speaker 1–4 占位，不虚构姓名与学号。
- 210 秒是目标讲述时长，包含简短换页与交接，不含现场 demo 和 Q&A，需排练校准。
- 技术说明以当前代码和已有验收记录为依据。实现机制与验收结果分开，不将 v14 检索指标写成答案准确率，不将 v15 待完成验收写成全部通过。

## 总体节奏

| 页码 | 标题 | 讲述人 | 时段 | 时长 |
|---|---|---|---|---|
| 1 | FinPilot: Financial answers with evidence | Speaker 1 · 总述 | 0:00–0:40 | 40 秒 |
| 2 | RAG connects data with expert knowledge | Speaker 2 · RAG | 0:40–1:15 | 35 秒 |
| 3 | Reliable grounding needs more than retrieval | Speaker 2 · RAG | 1:15–1:40 | 25 秒 |
| 4 | Frontend design keeps complex tasks usable | Speaker 3 · 前端 | 1:40–2:35 | 55 秒 |
| 5 | One companion, on the web and desktop | Speaker 4 · 虚拟形象 | 2:35–3:10 | 35 秒 |
| 6 | Shared conversation, explicit control | Speaker 4 · 虚拟形象与收尾 | 3:10–3:30 | 20 秒 |

四人合计：40 + 60 + 55 + 55 = 210 秒。

## Slide 1 — FinPilot: Financial answers with evidence

- Layout role: cover + project overview，标题与一个金融学习场景插画。
- Domain-specific chatbot for financial education, in English and Chinese.
- Three integrated features: traceable RAG, a usable frontend, and an interactive companion.
- Local calculators handle numeric planning tasks. The model explains concepts and saved reports.
- Positioning: education and report explanation. Avoid trading/prediction claims.
- Visual idea: student、资料、计算工具与助手形成一个简洁的复古扁平场景。无需虚构产品界面。
- Required source images: none.

## Slide 2 — RAG connects data with expert knowledge

- Layout role: architecture/process，一条清楚的证据链。
- Saved analysis supplies local values, timestamps and data limitations.
- Fourteen reviewed expert knowledge blocks supply conceptual explanations.
- BM25 and Chinese character n-grams retrieve separately. RRF combines their rankings.
- The generator receives both local evidence and expert sources. The answer shows their distinct references.
- Visual idea: local report / expert library 两个入口汇入生成与引用结果，插画化的资料页与索引。
- Required source images: none.

## Slide 3 — Reliable grounding needs more than retrieval

- Layout role: challenge / implementation / limit，突出两个关键挑战。
- Challenge 1: bilingual terms and paraphrases. Response: domain normalization and dual-route retrieval.
- Challenge 2: relevant sources may not support a claim. Response: topic-aware paragraph checks and at most one repair.
- Historical values and missing fields remain under local constraints. Missing data does not become zero.
- Limit: rule checks cannot guarantee semantic correctness. No embedding model or vector database is claimed.
- Visual idea: 索引匹配与来源核查的双场景插画，正文保持少量词组。
- Optional small evidence note: held-out retrieval Recall@4 87.04%; 18 relevant + 6 irrelevant questions. This is retrieval evaluation, not answer accuracy. 若影响可读性，仅放讲稿或备注，不强塞幻灯片。
- Required source images: none.

## Slide 4 — Frontend design keeps complex tasks usable

- Layout role: three paired design decisions，内容层级、动画与异步状态各有具体处理。
- Responsive layout: desktop columns become mobile drawers and a collapsible assistant.
- Progressive motion: GSAP / Motion enhance the homepage. A poster fallback keeps entry points visible when video fails.
- Async control: request IDs or cancellation prevent old calculations from replacing newer input. Failed chat preserves drafts.
- Stack note: React / TypeScript / Vite homepage; vanilla JavaScript / CSS workspace. FastAPI serves both.
- Visual idea: 复古插画中的桌面/手机框，配适配、静态回退、请求顺序三处注解。图形是概念示意，不冒充实测截图。
- Required source images: none.

## Slide 5 — One companion, on the web and desktop

- Layout role: character feature / implementation，保留真实项目角色，外围为复古扁平图形。
- Canvas2D renders multi-frame WebP atlases. The browser and Electron reuse the renderer.
- Listening, thinking, speaking and error states follow actual operations.
- Challenge: animation cost. Response: lazy loading, visibility pause and static fallback.
- Challenge: a transparent desktop window. Response: alpha-based hit regions, drag handling and panel placement near screen edges.
- Limit: reused 2D character assets, not a newly built 3D model or phoneme-level lip sync.
- Required image: real project character portrait, strict input; preserve identity, do not invent a replacement character.

  ![Current FinPilot companion portrait](../../../web/companion/assets/portrait.webp)

  Absolute source: F:/桌面/COMP4431_Project/web/companion/assets/portrait.webp

- Character attribution: YunYueSama / 上善无形 / ZipZipPipe · CC BY-NC-SA 4.0. Full provenance in web/companion/licenses/ATTRIBUTION.md.

## Slide 6 — Shared conversation, explicit control

- Layout role: synchronization diagram + concise ending。
- Users explicitly connect one conversation SID.
- SSE notifies clients after persistence. Both clients reload the authoritative saved conversation.
- Generation / sequence checks reject stale responses and help prevent duplicate or wrong-session display.
- Closing: the companion continues the conversation while preserving the same evidence and data limitations.
- Visual idea: web window and desktop window share one conversation record; fresh and stale message envelopes illustrate consistency.
- Required source images: none. 不重复使用角色立绘。
- Notes only: native physical click-through and real cloud end-to-end checks remain limited/incomplete in current v15 records. Do not claim full acceptance.

## 后续交付

1. 六页 PPTX。
2. 每页原始高清图片与整套预览。
3. 四位成员分开的英文演讲稿，配时间、换页点、交接句和中文理解提示。
4. 完整讲稿写入 PPT 备注。
5. 简短技术事实核对与可能的答辩问题，帮助避免误述实现。

## 审阅点

- 六页结构与 40 / 60 / 55 / 55 秒的分工。
- Slide 5 使用当前真实鲸鱼娘立绘，并保留归属。
- 是否授权跳过后续样张等重复确认，按已指定风格直接制作与检查整套。

## 本次真实证据补充

用户要求在现有项目基础上加入真实界面与仓库代码证据。保留六页主讲图片和3分半讲述，新增六页默认隐藏的证据附录，逐一对应主讲第1至6页。素材使用新截图、既存真实验收截图、连续原代码提取和已保存报告。截图原样直接嵌入，不使用AI重绘。精确映射、路径、裁剪和哈希见 evidence_manifest.json。第7至12页分别为主页、RRF检索、引用校验、前端响应式、原生助手/渲染、同步与真实验收。
