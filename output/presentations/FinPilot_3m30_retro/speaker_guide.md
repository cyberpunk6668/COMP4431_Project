# FinPilot · 四人演讲稿与排练提示

正式口述语言：英文。下方中文用于理解，不需要中英重复朗读。

总目标 3 分 30 秒，英文正文约 383 词。按每分钟约 115–120 词，加入换页、指图和交接停顿进行排练。时间为编排目标，并非实测录音时长。3 分半不包括现场 demo 和 Q&A。

| 成员 | 幻灯片 | 时段 | 时长 |
|---|---|---|---|
| Speaker 1 | 1 | 0:00–0:40 | 40 秒 |
| Speaker 2 | 2–3 | 0:40–1:40 | 60 秒 |
| Speaker 3 | 4 | 1:40–2:35 | 55 秒 |
| Speaker 4 | 5–6 | 2:35–3:30 | 55 秒 |

成员姓名和学号尚未提供，Speaker 编号是演讲分工占位，不代表真实开发贡献。

### Speaker 1 · Slide 1

时间：0:00–0:40。英文正文 72 词。

### English script

Hello everyone. Our project is FinPilot, a bilingual chatbot for financial education. Users can learn financial concepts, run planning calculations, use browser-supported voice, and discuss saved market reports with visible evidence. We focused on three connected features: RAG for traceable explanations, a clear frontend, and an interactive companion on the web and desktop. Local functions handle the numbers, while the language model explains the results. Let us start with the RAG pipeline.

### 中文理解提示

大家好，我们的项目是 FinPilot，一个面向金融教育的中英双语聊天机器人。用户可以学习金融概念、进行规划计算、在浏览器支持时使用语音，并结合可见证据讨论已保存的市场报告。我们聚焦三个相互结合的功能：可追溯的 RAG、清晰的前端、以及网页和桌面上的交互助手。数值由本地函数计算，语言模型负责解释。下面先介绍 RAG 流程。

### 换页与交接

开场停顿一秒，再指向三个功能标签。最后一句将话筒交给 Speaker 2。

### Speaker 2 · Slide 2

时间：0:40–1:15。英文正文 58 词。

### English script

Our RAG pipeline combines two kinds of evidence. Saved analyses provide numerical values, timestamps, and data limitations. Fourteen reviewed expert knowledge blocks provide financial concepts. We retrieve them using BM25 and Chinese character n-grams, then combine both rankings through reciprocal rank fusion, or RRF. DeepSeek receives both inputs, and the answer keeps local references separate from expert citations.

### 中文理解提示

RAG 结合两类证据。已保存的分析提供数值、时间戳和数据限制，十四个审阅过的专家知识块提供概念。我们使用 BM25 和中文字符 n-gram 分别检索，再通过倒数排名融合 RRF 合并结果。DeepSeek 同时接收两类输入，答案将本地数据引用与专家资料引用分开。

### 换页与交接

按画面先看上方本地报告，再看下方专家库与检索，最后看右侧回答。说完后由同一人切至第 3 页。

### Speaker 2 · Slide 3

时间：1:15–1:40。英文正文 53 词。

### English script

The first challenge is bilingual wording. Domain aliases and two retrieval routes help reduce missed sources. The second is unsupported claims. We check citations against recognized topics and allow one repair. Missing values stay missing. These rules improve traceability, but cannot guarantee correctness. Next, we will show how the frontend presents this clearly.

### 中文理解提示

第一个挑战是中英文的不同表达，我们用领域别名和两路检索减少漏召回。第二个挑战是论点可能没有来源支持，我们按已识别的主题检查引用，最多进行一次修正。缺失值继续保持缺失。这些规则改善可追溯性，但不能保证回答正确。下面介绍前端如何清楚展示这些内容。

### 换页与交接

两个挑战各一句解释。最后一句交给 Speaker 3。

### Speaker 3 · Slide 4

时间：1:40–2:35。英文正文 101 词。

### English script

The frontend must keep financial answers, tools, and the assistant usable together. Our React homepage introduces the product, while the JavaScript workspace handles real tasks. First, we manage information density: desktop columns become drawers and a collapsible assistant on mobile. Second, animations need reliable fallbacks. The homepage uses GSAP and Motion, with a static poster if video fails, and respects reduced motion. Third, asynchronous requests can arrive out of order. Request IDs or cancellation prevent old calculations from replacing new input, and failed chats keep the draft. These choices make the interface clearer and easier to recover. Next is our companion.

### 中文理解提示

前端需要让金融回答、工具和助手同时保持易用。React 首页介绍产品，JavaScript 工作台处理实际任务。首先处理信息密度：桌面分栏在手机上改为抽屉和可折叠助手。第二，动效需要可靠的回退：首页使用 GSAP 和 Motion；视频失败就显示静态海报，并尊重减少动态设置。第三，异步请求可能乱序返回，我们通过请求序号或取消机制防止旧计算覆盖新输入，聊天失败保留草稿。这些选择让界面更清晰，错误后也更容易恢复。接下来介绍虚拟助手。

### 换页与交接

按响应式、动效回退、异步状态的顺序讲，避免逐个介绍库。最后一句交给 Speaker 4。

### Speaker 4 · Slide 5

时间：2:35–3:10。英文正文 66 词。

### English script

Our companion uses multi-frame WebP atlases rendered by Canvas2D. The web page and Electron desktop app share this renderer, and its listening, thinking, and speaking states follow actual operations. Animation cost is one challenge, so we load assets on demand, pause hidden animation, and provide a static fallback. Transparent windows add another challenge: we use alpha-based hit regions, drag handling, and panel placement near screen edges.

### 中文理解提示

助手通过 Canvas2D 渲染多帧 WebP 图集，网页与 Electron 桌面共用渲染器。聆听、思考和朗读状态与真实操作对应。第一个挑战是动画开销，因此采用按需加载、隐藏时暂停和静态回退。第二个挑战是透明窗口，需要按透明度划分点击区域，处理拖动，并在屏幕边缘调整面板位置。

### 换页与交接

先指真实角色，再指渲染机制与两项挑战。仍由 Speaker 4 切至第 6 页。

### Speaker 4 · Slide 6

时间：3:10–3:30。英文正文 33 词。

### English script

Both interfaces share an explicitly selected conversation. The server saves messages, sends an SSE notification, and clients reload the record. We ignore responses from older connections, keeping the same evidence and limitations accessible.

### 中文理解提示

最后，两个界面延续用户明确选定的同一会话。服务器先保存消息，再通过 SSE 通知，客户端重新读取已保存的记录。连接代次检查会拒绝过时响应。助手让对话更容易继续，同时保留原有的依据和数据限制。

### 换页与交接

顺着网页、共享记录、桌宠的图示讲，最后一句收尾，不新增演示操作。

## 排练与发音

- BM25：读作“B M twenty-five”。
- RRF：先完整说一次“reciprocal rank fusion”，再说字母“R R F”。
- SSE：读字母“S S E”，代表服务器发送事件，不必在 20 秒收尾段展开协议。
- Canvas2D：读“Canvas two D”；WebP 可读“Web P”。
- 以 0:40、1:40、2:35、3:30 为交接时间点。首轮用计时器完整练一次，再按实际语速调整停顿。
- 如超时，先缩短指图停顿。避免删掉 RAG 的正确性边界，或把桌面跨端验证说成全部成功。

## 答辩时可用的补充

**为什么没有用向量数据库？** 当前专家库只有十四个经过审阅的知识块。词法检索轻量、容易审查，也能解释命中原因。未来可用独立评估比较 embedding 或混合检索，但当前实现没有这些组件。

**检索效果如何？** 已有 v14 保留集为 24 问，其中 18 个相关问题、6 个无关问题。相关问题平均 Recall@4 为 0.870370，即约 87.04%；15/18 取齐全部标注来源，4/6 个无关问题正确拒绝。该小样本由同团队标注，只评估原始检索，不是回答准确率或预测成功率。

**如何处理幻觉？** 本地数值、来源分层、有限主题检查和一次修正共同提供约束。规则无法验证所有自然语言论点，不能保证零幻觉。

**整个前端都是 React 吗？** 不是。React/TypeScript/Vite 用于展示首页，工作台使用原生 JavaScript/CSS，两者由 FastAPI 同源提供。

**角色是否自研？** 当前鲸鱼娘来自已有社区 2D 素材，团队工作在选帧与图集优化、共享渲染、状态联动、桌面交互与会话同步。素材归属与许可保留在项目和第 5 页。

**是否精准唇同步？** 不是。朗读时使用既有动作近似表达，角色状态表示操作状态，不表示金融判断的置信度。

**跨端同步是否已经全部验收？** 当前代码已实现明确连接 SID、SSE 通知、权威重读及迟到响应过滤。已有受控同步与宿主检查；本次读取的真实云跨端报告在第二轮失败，原生报告是插桩检查，未证明物理鼠标穿透全部成功。因此演讲强调实现机制，不声称最终原生与真实模型验收全部通过。

**本地 LoRA 是什么？** 项目另有 Qwen3-0.6B 的本地 LoRA 实验引擎，是否可用取决于真实训练产物与缓存。这不是对托管 DeepSeek 模型微调，也不属于当前三分钟半的重点。

**demo 如何衔接？** 可在这段说明之后，用已保存历史报告展示一次可追溯回答、展开本地与专家依据，再展示同一明确连接会话。实际云调用有延迟和失败可能，现场应按真实模式说明，不把离线降级说成云端成功。

## 使用范围

PPT 每页为整页图片，页内文字和插画不作为独立对象编辑。英文正文同步写入 PowerPoint 的演讲者备注。以当前交付包中的内容为准。

