/* 별빛공방 — 화면 전환 · 예약 접수 · 조회 · 문의
 *
 * 서버 없이도 동작한다 (예약은 localStorage 에 남는다).
 * server.js 가 뜬 환경이면 api-contract.yaml 대로 그쪽을 쓴다.
 * 외부 라이브러리 없음 — 교실에 인터넷이 없다.
 */
(function () {
  "use strict";

  // ── 데이터 (dba 의 seed.sql 과 같은 내용) ─────────────────────
  var CLASSES = [
    { id: 1, name: "물레 체험 — 그릇 하나", price: 45000, minutes: 120, cap: 4,
      desc: "발물레에 앉아 흙을 올리고 그릇 하나를 완성합니다. 처음이어도 괜찮습니다.",
      prep: ["앞치마는 공방에 있습니다", "손톱은 짧게", "소매가 넓지 않은 옷"] },
    { id: 2, name: "손으로 빚는 컵", price: 38000, minutes: 90, cap: 6,
      desc: "물레 없이 손으로만 빚습니다. 투박한 맛이 남는 컵을 만듭니다.",
      prep: ["앞치마 제공", "반지·시계는 빼 주세요"] },
    { id: 3, name: "유약 놀이 — 접시 채색", price: 32000, minutes: 80, cap: 6,
      desc: "초벌된 접시에 유약으로 그림을 그립니다. 아이와 함께 오기 좋습니다.",
      prep: ["앞치마 제공", "8세 이상 참여 가능"] },
    { id: 4, name: "커플 클래스 (2인)", price: 85000, minutes: 150, cap: 2,
      desc: "둘이 마주 앉아 각자 하나씩 만듭니다. 가격은 2인 기준입니다.",
      prep: ["2인 1팀으로 신청해 주세요", "앞치마 제공"] }
  ];
  var TIMES = ["10:00", "14:00", "19:00"];
  var KEY_BOOK = "byeolbit.bookings";
  var KEY_ASK = "byeolbit.asks";

  // ── 도구 ──────────────────────────────────────────────────────
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function won(n) { return n.toLocaleString("ko-KR") + "원"; }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m];
    });
  }
  function load(key) {
    try { return JSON.parse(localStorage.getItem(key)) || []; }
    catch (e) { return []; }
  }
  function save(key, v) {
    try { localStorage.setItem(key, JSON.stringify(v)); } catch (e) { /* 사파리 비공개 모드 */ }
  }
  function klassOf(id) {
    for (var i = 0; i < CLASSES.length; i++) if (CLASSES[i].id === Number(id)) return CLASSES[i];
    return null;
  }

  // ── 화면 전환 ─────────────────────────────────────────────────
  function go(name) {
    $$(".screen").forEach(function (s) { s.classList.toggle("is-active", s.id === name); });
    $$(".nav-link").forEach(function (b) {
      b.classList.toggle("is-current", b.dataset.go === name);
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
  }
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-go]");
    if (!t) return;
    e.preventDefault();
    go(t.dataset.go);
  });

  // ── 1. 클래스 목록 ────────────────────────────────────────────
  $("#class-grid").innerHTML = CLASSES.map(function (c) {
    return '<li><button type="button" class="class-card" data-klass="' + c.id + '">' +
      "<h3>" + esc(c.name) + "</h3>" +
      '<p class="price">' + won(c.price) + "</p>" +
      '<div class="meta">' +
        '<span class="tag">' + c.minutes + "분</span>" +
        '<span class="tag">정원 ' + c.cap + "명</span>" +
      "</div>" +
      '<p class="desc">' + esc(c.desc) + "</p>" +
      "</button></li>";
  }).join("");

  $$("[data-klass]").forEach(function (b) {
    b.addEventListener("click", function () { showDetail(Number(b.dataset.klass)); });
  });

  // ── 2. 클래스 상세 ────────────────────────────────────────────
  function showDetail(id) {
    var c = klassOf(id);
    if (!c) return;
    $("#detail-body").innerHTML =
      '<h2 id="detail-h">' + esc(c.name) + "</h2>" +
      '<p class="detail-price">' + won(c.price) + "</p>" +
      '<div class="meta" style="margin-bottom:var(--sp-3)">' +
        '<span class="tag">소요 ' + c.minutes + "분</span>" +
        '<span class="tag">정원 ' + c.cap + "명</span>" +
        '<span class="tag">화~일 10:00 / 14:00 / 19:00</span>' +
      "</div>" +
      "<p>" + esc(c.desc) + "</p>" +
      "<h3>준비물</h3><ul>" +
        c.prep.map(function (p) { return "<li>" + esc(p) + "</li>"; }).join("") +
      "</ul>" +
      '<button type="button" class="btn btn-primary btn-lg" id="detail-book">이 클래스 예약하기</button>';
    $("#detail-book").addEventListener("click", function () {
      $("#f-class").value = String(c.id);
      updateSeats();
      go("book");
    });
    go("detail");
  }

  // ── 3. 예약 ───────────────────────────────────────────────────
  var form = $("#book-form");
  var errBox = $("#book-error");

  $("#f-class").innerHTML = '<option value="">고르세요</option>' +
    CLASSES.map(function (c) {
      return '<option value="' + c.id + '">' + esc(c.name) + " · " + won(c.price) + "</option>";
    }).join("");

  // 오늘 이후만 고를 수 있게 (F-3)
  var today = new Date();
  $("#f-date").min = today.toISOString().slice(0, 10);

  function bookings() { return load(KEY_BOOK); }

  /** 같은 클래스·날짜·시간에 이미 접수된 인원 */
  function taken(klassId, date, time) {
    return bookings().reduce(function (sum, b) {
      return (b.klassId === Number(klassId) && b.date === date && b.time === time)
        ? sum + b.people : sum;
    }, 0);
  }

  function isMonday(dateStr) {
    if (!dateStr) return false;
    return new Date(dateStr + "T00:00:00").getDay() === 1;
  }

  function updateSeats() {
    var note = $("#seat-note");
    var kid = $("#f-class").value, date = $("#f-date").value, time = $("#f-time").value;
    note.classList.remove("is-full");

    if (isMonday(date)) {
      note.textContent = "월요일은 휴무입니다. 다른 날짜를 골라 주세요.";
      note.classList.add("is-full");
    } else if (kid && date && time) {
      var c = klassOf(kid);
      var left = c.cap - taken(kid, date, time);
      if (left <= 0) {
        note.textContent = "이 시간대는 자리가 찼습니다. 다른 시간을 골라 주세요.";
        note.classList.add("is-full");
      } else {
        note.textContent = "남은 자리 " + left + "명 (정원 " + c.cap + "명)";
      }
    } else {
      note.textContent = "";
    }
    $("#book-submit").disabled = !canSubmit();
  }

  function canSubmit() {
    var d = new FormData(form);
    if (!d.get("klass") || !d.get("date") || !d.get("time")) return false;
    if (!String(d.get("name")).trim()) return false;
    if (!String(d.get("tel")).trim()) return false;
    if (isMonday(d.get("date"))) return false;
    return true;
  }

  form.addEventListener("input", updateSeats);
  form.addEventListener("change", updateSeats);

  function fail(msg) {
    errBox.textContent = msg;
    errBox.hidden = false;
    return false;
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    errBox.hidden = true;

    var d = new FormData(form);
    var kid = Number(d.get("klass"));
    var c = klassOf(kid);
    var date = String(d.get("date"));
    var time = String(d.get("time"));
    var people = Number(d.get("people"));
    var name = String(d.get("name")).trim();
    var tel = String(d.get("tel")).trim();

    if (isMonday(date)) return fail("월요일은 휴무입니다.");
    if (new Date(date + "T23:59:59") < new Date(new Date().toDateString()))
      return fail("오늘 이후 날짜를 골라 주세요.");
    if (tel.replace(/\D/g, "").length < 9) return fail("연락처를 확인해 주세요.");
    if (!people || people < 1) return fail("인원을 1명 이상으로 적어 주세요.");
    if (people > c.cap) return fail("정원은 " + c.cap + "명입니다.");
    if (taken(kid, date, time) + people > c.cap)
      return fail("남은 자리는 " + (c.cap - taken(kid, date, time)) + "명입니다.");

    var list = bookings();
    var seq = list.filter(function (b) { return b.date === date; }).length + 1;
    var code = "BB-" + date.replace(/-/g, "") + "-" + String(seq).padStart(3, "0");

    var rec = { code: code, klassId: kid, klass: c.name, date: date, time: time,
                people: people, name: name, tel: tel, price: c.price * (kid === 4 ? 1 : people) };
    list.push(rec);
    save(KEY_BOOK, list);

    $("#receipt-no").textContent = code;
    $("#receipt-detail").innerHTML =
      "<dt>클래스</dt><dd>" + esc(c.name) + "</dd>" +
      "<dt>날짜</dt><dd>" + esc(date) + " " + esc(time) + "</dd>" +
      "<dt>인원</dt><dd>" + people + "명</dd>" +
      "<dt>예약자</dt><dd>" + esc(name) + "</dd>" +
      "<dt>결제 예정</dt><dd>" + won(rec.price) + " (현장 결제)</dd>";
    $("#receipt").hidden = false;
    $("#f-code").value = code;
    renderCheck(code);
    form.reset();
    $("#f-people").value = "1";
    updateSeats();
    $("#receipt").scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

  // ── 4. 예약 확인 ──────────────────────────────────────────────
  function renderCheck(code) {
    var box = $("#check-result");
    var hit = bookings().filter(function (b) {
      return b.code.toUpperCase() === String(code).trim().toUpperCase();
    })[0];
    if (!hit) {
      box.innerHTML = '<p class="empty">그런 예약번호가 없습니다. 번호를 다시 확인해 주세요.</p>';
      return;
    }
    box.innerHTML =
      '<div class="receipt">' +
        '<p class="receipt-label">예약이 확인되었습니다</p>' +
        '<p class="receipt-no">' + esc(hit.code) + "</p>" +
        '<dl class="receipt-detail">' +
          "<dt>클래스</dt><dd>" + esc(hit.klass) + "</dd>" +
          "<dt>날짜</dt><dd>" + esc(hit.date) + " " + esc(hit.time) + "</dd>" +
          "<dt>인원</dt><dd>" + hit.people + "명</dd>" +
          "<dt>예약자</dt><dd>" + esc(hit.name) + "</dd>" +
        "</dl>" +
      "</div>";
  }
  $("#check-form").addEventListener("submit", function (e) {
    e.preventDefault();
    renderCheck($("#f-code").value);
  });

  // ── 5. 문의 ───────────────────────────────────────────────────
  function renderAsks() {
    var list = load(KEY_ASK);
    $("#ask-list").innerHTML = list.length
      ? list.slice().reverse().map(function (q) {
          return "<li>" +
            '<span class="who">' + esc(q.name) + "</span> " +
            '<span class="when">' + esc(q.at) + "</span>" +
            "<p>" + esc(q.body) + "</p></li>";
        }).join("")
      : '<li class="empty muted">아직 보낸 문의가 없습니다.</li>';
  }
  $("#ask-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var err = $("#ask-error");
    err.hidden = true;
    var d = new FormData(e.target);
    var name = String(d.get("name")).trim();
    var tel = String(d.get("tel")).trim();
    var body = String(d.get("body")).trim();
    if (!name) { err.textContent = "이름을 적어 주세요."; err.hidden = false; return; }
    if (tel.replace(/\D/g, "").length < 9) { err.textContent = "연락처를 확인해 주세요."; err.hidden = false; return; }
    if (body.length < 10) { err.textContent = "문의 내용을 조금 더 적어 주세요 (10자 이상)."; err.hidden = false; return; }

    var list = load(KEY_ASK);
    list.push({ name: name, tel: tel, body: body, at: new Date().toLocaleString("ko-KR") });
    save(KEY_ASK, list);
    e.target.reset();
    renderAsks();
    err.textContent = "";
  });

  // ── 시작 ──────────────────────────────────────────────────────
  renderAsks();
  updateSeats();
  var start = (location.hash || "#list").slice(1);
  go($("#" + start) ? start : "list");
})();
