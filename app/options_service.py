"""Read-only batch workflow. Market measurements are computed outside the LLM."""
import asyncio
import hashlib
import json
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.llm import ProviderError
from app.options_analytics import analyze_option_snapshot
from app.options_collective import build_collective_analysis, build_batch_comparison
from app.options_brief import build_plain_brief, build_batch_plain_brief
from app.options_narrative import SYSTEM, build_model_evidence, read_model_report, narrative_text, identify_cohorts
from app.options_ibkr import IBKROptionsError


NARRATIVE_DEADLINE_SECONDS = 60


class OptionsTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=12, pattern=r"^[A-Z][A-Z0-9]*(?:[ .-][A-Z0-9]+)?$")
    expiry: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("expiry")
    @classmethod
    def validate_calendar_date(cls, value):
        if value is not None:
            date.fromisoformat(value)
        return value



class OptionsRequest(OptionsTarget):
    radius: int = Field(4, ge=1, le=6, strict=True)
    market_data_type: int | None = Field(None, ge=1, le=4, strict=True)
    interpret_with_llm: bool = Field(False, strict=True)
    language: Literal["zh", "en"] = "zh"



class OptionsBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[OptionsTarget] = Field(min_length=1, max_length=4)
    radius: int = Field(4, ge=1, le=6, strict=True)
    market_data_type: int | None = Field(None, ge=1, le=4, strict=True)
    interpret_with_llm: bool = Field(False, strict=True)
    language: Literal["zh", "en"] = "zh"

    @model_validator(mode="after")
    def unique_targets(self):
        targets = [(item.symbol, item.expiry) for item in self.items]
        if len(targets) != len(set(targets)):
            raise ValueError("Duplicate symbol and expiry in the batch")
        return self


class OptionsService:
    def __init__(self, gateway, llm, settings):
        self.gateway = gateway
        self.llm = llm
        self.settings = settings
        self.lock = asyncio.Lock()

    def require_available(self):
        if self.lock.locked():
            raise IBKROptionsError("ibkr_busy", "An option batch is already running.")

    async def capture(self, request: OptionsRequest) -> dict:
        snapshot = await self.gateway.snapshot(
            request.symbol, request.expiry, 2 * request.radius + 1, request.market_data_type,
        )
        now = datetime.now(UTC)
        analysis = analyze_option_snapshot(snapshot, now=now, language=request.language)
        collective = build_collective_analysis(snapshot, analysis, now=now, language=request.language)
        digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True, allow_nan=False).encode()).hexdigest()
        return {
            "snapshot": snapshot,
            "snapshot_id": digest,
            "analyzed_at": now.isoformat(),
            **analysis,
            "collective": collective,
        }

    async def run(self, request: OptionsRequest) -> dict:
        self.require_available()
        async with self.lock:
            report = await self.capture(request)
            report["interpretation"] = await self.interpret(
                request.interpret_with_llm, request.language, [report],
            )
            self.add_capture_ages([report])
            report["plain_brief"] = build_plain_brief(report, language=request.language)
            return report

    async def run_batch(self, request: OptionsBatchRequest) -> dict:
        self.require_available()
        async with self.lock:
            reports, failures = [], []
            captured_scopes = set()
            for target in request.items:
                capture_request = OptionsRequest(
                    **target.model_dump(), radius=request.radius,
                    market_data_type=request.market_data_type, language=request.language,
                )
                try:
                    report = await self.capture(capture_request)
                except IBKROptionsError as error:
                    failure = {"symbol": target.symbol, "expiry": target.expiry, "code": error.code}
                    if error.available_expirations is not None:
                        failure["available_expirations"] = error.available_expirations
                    if getattr(error, "diagnostics", None) is not None:
                        failure["diagnostics"] = error.diagnostics
                    failures.append(failure)
                    continue
                snapshot = report["snapshot"]
                scope = (snapshot["symbol"], snapshot["expiration"], snapshot.get("trading_class"),
                         snapshot.get("currency"), snapshot.get("multiplier"))
                if scope in captured_scopes:
                    failures.append({"symbol": target.symbol, "expiry": target.expiry, "code": "duplicate_resolved_contract_scope"})
                    continue
                captured_scopes.add(scope)
                report["interpretation"] = {"status": "skipped", "reason": "batch_synthesis"}
                reports.append(report)
            comparison = build_batch_comparison(reports, language=request.language)
            interpretation = await self.interpret(
                request.interpret_with_llm, request.language, reports, comparison,
            )
            completed = datetime.now(UTC)
            self.add_capture_ages(reports, completed)
            for report in reports:
                report["plain_brief"] = build_plain_brief(report, language=request.language)
            return {
                "reports": reports, "failures": failures, "comparison": comparison,
                "interpretation": interpretation, "completed_at": completed.isoformat(),
                "requested_items": len(request.items),
                "plain_brief": build_batch_plain_brief(reports, comparison, failures, language=request.language),
            }

    @staticmethod
    def add_capture_ages(reports: list[dict], completed: datetime | None = None):
        completed = completed or datetime.now(UTC)
        for report in reports:
            received = datetime.fromisoformat(report["snapshot"]["received_at"].replace("Z", "+00:00"))
            report["capture_age_seconds"] = round(max(0, (completed - received).total_seconds()), 3)

    async def interpret(self, requested: bool, language: str, reports: list[dict], comparison: dict | None = None) -> dict:
        if not requested:
            return {"status": "skipped", "reason": "not_requested"}
        evidence = build_model_evidence(reports, comparison)
        if not evidence["cohorts"]:
            return {"status": "unavailable", "reason": "evidence_insufficient"}
        if not self.settings.online:
            return {"status": "unavailable", "reason": "cloud_unconfigured"}
        allowed = {item["id"] for group in evidence["cohorts"] for item in group["evidence"]}
        allowed.update(item["id"] for item in evidence["comparisons"])
        messages = [
            {"role": "system", "content": SYSTEM + language},
            {"role": "user", "content": json.dumps(evidence, allow_nan=False)},
        ]
        try:
            async with asyncio.timeout(NARRATIVE_DEADLINE_SECONDS):
                output = await self.llm.complete(messages, json_output=True)
                try:
                    narrative = read_model_report(output, allowed)
                except ValueError as validation_error:
                    messages.extend([
                        {"role": "assistant", "content": output[:15000]},
                        {"role": "user", "content": (
                            "Correct the JSON without adding evidence or claims. Validation failed: "
                            + str(validation_error)[:1200]
                            + "\nUse only these IDs: " + json.dumps(sorted(allowed))
                            + "\nKeep prose qualitative. Use supplied cohort IDs only, no other digits or percent signs."
                            + "\nAvoid causal attribution and near-month labels. Return the full corrected JSON schema."
                        )},
                    ])
                    output = await self.llm.complete(messages, json_output=True)
                    narrative = read_model_report(output, allowed)
                narrative = identify_cohorts(narrative, reports)
        except TimeoutError:
            return {"status": "unavailable", "reason": "network_or_timeout"}
        except ProviderError as error:
            return {"status": "unavailable", "reason": error.code}
        except (TypeError, ValueError):
            return {"status": "unavailable", "reason": "unverified_model_output"}
        ids = {ref for item in [narrative["summary"], *narrative["observations"],
                               *narrative["conflicts"], *narrative["scenarios"]]
               for ref in item["evidence_ids"]}
        return {
            "status": "ok", "model": self.settings.model, "report": narrative,
            "text": narrative_text(narrative), "evidence": sorted(ids),
            "basis": "descriptive_snapshot", "generated_at": datetime.now(UTC).isoformat(),
        }
