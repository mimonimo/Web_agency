"""산출물 (BRIEF §3.5, §7).

모든 step 산출물은 아래 경로에만 쓴다. 재실행은 덮어쓴다.

    repo/runs/{cycle_id}/{step_id}/output/...
    repo/runs/{cycle_id}/{step_id}/report.md     ← 에이전트 완료 보고
    repo/project-001/...                          ← 확정 산출물(step DONE 시 승격)

step 을 두 번 돌려도 결과가 같아야 한다 (인수 #23). rewind/reset 의 전제다.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Artifact, Step
from ..services import REPO_ROOT

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])
files_router = APIRouter(prefix="/api/files", tags=["artifacts"])


def _safe(path: str):
    """repo/ 밖으로 나가지 못하게 한다."""
    target = (REPO_ROOT / path).resolve()
    try:
        target.relative_to(REPO_ROOT.resolve())
    except ValueError:
        raise HTTPException(400, "repo/ 밖의 경로는 다룰 수 없다")
    return target


# 보여주지 않을 것 — DB·로그·백업·git 내부
HIDE = {".git", ".archive", "agora.db", "agora.db-shm", "agora.db-wal",
        "hq.log", "boot.log", "__pycache__"}
TEXT_EXT = {".md", ".txt", ".yaml", ".yml", ".json", ".sql", ".sh", ".py",
            ".js", ".css", ".html", ".env", ".diff", ".log", ".toml", ".ini", ""}


@files_router.get("/tree")
async def file_tree(path: str = Query("", description="repo/ 기준 상대 경로")):
    """repo/ 안을 훑는다. 웹에서 산출물을 바로 찾아보게 하는 용도."""
    target = _safe(path)
    if not target.exists():
        raise HTTPException(404, f"그런 경로가 없다: {path}")
    if target.is_file():
        return {"ok": True, "data": {"path": path, "type": "file",
                                     "size": target.stat().st_size}}

    items = []
    for p in sorted(target.iterdir(), key=lambda x: (x.is_file(), x.name)):
        if p.name in HIDE or p.name.startswith("."):
            continue
        rel = str(p.relative_to(REPO_ROOT))
        st = p.stat()
        if p.is_dir():
            n = sum(1 for _ in p.rglob("*") if _.is_file())
            items.append({"name": p.name, "path": rel, "type": "dir",
                          "count": n, "mtime": st.st_mtime})
        else:
            items.append({"name": p.name, "path": rel, "type": "file",
                          "size": st.st_size, "mtime": st.st_mtime,
                          "editable": p.suffix.lower() in TEXT_EXT,
                          "viewable": p.suffix.lower() in VIEW_EXT})
    parent = str(pathlib_parent(path)) if path else None
    has_index = (target / "index.html").is_file()
    return {"ok": True, "data": {
        "path": path, "parent": parent, "items": items,
        # 이 폴더가 웹사이트면 바로 열 수 있게 알려 준다
        "site_url": f"/preview/{path}/index.html" if has_index and path else None,
    }}


VIEW_EXT = {".html", ".htm", ".css", ".js", ".json", ".svg", ".png", ".jpg",
            ".jpeg", ".gif", ".webp", ".md", ".txt"}


class NewFile(BaseModel):
    path: str
    content: str = ""


@files_router.post("")
async def create_file(body: NewFile, db: Session = Depends(get_db)):
    """새 파일(또는 폴더)을 만든다.

    사람이 산출물을 손으로 보태야 할 때가 있다 — 에이전트가 빠뜨린 파일,
    수업 중에 급히 끼워 넣는 예시 데이터. 웹에서 끝낼 수 있어야 한다.
    경로가 `/` 로 끝나면 폴더를 만든다.
    """
    rel = body.path.strip().lstrip("/")
    if not rel:
        raise HTTPException(400, "경로를 적어라")
    target = _safe(rel)
    if body.path.rstrip().endswith("/"):
        target.mkdir(parents=True, exist_ok=True)
        from .. import services
        services.audit(db, "pm", "file.mkdir", rel, {})
        db.commit()
        return {"ok": True, "data": {"path": rel, "type": "dir"}}
    if target.exists():
        raise HTTPException(409, f"이미 있는 파일이다: {rel}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.content, encoding="utf-8")
    from .. import services
    services.audit(db, "pm", "file.create", rel, {"bytes": len(body.content)})
    db.commit()
    return {"ok": True, "data": {"path": rel, "type": "file"}}


def pathlib_parent(path: str) -> str:
    from pathlib import PurePosixPath
    p = PurePosixPath(path).parent
    return "" if str(p) == "." else str(p)


@files_router.put("", response_class=PlainTextResponse)
async def write_file(path: str = Query(...),
                     body: str = Body(..., media_type="text/plain"),
                     db: Session = Depends(get_db)):
    """웹에서 산출물을 직접 고친다. 고친 사실은 감사 로그에 남는다."""
    target = _safe(path)
    if not target.exists():
        raise HTTPException(404, f"그런 파일이 없다: {path}")
    if not body.strip():
        raise HTTPException(400, "빈 내용은 저장할 수 없다")
    target.write_text(body, encoding="utf-8")
    from .. import services
    services.audit(db, "pm", "file.edit", path, {"bytes": len(body)})
    db.commit()
    return "저장했다"


preview_router = APIRouter(prefix="/preview", tags=["preview"], include_in_schema=False)

MIME = {
    ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",   ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".ico": "image/x-icon",
    ".woff": "font/woff", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
}


@preview_router.get("/sites")
async def list_sites():
    """에이전트들이 만든 **완성된 웹 페이지**를 찾아 목록으로 준다.

    프론트엔드가 어느 경로에 index.html 을 만들지 미리 알 수 없으므로
    repo/ 안을 훑어 index.html 이 있는 디렉터리를 전부 모은다.
    """
    sites = []
    for idx in sorted(REPO_ROOT.rglob("index.html")):
        rel = idx.relative_to(REPO_ROOT)
        parts = rel.parts
        if any(p in ("node_modules", ".git", ".archive", "__pycache__") for p in parts):
            continue
        d = rel.parent
        cycle = step = role = None
        if parts and parts[0] == "runs" and len(parts) >= 3:
            cycle, step = parts[1], parts[2]
            if len(parts) >= 5 and parts[3] == "output":
                role = parts[4] if not parts[4].endswith(".html") else None
        files = [f for f in idx.parent.rglob("*")
                 if f.is_file() and "node_modules" not in f.parts]
        sites.append({
            "dir": str(d), "url": f"/preview/{d}/index.html",
            "cycle": cycle, "step": step, "role": role,
            "files": len(files),
            "size": sum(f.stat().st_size for f in files),
            "mtime": idx.stat().st_mtime,
        })
    sites.sort(key=lambda s: s["mtime"], reverse=True)
    return {"ok": True, "data": sites}


@preview_router.get("/{path:path}")
async def preview(path: str):
    """만들어진 사이트를 브라우저에서 그대로 열어 본다.

    repo/ 밖으로는 절대 나갈 수 없다. 읽기 전용이다.
    """
    from fastapi.responses import FileResponse, Response
    target = (REPO_ROOT / path).resolve()
    try:
        target.relative_to(REPO_ROOT.resolve())
    except ValueError:
        raise HTTPException(400, "repo/ 밖의 경로는 열 수 없다")
    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        raise HTTPException(404, f"그런 파일이 없다: {path}")
    mime = MIME.get(target.suffix.lower(), "application/octet-stream")
    if mime.startswith(("text/", "application/javascript", "application/json")):
        return Response(target.read_text(encoding="utf-8", errors="replace"),
                        media_type=mime)
    return FileResponse(target, media_type=mime)


@files_router.get("", response_class=PlainTextResponse)
async def read_file(path: str = Query(..., description="repo/ 기준 상대 경로")):
    """노드가 참고 자료(SRS.md, schema.sql 등)를 읽어가는 주소.

    ⚠️ repo/ 밖으로는 절대 나갈 수 없다. 경로 탈출을 막는다.
    """
    target = (REPO_ROOT / path).resolve()
    try:
        target.relative_to(REPO_ROOT.resolve())
    except ValueError:
        raise HTTPException(400, "repo/ 밖의 경로는 읽을 수 없다")
    if not target.is_file():
        # 확정 산출물 쪽도 한 번 더 찾아본다
        alt = (REPO_ROOT / "project-001" / path).resolve()
        try:
            alt.relative_to(REPO_ROOT.resolve())
        except ValueError:
            raise HTTPException(400, "repo/ 밖의 경로는 읽을 수 없다")
        if not alt.is_file():
            raise HTTPException(404, f"그런 파일이 없다: {path}")
        target = alt
    return target.read_text(encoding="utf-8", errors="replace")


@router.get("")
async def list_artifacts(cycle: int | None = Query(None),
                         step: str | None = Query(None),
                         db: Session = Depends(get_db)):
    q = select(Artifact).order_by(Artifact.id.desc()).limit(200)
    if cycle:
        q = q.where(Artifact.cycle_id == cycle)
    arts = list(db.scalars(q).all())
    if step and cycle:
        keys = {s.id for s in db.scalars(
            select(Step).where(Step.cycle_id == cycle, Step.step_key == step)).all()}
        arts = [a for a in arts if a.step_id in keys]
    return {"ok": True, "data": [
        {"id": a.id, "cycle_id": a.cycle_id, "role": a.role, "path": a.path,
         "ts": a.ts.isoformat() if a.ts else None}
        for a in arts
    ]}


@router.get("/{artifact_id}/raw", response_class=PlainTextResponse)
async def get_artifact_raw(artifact_id: int, db: Session = Depends(get_db)):
    a = db.get(Artifact, artifact_id)
    if a is None:
        raise HTTPException(404, f"산출물 {artifact_id} 을 찾을 수 없다")
    p = REPO_ROOT / a.path
    if not p.exists():
        raise HTTPException(404, f"파일이 없다: {a.path}")
    return p.read_text(encoding="utf-8", errors="replace")
