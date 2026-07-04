"""Dev harness: run the full audit pipeline on the ACME fixtures from the CLI.

Streams the live event trace to stdout, prints a result summary, and leaves
the full trace JSON in traces/ (same artifact the API produces). Used for
prompt calibration and stability re-runs before the demo video.

Usage:  .venv\\Scripts\\python.exe scripts\\run_demo.py
"""

import asyncio
import io
import json
import sys
import time
from pathlib import Path

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows cp1252 console
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.graph import run_audit  # noqa: E402
from app.agent.state import AuditState  # noqa: E402
from app.core.events import RunBus  # noqa: E402
from app.ingest.parser import parse_upload  # noqa: E402


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FILES = [
    "acme_credit_agreement.txt",
    "acme_q2_2026_financial_report.txt",
    "acme_treasury_pack_q2_2026.txt",
]


async def print_events(bus: RunBus) -> None:
    async for event in bus.subscribe():
        payload = json.dumps(event.payload, default=str, ensure_ascii=False)
        print(f"[{event.node.value:>11}] {event.type.value:<20} {payload[:200]}", flush=True)


async def main() -> None:
    run_id = time.strftime("demo-%H%M%S")
    state = AuditState(run_id=run_id)
    for index, name in enumerate(FILES):
        raw = (FIXTURES / name).read_bytes()
        state.documents.append(parse_upload(f"doc{index}", name, raw))

    bus = RunBus(run_id)
    printer = asyncio.create_task(print_events(bus))
    started = time.time()
    final = await run_audit(state, bus)
    await asyncio.sleep(0.2)
    printer.cancel()

    print("\n" + "=" * 72)
    print(f"RESULT SUMMARY  ({time.time() - started:.0f}s, {final.retrieval_rounds} retrieval rounds)")
    print("=" * 72)
    print(f"rules: {[(r.rule_id, r.operator, r.threshold) for r in final.rules]}")
    print(f"facts extracted: {len(final.facts)}")
    for fact in final.facts:
        print(f"  - {fact.metric}={fact.value} ({fact.period or '?'}, {fact.basis}) [{fact.sources[0].section if fact.sources else '?'}]")
    print("findings:")
    for finding in final.findings:
        print(f"  - {finding.covenant}: {finding.status.upper()} (required {finding.required}, actual {finding.actual}) {finding.projection_note}")
    print("verdicts:")
    for verdict in final.verdicts:
        print(f"  - {verdict.rule_id}: {verdict.original_status} -> {verdict.final_status} "
              f"(overturned={verdict.overturned}, confidence={verdict.confidence:.0%})")
        for check in verdict.checks:
            print(f"      [{'PASS' if check.passed else 'FAIL'}] {check.check}: {check.note[:110]}")
    print(f"cause_coverage: {final.cause_coverage}")
    print(f"causes: {[(c.description[:60], c.amount, c.matched) for c in final.causes]}")
    print(f"overall_confidence: {final.overall_confidence}")
    print("\n----- MEMO -----\n")
    print(final.memo_markdown or "(no memo)")


if __name__ == "__main__":
    asyncio.run(main())
