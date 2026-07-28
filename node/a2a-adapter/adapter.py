#!/usr/bin/env python3
"""AGORA 노드 A2A 어댑터 (BRIEF §5.5).

Hermes 를 A2A 에이전트로 감싸는 얇은 래퍼. 하는 일은 네 가지뿐이다.

    1. 에이전트 카드 노출
    2. message/send 수신 → spec_url 로 AGENT.md 받아오기
    3. Hermes CLI 를 **작업 디렉터리를 제한한 상태로** 실행
    4. 산출물 수집 → tasks/get 응답 + HQ 미러링

의존성 없음 — 파이썬 표준 라이브러리만 쓴다. 학생 노드에 pip 설치가 필요 없고
`python3 adapter.py` 한 줄로 뜬다. 인터넷이 없는 교실에서 이게 가장 안전하다.

와이어 포맷은 A2A 와 글자 그대로 같다 (JSON-RPC 2.0, message/send, tasks/get).
나중에 표준 SDK 로 갈아끼울 수 있다 — ops/wheels/README.md 참조.

    사용법:  python3 adapter.py            # node.env 를 읽는다
             python3 adapter.py --port 41241
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ── 설정 ───────────────────────────────────────────────────────────────
HOME = Path.home()
NODE_ENV = HOME / "agora" / "node.env"


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if NODE_ENV.exists():
        for line in NODE_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


ENV = load_env()
ROLE = os.getenv("AGORA_ROLE", ENV.get("AGORA_ROLE", "unknown"))
NODE_ID = os.getenv("AGORA_NODE_ID", ENV.get("AGORA_NODE_ID", "unknown"))
DISPLAY = ENV.get("AGORA_DISPLAY_NAME", ROLE)
HQ = os.getenv("AGORA_HQ_URL", ENV.get("AGORA_HQ_URL", "http://220.67.5.62:8000"))
MODEL = ENV.get("AGORA_MODEL", "gpt-oss:120b")
WORKROOT = Path(ENV.get("AGORA_WORKSPACE", str(HOME / "agora" / "workspace")))
HERMES = str(HOME / ".local" / "bin" / "hermes")

# 산출물 하나가 이보다 크면 잘라서 보낸다 (교실 네트워크 보호)
MAX_ARTIFACT_BYTES = 256 * 1024

TASKS: dict[str, dict] = {}
LOCK = threading.Lock()


# ── HQ 통신 ────────────────────────────────────────────────────────────
def http_json(url: str, payload: dict | None = None, timeout: int = 15):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
    return json.loads(body) if body.strip().startswith(("{", "[")) else body


def http_text(url: str, timeout: int = 15) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def mirror(to_role: str, kind: str, summary: str, cycle_id=None) -> None:
    """모든 메시지는 HQ 에 미러링한다. 안 하면 픽셀 오피스에 안 그려진다 (BRIEF §5.3)."""
    try:
        http_json(f"{HQ}/api/messages", {
            "from_role": ROLE, "to_role": to_role, "kind": kind,
            "summary": summary[:500], "cycle_id": cycle_id,
        }, timeout=8)
    except Exception:
        pass


# ── 에이전트 카드 (BRIEF §5.2) ─────────────────────────────────────────
SKILLS_BY_ROLE = {
    "sales":     [("intake", "요구사항 접수·범위 판단"), ("intake_change", "변경 범위·비용 산정")],
    "planner":   [("draft_specs", "요구사항 해석 + AGENT.md 초안"), ("revise_specs", "변경 반영")],
    "designer":  [("design", "화면·디자인 토큰 설계")],
    "dba":       [("design", "스키마 설계"), ("implement", "DB 구현"), ("fix", "결함 수정")],
    "backend":   [("design", "API 계약 설계"), ("implement", "서버 구현"), ("fix", "결함 수정")],
    "frontend":  [("implement", "화면 구현"), ("fix", "결함 수정")],
    "sysadmin":  [("design", "운영 설계"), ("deploy", "배포")],
    "qa":        [("gate", "QA 게이트"), ("reproduce", "결함 재현")],
    "security":  [("gate", "보안 게이트"), ("assess", "위협 평가")],
    "customer":  [("gate", "고객 검수"), ("generate_feedback", "문의·클레임 생성")],
    "pm":        [("gate", "관리 판단")],
}


def agent_card(host: str) -> dict:
    return {
        "name": f"agora-{ROLE}",
        "description": f"AGORA Web {DISPLAY} 담당",
        "url": f"http://{host}/",
        "version": "1.0",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [
            {"id": sid, "name": name, "tags": [sid]}
            for sid, name in SKILLS_BY_ROLE.get(ROLE, [("work", "작업")])
        ],
        "provider": {"organization": "AGORA Web", "node": NODE_ID},
    }


# ── Hermes 실행 ────────────────────────────────────────────────────────
def build_prompt(spec: str, params: dict, ctx: dict[str, str], outdir: Path) -> str:
    """AGENT.md 를 먼저 읽힌 뒤 작업 지시를 붙인다 (BRIEF §4.3)."""
    outputs = params.get("outputs") or []
    parts = [
        "너는 웹에이전시 AGORA Web 의 팀원이다.",
        "아래는 **너의 지시문(AGENT.md)** 이다. 반드시 이 지시를 따라라.",
        "",
        "════════ AGENT.md 시작 ════════",
        spec.strip(),
        "════════ AGENT.md 끝 ════════",
        "",
        "## 이번 작업",
        f"- 사이클: {params.get('cycle_id')}",
        f"- 단계: {params.get('step_id')}  ({params.get('step_name', '')})",
        f"- 태스크: {params.get('task')}",
        "",
    ]

    # ★ 주문서 원문. 이게 없으면 에이전트가 고객사를 지어낸다.
    order = (params.get("order") or "").strip()
    if order:
        parts += [
            "## 고객이 낸 주문서 — 이것이 유일한 사실이다",
            "```",
            order[:6000],
            "```",
            "⚠️ 위 주문서에 없는 회사명·기능·기술스택을 만들어내지 마라.",
            "",
        ]

    # ★ 이 태스크의 지시 (BRIEF §4.1 의 템플릿)
    instruction = (params.get("instruction") or "").strip()
    if instruction:
        parts += ["## 해야 할 일", instruction, ""]

    if ctx:
        parts.append("## 참고 자료")
        for name, body in ctx.items():
            parts.append(f"### {name}")
            parts.append(body[:8000])
            parts.append("")

    parts += [
        "## 반드시 지킬 것",
        "- 산출물은 현재 디렉터리 아래 `output/` 에만 쓴다. 다른 경로는 건드리지 마라.",
    ]
    if outputs:
        names = ", ".join(o for o in outputs if "*" not in o)
        if names:
            parts.append(f"- `output/` 아래 이 파일들을 만든다: {names}")
    parts += [
        "- 각 파일은 실제로 쓸 수 있는 내용이어야 한다. 자리표시자만 넣지 마라.",
        "- 다 끝나면 `report.md` 에 무엇을 만들었고 남은 이슈가 무엇인지 적는다.",
        "- 한국어로 쓴다.",
        "",
        "지금 바로 파일을 만들어라. 설명만 하지 말고 실제로 써라.",
    ]
    return "\n".join(parts)


def run_hermes(workdir: Path, prompt: str, timeout: int) -> tuple[bool, str]:
    """작업 디렉터리를 제한한 상태로 Hermes 를 돌린다 (BRIEF §5.5-3)."""
    env = dict(os.environ)
    env["HOME"] = str(HOME)
    env["PATH"] = f"{HOME}/.local/bin:" + env.get("PATH", "")
    try:
        p = subprocess.run(
            [HERMES, "-z", prompt, "--yolo", "--no-restore-cwd"],
            cwd=str(workdir), env=env, capture_output=True, text=True,
            timeout=timeout,
        )
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode == 0, out[-8000:]
    except subprocess.TimeoutExpired:
        return False, f"Hermes 시간 초과 ({timeout}초)"
    except FileNotFoundError:
        return False, f"Hermes 를 찾을 수 없다: {HERMES}"


def collect(outdir: Path) -> list[dict]:
    arts = []
    if not outdir.exists():
        return arts
    for p in sorted(outdir.rglob("*")):
        if not p.is_file():
            continue
        try:
            body = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        arts.append({
            "name": str(p.relative_to(outdir)),
            "size": p.stat().st_size,
            "text": body[:MAX_ARTIFACT_BYTES],
            "truncated": p.stat().st_size > MAX_ARTIFACT_BYTES,
        })
    return arts


# ── 태스크 실행 ────────────────────────────────────────────────────────
def work(task_id: str, params: dict) -> None:
    cyc = params.get("cycle_id")
    step = params.get("step_id", "S?")
    timeout = int(params.get("timeout_sec", 900))

    # work_key 가 있으면 그걸 쓴다. 같은 step 을 역할별로 여러 번 부를 때
    # 앞 호출의 산출물이 섞이지 않게 하려는 것이다.
    key = str(params.get("work_key") or step)
    workdir = WORKROOT / f"cycle-{cyc}" / key
    outdir = workdir / "output"
    outdir.mkdir(parents=True, exist_ok=True)

    def finish(state: str, **kw):
        with LOCK:
            TASKS[task_id].update({"state": state, "ended": time.time(), **kw})

    try:
        # 2. spec_url 로 AGENT.md 받아오기
        spec = ""
        if params.get("spec_url"):
            try:
                spec = http_text(params["spec_url"], timeout=20)
            except Exception as e:
                spec = ""
                mirror("hq", "response", f"{step} AGENT.md 를 못 읽었다: {e}", cyc)
        if not spec.strip():
            spec = f"# 나는 AGORA Web 의 {DISPLAY} 담당이다\n(지시문을 받지 못했다)"

        (workdir / "AGENT.md").write_text(spec, encoding="utf-8")

        # 참고 자료
        ctx: dict[str, str] = {}
        for url in (params.get("context_urls") or []):
            try:
                ctx[url.rsplit("/", 1)[-1]] = http_text(url, timeout=20)
            except Exception:
                pass

        prompt = build_prompt(spec, params, ctx, outdir)
        (workdir / "prompt.txt").write_text(prompt, encoding="utf-8")

        mirror("hq", "response", f"{step} 착수 — 모델 {MODEL}", cyc)

        # 3. Hermes 실행
        okrun, log = run_hermes(workdir, prompt, timeout)
        (workdir / "hermes.log").write_text(log, encoding="utf-8")

        # 4. 산출물 수집
        arts = collect(outdir)

        # 에이전트가 report.md 를 안 썼으면 어댑터가 최소한의 보고를 남긴다
        report = workdir / "report.md"
        if not any(a["name"] == "report.md" for a in arts) and not report.exists():
            report.write_text(
                f"# {step} 완료 보고\n\n- 역할: {ROLE} ({DISPLAY})\n"
                f"- 모델: {MODEL}\n- 산출물 {len(arts)}건\n"
                f"- Hermes 종료: {'정상' if okrun else '오류'}\n",
                encoding="utf-8")

        if not arts and not okrun:
            finish("failed", error=f"산출물이 없다. {log[-500:]}")
            mirror("hq", "response", f"{step} 실패 — 산출물 없음", cyc)
            return

        finish("completed", artifacts=arts,
               report=(report.read_text(encoding="utf-8") if report.exists() else ""))
        mirror("hq", "response", f"{step} 완료 — 산출물 {len(arts)}건", cyc)

    except Exception:
        finish("failed", error=traceback.format_exc()[-2000:])
        mirror("hq", "response", f"{step} 어댑터 오류", cyc)


# ── HTTP ───────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):        # 로그를 조용히
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/.well-known/agent-card.json"):
            self._send(agent_card(self.headers.get("Host", "localhost")))
        elif self.path.startswith("/health"):
            self._send({"ok": True, "role": ROLE, "node": NODE_ID, "model": MODEL})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            self._send({"jsonrpc": "2.0", "error":
                        {"code": -32700, "message": "JSON 파싱 실패"}, "id": None}, 400)
            return

        rid = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}

        # ── message/send ────────────────────────────────────────────
        if method == "message/send":
            task_id = str(uuid.uuid4())
            with LOCK:
                TASKS[task_id] = {"state": "working", "started": time.time(),
                                  "params": params}
            threading.Thread(target=work, args=(task_id, params), daemon=True).start()
            self._send({"jsonrpc": "2.0", "id": rid,
                        "result": {"taskId": task_id, "state": "working"}})
            return

        # ── tasks/get ───────────────────────────────────────────────
        if method == "tasks/get":
            tid = params.get("taskId") or params.get("id")
            with LOCK:
                t = TASKS.get(tid)
            if t is None:
                self._send({"jsonrpc": "2.0", "id": rid,
                            "error": {"code": -32001, "message": "그런 태스크가 없다"}})
                return
            self._send({"jsonrpc": "2.0", "id": rid, "result": {
                "taskId": tid, "state": t["state"],
                "artifacts": t.get("artifacts", []),
                "report": t.get("report", ""),
                "error": t.get("error"),
            }})
            return

        # ── tasks/cancel ────────────────────────────────────────────
        if method == "tasks/cancel":
            tid = params.get("taskId")
            with LOCK:
                if tid in TASKS:
                    TASKS[tid]["state"] = "canceled"
            self._send({"jsonrpc": "2.0", "id": rid, "result": {"canceled": True}})
            return

        self._send({"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32601, "message": f"모르는 메서드: {method}"}})


def register(port: int) -> None:
    """HQ 에 자기 자신을 등록한다 (인수 #5·#6)."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "127.0.0.1"
    url = f"http://{ip}:{port}/"
    for _ in range(3):
        try:
            http_json(f"{HQ}/api/nodes/register", {
                "role": ROLE, "a2a_url": url, "dgx_host": NODE_ID,
                "card": agent_card(f"{ip}:{port}"),
            }, timeout=10)
            print(f"[adapter] HQ 등록 완료 — {ROLE} @ {url}", flush=True)
            return
        except Exception as e:
            print(f"[adapter] HQ 등록 실패: {e}", flush=True)
            time.sleep(5)


def heartbeat_loop() -> None:
    while True:
        try:
            http_json(f"{HQ}/api/nodes/{ROLE}/heartbeat", {}, timeout=8)
        except Exception:
            pass
        time.sleep(30)


def main() -> None:
    ap = argparse.ArgumentParser(description="AGORA 노드 A2A 어댑터")
    ap.add_argument("--port", type=int, default=41241)
    a = ap.parse_args()

    WORKROOT.mkdir(parents=True, exist_ok=True)
    print(f"[adapter] role={ROLE} node={NODE_ID} hq={HQ} model={MODEL}", flush=True)

    threading.Thread(target=lambda: (time.sleep(1), register(a.port)), daemon=True).start()
    threading.Thread(target=heartbeat_loop, daemon=True).start()

    srv = ThreadingHTTPServer(("0.0.0.0", a.port), Handler)
    print(f"[adapter] 0.0.0.0:{a.port} 에서 대기", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
