-- 별빛공방 — 스키마 (S4 DBA)
-- 금액은 정수(원), 시각은 문자열이 아닌 시간 타입. 타입이 곧 검증이다.

CREATE TABLE klass (                       -- 클래스
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT    NOT NULL UNIQUE,
  price       INTEGER NOT NULL CHECK (price > 0),   -- 원 단위
  minutes     INTEGER NOT NULL CHECK (minutes > 0),
  capacity    INTEGER NOT NULL CHECK (capacity > 0),
  description TEXT    NOT NULL,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  deleted_at  TIMESTAMP                              -- 물리 삭제 대신 표시
);

CREATE TABLE booking (                     -- 예약
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  code         TEXT    NOT NULL UNIQUE,             -- BB-20260812-001
  klass_id     INTEGER NOT NULL REFERENCES klass(id),
  book_date    DATE    NOT NULL,
  book_time    TEXT    NOT NULL CHECK (book_time IN ('10:00','14:00','19:00')),
  people       INTEGER NOT NULL CHECK (people > 0),
  guest_name   TEXT    NOT NULL,
  guest_tel    TEXT    NOT NULL,                    -- 개인정보. 평문 저장 최소화
  status       TEXT    NOT NULL DEFAULT 'received'
                       CHECK (status IN ('received','done','canceled')),
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  deleted_at   TIMESTAMP
);

-- 같은 클래스·날짜·시간의 인원 합을 자주 조회한다
CREATE INDEX idx_booking_slot ON booking (klass_id, book_date, book_time);

CREATE TABLE inquiry (                     -- 문의
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  guest_name TEXT NOT NULL,
  guest_tel  TEXT NOT NULL,
  body       TEXT NOT NULL CHECK (length(body) >= 10),
  answered   INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 비밀번호·주민번호 컬럼은 두지 않는다. 회원가입이 범위 밖이다 (SOW 제외 2).
