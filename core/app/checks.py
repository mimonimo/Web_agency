"""산출물이 완료 조건(DoD)을 지켰는지 **기계로** 검사한다.

## 왜 이게 있는가

이 수업의 목표는 "좋은 모델을 붙이면 좋은 결과가 나온다" 가 아니다.
**어떤 모델을 붙여도 결과의 바닥이 유지되는 것**이다.

모델에게 "viewport 를 넣어라" 라고 부탁하는 것과, 넣었는지 확인하고 안 넣었으면
그 사실을 알려 주며 다시 시키는 것은 완전히 다른 일이다.
전자는 부탁이고 후자는 계약이다. 작은 모델에게 필요한 것은 계약이다.

    지시(프롬프트)  →  실행  →  ★검사(여기)  →  실패하면 사유를 붙여 재실행
                                                └ 2회까지. 그래도 안 되면 게이트로 넘긴다.

## 게이트와 무엇이 다른가

| | 이 검사 | QA·보안 게이트 |
|---|---|---|
| 누가 | HQ 코드 | 에이전트(모델) |
| 무엇을 | 형식·존재·수치 | 의미·수용 기준 |
| 언제 | 단계가 끝난 직후 | 단계가 다 끝난 뒤 |
| 실패하면 | 그 역할만 즉시 재실행 | 되감기 + 티켓 |

기계가 볼 수 있는 것은 기계가 본다. 그래야 게이트 에이전트가
"viewport 가 없다" 같은 걸 찾느라 힘을 빼지 않고 진짜 문제를 본다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    ok: bool
    label: str          # 무엇을 봤나
    detail: str = ""    # 실패했을 때 무엇이 문제인가
    fix: str = ""       # 어떻게 고치나 (재실행 프롬프트에 그대로 들어간다)

    def line(self) -> str:
        s = f"- {self.label}"
        if self.detail:
            s += f" — {self.detail}"
        if self.fix:
            s += f"\n  → {self.fix}"
        return s


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _find(d: Path, name: str) -> Path | None:
    """산출물 디렉터리에서 파일을 찾는다. 하위 폴더에 들어가 있어도 찾아 준다."""
    direct = d / name
    if direct.is_file():
        return direct
    hits = [p for p in d.rglob(name)
            if p.is_file() and "node_modules" not in p.parts]
    return hits[0] if hits else None


def _joined(d: Path, pattern: str, exclude: tuple[str, ...] = ()) -> str:
    return "\n".join(_read(p) for p in sorted(d.rglob(pattern))
                     if p.is_file() and p.name not in exclude
                     and "node_modules" not in p.parts)


# ── 역할별 검사 ────────────────────────────────────────────────────────
def _designer(d: Path) -> list[Finding]:
    f: list[Finding] = []
    tok = _find(d, "design-tokens.json")
    if tok is None:
        return [Finding(False, "design-tokens.json 이 없다", "",
                        "`design-tokens.json` 을 output/ 바로 아래에 만들어라")]
    raw = _read(tok)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return [Finding(False, "design-tokens.json 이 올바른 JSON 이 아니다", str(e),
                        "따옴표·쉼표를 확인하고 순수 JSON 으로만 써라")]

    flat: dict[str, str] = {}
    def walk(o, ):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, (dict, list)):
                    walk(v)
                else:
                    flat[str(k)] = str(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data)

    colors = [v for v in flat.values() if re.fullmatch(r"#[0-9a-fA-F]{3,8}", v.strip())]
    spaces = [k for k in flat if "space" in k.lower() or "spacing" in k.lower()]
    fonts = [k for k in flat if "font" in k.lower() or "text" in k.lower()]
    f.append(Finding(len(colors) >= 6, f"색 {len(colors)}개 (6개 이상 필요)",
                     f"{len(colors)}개", "primary·bg·surface·text·muted·danger 를 채워라"))
    f.append(Finding(len(spaces) >= 4, f"간격 단계 {len(spaces)}개 (4단계 이상 필요)",
                     f"{len(spaces)}개", "xs·sm·md·lg 네 단계를 정의해라"))
    f.append(Finding(len(fonts) >= 4, f"글자 크기 단계 {len(fonts)}개 (4단계 이상 필요)",
                     f"{len(fonts)}개", "sm·md·lg·xl 네 단계를 정의해라"))
    default_colors = re.findall(r"#(?:4CAF50|45a049|0066CC|2196F3|008CBA|337ab7)",
                                raw, re.I)
    f.append(Finding(not default_colors, "기본 색에 의존하지 않는다",
                     f"{default_colors[:2]}",
                     "주문서의 톤&매너에서 도출한 색으로 바꿔라. 기본 파랑·초록은 반려된다"))
    f.append(Finding(any(k.startswith("--") for k in flat),
                     "토큰 이름이 CSS 변수 형태(--color-…)다", "",
                     "키를 `--color-primary` 처럼 두 하이픈으로 시작하게 써라"))
    g = _find(d, "UI-GUIDE.md")
    f.append(Finding(g is not None and len(_read(g)) > 300,
                     "UI-GUIDE.md 에 컴포넌트 규칙이 있다", "",
                     "버튼·입력창·카드 규칙과 색을 고른 근거를 300자 이상 써라"))
    return f


def _frontend(d: Path, screens: int = 0) -> list[Finding]:
    idx = _find(d, "index.html")
    if idx is None:
        return [Finding(False, "index.html 이 없다", "",
                        "`index.html` 을 output/ 바로 아래에 만들어라")]
    html = _read(idx)
    css = _joined(d, "*.css")
    js = _joined(d, "*.js", exclude=("server.js",))
    f: list[Finding] = []

    f.append(Finding('name="viewport"' in html, "viewport 메타 태그", "",
                     '<meta name="viewport" content="width=device-width, initial-scale=1"> 를 <head> 에 넣어라'))
    sem = [t for t in ("<header", "<nav", "<main", "<section", "<footer")
           if t in html.lower()]
    f.append(Finding(len(sem) >= 3, f"시맨틱 태그 {len(sem)}/5", ",".join(sem) or "0개",
                     "<header> <nav> <main> <section> <footer> 로 문서 뼈대를 잡아라"))
    nvar = len(re.findall(r"--[a-z0-9-]+\s*:", css))
    uvar = len(re.findall(r"var\(--", css))
    f.append(Finding(nvar >= 6, f"CSS 변수 정의 {nvar}개 (6개 이상)", f"{nvar}개",
                     "style.css 맨 위 :root 에 디자인 토큰을 변수로 선언해라"))
    f.append(Finding(uvar >= 6, f"CSS 변수 사용 {uvar}회 (6회 이상)", f"{uvar}회",
                     "색·간격을 직접 쓰지 말고 var(--x) 로 받아 써라"))
    # 정의 없이 쓰는 변수 — 색이 통째로 안 먹는 가장 흔한 사고
    used = set(re.findall(r"var\((--[a-z0-9-]+)", css))
    defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", css))
    orphan = sorted(used - defined)
    f.append(Finding(not orphan, "쓰는 변수가 전부 정의돼 있다",
                     f"정의 없음: {orphan[:4]}",
                     "같은 파일 :root 에 그 변수를 정의해라. 파일을 나누면 링크가 깨진다"))
    flat_css = css.replace(" ", "")
    f.append(Finding("display:flex" in flat_css or "display:grid" in flat_css,
                     "flex/grid 레이아웃", "", "<br> 나열 대신 flex 또는 grid 로 배치해라"))
    br = html.lower().count("<br")
    f.append(Finding(br <= 2, f"<br> 로 폼을 배치하지 않음", f"{br}개",
                     "<br> 를 지우고 CSS 로 간격을 줘라"))
    inputs = len(re.findall(r"<(?:input|select|textarea)\b", html, re.I))
    labels = len(re.findall(r"<label\b[^>]*\bfor=", html, re.I))
    f.append(Finding(inputs == 0 or labels >= inputs,
                     f"label 이 입력 수를 덮음 ({labels}/{inputs})", f"{labels}/{inputs}",
                     "모든 input·select 에 <label for=\"...\"> 를 붙여라"))
    imgs = re.findall(r"<img\b[^>]*>", html, re.I)
    f.append(Finding(all("alt=" in i for i in imgs), "모든 img 에 alt", f"{len(imgs)}개",
                     "img 마다 alt 를 써라"))
    f.append(Finding(not re.search(r"<div[^>]*onclick", html, re.I),
                     "클릭되는 div 없음", "", "<div onclick> 을 <button> 으로 바꿔라"))
    ext = re.findall(r'(?:src|href)=["\'](https?://[^"\']+)', html)
    f.append(Finding(not ext, "외부 리소스 참조 없음", f"{len(ext)}건 {ext[:2]}",
                     "교실에 인터넷이 없다. CDN·구글폰트를 지우고 직접 작성해라"))
    f.append(Finding(len(js.strip()) >= 200, f"app.js 동작 ({len(js.strip())}자)",
                     f"{len(js.strip())}자",
                     "버튼을 눌렀을 때 실제로 무언가 일어나게 app.js 를 채워라"))
    f.append(Finding(not re.search(r"\bTODO\b|lorem ipsum|여기에 내용", html + css + js, re.I),
                     "자리표시자 없음", "", "TODO·lorem ipsum 을 실제 내용으로 바꿔라"))
    sections = len(re.findall(r"<section\b", html, re.I))
    if screens:
        f.append(Finding(sections >= max(2, screens // 2),
                         f"화면 {sections}개 (SCREENS.md 목표 {screens}개)",
                         f"{sections}/{screens}",
                         "SCREENS.md 의 화면을 <section> 으로 전부 만들어라"))
    # 두 겹 폴더 — 링크가 통째로 깨진다
    nested = [p for p in d.rglob("index.html") if p.parent != d]
    f.append(Finding(not nested, "output/ 바로 아래 평평하게 둠",
                     str(nested[0].relative_to(d)) if nested else "",
                     "하위 폴더를 만들지 말고 index.html·style.css·app.js 를 나란히 둬라"))
    return f


def _backend(d: Path) -> list[Finding]:
    f: list[Finding] = _no_web_files(d, "백엔드")
    api = _find(d, "api-contract.yaml") or _find(d, "api-contract.yml")
    srv = _find(d, "server.js")
    if api is not None:
        t = _read(api)
        f.append(Finding(len(t) > 200, "api-contract.yaml 에 내용이 있다", f"{len(t)}자",
                         "엔드포인트마다 method·path·요청 예시·응답 예시를 써라"))
        f.append(Finding('"ok"' in t or "ok:" in t, "공통 응답 형식(ok/data)이 명시됨", "",
                         '성공 {"ok":true,"data":{}} / 실패 {"ok":false,"error":"..."} 로 통일해라'))
    if srv is not None:
        s = _read(srv)
        ext = [m for m in re.findall(r"require\(['\"]([^'\"]+)", s)
               if not m.startswith(".") and m not in {
                   "http", "https", "fs", "path", "url", "crypto", "os",
                   "querystring", "events", "stream", "zlib", "util", "buffer"}]
        f.append(Finding(not ext, "외부 패키지를 쓰지 않는다", f"{ext[:3]}",
                         "교실에 인터넷이 없다. Node 표준 모듈만 써라 (express 금지)"))
        f.append(Finding('"ok"' in s or "ok:" in s, "응답에 ok 필드가 있다", "",
                         '{"ok":true,"data":...} 형식으로 응답해라'))
        f.append(Finding("stack" not in s.lower() or "err.stack" not in s,
                         "스택 트레이스를 노출하지 않는다", "",
                         "err.stack 대신 한국어 안내 문구로 감싸라"))
        rp = _find(d, "README.md")
        f.append(Finding(rp is not None and len(_read(rp)) > 150,
                         "README.md 에 실행 방법이 있다", "",
                         "실행 명령과 엔드포인트 목록을 README.md 에 써라"))
    if api is None and srv is None:
        f.append(Finding(False, "api-contract.yaml / server.js 가 없다", "",
                         "이 단계에서 만들어야 할 파일을 output/ 아래에 만들어라"))
    return f


def _no_web_files(d: Path, role: str) -> list[Finding]:
    """화면 파일을 만들지 않았는가.

    ★ DBA 가 `seed.sql` 만 내야 하는데 사이트 한 벌을 통째로 만든 일이 있었다.
      같은 파일이 두 벌 생기면 어느 것이 진짜인지 아무도 모른다.
    """
    bad = [p.name for p in d.rglob("*")
           if p.is_file() and p.suffix.lower() in (".html", ".htm", ".css")]
    return [Finding(not bad, "화면 파일을 만들지 않았다", f"{bad[:3]}",
                    f"{role} 는 화면을 만들지 않는다. 그건 프론트엔드의 일이다. "
                    f"html·css 파일을 지우고 내 산출물만 내라")]


def _dba(d: Path) -> list[Finding]:
    f: list[Finding] = _no_web_files(d, "DBA")
    sc = _find(d, "schema.sql")
    sd = _find(d, "seed.sql")
    if sc is not None:
        s = _read(sc)
        tables = re.findall(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"']?(\w+)",
                            s, re.I)
        pk = len(re.findall(r"PRIMARY\s+KEY", s, re.I))
        f.append(Finding(len(tables) >= 2, f"테이블 {len(tables)}개", f"{tables}",
                         "SRS 의 명사(주문·상품…)마다 테이블을 만들어라"))
        f.append(Finding(pk >= len(tables) and len(tables) > 0,
                         f"모든 테이블에 기본키 ({pk}/{len(tables)})", f"{pk}/{len(tables)}",
                         "테이블마다 PRIMARY KEY 를 넣어라"))
        f.append(Finding(bool(re.search(r"REFERENCES|FOREIGN\s+KEY", s, re.I))
                         or len(tables) < 2, "관계에 외래키가 있다", "",
                         "참조하는 컬럼에 REFERENCES 를 붙여라"))
        cols = re.findall(r"^\s*\w+\s+(\w+)", s, re.M)
        texty = sum(1 for c in cols if c.upper() in ("TEXT", "VARCHAR", "STRING"))
        f.append(Finding(not cols or texty < len(cols),
                         "모든 컬럼이 TEXT 가 아니다", f"TEXT {texty}/{len(cols)}",
                         "금액은 INTEGER, 시각은 DATE/TIMESTAMP 로 써라. 타입이 곧 검증이다"))
        f.append(Finding(not re.search(r"\b(password|passwd|pwd|ssn|jumin)\b\s+(TEXT|VARCHAR)",
                                       s, re.I),
                         "비밀번호 평문 컬럼 없음", "",
                         "password 대신 password_hash 로 만들어라"))
    if sd is not None:
        n = len(re.findall(r"INSERT\s+INTO", _read(sd), re.I))
        vals = len(re.findall(r"\(\s*'", _read(sd)))
        f.append(Finding(n >= 1 and vals >= 3, f"시드 데이터 {vals}건", f"{vals}건",
                         "화면당 3건 이상, 주문서의 실제 상품명·가격으로 채워라"))
    if sc is None and sd is None:
        f.append(Finding(False, "schema.sql / seed.sql 이 없다", "",
                         "이 단계에서 만들어야 할 파일을 output/ 아래에 만들어라"))
    return f


def _sysadmin(d: Path) -> list[Finding]:
    f: list[Finding] = []
    run = _find(d, "run.sh")
    if run is not None:
        s = _read(run)
        bad = re.findall(r"(npm\s+(?:install|i|ci)|pip3?\s+install|apt(?:-get)?\s+install)", s)
        f.append(Finding(not bad, "인터넷 없이 동작한다", f"{bad[:2]}",
                         "설치 명령을 지워라. 교실에 인터넷이 없다"))
        f.append(Finding(len(s) > 80, "run.sh 에 실행 내용이 있다", f"{len(s)}자",
                         "실제로 서비스를 띄우는 명령을 써라"))
    for name, need in (("DEPLOY.md", ("실행", "포트", "확인")),
                       ("DEPLOY-LOG.md", ("$",))):
        p = _find(d, name)
        if p is None:
            continue
        t = _read(p)
        miss = [k for k in need if k not in t]
        f.append(Finding(not miss, f"{name} 에 필요한 내용이 있다", f"빠짐: {miss}",
                         "실행 방법·포트·확인 방법·되돌리는 방법을 쓰고, "
                         "실제로 친 명령과 그 출력을 붙여라"))
    if run is None and _find(d, "DEPLOY.md") is None and _find(d, "DEPLOY-LOG.md") is None:
        f.append(Finding(False, "배포 산출물이 없다", "",
                         "ops/run.sh 와 DEPLOY.md(또는 DEPLOY-LOG.md)를 만들어라"))
    return f


def _planner(d: Path) -> list[Finding]:
    f: list[Finding] = []
    srs = _find(d, "SRS.md")
    scr = _find(d, "SCREENS.md")
    if srs is not None:
        t = _read(srs)
        feats = re.findall(r"^##\s*F-?\s*\d+", t, re.M) or re.findall(r"^##\s+\S", t, re.M)
        crit = len(re.findall(r"^\s*-\s*\[\s*\]", t, re.M))
        f.append(Finding(len(feats) >= 3, f"기능 항목 {len(feats)}개", f"{len(feats)}개",
                         "주문서의 필요 기능 하나하나를 `## F-1` 형식으로 나눠라"))
        f.append(Finding(crit >= 2 * max(1, len(feats)),
                         f"수용 기준 {crit}개 (기능당 2개 이상)", f"{crit}개",
                         "기능마다 `- [ ]` 수용 기준을 2개 이상 붙여라"))
        vague = re.findall(r"잘 동작|적절히|빠르게|사용자 친화|편리하게", t)
        f.append(Finding(not vague, "모호한 표현 없음", f"{vague[:3]}",
                         "QA 가 그대로 실행할 수 있는 문장으로 바꿔라"))
    else:
        f.append(Finding(False, "SRS.md 가 없다", "", "요구사항 명세를 만들어라"))
    if scr is not None:
        n = len(re.findall(r"^##\s+\S", _read(scr), re.M))
        f.append(Finding(n >= 3, f"화면 {n}개 (3개 이상)", f"{n}개",
                         "필요한 화면을 `## 화면이름` 으로 나누고 "
                         "보이는 것/할 수 있는 것/이동을 적어라"))
    else:
        f.append(Finding(False, "SCREENS.md 가 없다", "", "화면 목록을 만들어라"))
    return f


def _sales(d: Path) -> list[Finding]:
    f: list[Finding] = []
    sow = _find(d, "SOW.md")
    if sow is None:
        return [Finding(False, "SOW.md 가 없다", "", "작업 범위 기술서를 만들어라")]
    t = _read(sow)
    f.append(Finding("포함" in t, "포함 범위가 있다", "", "`## 포함 범위` 를 써라"))
    has_ex = "제외" in t
    f.append(Finding(has_ex, "제외 범위가 있다", "",
                     "`## 제외 범위` 를 써라. 안 적으면 전부 포함이 된다"))
    if has_ex:
        tail = t.split("제외", 1)[1]
        n = len([ln for ln in tail.splitlines()
                 if re.match(r"^\s*(?:[-*]|\d+\.)\s+\S", ln)])
        f.append(Finding(n >= 3, f"제외 항목 {n}개 (3개 이상)", f"{n}개",
                         "안 하기로 한 것을 3개 이상 구체적으로 적어라"))
    q = _find(d, "QUOTE.md")
    f.append(Finding(q is not None and len(_read(q)) > 100, "QUOTE.md 에 견적이 있다", "",
                     "작업 항목별 금액과 합계를 표로 써라"))
    return f


def _verdict(d: Path, role: str) -> list[Finding]:
    p = _find(d, "VERDICT.md")
    if p is None:
        return [Finding(False, "VERDICT.md 가 없다", "",
                        "첫 줄에 `판정: 통과` 또는 `판정: 반려` 를 쓴 VERDICT.md 를 만들어라")]
    t = _read(p).strip()
    first = t.splitlines()[0].strip() if t else ""
    f = [Finding(bool(re.match(r"^판정\s*[:：]\s*(통과|반려)\s*$", first)),
                 "첫 줄이 판정이다", f"실제: {first[:40]!r}",
                 "첫 줄을 정확히 `판정: 통과` 또는 `판정: 반려` 로 써라. "
                 "HQ 가 이 줄을 읽어 자동 처리한다")]
    f.append(Finding(len(t) >= 400, f"판정서 분량 {len(t)}자 (400자 이상)", f"{len(t)}자",
                     "무엇을 확인했는지, 무엇이 문제인지 파일명과 함께 구체적으로 써라"))
    rejected = "반려" in first
    if rejected:
        body = "\n".join(t.splitlines()[1:])
        f.append(Finding(len(body.strip()) >= 200, "반려 사유가 구체적이다", "",
                         "어느 파일 어느 부분이 왜 문제인지 3줄 이상 써라. "
                         "이 내용이 그대로 재작업 티켓이 된다"))
    if role == "qa":
        f.append(Finding(bool(re.search(r"기대|실제|재현", t)), "재현 절차가 있다", "",
                         "실패 항목마다 [무엇을 했을 때][기대][실제] 를 써라"))
    if role == "security":
        seen = sum(1 for k in ("비밀번호", "검증", "에러", "하드코딩", "외부")
                   if k in t)
        f.append(Finding(seen >= 3, f"확인 항목 {seen}/5", f"{seen}/5",
                         "비밀번호 저장·입력 검증·에러 노출·하드코딩된 비밀값·"
                         "외부 리소스를 각각 확인하고 기록해라"))
    return f


def _pm(d: Path) -> list[Finding]:
    p = _find(d, "STATUS.md")
    if p is None:
        return [Finding(False, "STATUS.md 가 없다", "", "단계별 상태 표를 만들어라")]
    t = _read(p)
    return [Finding(t.count("|") >= 8, "상태가 표로 정리돼 있다", "",
                    "단계·상태·담당·다음 행동을 표로 써라")]


def _feedback(d: Path) -> list[Finding]:
    p = _find(d, "FEEDBACK.md")
    if p is None:
        return []
    t = _read(p)
    n = len(re.findall(r"^##\s+\S", t, re.M))
    return [Finding(n >= 1 and len(t) > 200, f"문의 {n}건", f"{n}건 / {len(t)}자",
                    "실제 화면을 보고 나온 문의를 구체적으로 써라. "
                    "다음 사이클의 주문으로 바로 쓸 수 있어야 한다")]


_ROLE_CHECKS = {
    "designer": lambda d, c: _designer(d),
    "frontend": lambda d, c: _frontend(d, c.get("screens", 0)),
    "backend": lambda d, c: _backend(d),
    "dba": lambda d, c: _dba(d),
    "sysadmin": lambda d, c: _sysadmin(d),
    "planner": lambda d, c: _planner(d),
    "sales": lambda d, c: _sales(d),
    "qa": lambda d, c: _verdict(d, "qa"),
    "security": lambda d, c: _verdict(d, "security"),
    "customer": lambda d, c: _verdict(d, "customer") + _feedback(d),
    "pm": lambda d, c: _pm(d),
}


def check(role: str, out_dir: Path, ctx: dict | None = None) -> list[Finding]:
    """역할의 산출물을 검사한다. 검사할 것이 없으면 빈 목록."""
    fn = _ROLE_CHECKS.get(role)
    if fn is None or not out_dir.exists():
        return []
    try:
        return fn(out_dir, ctx or {})
    except Exception as e:            # 검사가 터져서 사이클을 멈추면 안 된다
        return [Finding(True, f"검사 생략 ({type(e).__name__})")]


def failures(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if not f.ok]


def report(findings: list[Finding]) -> str:
    """재실행 프롬프트에 붙일 실패 목록."""
    bad = failures(findings)
    if not bad:
        return ""
    return (
        "## ★ 방금 낸 산출물이 완료 조건을 못 지켰다 — 고쳐서 다시 내라\n\n"
        + "\n".join(f.line() for f in bad)
        + "\n\n**위 항목만 고쳐라.** 통과한 부분은 그대로 두고, "
          "같은 파일 이름으로 전체를 다시 내라."
    )


def score(findings: list[Finding]) -> tuple[int, int]:
    return sum(1 for f in findings if f.ok), len(findings)
