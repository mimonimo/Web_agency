import sys, pathlib
sys.path.insert(0, "core")
from app import runner
from app.services import REPO_ROOT

ok = ng = 0
def check(label, cond, detail=""):
    global ok, ng
    if cond: ok += 1; print(f"  ✅ {label}")
    else:    ng += 1; print(f"  ❌ {label}   {detail}")

base = REPO_ROOT / "runs" / "9999" / "SX" / "output"
base.mkdir(parents=True, exist_ok=True)

cases = [
    ("판정: 반려\n\n- 로그인 실패 시 500 이 난다\n", True,  "로그인 실패 시 500 이 난다"),
    ("판정: 통과\n\n다음에 볼 위험: 동시 주문\n",     False, ""),
    ("# 검수 결과\n판정: 반려\n이유\n- 장바구니 수량이 음수로 들어간다\n", True, None),
    ("아무 판정도 없는 문서\n",                        False, ""),
]
for text, want_rej, want_reason in cases:
    (base / "VERDICT.md").write_text(text, encoding="utf-8")
    rej, reason = runner.read_verdict(9999, "SX")
    label = f"{'반려' if want_rej else '통과'} 판정 — {text.splitlines()[0][:20]!r}"
    check(label, rej == want_rej, f"got rejected={rej}, reason={reason!r}")
    if want_rej and want_reason:
        check("   사유를 뽑아낸다", want_reason in reason, repr(reason))

# VERDICT.md 가 아예 없으면 통과로 본다 (사이클을 멈춰 세우지 않는다)
(base / "VERDICT.md").unlink()
rej, _ = runner.read_verdict(9999, "SX")
check("VERDICT.md 가 없으면 통과로 본다", rej is False)

import shutil; shutil.rmtree(REPO_ROOT / "runs" / "9999", ignore_errors=True)
print(f"\n통과 {ok} · 실패 {ng}")
sys.exit(1 if ng else 0)
