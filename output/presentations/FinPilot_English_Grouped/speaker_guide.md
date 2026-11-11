# FinPilot · 四人讲稿与连续页序

所有幻灯片及展示内容使用英语。中文提示只用于排练，不在 PPT 页面展示。13 页全部可见，概念页和证据页按主题放在一起。目标总长 3 分 30 秒，时间为编排估计，需排练校准。代码只指关键判断，不逐行朗读。

| 成员 | 页码 | 内容 | 目标时长 |
|---|---|---|---|
| Speaker 1 | 1-2 | 总述与真实英文界面 | 40 秒 |
| Speaker 2 | 3-6 | RAG 集成、检索与引用约束 | 60 秒 |
| Speaker 3 | 7-9 | 前端、响应式及视频回退 | 55 秒 |
| Speaker 4 | 10-13 | 形象、渲染、同步与验收 | 55 秒 |

## Slide 1: FinPilot

时间：0:00-0:20，目标 20 秒。

### English script

Hello everyone. Our project is FinPilot, a bilingual chatbot for financial education. We focused on three connected features: RAG for traceable explanations, a clear frontend, and an interactive companion on the web and desktop.

### 中文指图与换页提示

介绍项目定位和三个技术重点。

## Slide 2: The actual English workspace

时间：0:20-0:40，目标 20 秒。

### English script

This is the actual English workspace. Users can learn financial concepts, run planning calculations, and use browser-supported voice. Local functions handle the numbers, while the language model explains the results. Let us start with the RAG pipeline.

### 中文指图与换页提示

指向真实英文工作台，概括学习、计算和语音；交给第二位。

## Slide 3: RAG connects data with expert knowledge

时间：0:40-1:00，目标 20 秒。

### English script

Our RAG pipeline combines local evidence with reviewed expert knowledge. Saved analyses provide values, timestamps, and data limitations. Fourteen expert knowledge blocks explain financial concepts. The answer keeps local references separate from expert citations.

### 中文指图与换页提示

按本地数据、专家知识、带来源回答的顺序讲。

## Slide 4: Two routes, one ranking

时间：1:00-1:16，目标 16 秒。

### English script

We use BM25 and Chinese character n-grams, then combine their rankings with RRF. The colored code shows this step. The small held-out evaluation measures retrieval, rather than answer accuracy.

### 中文指图与换页提示

指出蓝紫色排名融合代码与指标边界，不读完整公式。

## Slide 5: Reliable grounding needs more than retrieval

时间：1:16-1:28，目标 12 秒。

### English script

Two challenges are bilingual wording and unsupported claims. Domain aliases improve matching. Topic-aware citation checks reject sources that fail to support a recognized claim.

### 中文指图与换页提示

概括两个挑战及对应处理，接着切具体证据。

## Slide 6: Missing values remain unavailable

时间：1:28-1:40，目标 12 秒。

### English script

Here, missing open interest remains null. It never becomes zero. We allow one repair, but these checks cannot guarantee correctness. Next is the frontend.

### 中文指图与换页提示

指真实报告中的 null 和右侧校验，保留正确性边界；交给第三位。

## Slide 7: Frontend design keeps complex tasks usable

时间：1:40-1:56，目标 16 秒。

### English script

Our React homepage introduces the product, while the JavaScript workspace handles real tasks. We designed the interface around readable information, resilient motion, and safe asynchronous updates.

### 中文指图与换页提示

准确区分 React 首页和原生 JavaScript 工作台。

## Slide 8: Real English views, responsive controls

时间：1:56-2:15，目标 19 秒。

### English script

These are actual English calculator forms. On narrow screens, headings and controls adapt to the available space. Request IDs prevent old calculation responses from replacing newer input.

### 中文指图与换页提示

对照两个表单，再指代码中请求序号的比较。

## Slide 9: Motion with a safe fallback

时间：2:15-2:35，目标 20 秒。

### English script

Animations also need a reliable fallback. This code keeps a poster behind the video and falls back after two point five seconds. Users can reduce motion. These choices keep the interface usable. Next, we explain our companion.

### 中文指图与换页提示

分别指超时和常驻海报两段代码，说明减少动态；交给第四位。

## Slide 10: One companion, on the web and desktop

时间：2:35-2:49，目标 14 秒。

### English script

Our companion uses Canvas2D and WebP atlases. Its states follow user actions. Transparent windows need alpha-based hit regions, dragging, and panel placement.

### 中文指图与换页提示

概括图集、操作状态和透明窗口交互挑战。

## Slide 11: One shared 2D renderer

时间：2:49-3:04，目标 15 秒。

### English script

The English browser companion and Electron app share this renderer. Frame bounds, lazy loading, visibility pause, and static fallback manage animation cost.

### 中文指图与换页提示

明确截图来自浏览器，Electron 共用渲染器；指 drawImage 与帧坐标。

## Slide 12: Shared conversation, explicit control

时间：3:04-3:16，目标 12 秒。

### English script

Users explicitly select a conversation. The server saves messages, sends an SSE notification, and clients reload the record.

### 中文指图与换页提示

按明确选择会话、保存、通知、重读的顺序讲同步。

## Slide 13: Guard stale responses, preserve the evidence

时间：3:16-3:30，目标 14 秒。

### English script

This guard rejects stale responses. The saved cloud run passed two turns, with physical input limits. The conversation keeps the same evidence.

### 中文指图与换页提示

指过期响应判断及验收记录，保留物理输入限制并收尾。


英文口述正文共 356 词。13 页含更多指图和切换，预留停顿后约 3 分半。建议按40秒、1分40秒、2分35秒、3分30秒四个交接点排练。已有模型验收结果来自保存的报告，本次没有重新调用模型或 IBKR。原主页没有英文版本，本版用实际英文工作台替代；中文历史列表、语言切换按钮及双语计算提示均位于截图裁剪范围之外，未改写截图内容。
