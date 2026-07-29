"""역할 카탈로그 · 기준선 AGENT.md · 산출물 검사기가 성한지 확인한다.

여기서 잡는 것은 "돌아가느냐" 가 아니라 **"에이전트에게 온전한 문장이 가느냐"** 다.

한 번 겪은 사고: `- 색이 기본값(#4CAF50, ...)` 이 YAML 주석으로 잘려
완료 조건이 `- 색이 기본값(#4CAF50,` 로 노드에 전달됐다. 아무도 못 알아챘다.
"""

import pathlib
import sys

sys.path.insert(0, "core")

from app import checks, roles as catalog, services   # noqa: E402
from app.models import ROLES                          # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASELINE = ROOT / "agents"
SECTIONS = ("나의 역할", "내 파일", "출력 형식", "금지", "애매할 때", "완료 보고")

ok = ng = 0


def check(label, cond, detail=""):
    global ok, ng
    if cond:
        ok += 1
        print(f"  ✅ {label}")
    else:
        ng += 1
        print(f"  ❌ {label}   {detail}")


print("\n[역할 카탈로그]")
cat = catalog.all_roles()
check("11개 역할이 다 있다", set(cat) == set(ROLES), f"차이 {set(cat) ^ set(ROLES)}")
for r in ROLES:
    d = catalog.get(r)
    miss = [k for k in ("display", "node", "mission", "goals", "dod", "forbid", "owns")
            if not d.get(k)]
    check(f"{r:9} 필수 항목", not miss, f"빠짐 {miss}")
    check(f"{r:9} 완료 조건 3개 이상", len(d.get("dod") or []) >= 3,
          f"{len(d.get('dod') or [])}개")

print("\n[문장이 잘리지 않았나 — YAML 주석 사고 방지]")
for r in ROLES:
    d = catalog.get(r)
    bad = []
    for key in ("goals", "dod", "forbid"):
        for line in d.get(key) or []:
            s = str(line).rstrip()
            if s.endswith((",", "(", "·", "—", "및")) or s.count("(") != s.count(")"):
                bad.append(f"{key}: {s[:50]}")
    check(f"{r:9} 온전한 문장", not bad, f"{bad[:2]}")

print("\n[기준선 AGENT.md]")
bodies = {}
for r in ROLES:
    p = BASELINE / r / "AGENT.md"
    if not p.exists():
        check(f"{r:9} 기준선 존재", False, str(p))
        continue
    txt = p.read_text(encoding="utf-8")
    bodies[r] = txt
    miss = [s for s in SECTIONS if f"## {s}" not in txt]
    check(f"{r:9} 6칸 + 분량 ({len(txt)}자)",
          not miss and len(txt) >= 1200 and "## 이번 프로젝트" in txt,
          f"빠진 칸 {miss}" if miss else f"{len(txt)}자")
    check(f"{r:9} front-matter 없음", not txt.lstrip().startswith("---"))

dups = [(a, b) for i, a in enumerate(ROLES) for b in ROLES[i + 1:]
        if bodies.get(a) and bodies.get(a) == bodies.get(b)]
check("기준선 11개가 서로 다르다", not dups, f"{dups[:2]}")

print("\n[프롬프트에 붙는 요약 크기]")
for r in ROLES:
    b = catalog.brief(r)
    check(f"{r:9} brief {len(b)}자 (1500자 미만)", bool(b) and len(b) < 1500)

print("\n[기준선 + 이번 프로젝트 합성]")
block = "- **맡는 것**: 테스트 프로젝트에서 맡는 일.\n- **조심할 것**: 아무것도."
for r in ROLES:
    out = services.compose_spec(r, block)
    check(f"{r:9} 프로젝트 칸 삽입", block.splitlines()[0] in out)
legacy = "# x\n\n## 나의 역할\na\n\n## 내 파일\nb\n\n## 출력 형식\nc\n\n## 금지\nd\n\n## 애매할 때\ne\n"
check("기획이 전문을 보내와도 안 깨진다", bool(services.compose_spec("designer", legacy)))
check("빈 블록이면 기준선 그대로", services.compose_spec("qa", "") == bodies.get("qa", ""))

print("\n[산출물 검사기]")
sc = ROOT / "repo" / "showcase"
if (sc / "v1-before").exists() and (sc / "v2-after").exists():
    a = checks.score(checks.check("frontend", sc / "v1-before", {"screens": 5}))
    b = checks.score(checks.check("frontend", sc / "v2-after", {"screens": 5}))
    check(f"개선 전 {a[0]}/{a[1]} < 개선 후 {b[0]}/{b[1]}", b[0] > a[0])
    check("개선 후는 만점", b[0] == b[1], f"{b}")
else:
    print("  ⏭  showcase 보존본이 없어 건너뜀")

rep = checks.report([checks.Finding(False, "viewport 메타 태그", "", "meta 태그를 넣어라")])
check("실패 보고에 고치는 법이 들어간다",
      "viewport" in rep and "meta 태그를 넣어라" in rep)
check("전부 통과면 보고가 비어 있다", checks.report([checks.Finding(True, "ok")]) == "")

print("\n[사람이 끼워 넣는 지시]")
from app import directives                                     # noqa: E402
directives.write("", "designer")
directives.append("버튼을 작게", "designer", who="pm")
b = directives.block("designer")
check("지시가 프롬프트 블록으로 나온다", "버튼을 작게" in b)
check("최우선이라고 명시한다", "최우선" in b and "우선한다" in b)
check("항목으로도 뽑힌다", any("버튼을 작게" in x for x in directives.items("designer")))
directives.write("", "designer")
check("비우면 사라진다", directives.block("designer") == "")

print("\n[역할 경계 — 남의 파일을 만들지 않는가]")
import tempfile, shutil as _sh
tmp = pathlib.Path(tempfile.mkdtemp())
(tmp / "seed.sql").write_text("INSERT INTO product VALUES ('빵', 8500);\n" * 4, encoding="utf-8")
(tmp / "schema.sql").write_text(
    "CREATE TABLE product (id INTEGER PRIMARY KEY, name TEXT, price INTEGER);\n"
    "CREATE TABLE ord (id INTEGER PRIMARY KEY, pid INTEGER REFERENCES product(id), qty INTEGER);\n",
    encoding="utf-8")
clean = checks.check("dba", tmp, {})
check("DBA 가 SQL 만 내면 통과", all(f.ok for f in clean if "화면 파일" in f.label))

(tmp / "index.html").write_text("<html></html>", encoding="utf-8")
dirty = checks.check("dba", tmp, {})
web = [f for f in dirty if "화면 파일" in f.label]
check("DBA 가 index.html 을 내면 잡힌다", web and not web[0].ok,
      f"{[f.label for f in web]}")
check("고치는 법이 붙어 있다", web and "프론트엔드" in web[0].fix)
_sh.rmtree(tmp, ignore_errors=True)

# runner 가 남의 역할 파일을 실제로 걸러 내는가
from app import pipelines, runner as _runner
_s5 = pipelines.load("web_delivery").step("S5")
foreign = _runner._foreign_outputs(_s5, "dba")
check("S5 에서 dba 의 '남의 파일' 목록에 index.html 이 있다", "index.html" in foreign,
      f"{sorted(foreign)}")
check("자기 파일(seed.sql)은 안 들어 있다", "seed.sql" not in foreign)
check("frontend 기준으로는 seed.sql 이 남의 파일",
      "seed.sql" in _runner._foreign_outputs(_s5, "frontend"))

print(f"\n통과 {ok} · 실패 {ng}")
sys.exit(1 if ng else 0)
