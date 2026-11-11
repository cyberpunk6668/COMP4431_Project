# Speaker 4 · 虚拟形象与跨端同步

## Slide 5: One companion, on the web and desktop

时间：2:35–3:10。英文正文 66 词。

### English script

Our companion uses multi-frame WebP atlases rendered by Canvas2D. The web page and Electron desktop app share this renderer, and its listening, thinking, and speaking states follow actual operations. Animation cost is one challenge, so we load assets on demand, pause hidden animation, and provide a static fallback. Transparent windows add another challenge: we use alpha-based hit regions, drag handling, and panel placement near screen edges.

### 中文理解提示

助手通过 Canvas2D 渲染多帧 WebP 图集，网页与 Electron 桌面共用渲染器。聆听、思考和朗读状态与真实操作对应。第一个挑战是动画开销，因此采用按需加载、隐藏时暂停和静态回退。第二个挑战是透明窗口，需要按透明度划分点击区域，处理拖动，并在屏幕边缘调整面板位置。

### 换页与交接

先指真实角色，再指渲染机制与两项挑战。仍由 Speaker 4 切至第 6 页。

## Slide 6: Shared conversation, explicit control

时间：3:10–3:30。英文正文 33 词。

### English script

Both interfaces share an explicitly selected conversation. The server saves messages, sends an SSE notification, and clients reload the record. We ignore responses from older connections, keeping the same evidence and limitations accessible.

### 中文理解提示

最后，两个界面延续用户明确选定的同一会话。服务器先保存消息，再通过 SSE 通知，客户端重新读取已保存的记录。连接代次检查会拒绝过时响应。助手让对话更容易继续，同时保留原有的依据和数据限制。

### 换页与交接

顺着网页、共享记录、桌宠的图示讲，最后一句收尾，不新增演示操作。


