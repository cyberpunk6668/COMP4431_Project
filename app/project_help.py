"""Reviewed bilingual product help; deterministic routing, no model or tools.

This corpus describes FinPilot's UI, not financial theory. Only fixed public
manual IDs become evidence links. Source-file reads compute hashes from an
explicit allowlist; their contents are never retrieved or put in model prompts.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data/project_help.json"
CURRENT_VERSION = 17
MANUAL_VERSION = "17.0"
METHOD = "reviewed_manual_rules"
TOPIC_PREFIX = "/help#"
SAFE_LINKS = frozenset({"/", "/workspace", "/workspace?view=options",
    "/workspace?view=history", "/workspace?view=calculator", "/workspace?view=knowledge",
    "/workspace?tool=compound", "/workspace?tool=loan", "/workspace?tool=budget",
    "/demo", "/learn", "/pet", "/docs"})
SOURCE_FILES = frozenset({"README.md", "web/index.html", "web/app.js", "web/options.js",
    "web/history.js", "web/demo.html", "web/demo.js", "web/pet.html", "web/pet.js",
    "docs/desktop_pet_v15.md", "docs/history_rag_v13.md", "docs/innovation_rag_v14.md",
    "docs/ibkr_gateway_v12.md", "docs/options_chat_v10.md", "docs/options_refresh_v11.md",
    "docs/options_analysis_v6.md", "docs/innovation_upgrade.md", "finetuning/README.md",
    "web/learn.html", "web/learn.js", "web/learn.css", "docs/options_learning_v17.md"})


def _normal(value: str) -> str:
    return unicodedata.normalize("NFKC", value).lower().strip()


def _has(pattern: str, query: str) -> bool:
    return bool(re.search(pattern, query, re.I))


def _phrase(term: str, query: str) -> bool:
    term = _normal(term)
    if re.fullmatch(r"[a-z0-9 /_-]+", term):
        return _has(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", query)
    return term in query


_PRODUCT = r"finpilot|本项目|这个项目|(?:我们|你们|咱们)(?:的)?项目|你的项目|项目(?:里|内|中|的|帮助|计算器|显示)|本应用|这个软件|本软件|这个网站|本网站|我们的系统|此系统|工作台|this (?:app|project|application)|the (?:app|project|application)"
_INSTRUCTION = r"怎么|怎样|如何|哪里|在哪|入口|步骤|教程|使用|操作|切换|打开|点击|找不到|在哪里|\b(?:how|where|tutorial|guide|steps|use|open|switch|enable|disable|connect|export|import)\b"
_CAPABILITY = r"支持|功能|可以|能不能|能否|[能会有][^。?？]{0,50}吗|可不可以|有没有|是否|最多|区别|不同|\b(?:can|does|support|available|features?|capabilit(?:y|ies))\b"
_CONTENT_TASK = r"^(?:请|帮我|please\s+)?(?:翻译|写(?:一段|一篇|个|代码)|编写|润色|总结这|translate\b|write\b|summari[sz]e\b|debug\b)"
_SELF_INTRO = re.compile(r"^(?:(?:你好|您好)[,，!！\s]*)?(?:请)?(?:你是谁|介绍一下你自己|介绍你自己|自我介绍|你能做什么|你有哪些功能|你有什么功能|你的功能是什么|你能帮我做什么|你可以做什么)[?？!！。\s]*$|^(?:please\s+)?(?:who are you|introduce yourself|tell me about yourself|what can you do|how can you help(?: me)?|what are your features)[?.!\s]*$", re.I)
_SELF_OPTIONS = re.compile(r"^(?:请问)?你(?:能|会|可以|能不能|可不可以)(?:分析期权|做期权分析|进行期权分析)(?:吗|么)?[?？!！。\s]*$|^(?:can|could) you (?:analy[sz]e options?|do options? analysis)[?.!\s]*$", re.I)
_LEARNING_TOOL = r"期权互动(?:演示|学习)|学习实验室|到期盈亏试算|options? learning(?: lab)?|learning lab|interactive options? demo|expiry payoff (?:lab|trial|calculator)|options? (?:lab|playground)"
_FOLLOWUP = re.compile(r"^(?:那|那么|然后)?(?:还有呢|接下来呢|下一步|然后呢|怎么做|具体(?:呢|步骤|怎么做)?|详细(?:一点|些|步骤)?|再详细一点|继续|再说(?:一点|一下)|怎么打开|在哪(?:里)?|英文呢|中文呢|可以详细解释吗)[?？!！。\s]*$|^(?:and then|what next|next step|more(?: details)?|please continue|continue|tell me more|how exactly|where is it|in english|in chinese)[?.!\s]*$", re.I)


class ProjectHelp:
    """A closed, auditable manual with conservative project-intent detection.

    ``resolve`` returns None for ordinary financial/general questions. A short
    follow-up can reuse the nearest substantive user manual question only; an
    intervening non-manual user message is a hard boundary. Assistant text is
    never treated as routing authority or corpus content.
    """

    def __init__(self, path: Path = DEFAULT_PATH):
        raw_bytes = Path(path).read_bytes()
        raw = json.loads(raw_bytes)
        if raw.get("current_version") != CURRENT_VERSION or raw.get("manual_version") != MANUAL_VERSION:
            raise ValueError("Unsupported reviewed project manual version")
        documents = raw.get("documents")
        if not isinstance(documents, list) or not documents:
            raise ValueError("Project manual requires reviewed documents")
        self.manual_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        self.documents = deepcopy(documents)
        self._documents = {}
        self._hashes = {}
        for doc in self.documents:
            topic = doc.get("id", "")
            if not re.fullmatch(r"help\.[a-z_]+", topic) or topic in self._documents:
                raise ValueError("Invalid or duplicate public manual ID")
            for lang in ("zh", "en"):
                copy = doc.get(lang)
                if not isinstance(copy, dict) or any(not isinstance(copy.get(key), str) or not copy[key].strip() for key in ("title", "summary")):
                    raise ValueError("Manual topics require bilingual titles and summaries")
                for key in ("steps", "restrictions"):
                    if not isinstance(copy.get(key), list) or not copy[key] or any(not isinstance(x, str) or not x.strip() for x in copy[key]):
                        raise ValueError("Manual topics require bilingual steps and limits")
            if not isinstance(doc.get("keywords"), list) or not doc["keywords"] or any(not isinstance(x, str) or not x.strip() for x in doc["keywords"]):
                raise ValueError("Manual keywords must be text")
            if not isinstance(doc.get("links"), list):
                raise ValueError("Manual links must be fixed local routes")
            for link in doc["links"]:
                if not isinstance(link, dict) or link.get("url") not in SAFE_LINKS or any(not isinstance(link.get(lang), str) or not link[lang].strip() for lang in ("zh", "en")):
                    raise ValueError("Manual links must be bilingual fixed local routes")
            if not isinstance(doc.get("source_files"), list) or not doc["source_files"]:
                raise ValueError("Manual topics require reviewed source hashes")
            for source in doc["source_files"]:
                if not isinstance(source, dict) or source.get("path") not in SOURCE_FILES or not re.fullmatch(r"[0-9a-f]{64}", source.get("sha256", "")):
                    raise ValueError("Source audit paths must use the public allowlist")
                name = source["path"]
                if name not in self._hashes:
                    candidate = ROOT / name
                    # Refuse a replaced symlink escaping the public workspace.
                    if not candidate.resolve().is_relative_to(ROOT.resolve()):
                        raise ValueError("Public manual source escaped the workspace")
                    self._hashes[name] = hashlib.sha256(candidate.read_bytes()).hexdigest() if candidate.is_file() else None
            self._documents[topic] = doc
        if "help.boundaries" not in self._documents:
            raise ValueError("Manual must contain an explicit unknown-feature boundary")

    @staticmethod
    def _language(language: str) -> str:
        return "en" if language == "en" else "zh"

    def get_topic(self, topic_id: str, language: str = "zh") -> dict | None:
        """Select an already-known public ID; never map a path/URL to a file."""
        doc = self._documents.get(topic_id) if isinstance(topic_id, str) else None
        if doc is None:
            return None
        lang = self._language(language)
        sources = [{"path": source["path"], "reviewed_sha256": source["sha256"],
                    "current_sha256": self._hashes[source["path"]],
                    "matches_reviewed": source["sha256"] == self._hashes[source["path"]]}
                   for source in doc["source_files"]]
        return {"id": doc["id"], **deepcopy(doc[lang]), "url": TOPIC_PREFIX + doc["id"],
                "links": [{"label": link[lang], "url": link["url"]} for link in doc["links"]],
                "known": doc["id"] != "help.boundaries", "current_version": CURRENT_VERSION,
                "manual_version": MANUAL_VERSION, "source_files": sources}

    def catalogue(self, language: str = "zh") -> list[dict]:
        return [self.get_topic(doc["id"], language) for doc in self.documents]

    def search(self, query: str, language: str = "zh", limit: int = 4) -> list[dict]:
        """Search the public manual, independent of chat intent routing.

        Exact bilingual reviewed aliases determine ranking; scores indicate
        lexical relevance, not answer confidence. No untrusted query is echoed.
        """
        if not isinstance(query, str) or not query.strip() or not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            return []
        text = _normal(query[:3000])
        scored = []
        for doc in self.documents:
            hits = [term for term in doc["keywords"] if _phrase(term, text)]
            if hits:
                score = sum(2 + min(len(term), 24) / 12 for term in hits)
                scored.append((score, doc["id"]))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [{**self.get_topic(topic, language), "score": round(score, 4)} for score, topic in scored[:min(limit, 8)]]

    def _classify(self, message: str) -> list[str]:
        q = _normal(message)
        if not q or _has(_CONTENT_TASK, q):
            return []
        if _SELF_INTRO.fullmatch(q):
            return ["help.overview"]
        if _SELF_OPTIONS.fullmatch(q):
            return ["help.options"]
        product = _has(_PRODUCT, q)
        if not product and _has(r"微信|钉钉|语音障碍|\b(?:chatgpt|claude|telegram|discord|notion|python|javascript|typescript)\b|voice (?:disorder|therapy|lessons?)", q):
            return []
        instructional = _has(_INSTRUCTION, q)
        capability = _has(_CAPABILITY, q)
        ui_question = _has(r"按钮|页面|界面|入口|菜单|设置|点击|点哪里|在哪里|在哪|填(?:写|入)|怎么选|如何选择|怎么用|如何使用|工作台|\b(?:button|page|menu|settings|where)\b|how.{0,8}use", q)
        report_tutorial = _has(r"怎么(?:用|使用|操作|带|绑定|连接|切换|打开|保存)|如何(?:使用|操作|带|绑定|连接|切换|打开|保存)|怎样(?:使用|操作|保存)|(?:怎样|如何|怎么)让\s*(?:ai|模型|助手).{0,8}(?:解释|解读)|(?:刷新并解释变化|一键刷新).{0,6}(?:会做什么|有什么作用|什么意思|作用是什么)|教程|入口|按钮|功能|在哪|哪里|how.{0,15}(?:use|open|bind|connect|switch|refresh|save)|\b(?:where|button|feature|tutorial)\b", q)
        # A report-explanation imperative is real analysis, even with the app
        # name or a polite capability prefix. Product branding is not UI intent.
        if not report_tutorial and (_has(r"本报告|这(?:份|个|批).{0,16}(?:报告|分析|期权|数据|试算|演示|情景)|当前(?:报告|分析|试算|情景)|已保存.{0,8}(?:试算|情景)|(?:this|current|the|saved) (?:report|analysis|dataset|trial|scenario|simulation)", q)
                and _has(r"解释|解读|看跌|看涨|市场情绪|变化|盈亏|亏损|亏钱|盈利|成本|最大损失|explain|interpret|sentiment|change|payoff|break.?even|profit|loss|cost", q)
                or _has(r"刷新后.{0,8}(?:变化|差异).{0,8}(?:解读|解释)|(?:interpret|explain).{0,20}(?:changes after|refreshed)", q)):
            return []
        if not product and not ui_question and _has(r"看(?:空|多)|涨跌|市场情绪|(?:成交|持仓).{0,12}(?:说明|意味着)|\b(?:bullish|bearish|sentiment|predict|forecast)\b", q):
            return []
        found = []
        def add(name, condition):
            if condition:
                found.append("help." + name)
        # Only named-tool navigation is a learning tutorial. A calculation or
        # explanation of the bound trial remains real report/financial chat.
        learning_tool = _has(_LEARNING_TOOL, q)
        learning_navigation = _has(r"怎么(?:用|使用|操作|进入|打开|保存)|如何(?:使用|操作|进入|打开|保存|选择)|怎样(?:使用|操作|进入|打开|保存)|打开|进入|教程|指南|入口|按钮|页面|界面|在哪|哪里|怎么选|\b(?:where|tutorial|guide|button|page)\b|how.{0,24}(?:use|open|save|select)|\b(?:open|launch|enter)\b", q)
        learning_bare = bool(re.fullmatch(r"(?:" + _LEARNING_TOOL + r")[?？!！。\s]*", q, re.I))
        add("learning", learning_tool and (learning_navigation or learning_bare))
        add("trading", _has(r"自动(?:交易|下单|买卖)|代(?:我|用户)(?:交易|下单)|执行(?:交易|订单)|auto(?:matic(?:ally)?|mated)?[ -]trad|trad\w*.{0,12}automat|place (?:(?:real|live|buy|sell)[ /-]+)*orders?", q)
            and (product or capability or _has(r"你|桌宠|助手|chatbot|assistant", q)))
        add("rag", _has(r"rag|检索增强|微调|fine[ -]?tun|lora|知识来源|回答依据", q)
            and (product or _has(r"本地\s*lora\s*实验引擎|local lora (?:experimental )?engine", q)))
        add("models", (_has(r"(?:切换|选择|换个|更换).{0,8}(?:模型|引擎)|(?:模型|引擎).{0,10}(?:切换|选择|在哪|不可用|没就绪)|switch.{0,20}(?:model|engine)|(?:model|engine).{0,20}(?:switch|selector|unavailable)|本地.{0,8}模型|local.{0,12}(?:model|engine)", q)
            and (instructional or capability or product)) or (product and _has(r"deepseek", q)))
        add("pet", _has(r"桌宠|鲸鱼娘|小鲸|desktop (?:pet|companion)|whale (?:maid|girl)", q)
            and (instructional or capability or product or _has(r"连接|断开|同步|托盘|启动|connect|disconnect|sync|tray|launch", q)))
        add("avatar", _has(r"avatar|形象|2d|3d|机器人", q)
            and (instructional or capability) and (product or _has(r"avatar|鲸鱼|机器人|2d.{0,12}3d|3d.{0,12}2d", q)))
        add("export", _has(r"导出.{0,8}(?:对话|会话|聊天)|(?:对话|会话|聊天).{0,8}导出|export.{0,15}(?:chat|conversation|session)|download.{0,15}(?:chat|conversation|session)", q))
        add("voice", _has(r"语音|朗读|麦克风|speech|voice|microphone|read aloud", q)
            and (instructional or capability or product) and not _has(r"原理|算法|principle|algorithm", q))
        add("history", _has(r"导入.{0,10}(?:历史|数据|csv|json)|历史.{0,10}导入|历史复盘|历史样本|历史回放|教学样例|import.{0,20}(?:histor|data|csv|json)|historical review|saved.{0,12}(?:archive|sample)|teaching (?:example|sample)", q)
            and (instructional or capability or product or _has(r"导入|import", q)))
        add("ibkr", _has(r"ibkr|ib gateway|网关|354|10090|10167|行情.{0,6}(?:订阅|权限)|(?:订阅|权限).{0,8}(?:错误|行情)|双边报价|实时报价|market data.{0,12}(?:subscription|permission)|subscription error", q)
            and (instructional or capability or product or _has(r"错误|没.{0,5}报价|无.{0,5}报价|报错|error|missing|unavailable", q)))
        add("reports", _has(r"针对这批数据追问|刷新并解释变化|解释本报告|聊天.{0,8}刷新|一键刷新|分析记录|旧报告|期权报告.{0,12}聊天|follow.?up.{0,18}(?:report|analysis)|refresh.{0,15}(?:report|analysis)|analysis history", q)
            and (report_tutorial or bool(re.fullmatch(r"[「“\"]?(?:刷新并解释变化|一键刷新)[」”\"]?[?？。\s]*", q))))
        add("options", (_has(r"期权分析|易懂解读|专业详情|批量分析|联合分析|期权.{0,4}(?:到期日|日期).{0,12}(?:填|选)|options? analys(?:is|es)|batch analys(?:is|es)", q)
            and (instructional or product or _has(r"功能|页面|按钮|结果怎么看|开始|界面|feature|page|button", q))
            and (product or not _has(r"期权分析.{0,6}(?:如何|怎么).{0,8}(?:判断|预测|计算|估值|定价|推断)|options? analys(?:is|es).{0,16}(?:predict|calculate|forecast|imply)", q)))
            or (product and capability and _has(r"分析期权|analy[sz]e options?", q)))
        add("calculator", _has(r"计算器|calculator|贷款月供|收支预算|loan payments?|monthly budget", q)
            and (ui_question or product or _has(r"计算器|calculator", q) and (instructional or capability)))
        add("chat", _has(r"新建.{0,4}(?:会话|聊天)|删除.{0,4}(?:会话|聊天)|恢复.{0,4}(?:会话|聊天)|(?:切换|更改).{0,5}(?:语言|中英)|new (?:chat|session)|delete.{0,10}(?:chat|session)|switch.{0,12}language|chat history", q)
            and (instructional or capability or product or _has(r"新建|删除|new|delete", q)))
        add("appearance", _has(r"主题|浅色|深色|减少动态|暂停动画|theme|dark mode|light mode|reduce.{0,5}motion", q)
            and (instructional or product))
        add("overview", product and _has(r"是什么|介绍|能做什么|哪些功能|如何开始|哪里开始|怎么用|怎么使用|使用指南|教程|演示页|what is|what can|features|getting started|how.{0,12}use|guide|tutorial", q) and not found)
        # Unknown product capability requests receive only a documented boundary.
        # Financial definitions with the app name still belong to financial chat.
        if not found and product and (instructional or capability) and not _has(r"什么是|是什么意思|定义|what (?:is|are)|define|explain", q):
            found.append("help.boundaries")
        return [topic for topic in found if topic in self._documents][:4]

    def _followup_topics(self, message: str, history: list | None) -> list[str]:
        if not isinstance(history, (list, tuple)) or len(message) > 65:
            return []
        q = _normal(message)
        targeted = _has(r"^(?:那|那么)?(?:历史(?:复盘)?|导出|模型|桌宠|计算器|语音|avatar|2d|3d|学习实验室|期权互动学习|期权互动演示)(?:呢|怎么用|在哪)?[?？。\s]*$|^(?:what about|and) (?:history|export|models?|the pet|voice|the calculator|the learning lab)[?.\s]*$", q)
        if not _FOLLOWUP.fullmatch(q) and not targeted:
            return []
        prior = []
        user_count = 0
        for entry in reversed(history):
            if not isinstance(entry, dict) or entry.get("role") != "user":
                continue
            user_count += 1
            if user_count > 8:
                return []
            text = entry.get("content", entry.get("text", ""))
            if not isinstance(text, str):
                return []
            prior = self._classify(text[:3000])
            if prior:
                break
            if len(text) <= 65 and _FOLLOWUP.fullmatch(_normal(text)):
                continue
            return []
        if not prior:
            return []
        if targeted:
            for pattern, topic in ((r"历史|history", "history"), (r"导出|export", "export"),
                (r"模型|model", "models"), (r"桌宠|pet", "pet"), (r"计算器|calculator", "calculator"),
                (r"语音|voice", "voice"), (r"avatar|2d|3d", "avatar"),
                (r"学习实验室|期权互动(?:学习|演示)|learning lab", "learning")):
                if _has(pattern, q):
                    return ["help." + topic]
        return prior

    def resolve(self, message: str, history: list | None = None, language: str = "zh") -> dict | None:
        if not isinstance(message, str) or not message.strip():
            return None
        direct = self._classify(message[:3000])
        ids = direct or self._followup_topics(message[:3000], history)
        if not ids:
            return None
        return self.build_result(ids, language, followup_used=not bool(direct))

    def build_result(self, topic_ids: list[str], language: str = "zh", *, followup_used: bool = False,
                     known: bool = True) -> dict:
        """Compose exclusively from known IDs, including model-selected IDs.

        Invalid/empty IDs fail closed instead of silently turning model prose,
        file paths or URLs into evidence. The caller enforces its candidate set.
        ``known`` may narrow truth, never turn the boundary topic into support.
        """
        if not isinstance(topic_ids, (list, tuple)) or not 1 <= len(topic_ids) <= 4:
            raise ValueError("Select one to four reviewed public manual IDs")
        if any(not isinstance(topic, str) or topic not in self._documents for topic in topic_ids):
            raise ValueError("Unknown public manual ID")
        ids = list(dict.fromkeys(topic_ids))
        lang = self._language(language)
        topics = [self.get_topic(topic, lang) for topic in ids]
        links, seen, source_files = [], set(), {}
        for topic in topics:
            for link in topic["links"]:
                if link["url"] not in seen:
                    seen.add(link["url"])
                    links.append(link)
            for source in topic["source_files"]:
                source_files[source["path"]] = source
        sections = []
        for topic in topics:
            lines = ["## " + topic["title"], topic["summary"] + " [" + topic["id"] + "]"]
            lines.extend(f"{index}. {step}" for index, step in enumerate(topic["steps"], 1))
            lines.append("使用边界：" if lang == "zh" else "Limits:")
            lines.extend("- " + text for text in topic["restrictions"])
            sections.append("\n\n".join(lines))
        sources = [{"id": topic["id"], "title": topic["title"], "url": topic["url"],
                    "snippet": topic["summary"], "publisher": "FinPilot project manual",
                    "category": "project_help", "manual_version": MANUAL_VERSION} for topic in topics]
        drift = [item["path"] for item in source_files.values() if not item["matches_reviewed"]]
        return {"intent": "project_help", "current_version": CURRENT_VERSION, "manual_version": MANUAL_VERSION,
                "topic_ids": ids, "known": bool(known) and all(topic["known"] for topic in topics),
                "followup_used": bool(followup_used), "title": topics[0]["title"],
                "summary": "\n".join(topic["summary"] for topic in topics),
                "steps": [step for topic in topics for step in topic["steps"]],
                "restrictions": [text for topic in topics for text in topic["restrictions"]],
                "links": links, "topics": topics, "answer": "\n\n".join(sections), "sources": sources,
                "warnings": ["project_manual_source_drift"] if drift else [],
                "grounding": {"method": METHOD, "manual_sha256": self.manual_sha256,
                    "scope": "Hand-reviewed public manual sources only; no arbitrary repository RAG.",
                    "source_files": list(source_files.values()), "uses_model": False,
                    "source_drift": drift,
                    "reads_source_contents_for_answers": False,
                    "all_sources_match_reviewed": all(item["matches_reviewed"] for item in source_files.values())}}

    compose = build_result
