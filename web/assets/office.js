/* 픽셀 오피스 — /api/dashboard 를 폴링해 화면을 그린다 (BRIEF §8).
   빌드 없음. 프레임워크 없음. CDN 없음. */

const POLL_MS = 2000;          // 인수 #26: 5초 내 반영
const AVATAR = {
  pm:"🧑‍💼", planner:"🧑‍🏫", sales:"🧑‍💻", sysadmin:"🧑‍🔧", designer:"🧑‍🎨",
  frontend:"🧑‍🚀", backend:"🧑‍🍳", dba:"🧑‍🌾", security:"🧑‍✈️",
  qa:"🧑‍🔬", customer:"🧑"
};
const ENV = { request:"📨", response:"📬", reject:"📕", mirror:"📄" };

let CUR = null;                 // 마지막 대시보드 데이터
let lastMsgId = 0;
let rewound = new Set();        // 되감김이 일어난 구간

const $ = (id) => document.getElementById(id);

async function api(path, opts) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" }, ...opts
  });
  const t = await r.text();
  try { return { ok: r.ok, body: JSON.parse(t) }; }
  catch { return { ok: r.ok, body: { error: t } }; }
}

/* ── 그리기 ─────────────────────────────────────────────── */
function drawHeader(d) {
  const c = d.cycle;
  if (!c) {
    $("c-title").textContent = "사이클 없음 — 주문을 넣으면 시작됩니다";
    $("c-status").textContent = "-";
    $("c-status").className = "badge";
    return;
  }
  const step = d.steps.find(s => s.key === c.current_step);
  $("c-title").textContent =
    `사이클 #${c.id} · ${c.pipeline} · ${c.attempt_no}회차` +
    (step ? ` · ${step.key} ${step.name}` : "");
  $("c-status").textContent = c.status;
  $("c-status").className = "badge " + c.status;

  const running = c.status === "RUNNING";
  $("btn-pause").disabled  = !running;
  $("btn-resume").disabled = !["PAUSED","BLOCKED","READY","FAILED"].includes(c.status);
  $("btn-step").disabled   = !["PAUSED","READY"].includes(c.status);
}

function drawDesks(d) {
  const byRole = d.specs.by_role || {};
  $("desks").innerHTML = d.nodes.map(n => {
    const spec = byRole[n.role];
    const badge = spec
      ? `<div class="spec ${spec}">${spec === "customized" ? "✅ AGENT.md" : "⏳ AGENT.md 대기"}</div>`
      : "";
    return `<a class="desk ${n.status} ${n.busy ? "busy" : ""}"
      href="/agent.html?role=${n.role}" title="${n.display_name} 상세 보기">
      <span class="dot"></span>
      <div class="avatar">${AVATAR[n.role] || "🧑"}</div>
      <div class="role">${n.display_name}</div>
      <div class="en">${n.role}</div>
      <div class="host">${n.dgx_host || "-"}</div>
      ${badge}
    </a>`;
  }).join("");

  const s = d.specs;
  const el = $("spec-counter");
  if (s && s.total) {
    el.hidden = false;
    el.textContent = `AGENT.md ${s.customized} / ${s.total}`;
    el.classList.toggle("full", s.customized >= s.total);
  } else { el.hidden = true; }
}

function drawRooms(d) {
  const cur = d.cycle && d.cycle.current_step;
  const st = (k) => (d.steps.find(s => s.key === k) || {}).status;
  ["S6","S7","S8","S9"].forEach(k => {
    const el = $("room-" + k);
    if (!el) return;
    el.classList.toggle("on", cur === k || st(k) === "RUNNING");
    el.classList.toggle("alarm", st(k) === "FAILED");
  });

  const t = d.tickets || {};
  const list = (t.list || []).filter(x => x.status !== "done").slice(0, 4);
  $("tickets").innerHTML =
    `<div>티켓 · 할일 ${t.todo || 0} / 진행 ${t.doing || 0} / 완료 ${t.done || 0}</div>` +
    list.map(x => `<div class="t"><b>${x.title}</b><br>${x.reason || ""}</div>`).join("");
}

function drawMessages(d) {
  const ul = $("messages");
  const msgs = d.messages || [];
  ul.innerHTML = msgs.slice(-25).reverse().map(m => `
    <li class="${m.kind}">
      <span class="env">${ENV[m.kind] || "📄"}</span>
      <span class="who">${m.from} → ${m.to}</span>
      <span>${m.summary || ""}</span>
    </li>`).join("");
  if (msgs.length) lastMsgId = msgs[msgs.length - 1].id;
}

/* 에이전트들이 만들어낸 실제 웹사이트 — 배포 결과물을 바로 열어 본다 */
async function drawSites() {
  const el = $("sites");
  if (!el) return;
  try {
    const { body } = await api("/preview/sites");
    const list = (body && body.data) || [];
    const top = $("site-top");
    if (top) {
      if (list.length) { top.hidden = false; top.href = list[0].url; }
      else top.hidden = true;
    }
    el.innerHTML = `<div class="hd">완성된 사이트</div>` + (list.length
      ? list.slice(0, 4).map(s =>
          `<a href="${s.url}" target="_blank" rel="noopener">🌐 ${s.role || s.step || "site"}
             <span class="sub">${s.files}개 · ${Math.round(s.size / 1024)}KB</span></a>`).join("")
      : `<div class="none">아직 만들어진 사이트가 없습니다.</div>`);
  } catch (e) {}
}

function drawOrders(d) {
  $("orders").innerHTML = (d.orders || []).slice(0, 6).map(o =>
    `<div class="o"><span class="kind ${o.kind}">${o.kind}</span>${o.title}</div>`
  ).join("") || `<div class="o">주문 없음</div>`;
}

/* ★ 타임라인 — 되감기가 일어나면 화살표를 역방향으로 그린다 */
function drawTimeline(d) {
  const tl = $("timeline");
  if (!d.steps.length) { tl.innerHTML = ""; return; }
  const cur = d.cycle && d.cycle.current_step;

  const parts = [];
  d.steps.forEach((s, i) => {
    if (i > 0) {
      const prev = d.steps[i - 1].key;
      const back = rewound.has(`${prev}<-${s.key}`) || rewound.has(`${s.key}<-${prev}`);
      parts.push(`<div class="tl-arrow ${back ? "rewound" : ""}">${back ? "⟵" : "─"}</div>`);
    }
    const isRewound = rewound.has(s.key);
    parts.push(`<div class="tl-step ${s.status} ${s.type ? "gate" : ""}
        ${s.key === cur ? "cur" : ""} ${isRewound ? "rewound" : ""}"
        title="${s.name}${s.error ? " — " + s.error : ""}">
      <div class="k">${s.key}</div><div class="n">${s.name}</div>
    </div>`);
  });
  tl.innerHTML = parts.join("");
}

/* 되감기 흔적 기록 — 진행하던 단계보다 뒤로 갔으면 그 구간을 표시한다 */
let lastStepKey = null;
function trackRewind(d) {
  const c = d.cycle;
  if (!c || !c.current_step) return;
  const idx = (k) => d.steps.findIndex(s => s.key === k);
  if (lastStepKey && idx(c.current_step) < idx(lastStepKey)) {
    rewound.add(`${c.current_step}<-${lastStepKey}`);
    for (let i = idx(c.current_step); i <= idx(lastStepKey); i++) {
      rewound.add(d.steps[i].key);
    }
    setTimeout(() => { rewound.clear(); }, 20000);   // 20초 뒤 흔적을 지운다
  }
  lastStepKey = c.current_step;
}

async function tick() {
  try {
    const { body } = await api("/api/dashboard");
    if (!body || !body.data) return;
    CUR = body.data;
    trackRewind(CUR);
    drawHeader(CUR); drawDesks(CUR); drawRooms(CUR);
    drawMessages(CUR); drawOrders(CUR); drawTimeline(CUR); drawSites();
  } catch (e) { /* 폴링은 절대 죽지 않는다 */ }
}

/* ── 컨트롤 ─────────────────────────────────────────────── */
function cid() { return CUR && CUR.cycle ? CUR.cycle.id : null; }

async function post(path, body) {
  const id = cid();
  if (!id) return alert("사이클이 없습니다.");
  const r = await api(`/api/cycles/${id}${path}`, {
    method: "POST", body: JSON.stringify(body || {})
  });
  if (r.body && r.body.data && r.body.data.note) console.log(r.body.data.note);
  tick();
}

$("btn-pause").onclick  = () => post("/pause");
$("btn-resume").onclick = () => post("/resume");
$("btn-step").onclick   = () => post("/step");

$("btn-rewind").onclick = () => {
  if (!CUR || !CUR.steps.length) return;
  $("rewind-opts").innerHTML = CUR.steps.map((s, i) =>
    `<label><input type="radio" name="sk" value="${s.key}" ${i === 0 ? "checked" : ""}>
       ${s.key}</label>`).join("");
  $("dlg-rewind").showModal();
};
$("dlg-rewind").addEventListener("close", () => {
  if ($("dlg-rewind").returnValue !== "ok") return;
  const sel = document.querySelector('#rewind-opts input:checked');
  if (sel) post("/rewind", { step_key: sel.value });
});

$("btn-reset").onclick = () => {
  document.querySelector('#dlg-reset input[value="true"]').checked = true;  // 기본값 '유지'
  $("dlg-reset").showModal();
};
$("dlg-reset").addEventListener("close", () => {
  if ($("dlg-reset").returnValue !== "ok") return;
  const keep = document.querySelector('#dlg-reset input[name=keep]:checked').value === "true";
  if (!keep && !confirm("학생들이 고친 AGENT.md 가 모두 사라집니다. 정말 진행할까요?")) return;
  post("/reset", { keep_specs: keep });
});

tick();
setInterval(tick, POLL_MS);
