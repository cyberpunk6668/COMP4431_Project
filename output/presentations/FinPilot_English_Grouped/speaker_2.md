# Speaker 2

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

