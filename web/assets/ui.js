/* AGORA Web 공통 UI — 내비게이션 · API 헬퍼 · 알림
 *
 * 화면마다 상단 바를 손으로 복사해 두었더니 페이지가 늘 때마다 링크가 빠졌다.
 * 여기 한 군데서 만든다. 페이지를 추가하면 PAGES 에만 넣으면 된다.
 *
 * CDN 없음 — 교실에 인터넷이 없다. */

const PAGES = [
  ["/index.html",    "🏢 오피스",   "지금 누가 무엇을 하고 있나"],
  ["/console.html",  "🖥 실시간 콘솔", "에이전트가 지금 무엇을 하고 있나"],
  ["/review.html",   "👀 보고 고치기", "만들어진 화면을 보면서 바로 수정 요청"],
  ["/projects.html", "📦 작업물",   "작업별 결과물 — 메인·서브 페이지"],
  ["/agent.html",    "🧑‍💻 에이전트", "역할별 현황·지시·재요청"],
  ["/edit.html",     "📝 AGENT.md", "역할 지시문 편집 (학생)"],
  ["/board.html",    "🎫 티켓",     "반려·재작업 티켓"],
  ["/files.html",    "🗂 파일",     "repo/ 탐색기"],
  ["/order.html",    "🧾 주문 접수", "새 일 시작"],
];

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
const sz = (n) => n < 1024 ? `${n}B`
  : n < 1048576 ? `${(n / 1024).toFixed(1)}KB` : `${(n / 1048576).toFixed(1)}MB`;

/** API 호출. 실패하면 서버가 준 한국어 메시지를 그대로 던진다. */
async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  const ct = r.headers.get("content-type") || "";
  const body = ct.includes("json") ? await r.json().catch(() => null) : await r.text();
  if (!r.ok) {
    const msg = (body && body.detail) || (typeof body === "string" && body) || `HTTP ${r.status}`;
    throw new Error(msg);
  }
  return (body && typeof body === "object" && "data" in body) ? body.data : body;
}

/** 상단 내비게이션을 그린다. 현재 페이지는 강조된다. */
function nav(extraHTML = "") {
  const here = location.pathname.replace(/\/$/, "/index.html");
  const links = PAGES.map(([href, label, title]) =>
    `<a class="navlink${href === here ? " on" : ""}" href="${href}" title="${esc(title)}">${label}</a>`
  ).join("");
  const bar = document.createElement("header");
  bar.className = "bar navbar";
  bar.innerHTML =
    `<a class="brand" href="/index.html" style="text-decoration:none;color:inherit">AGORA<span>Web</span></a>
     <nav class="navlinks">${links}</nav>
     <div class="navextra">${extraHTML}</div>`;
  document.body.prepend(bar);
  return bar;
}

/** 오른쪽 아래에 잠깐 뜨는 알림. 조작 결과를 반드시 눈에 보이게 한다. */
function toast(msg, kind = "ok", ms = 4200) {
  let box = $("toastbox");
  if (!box) {
    box = document.createElement("div");
    box.id = "toastbox";
    document.body.appendChild(box);
  }
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = esc(msg).replace(/\n/g, "<br>");
  box.appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; setTimeout(() => el.remove(), 400); }, ms);
}

/** 버튼을 누르는 동안 잠그고, 끝나면 결과를 알린다. */
async function act(btn, fn, okMsg) {
  const old = btn.textContent;
  btn.disabled = true; btn.dataset.busy = "1"; btn.textContent = "…";
  try {
    const r = await fn();
    toast(okMsg || (r && r.note) || "완료", "ok");
    return r;
  } catch (e) {
    toast(e.message || String(e), "bad", 7000);
    throw e;
  } finally {
    btn.disabled = false; delete btn.dataset.busy; btn.textContent = old;
  }
}

/** 현재 사이클 요약 — 여러 화면이 상단에 같은 것을 띄운다. */
async function cycleBadge(el) {
  try {
    const d = await api("/api/dashboard");
    if (!d.cycle) { el.innerHTML = `<span class="muted">사이클 없음</span>`; return null; }
    el.innerHTML =
      `<span class="muted">사이클 #${d.cycle.id}</span>
       <span class="badge ${d.cycle.status}">${d.cycle.status}</span>
       <span class="muted">${esc(d.cycle.current_step || "")}</span>`;
    return d;
  } catch { el.innerHTML = ""; return null; }
}

/* ── 역할 선택기 ────────────────────────────────────────────────────
 * 다섯 화면이 각자 다르게 그리고 있던 것을 하나로 모았다.
 * 어느 화면에서 역할을 고르든 같은 모양·같은 동작이고,
 * **화면을 옮겨도 고른 역할이 따라간다** (URL 의 ?role= 로 이어받는다).
 * 매번 다시 고르게 만드는 것이 가장 흔한 불편이다. */

let _role = new URLSearchParams(location.search).get("role") || null;

/** 지금 보고 있는 역할. 없으면 기본값을 준다. */
function currentRole(fallback = null) { return _role || fallback; }

/** 역할을 유지한 채 다른 화면으로 가는 주소. */
function withRole(href, role = _role) {
  if (!role) return href;
  const u = new URL(href, location.origin);
  u.searchParams.set("role", role);
  return u.pathname + u.search;
}

/**
 * 역할 칩 줄을 그린다.
 *   roleBar(el, {roles, onPick, badge, dot})
 *     roles  [{role, display_name, ...}]
 *     onPick 고르면 부르는 함수. 없으면 agent.html 로 이동한다.
 *     badge  (r) => 숫자|"" — 칩 오른쪽에 뱃지
 *     dot    (r) => true|false — 왼쪽 점(노드 살아 있음)
 */
function roleBar(el, { roles = [], onPick = null, badge = null, dot = null } = {}) {
  el.classList.add("rolebar");
  el.innerHTML = roles.map((r) => {
    const id = r.role || r;
    const ko = r.display_name || id;
    const n = badge ? badge(id) : "";
    const up = dot ? dot(id) : null;
    return `<button data-r="${id}" class="${id === _role ? "on" : ""}" title="${esc(ko)}">
      ${up === null ? "" : `<i class="dot${up ? " up" : ""}"></i>`}
      <b>${esc(ko)}</b><span class="en">${esc(id)}</span>
      ${n ? `<em>${n}</em>` : ""}
    </button>`;
  }).join("");
  el.querySelectorAll("button").forEach((b) => b.onclick = () => {
    _role = b.dataset.r;
    const u = new URL(location.href);
    u.searchParams.set("role", _role);
    history.replaceState(null, "", u.pathname + u.search);
    el.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    if (onPick) onPick(_role);
    else location.href = `/agent.html?role=${_role}`;
    // 내비게이션 링크도 역할을 이어받게 갱신
    document.querySelectorAll("a[data-keeprole]").forEach((a) =>
      a.href = withRole(a.dataset.keeprole));
  });
  document.querySelectorAll("a[data-keeprole]").forEach((a) =>
    a.href = withRole(a.dataset.keeprole));
  return el;
}
