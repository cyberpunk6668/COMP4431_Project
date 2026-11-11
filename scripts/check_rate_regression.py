"""One billable targeted regression, not a general financial correctness benchmark."""
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import ROOT, Settings
from app.knowledge import KnowledgeRetriever
from app.llm import DeepSeek
from app.service import ChatService


async def main():
    settings = Settings()
    service = ChatService(KnowledgeRetriever(settings.knowledge_path), DeepSeek(settings), settings)
    question = "For a positive APY, does dividing APY by 12 overstate or understate the equivalent monthly rate? Explain the formula, without numerical estimates."
    result = await service.answer(question, [], "en")
    # Explicit narrow check; answer still requires reading rather than blind trust.
    passed = result["mode"] == "deepseek" and bool(re.search(r"overstat|高估", result["answer"], re.I))
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "question": question,
              "passed": passed, "check_scope": "Targeted wording regression for the APY comparison error discovered in initial live sample; not broad semantic accuracy.", **result}
    (ROOT / "reports" / "rate_regression.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return int(not passed)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
