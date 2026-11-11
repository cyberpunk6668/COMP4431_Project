# Speaker 3 · 前端设计与技术挑战

## Slide 4: Frontend design keeps complex tasks usable

时间：1:40–2:35。英文正文 101 词。

### English script

The frontend must keep financial answers, tools, and the assistant usable together. Our React homepage introduces the product, while the JavaScript workspace handles real tasks. First, we manage information density: desktop columns become drawers and a collapsible assistant on mobile. Second, animations need reliable fallbacks. The homepage uses GSAP and Motion, with a static poster if video fails, and respects reduced motion. Third, asynchronous requests can arrive out of order. Request IDs or cancellation prevent old calculations from replacing new input, and failed chats keep the draft. These choices make the interface clearer and easier to recover. Next is our companion.

### 中文理解提示

前端需要让金融回答、工具和助手同时保持易用。React 首页介绍产品，JavaScript 工作台处理实际任务。首先处理信息密度：桌面分栏在手机上改为抽屉和可折叠助手。第二，动效需要可靠的回退：首页使用 GSAP 和 Motion；视频失败就显示静态海报，并尊重减少动态设置。第三，异步请求可能乱序返回，我们通过请求序号或取消机制防止旧计算覆盖新输入，聊天失败保留草稿。这些选择让界面更清晰，错误后也更容易恢复。接下来介绍虚拟助手。

### 换页与交接

按响应式、动效回退、异步状态的顺序讲，避免逐个介绍库。最后一句交给 Speaker 4。



## 对应证据页（不额外朗读）

第 10 页：桌面/移动抽屉截图和请求序号代码。 放映时按页码再按 Enter，可跳到隐藏附录；点击右下角 Back to talk 回到主讲。主讲英文正文与原时长保持一致。
