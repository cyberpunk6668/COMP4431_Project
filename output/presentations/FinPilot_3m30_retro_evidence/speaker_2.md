# Speaker 2 · RAG 集成与技术挑战

## Slide 2: RAG connects data with expert knowledge

时间：0:40–1:15。英文正文 58 词。

### English script

Our RAG pipeline combines two kinds of evidence. Saved analyses provide numerical values, timestamps, and data limitations. Fourteen reviewed expert knowledge blocks provide financial concepts. We retrieve them using BM25 and Chinese character n-grams, then combine both rankings through reciprocal rank fusion, or RRF. DeepSeek receives both inputs, and the answer keeps local references separate from expert citations.

### 中文理解提示

RAG 结合两类证据。已保存的分析提供数值、时间戳和数据限制，十四个审阅过的专家知识块提供概念。我们使用 BM25 和中文字符 n-gram 分别检索，再通过倒数排名融合 RRF 合并结果。DeepSeek 同时接收两类输入，答案将本地数据引用与专家资料引用分开。

### 换页与交接

按画面先看上方本地报告，再看下方专家库与检索，最后看右侧回答。说完后由同一人切至第 3 页。

## Slide 3: Reliable grounding needs more than retrieval

时间：1:15–1:40。英文正文 53 词。

### English script

The first challenge is bilingual wording. Domain aliases and two retrieval routes help reduce missed sources. The second is unsupported claims. We check citations against recognized topics and allow one repair. Missing values stay missing. These rules improve traceability, but cannot guarantee correctness. Next, we will show how the frontend presents this clearly.

### 中文理解提示

第一个挑战是中英文的不同表达，我们用领域别名和两路检索减少漏召回。第二个挑战是论点可能没有来源支持，我们按已识别的主题检查引用，最多进行一次修正。缺失值继续保持缺失。这些规则改善可追溯性，但不能保证回答正确。下面介绍前端如何清楚展示这些内容。

### 换页与交接

两个挑战各一句解释。最后一句交给 Speaker 3。



## 对应证据页（不额外朗读）

第 8 页：RRF 代码及检索指标。第 9 页：真实回答与引用支持校验。 放映时按页码再按 Enter，可跳到隐藏附录；点击右下角 Back to talk 回到主讲。主讲英文正文与原时长保持一致。
