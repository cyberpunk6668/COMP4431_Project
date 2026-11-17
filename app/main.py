"""Local-only demo API and static client. Run with uvicorn on loopback."""
import asyncio
import json
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from uuid import UUID
from typing import Literal
import hashlib

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app import __version__
from app.config import ROOT, Settings
from app.finance import CalculationRequest, calculate
from app.knowledge import KnowledgeRetriever
from app.llm import DeepSeek
from app.local_llm import LocalLoRA
from app.options_ibkr import IBKROptionsError, IBKROptionsProvider
from app.options_service import OptionsBatchRequest, OptionsRequest, OptionsService, OptionsTarget
from app.options_chat import OptionsChat, describe_analysis
from app.options_changes import build_refresh_comparison
from app.options_refresh import attach_refresh_request, capture_refresh
from app.options_history import HistoryDataset, analyze_history, demo_dataset
from app.history_chat import HistoryChat, describe_history
from app.expert_knowledge import ExpertKnowledge
from app.service import ChatService, _FINANCE_CONTEXT, _GENERAL_TASK, _follow_up
from app.storage import Store
from app.companion import CompanionBus, ConnectionInput, ActivityInput, StaleConnection, ActivityLimit, encode_event
from app.options_lab import catalogue as lab_catalogue, build_scenario, evaluate as evaluate_lab, LabEvaluationRequest
from app.project_help import CURRENT_VERSION as HELP_VERSION, MANUAL_VERSION
from app.options_demo import create_demo_router


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=3000)
    session_id: str | None = Field(None, max_length=36)
    language: str = Field("zh", pattern="^(zh|en)$")
    engine: str = Field("deepseek", pattern="^(deepseek|local)$")
    analysis_id: UUID | None = None

    @field_validator("message")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("message cannot be blank")
        return value.strip()


class NewSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field("新对话 / New chat", min_length=1, max_length=80)


class AnalysisBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_id: UUID | None


class AnalysisRefresh(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_id: UUID
    language: str = Field("zh", pattern="^(zh|en)$")
    engine: str = Field("deepseek", pattern="^(deepseek|local)$")


class HistoryFetchRequest(OptionsTarget):
    expiry: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    strike: float = Field(gt=0, le=1000000, strict=True, allow_inf_nan=False)
    days: Literal[3, 4, 5] = 5


def uses_analysis_context(message: str) -> bool:
    """Keep independent everyday questions on the ordinary chat route."""
    if re.match(r"^/?(?:compound|loan|budget|复利|贷款|预算)(?:\s|$)", message.strip(), re.I):
        return False
    financial = bool(_FINANCE_CONTEXT.search(message))
    if _GENERAL_TASK.search(message) and not financial:
        return False
    return _follow_up(message) or bool(re.search(
        r"这批|本批|这份|这组|这段历史|历史(?:数据|样本|复盘)|专家(?:依据|知识)|知识库|复盘|(?:当前|刚才|上述|所选|该)(?:的)?(?:分析|报告|数据|样本)|"
        r"报告(?:里|中|显示|说明)|期权|依据|市场|情绪|合约|成交|持仓|"
        r"隐含波动|价差|报价|行权|到期|涨跌|看涨|看跌|有什么不能|不能确定|说简单|为什么[？?]?\s*$|"
        r"数据.{0,12}(?:新鲜|过时|实时|时间)|(?:这|那)是什么意思|"
        r"这个变化|这些变化|这次变化|新旧|前后(?:变化|差异|对比|有何|有什么)|"
        r"\b(?:snapshot|evidence|options?|market|sentiment|liquidity|volatility|"
        r"put.call|call options?|put options?|open interest|implied volatility|bullish|bearish)\b|"
        r"\b(?:this|that|these|those|saved|current)\s+(?:data|analysis|results?|figures?|risks?|findings|reports?|samples?)\b|"
        r"\bthe\s+(?:report|snapshot|analysis)\b|"
        r"\bhow old.{0,30}\b(?:data|quotes?|snapshot)\b|\b(?:when|what time).{0,30}(?:collected|captured|received)\b|"
        r"\b(?:what (?:has |have )?changed|before and after|this change|these changes|since (?:the )?last capture)\b|"
        r"^\s*(?:what remains uncertain|what can(?:not|'t) we (?:tell|conclude)|why is that|"
        r"what does (?:it|this|that) mean|why|有什么变化|哪些变了|哪些不能确定|还有呢|什么意思)[?？.!。\s]*$", message, re.I,
    ))


OPTIONS_ERRORS = {
    "ibkr_disabled": (503, "Enable the IBKR provider in the server configuration."),
    "ibkr_dependency_missing": (503, "Install the optional IBKR transport dependency."),
    "ibkr_busy": (429, "An option batch is already running."),
    "ibkr_connection_failed": (503, "Check the logged-in Gateway, API port and read-only API settings."),
    "ibkr_client_id_conflict": (503, "The configured IBKR client ID is already in use."),
    "ibkr_contract_not_found": (404, "The US stock or ETF contract could not be uniquely resolved."),
    "ibkr_chain_unavailable": (424, "IBKR did not return a supported option chain."),
    "ibkr_expiration_unavailable": (404, "The requested expiration is unavailable for this chain."),
    "ibkr_entitlement_missing": (424, "IBKR did not grant the requested market data. Check the API subscriptions and concurrent sessions."),
    "ibkr_underlying_unavailable": (424, "IBKR did not provide a usable underlying price during collection."),
    "ibkr_option_data_unavailable": (424, "IBKR did not provide usable option ticks during collection."),
    "ibkr_timeout": (504, "The IBKR collection window expired."),
    "ibkr_invalid_request": (422, "The IBKR request parameters are invalid."),
    "ibkr_invalid_config": (503, "Check the local IBKR server configuration."),
    "ibkr_competing_session": (424, "Another IBKR session has priority for market data."),
    "ibkr_line_limit": (429, "The account's market data line capacity was reached."),
    "ibkr_refresh_empty": (424, "No refreshed group returned usable data. The previous analysis is still attached."),
    "ibkr_refresh_invalid": (422, "The saved collection parameters could not be safely restored. Collect another analysis first."),
    "ibkr_historical_unavailable": (424, "IBKR did not return the required historical bars. Inspect the historical permission and data-availability diagnostics."),
    "ibkr_historical_timeout": (504, "The bounded historical collection window expired."),
    "ibkr_historical_expired_option": (422, "IBKR does not provide expired-option history. Use a legitimate historical file or an archived capture."),
}


def describe_saved_analysis(record, language="zh"):
    return describe_history(record, language) if record.get("analysis_kind") == "historical_options" else describe_analysis(record, language)


def analyze_history_capture(capture, language="zh"):
    dataset = {**capture["dataset"], "bar_basis": "derived_from_intraday_trades"}
    record = analyze_history(HistoryDataset.model_validate(dataset), source_kind="ibkr_historical", language=language)
    record["historical_capture"] = {key: capture.get(key) for key in ("checked_at", "request", "aggregation", "row_provenance", "history_requests")}
    record["source"]["verification_scope"] = "Returned by the configured Gateway; not independently verified against an exchange or complete-session archive"
    stocks = [item for item in capture.get("instruments", []) if item.get("role") == "stock"]
    underlying = stocks[0].get("derived_daily", []) if stocks else []
    record["underlying_history"] = underlying
    if underlying:
        by_date = {item.get("trading_date"): item for item in underlying}
        first, last = by_date.get(record["period"]["start"], {}), by_date.get(record["period"]["end"], {})
        before, after = first.get("close"), last.get("close")
        valid = len(record["daily"]) >= 2 and type(before) in (float, int) and type(after) in (float, int) and before > 0
        delta = after - before if valid else None
        record["evidence"].append({"id": "h.underlying.trade_close", "scope": "history", "symbol": record["symbol"],
            "label": "标的所收成交记录末值的首尾变化", "value": after, "unit": "USD", "before": before, "after": after,
            "delta": delta, "delta_unit": "USD", "status": "comparable" if valid else "incomparable",
            "direction": "unavailable" if delta is None else "increase" if delta > 0 else "decrease" if delta < 0 else "unchanged",
            "reason": None if valid else "underlying_period_endpoint_missing",
            "trading_date": record["period"]["end"], "previous_trading_date": record["period"]["start"],
            "description": "仅比较所收标的成交 bars 的末值，不证明官方收盘、完整时段覆盖或当前方向。"})
    return record


def options_failure(error: IBKROptionsError) -> HTTPException:
    status, message = OPTIONS_ERRORS.get(error.code, (503, "The IBKR data request could not be completed."))
    detail = {"code": error.code, "message": message}
    if error.available_expirations is not None:
        detail["available_expirations"] = error.available_expirations
    if getattr(error, "diagnostics", None) is not None:
        detail["diagnostics"] = error.diagnostics
    return HTTPException(status, detail)


def create_app(settings: Settings | None = None, *, options_provider=None, history_provider=None) -> FastAPI:
    config = settings or Settings()
    store = Store(config.db_path)
    retriever = KnowledgeRetriever(config.knowledge_path)
    local_provider = LocalLoRA(config)
    cloud = DeepSeek(config)
    service = ChatService(retriever, cloud, config, local_provider)
    option_chat = OptionsChat(config, cloud, local_provider)
    history_chat = HistoryChat(config, cloud, local_provider)
    experts = ExpertKnowledge()
    history_gateway = history_provider
    options = OptionsService(options_provider if options_provider is not None else IBKROptionsProvider(), cloud, config)
    # Fixed stripes bound lock memory while serializing concurrent writes to one session.
    locks = [asyncio.Lock() for _ in range(64)]
    recent = defaultdict(deque)
    refreshing_sessions = set()
    companion = CompanionBus()

    @asynccontextmanager
    async def lifespan(app):
        yield
        companion.close()
        await local_provider.close()

    app = FastAPI(title="FinPilot API", version=__version__, description="Local financial education and read-only IBKR options analysis.", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.store, app.state.service, app.state.options = store, service, options
    app.state.options_chat = option_chat
    app.state.history_chat = history_chat
    app.state.companion = companion
    app.state.project_help = service.project_help
    app.include_router(create_demo_router(config, cloud))

    @app.middleware("http")
    async def local_security(request: Request, call_next):
        host = request.url.hostname
        if host not in {"127.0.0.1", "localhost", "::1", "testserver"}:
            return JSONResponse({"detail": "This application is configured for local use only."}, status_code=400)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin:
                parsed = urlsplit(origin)
                if parsed.scheme not in {"http", "https"} or parsed.netloc != request.url.netloc:
                    return JSONResponse({"detail": "Cross-origin mutation blocked."}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-site mutation blocked."}, status_code=403)
            size = request.headers.get("content-length")
            if size and (not size.isdigit() or int(size) > 32768):
                return JSONResponse({"detail": "Request too large."}, status_code=413)
            path = request.url.path
            is_refresh = bool(re.fullmatch(r"/api/sessions/[^/]+/analysis/refresh", path))
            if path in {"/api/chat", "/api/options-demo/run", "/api/options/analyze", "/api/options/batch", "/api/options/history/import", "/api/options/history/demo", "/api/options/history/fetch"} or is_refresh:
                ip = request.client.host if request.client else "local"
                queue = recent[(ip, "/api/options/refresh" if is_refresh else path)]
                tick = time.monotonic()
                while queue and queue[0] < tick - 60:
                    queue.popleft()
                if len(queue) >= (20 if path in {"/api/chat", "/api/options-demo/run"} else 6):
                    return JSONResponse({"detail": "Too many requests. Please wait a minute."}, status_code=429)
                queue.append(tick)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        # HTML and these unversioned client assets must be fetched again after
        # local updates; an older document can retain obsolete navigation links.
        fresh_client = request.url.path in {
            "/static/options-demo.js", "/static/options-demo.css", "/static/app.js",
        }
        if request.url.path.startswith("/api/") or fresh_client or response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health():
        return dict(application="FinPilot", status="ok", mode="deepseek" if config.online else "offline", model=config.model,
                    knowledge_documents=len(retriever.documents), version=__version__,
                    provider_verified=False, local_model=local_provider.status(), avatar_modes=["3d", "2d"],
                    note="Mode indicates configuration, not a live provider connectivity test.")

    @app.get("/api/models")
    def models():
        status = local_provider.status()
        return {"default": "deepseek", "models": [
            {"id": "deepseek", "label": "DeepSeek + RAG", "available": True, "configured": config.online,
             "description": "General questions and financial education with relevant references; disclosed offline extracts when unavailable."},
            {"id": "local", "label": "FinPilot LoRA · Qwen3-0.6B", **status,
             "description": "Experimental locally fine-tuned small model. Training evidence required; not a substitute for DeepSeek accuracy."},
        ]}

    @app.get("/api/knowledge")
    def knowledge():
        return {"documents": [{k: d[k] for k in ("id", "title", "url", "category", "updated_at") if k in d} for d in retriever.documents]}

    @app.get("/api/showcase")
    def showcase_data():
        """Public, source-backed exhibition data; never invokes a model."""
        def report(path):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                return value if isinstance(value, dict) else {}
            except (OSError, ValueError):
                return {}
        training = report(config.adapter_path / "training_manifest.json")
        evaluation = report(ROOT / "reports" / "finetuning_evaluation.json")
        local = local_provider.status()
        evidence_verified = training.get("trained") and local["reason"] not in {"adapter_not_trained", "adapter_hash_mismatch", "invalid_training_manifest", "training_evidence_missing"}
        if not evidence_verified or evaluation.get("adapter_sha256") != training.get("adapter_sha256"):
            evaluation = {}
        return {
            "document_count": len(retriever.documents),
            "knowledge_sources": [{"id": d["id"], "title": d["title"], "url": d["url"],
                                   "title_zh": d["title"].split(" / ", 1)[0].strip(),
                                   "title_en": d["title"].split(" / ", 1)[-1].strip(),
                                   "category": d.get("category", "education"), "snippet": d.get("text_zh", ""),
                                   "snippet_zh": d.get("text_zh", ""), "snippet_en": d.get("text_en", ""),
                                   "updated_at": d.get("updated_at")} for d in retriever.documents],
            "training": {"completed": bool(evidence_verified), "steps": training.get("steps", 0) if evidence_verified else 0,
                         "epochs": training.get("epochs", 0) if evidence_verified else 0,
                         "trainable_parameters": training.get("trainable_parameters", 0) if evidence_verified else 0,
                         "inference_available": local["available"]},
            "evaluation": {"test_prompts": evaluation.get("test_examples", 0),
                           "citation_base": evaluation.get("baseline", {}).get("metrics", {}).get("expected_citation_present_rate"),
                           "citation_lora": evaluation.get("finetuned", {}).get("metrics", {}).get("expected_citation_present_rate")},
            "disclaimer": "固定小样本中的来源引用与格式诊断，不代表开放金融问答准确率，也不代表优于 DeepSeek。",
        }

    @app.get("/api/sessions")
    def sessions():
        return {"sessions": store.list()}

    @app.post("/api/sessions", status_code=201)
    def new_session(body: NewSession):
        return store.create(body.title)

    def require_session(sid):
        item = store.get(sid)
        if item is None:
            raise HTTPException(404, "Session not found")
        record = store.get_analysis(item.get("active_analysis_id")) if item.get("active_analysis_id") else None
        item["active_analysis"] = describe_saved_analysis(record) if record is not None else None
        item["analysis_history"] = session_analysis_history(sid, item.get("active_analysis_id"))
        return item

    def session_analysis_history(sid, active_id, language="zh"):
        history = []
        for entry in store.get_analysis_history(sid):
            record = store.get_analysis(entry["analysis_id"])
            if record is None:
                continue
            metadata = describe_saved_analysis(record, language)
            history.append({key: metadata[key] for key in (
                "analysis_id", "captured_at", "completed_at", "source", "stale",
            )} | {"scopes": [{key: scope.get(key) for key in (
                "id", "symbol", "expiry", "received_at", "market_data_status", "time_status",
            )} for scope in metadata["scopes"]],
                  "attached_at": entry["attached_at"], "is_current": entry["analysis_id"] == active_id,
                  "previous_analysis_id": record.get("previous_analysis_id"),
                  "analysis_kind": metadata.get("analysis_kind"), "period": metadata.get("period"),
                  "notice": metadata.get("notice")})
        return history

    def require_analysis(analysis_id):
        result = store.get_analysis(str(analysis_id))
        if result is None:
            raise HTTPException(404, {"code": "analysis_not_found", "message": "The saved option analysis is unavailable. Select or collect another report."})
        return result

    @app.get("/api/companion/connection")
    async def companion_connection():
        companion.expire_activities()
        return companion.connection()

    @app.put("/api/companion/connection")
    async def connect_companion(body: ConnectionInput):
        sid = str(body.session_id) if body.session_id is not None else None
        # Sharing is an explicit selection, not a scan of recent chats. These
        # synchronous reads and the memory update have no await between them;
        # do not wait behind a potentially long model/refresh conversation lock.
        if sid is not None:
            require_session(sid)
        try:
            return companion.connect(sid, language=body.language, engine=body.engine,
                                     expected_generation=body.expected_generation)
        except StaleConnection as error:
            raise HTTPException(409, {"code": str(error), "message": "The shared conversation changed. Reload its connection before updating."}) from None

    @app.post("/api/companion/activity")
    async def companion_activity(body: ActivityInput):
        try:
            companion.frontend_activity(body)
        except StaleConnection as error:
            raise HTTPException(409, {"code": str(error), "message": "This activity belongs to an earlier shared conversation."}) from None
        except ActivityLimit as error:
            raise HTTPException(429, {"code": str(error), "message": "Too many companion activities are pending."}) from None
        return {"accepted": True, **companion.connection()}

    @app.get("/api/companion/events")
    async def companion_events(request: Request, surface: Literal["desktop", "workspace"] = "workspace"):
        try:
            subscriber = companion.subscribe(surface)
        except ActivityLimit as error:
            raise HTTPException(429, {"code": str(error), "message": "Too many companion event streams are open."}) from None

        async def events():
            try:
                yield encode_event(companion.reset())
                while not companion.closed and not await request.is_disconnected():
                    companion.expire_activities()
                    try:
                        event = await asyncio.wait_for(subscriber.queue.get(), timeout=15)
                    except TimeoutError:
                        yield ": heartbeat\n\n"
                        continue
                    if event is None:
                        break
                    yield encode_event(event)
            finally:
                companion.unsubscribe(subscriber)

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.get("/api/sessions/{sid}")
    def get_session(sid: str):
        return require_session(sid)

    @app.put("/api/sessions/{sid}/analysis")
    async def bind_analysis(sid: str, body: AnalysisBinding):
        async with locks[hash(sid) % len(locks)]:
            require_session(sid)
            record = require_analysis(body.analysis_id) if body.analysis_id is not None else None
            analysis_id = str(body.analysis_id) if body.analysis_id is not None else None
            store.set_active_analysis(sid, analysis_id)
            companion.notify("analysis.changed", sid, analysis_id=analysis_id)
            return {"active_analysis_id": analysis_id,
                    "active_analysis": describe_saved_analysis(record) if record is not None else None}

    @app.post("/api/sessions/{sid}/analysis/refresh")
    async def refresh_session_analysis(sid: str, body: AnalysisRefresh):
        if sid in refreshing_sessions:
            raise HTTPException(409, {"code": "analysis_refresh_busy", "message": "This conversation is already refreshing. Wait for its result."})
        refreshing_sessions.add(sid)
        operation = None
        operation_status = "failed"
        try:
            async with locks[hash(sid) % len(locks)]:
                session = require_session(sid)
                expected_id = str(body.analysis_id)
                if session.get("active_analysis_id") != expected_id:
                    raise HTTPException(409, {"code": "analysis_refresh_conflict", "message": "The attached analysis changed. Reload this conversation before refreshing."})
                previous = require_analysis(expected_id)
                if previous.get("analysis_kind") == "historical_options":
                    raise HTTPException(422, {"code": "historical_refresh_requires_new_dataset", "message": "This is a fixed historical review. Import or fetch another historical dataset; it cannot be refreshed as live quotes."})
                operation = companion.start_operation(sid, "refresh")
                try:
                    collected = await capture_refresh(options, previous, body.language)
                except IBKROptionsError as error:
                    raise options_failure(error) from None
                collected["previous_analysis_id"] = expected_id
                collected["refresh_comparison"] = build_refresh_comparison(previous, collected, body.language)
                try:
                    new_id = store.commit_analysis_refresh(sid, expected_id, collected)
                except KeyError:
                    raise HTTPException(404, "Session not found") from None
                except ValueError:
                    raise HTTPException(409, {"code": "analysis_refresh_conflict", "message": "The attached analysis changed during collection. Its existing records were preserved."}) from None
                companion.notify("analysis.changed", sid, analysis_id=new_id)
                current = require_analysis(new_id)
                user_message = ("刷新这批期权分析，并用白话解释前后变化、数据时间和判断依据。" if body.language == "zh"
                                else "Refresh this options analysis and explain what changed in plain language, with data times and evidence.")
                try:
                    result = await option_chat.answer(user_message, session["messages"], body.language, body.engine, current)
                except Exception:
                    # Collection is already safely committed. Model failure must
                    # not pretend that the successfully refreshed data vanished.
                    fallback = OptionsChat(Settings(api_key="", offline=True), cloud)
                    result = await fallback.answer(user_message, [], body.language, "deepseek", current)
                    result["warning"] = "options_answer_unavailable"
                store.append_turn(sid, user_message, result)
                companion.notify("session.changed", sid)
                operation_status = "completed"
                return {"session_id": sid, "user_message": user_message, "refreshed": True, **result,
                        "active_analysis": describe_analysis(current, body.language),
                        "analysis_history": session_analysis_history(sid, new_id, body.language)}
        finally:
            companion.finish_operation(operation, operation_status)
            refreshing_sessions.discard(sid)

    @app.delete("/api/sessions/{sid}")
    async def delete_session(sid: str):
        async with locks[hash(sid) % len(locks)]:
            if not store.delete(sid):
                raise HTTPException(404, "Session not found")
            companion.notify("session.deleted", sid)
        return {"deleted": True}

    @app.get("/api/sessions/{sid}/export")
    def export(sid: str):
        item = require_session(sid)
        return JSONResponse({"application": "FinPilot", "version": __version__, **item},
                            headers={"Content-Disposition": f'attachment; filename="finpilot-{item["id"]}.json"'})

    @app.post("/api/calculate")
    def calculation(body: CalculationRequest):
        return calculate(body)

    @app.get("/api/options/status")
    async def options_status():
        return {**await options.gateway.status(), "cloud_configured": config.online}

    @app.get("/api/options/expirations")
    async def option_expirations(symbol: str):
        try:
            target = OptionsTarget(symbol=symbol)
        except ValidationError:
            raise HTTPException(422, {"code": "ibkr_invalid_request", "message": "Enter a valid stock or ETF symbol."}) from None
        try:
            return await options.gateway.list_expirations(target.symbol)
        except IBKROptionsError as error:
            raise options_failure(error) from None

    @app.post("/api/options/analyze")
    async def analyze_options(body: OptionsRequest):
        try:
            report = attach_refresh_request(await options.run(body), body)
            return {**report, "analysis_id": store.save_analysis(report)}
        except IBKROptionsError as error:
            raise options_failure(error) from None

    @app.post("/api/options/batch")
    async def analyze_option_batch(body: OptionsBatchRequest):
        try:
            report = attach_refresh_request(await options.run_batch(body), body)
            return {**report, "analysis_id": store.save_analysis(report) if report["reports"] else None}
        except IBKROptionsError as error:
            raise options_failure(error) from None

    @app.get("/api/options/analyses/{analysis_id}")
    def saved_option_analysis(analysis_id: UUID):
        return require_analysis(analysis_id)

    @app.get("/api/options/history/demo")
    def history_example_template():
        return demo_dataset()

    @app.post("/api/options/history/demo")
    def history_teaching_example(language: Literal["zh", "en"] = "zh"):
        report = analyze_history(HistoryDataset.model_validate(demo_dataset()), source_kind="demo", language=language)
        return {**report, "analysis_id": store.save_analysis(report)}

    @app.post("/api/options/history/import")
    def import_history(body: HistoryDataset, language: Literal["zh", "en"] = "zh"):
        if re.search(r"\bsk-[a-zA-Z0-9_-]{16,}", body.model_dump_json()):
            raise HTTPException(422, {"code": "sensitive_credential", "message": "Remove credentials from the dataset before importing."})
        try:
            report = analyze_history(body, source_kind="import", language=language)
        except ValueError as error:
            raise HTTPException(422, {"code": "historical_dataset_invalid", "message": str(error)}) from None
        return {**report, "analysis_id": store.save_analysis(report)}

    def historical_archive():
        path = ROOT / "reports" / "ibkr_history_probe_v13.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("status") != "passed" or not value.get("dataset", {}).get("rows"):
                raise ValueError("Historical sample unavailable")
            return value
        except (OSError, ValueError):
            raise HTTPException(404, {"code": "history_sample_unavailable", "message": "The archived IBKR historical sample is unavailable. Import a historical file instead."}) from None

    @app.get("/api/options/history/sample")
    def historical_sample_status():
        report = analyze_history_capture(historical_archive())
        return {key: report[key] for key in ("symbol", "expiry", "period", "source", "bar_basis", "limitations")} | {"available": True}

    @app.post("/api/options/history/sample")
    def historical_archived_sample(language: Literal["zh", "en"] = "zh"):
        capture = historical_archive()
        report = analyze_history_capture(capture, language)
        report["source"]["archive_sha256"] = hashlib.sha256(json.dumps(capture, sort_keys=True).encode()).hexdigest()
        return {**report, "analysis_id": store.save_analysis(report)}

    @app.post("/api/options/history/fetch")
    async def fetch_historical_options(body: HistoryFetchRequest, language: Literal["zh", "en"] = "zh"):
        nonlocal history_gateway
        if history_gateway is None:
            from app.options_history_ibkr import IBKRHistoryProvider
            history_gateway = IBKRHistoryProvider(config=getattr(options.gateway, "config", None), lock=getattr(options.gateway, "_lock", None))
        try:
            capture = await history_gateway.fetch(body.symbol, body.expiry, body.strike, body.days)
            report = analyze_history_capture(capture, language)
        except IBKROptionsError as error:
            raise options_failure(error) from None
        except (ValueError, KeyError):
            raise HTTPException(424, {"code": "historical_dataset_invalid", "message": "The returned historical dataset did not pass local consistency checks."}) from None
        return {**report, "analysis_id": store.save_analysis(report)}

    @app.get("/api/experts/search")
    def expert_search(q: str = "期权成交量与未平仓量", limit: int = 4):
        if not 1 <= len(q) <= 500 or not 1 <= limit <= 6:
            raise HTTPException(422, "Use a query of 1–500 characters and a limit of 1–6")
        return experts.search(q, limit=limit)

    @app.get("/api/experts")
    def expert_catalogue():
        return {"version": experts.version, "corpus_sha256": experts.corpus_sha256,
                "document_count": len(experts.documents), "embedding": False,
                "documents": [{key: doc.get(key) for key in ("id", "title", "url", "publisher", "reviewed_at", "topics", "supports")} for doc in experts.documents]}

    @app.post("/api/chat")
    async def chat(body: ChatRequest):
        # Reject before creation/persistence: the database should not retain a pasted API key.
        if re.search(r"\bsk-[a-zA-Z0-9_-]{16,}", body.message):
            raise HTTPException(422, "Sensitive credential detected. Remove it before sending.")
        explicit_analysis = "analysis_id" in body.model_fields_set
        record = require_analysis(body.analysis_id) if body.analysis_id is not None else None
        sid = body.session_id
        if sid is None:
            sid = store.create()["id"]
        async with locks[hash(sid) % len(locks)]:
            session = require_session(sid)
            if not explicit_analysis and session.get("active_analysis_id"):
                record = require_analysis(session["active_analysis_id"])
            if explicit_analysis:
                store.set_active_analysis(sid, str(body.analysis_id) if body.analysis_id is not None else None)
                companion.notify("analysis.changed", sid, analysis_id=str(body.analysis_id) if body.analysis_id is not None else None)
            operation = companion.start_operation(sid, "chat")
            operation_status = "failed"
            try:
                # Product usage questions take precedence over a bound market
                # report. They never clear/rebind the report or call a broker.
                help_context = service.project_help.resolve(body.message,session["messages"],body.language)
                if help_context is not None:
                    result = await service.answer(body.message,session["messages"],body.language,body.engine,project_context=help_context)
                elif record is not None and (uses_analysis_context(body.message) or record.get("lab_context") and re.search(
                    r"盈亏|试算|到期|权利金|成本|最大(?:损失|收益)|行权|\b(?:payoff|break.even|premium|cost|expiry|expiration|strategy|maximum (?:loss|gain))\b", body.message,re.I)):
                    selected_chat = history_chat if record.get("analysis_kind") == "historical_options" else option_chat
                    result = await selected_chat.answer(body.message, session["messages"], body.language, body.engine, record)
                else:
                    result = await service.answer(body.message, session["messages"], body.language, body.engine)
                store.append_turn(sid, body.message, result)
                companion.notify("session.changed", sid)
                operation_status = "completed"
            finally:
                companion.finish_operation(operation, operation_status)
            return {"session_id": sid, **result,
                    "active_analysis": describe_saved_analysis(record, body.language) if record is not None else None,
                    "analysis_history": session_analysis_history(sid, record["analysis_id"] if record is not None else None, body.language)}

    @app.get("/", include_in_schema=False)
    def index():
        showcase = ROOT / "web" / "showcase" / "index.html"
        return FileResponse(showcase if showcase.is_file() else ROOT / "web" / "index.html")

    @app.get("/workspace", include_in_schema=False)
    @app.get("/app", include_in_schema=False)
    def workspace():
        return FileResponse(ROOT / "web" / "index.html")

    @app.get("/demo", include_in_schema=False)
    def innovation_demo():
        return FileResponse(ROOT / "web" / "demo.html")

    @app.get("/options-demo", include_in_schema=False)
    def options_data_demo():
        return FileResponse(ROOT / "web" / "options-demo.html")

    @app.get("/pet", include_in_schema=False)
    def desktop_pet():
        return FileResponse(ROOT / "web" / "pet.html")

    @app.get("/learn", include_in_schema=False)
    def options_learning_page():
        return FileResponse(ROOT / "web" / "learn.html")

    @app.get("/api/options-lab/scenarios")
    def options_learning_scenarios(language: Literal["zh","en"] = "zh"):
        return lab_catalogue(language=language)

    @app.get("/api/options-lab/scenarios/{scenario_id}")
    def options_learning_scenario(scenario_id: str, language: Literal["zh","en"] = "zh"):
        try:
            return build_scenario(scenario_id,language=language)
        except (KeyError,ValueError):
            raise HTTPException(404,"Unknown teaching scenario") from None

    @app.post("/api/options-lab/evaluate")
    def options_learning_evaluate(body: LabEvaluationRequest):
        try:
            return evaluate_lab(body)
        except ValueError as error:
            raise HTTPException(422,"Invalid teaching calculation") from error

    @app.post("/api/options-lab/save")
    def options_learning_save(body: LabEvaluationRequest):
        try:
            result = evaluate_lab(body)
        except ValueError as error:
            raise HTTPException(422,"Invalid teaching calculation") from error
        return {**result,"analysis_id":store.save_analysis(result)}

    @app.get("/help", include_in_schema=False)
    def project_manual_page():
        return FileResponse(ROOT / "web" / "help.html")

    @app.get("/api/project-help")
    def project_manual(language: Literal["zh","en"] = "zh"):
        manual = service.project_help
        topics = manual.catalogue(language=language)
        sample = topics[0] if topics else {}
        return {"manual_version":sample.get("manual_version",MANUAL_VERSION),"current_version":HELP_VERSION,"topics":topics}

    @app.get("/api/project-help/search")
    def search_project_manual(q: str = "", language: Literal["zh","en"] = "zh", limit: int = 4):
        if not 1 <= len(q.strip()) <= 500 or not 1 <= limit <= 6:
            raise HTTPException(422,"Use a query of 1–500 characters and a limit of 1–6")
        if re.search(r"\bsk-[a-zA-Z0-9_-]{16,}",q):
            raise HTTPException(422,"Remove credentials before searching the public manual")
        topics = service.project_help.search(q,language=language,limit=limit)
        return {"manual_version":topics[0].get("manual_version",MANUAL_VERSION) if topics else MANUAL_VERSION,"topics":topics}

    @app.get("/api/project-help/topics/{topic_id}")
    def project_manual_topic(topic_id: str, language: Literal["zh","en"] = "zh"):
        topic = next((entry for entry in service.project_help.catalogue(language=language) if entry["id"]==topic_id),None)
        if topic is None:
            raise HTTPException(404,"Unknown project manual topic")
        return topic

    @app.get("/docs", include_in_schema=False)
    def api_documentation():
        return FileResponse(ROOT / "web" / "api-docs.html")

    app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")
    return app


app = create_app()
