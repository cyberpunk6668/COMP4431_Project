"""Recollect a saved analysis using server-owned parameters and fixed expiries.

No client overrides, broker connection, storage writes or model requests belong
here. Initial requests retain their exact radius. Legacy v10 results can only
infer a bounded radius from the strike window actually returned by the broker.
"""
from copy import deepcopy

from pydantic import ValidationError

from app.options_ibkr import IBKROptionsError
from app.options_service import OptionsBatchRequest, OptionsRequest, OptionsTarget


def _invalid():
    return IBKROptionsError("ibkr_refresh_invalid", "The saved analysis does not contain safe, reproducible refresh parameters.")


def _reports(analysis):
    if "reports" in analysis:
        reports = analysis["reports"]
        if not isinstance(reports, list) or not all(isinstance(item, dict) for item in reports):
            raise _invalid()
        return reports
    return [analysis]


def _target(report):
    snapshot = report.get("snapshot")
    if not isinstance(snapshot, dict) or not snapshot.get("expiration"):
        raise _invalid()
    # Successful scopes always pin the resolved date, even when the original
    # request asked for the nearest date or the saved date has since expired.
    return OptionsTarget(symbol=snapshot.get("symbol"), expiry=snapshot["expiration"])


def _effective_mode(reports, original=None):
    if original is not None:
        return original
    modes = set()
    for report in reports:
        mode = report.get("snapshot", {}).get("requested_market_data_type")
        if mode is not None:
            if type(mode) is not int or mode not in {1, 2, 3, 4}:
                raise _invalid()
            modes.add(mode)
    if len(modes) > 1:
        # The current batch API has one feed request for the whole batch.
        raise _invalid()
    # A legacy result without an effective request mode retains None, rather
    # than inventing an entitlement or treating observed feed as requested feed.
    return next(iter(modes), None)


def _deduplicate(targets):
    result, seen = [], set()
    for target in targets:
        key = (target.symbol, target.expiry)
        if key not in seen:
            seen.add(key)
            result.append(target)
    return result


def _failure_targets(analysis):
    failures = analysis.get("failures", [])
    if not isinstance(failures, list) or not all(isinstance(item, dict) for item in failures):
        raise _invalid()
    return [OptionsTarget(symbol=item.get("symbol"), expiry=item.get("expiry")) for item in failures]


def _pin_request(analysis, request):
    reports = _reports(analysis)
    if isinstance(request, OptionsRequest):
        if "reports" in analysis or len(reports) != 1:
            raise _invalid()
        target = _target(reports[0])
        if target.symbol != request.symbol or request.expiry is not None and target.expiry != request.expiry:
            raise _invalid()
        return OptionsRequest(**target.model_dump(), radius=request.radius,
                              market_data_type=_effective_mode(reports, request.market_data_type),
                              interpret_with_llm=False, language=request.language)
    if "reports" not in analysis:
        raise _invalid()
    successful = [_target(item) for item in reports]
    failed = _failure_targets(analysis)
    targets = []
    for original in request.items:
        # Failures retain the original explicit expiry, including None. They
        # have no successfully resolved date to pin and are retried as requested.
        failure_index = next((index for index, item in enumerate(failed)
                              if item.symbol == original.symbol and item.expiry == original.expiry), None)
        if failure_index is not None:
            targets.append(failed.pop(failure_index))
            continue
        success_index = next((index for index, item in enumerate(successful)
                              if item.symbol == original.symbol and (original.expiry is None or item.expiry == original.expiry)), None)
        if success_index is None:
            raise _invalid()
        targets.append(successful.pop(success_index))
    if successful or failed:
        raise _invalid()
    return OptionsBatchRequest(items=_deduplicate(targets), radius=request.radius,
                               market_data_type=_effective_mode(reports, request.market_data_type),
                               interpret_with_llm=False, language=request.language)


def attach_refresh_request(report: dict, request: OptionsRequest | OptionsBatchRequest) -> dict:
    """Return a separate report with validated, expiry-pinned refresh parameters."""
    try:
        if not isinstance(report, dict) or not isinstance(request, (OptionsRequest, OptionsBatchRequest)):
            raise _invalid()
        pinned = _pin_request(report, request)
        result = deepcopy(report)
        result["refresh_request"] = {"kind": "batch" if isinstance(pinned, OptionsBatchRequest) else "single",
                                     "request": pinned.model_dump()}
        return result
    except (ValidationError, TypeError, KeyError, AttributeError):
        raise _invalid() from None


def _legacy_request(analysis, language):
    reports = _reports(analysis)
    radii = []
    for report in reports:
        strikes = report.get("snapshot", {}).get("requested_strikes")
        if not isinstance(strikes, list) or not strikes:
            raise _invalid()
        radii.append(max(1, min(6, (len(strikes) - 1) // 2)))
    if not radii:
        raise _invalid()
    common = {"radius": max(radii), "market_data_type": _effective_mode(reports),
              "interpret_with_llm": False, "language": language}
    if "reports" in analysis:
        targets = _deduplicate([*[_target(item) for item in reports], *_failure_targets(analysis)])
        return OptionsBatchRequest(items=targets, **common)
    return OptionsRequest(**_target(analysis).model_dump(), **common)


def build_refresh_request(analysis: dict, language: str = "zh") -> OptionsRequest | OptionsBatchRequest:
    """Recover only server-saved scope; never roll an expired successful scope."""
    try:
        if not isinstance(analysis, dict):
            raise _invalid()
        if "refresh_request" not in analysis:
            return _legacy_request(analysis, language)
        saved = analysis["refresh_request"]
        if not isinstance(saved, dict) or set(saved) != {"kind", "request"} or not isinstance(saved["request"], dict):
            raise _invalid()
        if saved["kind"] == "single":
            request = OptionsRequest.model_validate({**saved["request"], "language": language, "interpret_with_llm": False})
        elif saved["kind"] == "batch":
            request = OptionsBatchRequest.model_validate({**saved["request"], "language": language, "interpret_with_llm": False})
        else:
            raise _invalid()
        reports = _reports(analysis)
        if isinstance(request, OptionsRequest):
            if "reports" in analysis or _target(analysis).model_dump() != {"symbol": request.symbol, "expiry": request.expiry}:
                raise _invalid()
        else:
            if "reports" not in analysis:
                raise _invalid()
            successful = {(item.symbol, item.expiry) for item in (_target(report) for report in reports)}
            failed = {(item.symbol, item.expiry) for item in _failure_targets(analysis)}
            requested = {(item.symbol, item.expiry) for item in request.items}
            if not successful <= requested or not requested <= successful | failed:
                raise _invalid()
        return type(request).model_validate({**request.model_dump(),
                                             "market_data_type": _effective_mode(reports, request.market_data_type)})
    except (ValidationError, TypeError, KeyError, AttributeError):
        raise _invalid() from None


async def capture_refresh(options_service, analysis: dict, language: str = "zh") -> dict:
    """Collect and analyze once; the API commits the result only after CAS checks."""
    request = build_refresh_request(analysis, language)
    if isinstance(request, OptionsBatchRequest):
        result = await options_service.run_batch(request)
        if not result.get("reports"):
            raise IBKROptionsError("ibkr_refresh_empty", "No requested option scope could be refreshed; the previous analysis is retained.")
    else:
        result = await options_service.run(request)
    return attach_refresh_request(result, request)
