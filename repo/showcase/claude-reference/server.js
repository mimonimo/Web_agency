/* 별빛공방 API + 정적 서버 (S5 백엔드)
 *
 * Node 표준 모듈만 쓴다. express 를 쓰지 않는다 — 교실에 인터넷이 없다.
 * 응답 형식은 api-contract.yaml 그대로:
 *   성공  {"ok": true,  "data": ...}
 *   실패  {"ok": false, "error": "사람이 읽을 한국어"}
 *
 * ★ 입력 검증은 화면과 서버 **양쪽**에서 한다. 브라우저 검증은 우회된다.
 */
"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");
const url = require("url");

const PORT = Number(process.env.PORT || 8080);
const ROOT = __dirname;

// ── 데이터 (seed.sql 과 같은 내용을 메모리로) ──────────────────
// DB 연결은 이번 범위 밖이다. schema.sql 대로 옮기면 그대로 동작한다.
const CLASSES = [
  { id: 1, name: "물레 체험 — 그릇 하나", price: 45000, minutes: 120, capacity: 4,
    description: "발물레에 앉아 흙을 올리고 그릇 하나를 완성합니다. 처음이어도 괜찮습니다." },
  { id: 2, name: "손으로 빚는 컵", price: 38000, minutes: 90, capacity: 6,
    description: "물레 없이 손으로만 빚습니다. 투박한 맛이 남는 컵을 만듭니다." },
  { id: 3, name: "유약 놀이 — 접시 채색", price: 32000, minutes: 80, capacity: 6,
    description: "초벌된 접시에 유약으로 그림을 그립니다. 아이와 함께 오기 좋습니다." },
  { id: 4, name: "커플 클래스 (2인)", price: 85000, minutes: 150, capacity: 2,
    description: "둘이 마주 앉아 각자 하나씩 만듭니다. 가격은 2인 기준입니다." }
];
const TIMES = ["10:00", "14:00", "19:00"];

const bookings = [
  { code: "BB-20260812-001", klassId: 1, date: "2026-08-12", time: "10:00", people: 2, name: "한지우", tel: "010-3312-8890" },
  { code: "BB-20260812-002", klassId: 3, date: "2026-08-12", time: "14:00", people: 4, name: "오세림", tel: "010-5521-4417" },
  { code: "BB-20260813-001", klassId: 2, date: "2026-08-13", time: "19:00", people: 3, name: "문가온", tel: "010-8834-2201" }
];
const inquiries = [];

// ── 응답 헬퍼 ─────────────────────────────────────────────────
function ok(res, data) { send(res, 200, { ok: true, data }); }
function bad(res, message, code) { send(res, code || 400, { ok: false, error: message }); }
function send(res, status, body) {
  const s = JSON.stringify(body);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(s),
    "Cache-Control": "no-store"
  });
  res.end(s);
}

// ── 검증 ──────────────────────────────────────────────────────
function klassOf(id) { return CLASSES.find((c) => c.id === Number(id)) || null; }

function isMonday(d) { return new Date(d + "T00:00:00").getDay() === 1; }

function isPast(d) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  return new Date(d + "T00:00:00") < today;
}

function taken(klassId, date, time) {
  return bookings
    .filter((b) => b.klassId === Number(klassId) && b.date === date && b.time === time)
    .reduce((s, b) => s + b.people, 0);
}

/** 예약 요청을 본다. 문제가 있으면 사람이 읽을 문장을 돌려준다. */
function validateBooking(b) {
  if (!b || typeof b !== "object") return "요청 형식이 올바르지 않습니다";
  const c = klassOf(b.klassId);
  if (!c) return "그런 클래스가 없습니다";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(b.date || ""))) return "날짜를 골라 주세요";
  if (isPast(b.date)) return "오늘 이후 날짜를 골라 주세요";
  if (isMonday(b.date)) return "월요일은 휴무입니다";
  if (TIMES.indexOf(b.time) < 0) return "시간을 골라 주세요";
  if (!Number.isInteger(b.people) || b.people < 1) return "인원을 1명 이상으로 적어 주세요";
  if (b.people > c.capacity) return "정원은 " + c.capacity + "명입니다";
  const left = c.capacity - taken(b.klassId, b.date, b.time);
  if (b.people > left) return "남은 자리는 " + left + "명입니다";
  if (!String(b.name || "").trim()) return "이름을 적어 주세요";
  if (String(b.tel || "").replace(/\D/g, "").length < 9) return "연락처를 확인해 주세요";
  return null;
}

function nextCode(date) {
  const n = bookings.filter((b) => b.date === date).length + 1;
  return "BB-" + date.replace(/-/g, "") + "-" + String(n).padStart(3, "0");
}

// ── 정적 파일 ─────────────────────────────────────────────────
const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".md": "text/plain; charset=utf-8"
};

function serveStatic(req, res, pathname) {
  const rel = pathname === "/" ? "/index.html" : pathname;
  // 경로 탈출 차단 — 사용자가 준 경로를 그대로 열지 않는다
  const target = path.normalize(path.join(ROOT, rel));
  if (!target.startsWith(ROOT)) return bad(res, "잘못된 경로입니다", 400);
  fs.readFile(target, (err, buf) => {
    if (err) { res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" }); return res.end("없는 페이지입니다"); }
    res.writeHead(200, { "Content-Type": MIME[path.extname(target)] || "application/octet-stream" });
    res.end(buf);
  });
}

// ── 라우팅 ────────────────────────────────────────────────────
const server = http.createServer((req, res) => {
  const u = url.parse(req.url, true);
  const p = u.pathname;

  try {
    if (!p.startsWith("/api/")) return serveStatic(req, res, p);

    if (req.method === "GET" && p === "/api/classes") {
      return ok(res, CLASSES.map((c) => ({
        id: c.id, name: c.name, price: c.price, minutes: c.minutes, capacity: c.capacity
      })));
    }

    let m = p.match(/^\/api\/classes\/(\d+)$/);
    if (req.method === "GET" && m) {
      const c = klassOf(m[1]);
      return c ? ok(res, c) : bad(res, "그런 클래스가 없습니다", 404);
    }

    if (req.method === "GET" && p === "/api/slots") {
      const { klassId, date } = u.query;
      const c = klassOf(klassId);
      if (!c) return bad(res, "그런 클래스가 없습니다", 404);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(String(date || ""))) return bad(res, "날짜를 골라 주세요");
      if (isMonday(date)) return bad(res, "월요일은 휴무입니다");
      return ok(res, TIMES.map((t) => ({ time: t, left: c.capacity - taken(c.id, date, t) })));
    }

    m = p.match(/^\/api\/bookings\/([A-Za-z0-9-]+)$/);
    if (req.method === "GET" && m) {
      const b = bookings.find((x) => x.code.toUpperCase() === m[1].toUpperCase());
      if (!b) return bad(res, "그런 예약번호가 없습니다", 404);
      const c = klassOf(b.klassId);
      return ok(res, { code: b.code, klass: c.name, date: b.date, time: b.time,
                       people: b.people, name: b.name });
    }

    if (req.method === "POST" && (p === "/api/bookings" || p === "/api/inquiries")) {
      let body = "";
      req.on("data", (ch) => {
        body += ch;
        if (body.length > 8192) { req.destroy(); }      // 과대 요청 차단
      });
      req.on("end", () => {
        let data;
        try { data = JSON.parse(body || "{}"); }
        catch (e) { return bad(res, "요청 형식이 올바르지 않습니다"); }

        if (p === "/api/inquiries") {
          if (!String(data.name || "").trim()) return bad(res, "이름을 적어 주세요");
          if (String(data.tel || "").replace(/\D/g, "").length < 9) return bad(res, "연락처를 확인해 주세요");
          if (String(data.body || "").trim().length < 10) return bad(res, "문의 내용을 조금 더 적어 주세요");
          inquiries.push({ name: data.name, tel: data.tel, body: data.body, at: new Date().toISOString() });
          return ok(res, { received: true });
        }

        const why = validateBooking(data);
        if (why) return bad(res, why);
        const c = klassOf(data.klassId);
        const rec = {
          code: nextCode(data.date), klassId: c.id, date: data.date, time: data.time,
          people: data.people, name: String(data.name).trim(), tel: String(data.tel).trim()
        };
        bookings.push(rec);
        return ok(res, { code: rec.code, price: c.price * (c.id === 4 ? 1 : rec.people) });
      });
      return;
    }

    return bad(res, "없는 주소입니다", 404);
  } catch (e) {
    // ★ 스택 트레이스를 그대로 뱉지 않는다. 상세는 서버 로그에만.
    console.error("[server]", e);
    return bad(res, "요청을 처리하지 못했습니다", 400);
  }
});

server.listen(PORT, () => {
  console.log("별빛공방 → http://localhost:" + PORT + "/");
});
