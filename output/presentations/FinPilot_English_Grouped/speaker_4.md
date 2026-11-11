# Speaker 4

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

