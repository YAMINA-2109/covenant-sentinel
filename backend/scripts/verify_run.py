"""Regression gate: assert the ACME audit produces the expected verdicts.

Usage:
  python scripts/verify_run.py              # verify the newest trace in traces/
  python scripts/verify_run.py --run        # execute a fresh audit first (txt fixtures)
  python scripts/verify_run.py --run --pdf  # fresh audit on the PDF fixtures

Exit code 0 = every expectation holds; 1 = at least one failed.
"""

import asyncio
import io
import json
import sys
import time
from pathlib import Path

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.state import AuditState  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
TRACES = Path(__file__).resolve().parents[1] / "traces"

TXT_FILES = [
    "acme_credit_agreement.txt",
    "acme_q2_2026_financial_report.txt",
    "acme_treasury_pack_q2_2026.txt",
]
PDF_FILES = [
    "pdf/acme_credit_agreement.pdf",
    "pdf/acme_q2_2026_financial_report.pdf",
    "pdf/acme_treasury_pack_q2_2026.pdf",
]


def _verdict(state: AuditState, needle: str):
    for verdict in state.verdicts:
        if needle in verdict.rule_id.lower():
            return verdict
    return None


def check_state(state: AuditState) -> int:
    failures = 0

    def expect(name: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            failures += 1

    leverage = _verdict(state, "leverage")
    liquidity = _verdict(state, "liquid")
    coverage = _verdict(state, "coverage") or _verdict(state, "interest")

    expect("three verdicts produced", len(state.verdicts) == 3, f"got {len(state.verdicts)}")
    expect(
        "leverage: confirmed breach, high confidence",
        leverage is not None
        and leverage.final_status == "breach"
        and not leverage.overturned
        and 0.90 <= leverage.confidence <= 1.0,
        f"{leverage and (leverage.final_status, leverage.overturned, leverage.confidence)}",
    )
    expect(
        "liquidity: false positive overturned to ok",
        liquidity is not None
        and liquidity.final_status == "ok"
        and liquidity.overturned
        and liquidity.confidence >= 0.9,
        f"{liquidity and (liquidity.final_status, liquidity.overturned, liquidity.confidence)}",
    )
    expect(
        "interest coverage: early warning kept (at_risk, projection factor)",
        coverage is not None
        and coverage.final_status == "at_risk"
        and 0.80 <= coverage.confidence <= 0.95,
        f"{coverage and (coverage.final_status, coverage.confidence)}",
    )
    lev_coverage = next(
        (value for key, value in state.cause_coverage.items() if "leverage" in key.lower()), None
    )
    expect(
        "cause coverage ≈ 88.9% (EUR 40m documented / 45m total)",
        lev_coverage is not None and 0.85 <= lev_coverage <= 0.93,
        f"got {lev_coverage}",
    )
    expect(
        "overall confidence in honest band",
        state.overall_confidence is not None and 0.85 <= state.overall_confidence <= 0.95,
        f"got {state.overall_confidence}",
    )
    memo = state.memo_markdown or ""
    expect("memo names the borrower's exact legal name", "ACME INDUSTRIES" in memo.upper())
    expect("memo cites the supersession clause (Section 9.4)", "9.4" in memo)
    expect(
        "both conflicting cash figures were extracted (4.2 prelim / 5.3 final)",
        any(f.value == 4.2 and f.basis == "preliminary" for f in state.facts)
        and any(f.value == 5.3 and f.basis == "final" for f in state.facts),
    )
    return failures


async def _fresh_run(files: list[str]) -> AuditState:
    from app.agent.graph import run_audit
    from app.core.events import RunBus
    from app.ingest.parser import parse_upload

    run_id = time.strftime("verify-%H%M%S")
    state = AuditState(run_id=run_id)
    for index, name in enumerate(files):
        state.documents.append(parse_upload(f"doc{index}", Path(name).name, (FIXTURES / name).read_bytes()))
    await run_audit(state, RunBus(run_id))
    return state


def main() -> None:
    if "--run" in sys.argv:
        files = PDF_FILES if "--pdf" in sys.argv else TXT_FILES
        print(f"running fresh audit on {'PDF' if '--pdf' in sys.argv else 'txt'} fixtures…")
        started = time.time()
        state = asyncio.run(_fresh_run(files))
        print(f"audit finished in {time.time() - started:.0f}s — verifying:")
    else:
        traces = sorted(TRACES.glob("*.json"))
        if not traces:
            print("no traces to verify");  sys.exit(1)
        print(f"verifying newest trace: {traces[-1].name}")
        state = AuditState.model_validate(json.loads(traces[-1].read_text(encoding="utf-8"))["state"])

    failures = check_state(state)
    print(f"\n{'✅ ALL EXPECTATIONS HOLD' if failures == 0 else f'❌ {failures} expectation(s) FAILED'}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
