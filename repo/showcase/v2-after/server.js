// -*- coding: utf-8 -*-
// 밀밭제과 백엔드 서버 (Node.js 표준 모듈만 사용)

const http = require('http');
const url = require('url');
const crypto = require('crypto');
const { execSync, spawn } = require('child_process');
const fs = require('fs');

// ---------- 설정 ----------
const PORT = process.env.PORT || 3000;
const DB_PATH = process.env.DB_PATH || './database.db';
const JWT_SECRET = process.env.JWT_SECRET || crypto.randomBytes(32).toString('hex'); // 비밀키는 환경변수 또는 자동 생성

// ---------- 헬퍼 ----------
function jsonResponse(res, statusCode, obj) {
  const data = JSON.stringify(obj);
  res.writeHead(statusCode, { 'Content-Type': 'application/json' });
  res.end(data);
}

function parseBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => (body += chunk));
    req.on('end', () => {
      try {
        resolve(JSON.parse(body || '{}'));
      } catch (e) {
        reject(e);
      }
    });
  });
}

function generateToken(payload) {
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const body = Buffer.from(JSON.stringify(payload)).toString('base64url');
  const sig = crypto.createHmac('sha256', JWT_SECRET).update(`${header}.${body}`).digest('base64url');
  return `${header}.${body}.${sig}`;
}

function verifyToken(token) {
  if (!token) return null;
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  const [header, body, sig] = parts;
  const expectedSig = crypto.createHmac('sha256', JWT_SECRET).update(`${header}.${body}`).digest('base64url');
  if (sig !== expectedSig) return null;
  try {
    return JSON.parse(Buffer.from(body, 'base64url').toString());
  } catch (_) {
    return null;
  }
}

function hashPassword(password, salt = crypto.randomBytes(16).toString('hex')) {
  // pbkdf2 를 사용해 bcrypt와 유사한 보안 수준 제공
  const hash = crypto.pbkdf2Sync(password, salt, 100000, 64, 'sha256').toString('hex');
  return `${salt}$${hash}`;
}
function verifyPassword(stored, password) {
  const [salt, hash] = stored.split('$');
  const attempt = crypto.pbkdf2Sync(password, salt, 100000, 64, 'sha256').toString('hex');
  return attempt === hash;
}

function execSql(sql, params = []) {
  // sqlite3 CLI 를 사용해 한줄 쿼리 실행 (파라미터는 간단히エ스케이프)
  const escapedParams = params.map(p => `'${String(p).replace(/'/g, "''")}'`).join(' ');
  const cmd = `sqlite3 ${DB_PATH} "${sql}${escapedParams ? ' ' + escapedParams : ''}"`;
  try {
    const out = execSync(cmd, { encoding: 'utf8' }).trim();
    return out;
  } catch (e) {
    console.error('SQL Error:', e.message);
    throw e;
  }
}

function initDb() {
  if (!fs.existsSync(DB_PATH)) {
    console.log('데이터베이스 초기화 중...');
    const schema = `-- SQLite schema for 밀밭제과 온라인 주문 시스템
${fs.readFileSync('./schema.sql', 'utf8')}`;
    // 임시 파일에 저장 후 sqlite3 로 실행
    fs.writeFileSync('/tmp/init_schema.sql', schema);
    execSync(`sqlite3 ${DB_PATH} < /tmp/init_schema.sql`);
    console.log('데이터베이스 생성 완료');
  }
}

initDb();

// ---------- 라우팅 ----------
const server = http.createServer(async (req, res) => {
  const parsedUrl = url.parse(req.url, true);
  const pathname = parsedUrl.pathname;
  const method = req.method;

  // CORS & JSON 헤더
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  if (method === 'OPTIONS') {
    res.writeHead(204);
    return res.end();
  }

  // ---- 로그인 ---------------------------------------------------
  if (pathname === '/api/login' && method === 'POST') {
    try {
      const body = await parseBody(req);
      const { email, password } = body;
      if (!email || !password) {
        return jsonResponse(res, 400, { ok: false, error: '이메일 또는 비밀번호가 올바르지 않습니다' });
      }
      // 사용자 조회
      const userRow = execSql(`SELECT id, password_hash FROM users WHERE email = ?`, [email]);
      if (!userRow) {
        return jsonResponse(res, 400, { ok: false, error: '이메일 또는 비밀번호가 올바르지 않습니다' });
      }
      const [id, storedHash] = userRow.split('|'); // sqlite3 기본 구분자 '|'
      if (!verifyPassword(storedHash, password)) {
        return jsonResponse(res, 400, { ok: false, error: '이메일 또는 비밀번호가 올바르지 않습니다' });
      }
      const token = generateToken({ userId: id, email });
      return jsonResponse(res, 200, { ok: true, data: { sessionToken: token } });
    } catch (e) {
      console.error(e);
      return jsonResponse(res, 400, { ok: false, error: '입력값 검증 실패' });
    }
  }

  // ---- 상품 목록 -------------------------------------------------
  if (pathname === '/api/products' && method === 'GET') {
    try {
      const search = parsedUrl.query.search || '';
      let sql = `SELECT id, name, price, stock, image_url FROM products`;
      if (search) sql += ` WHERE name LIKE '%${search.replace(/'/g, "''")}%'
        OR description LIKE '%${search.replace(/'/g, "''")}%'`;
      const rows = execSql(`${sql}`, []);
      // sqlite3 기본 출력은 파이프 구분: 한줄 per row, 컬럼 구분 '|'
      const items = rows
        .split('\n')
        .filter(Boolean)
        .map(line => {
          const [id, name, price, stock, image_url] = line.split('|');
          return { id: Number(id), name, price: Number(price), stock: Number(stock), imageUrl: image_url };
        });
      return jsonResponse(res, 200, { ok: true, data: items });
    } catch (e) {
      console.error(e);
      return jsonResponse(res, 404, { ok: false, error: '상품이 없음' });
    }
  }

  // 인증 필요 라우트 공통 처리
  const authHeader = req.headers['authorization'];
  let tokenPayload = null;
  if (authHeader && authHeader.startsWith('Bearer ')) {
    tokenPayload = verifyToken(authHeader.slice(7));
  }
  if (!tokenPayload) {
    return jsonResponse(res, 401, { ok: false, error: '인증이 필요합니다' });
  }

  const userId = tokenPayload.userId;

  // ---- 장바구니 추가 --------------------------------------------
  if (pathname === '/api/cart/add' && method === 'POST') {
    try {
      const body = await parseBody(req);
      const { productId, quantity } = body;
      if (!productId || !quantity || quantity < 1) {
        return jsonResponse(res, 400, { ok: false, error: '잘못된 입력' });
      }
      // 카트 존재 여부 확인/생성
      let cartRow = execSql(`SELECT id FROM carts WHERE user_id = ?`, [userId]);
      let cartId;
      if (!cartRow) {
        const out = execSql(`INSERT INTO carts (user_id) VALUES (?)`, [userId]);
        // 마지막 삽입 ID 얻기
        cartId = execSql('SELECT last_insert_rowid()', []);
      } else {
        cartId = cartRow.split('|')[0];
      }
      // 재고 확인
      const productRow = execSql(`SELECT stock, name, price FROM products WHERE id = ?`, [productId]);
      if (!productRow) return jsonResponse(res, 400, { ok: false, error: '상품이 존재하지 않음' });
      const [stockStr, prodName, priceStr] = productRow.split('|');
      const stock = Number(stockStr);
      const price = Number(priceStr);
      if (quantity > stock) return jsonResponse(res, 400, { ok: false, error: '재고 부족' });

      // 기존 아이템 있으면 수량 합산
      const existing = execSql(`SELECT id, quantity FROM cart_items WHERE cart_id = ? AND product_id = ?`, [cartId, productId]);
      if (existing) {
        const [itemId, curQty] = existing.split('|');
        const newQty = Number(curQty) + Number(quantity);
        execSql(`UPDATE cart_items SET quantity = ? WHERE id = ?`, [newQty, itemId]);
      } else {
        execSql(`INSERT INTO cart_items (cart_id, product_id, quantity) VALUES (?,?,?)`, [cartId, productId, quantity]);
      }
      // 응답: 최신 장바구니 반환
      const cartResponse = getCartResponse(cartId);
      return jsonResponse(res, 200, { ok: true, data: cartResponse });
    } catch (e) {
      console.error(e);
      return jsonResponse(res, 400, { ok: false, error: '장바구니 추가 실패' });
    }
  }

  // ---- 장바구니 수정 --------------------------------------------
  if (pathname === '/api/cart/update' && method === 'PUT') {
    try {
      const body = await parseBody(req);
      const { productId, quantity } = body;
      if (productId == null || quantity == null) return jsonResponse(res, 400, { ok: false, error: '잘못된 입력' });

      let cartRow = execSql(`SELECT id FROM carts WHERE user_id = ?`, [userId]);
      if (!cartRow) return jsonResponse(res, 400, { ok: false, error: '카트가 없음' });
      const cartId = cartRow.split('|')[0];

      if (quantity === 0) {
        execSql(`DELETE FROM cart_items WHERE cart_id = ? AND product_id = ?`, [cartId, productId]);
      } else {
        // 재고 검증
        const prod = execSql(`SELECT stock FROM products WHERE id = ?`, [productId]);
        if (!prod) return jsonResponse(res, 400, { ok: false, error: '상품 없음' });
        const stock = Number(prod.split('|')[0]);
        if (quantity > stock) return jsonResponse(res, 400, { ok: false, error: '재고 부족' });
        execSql(`UPDATE cart_items SET quantity = ? WHERE cart_id = ? AND product_id = ?`, [quantity, cartId, productId]);
      }
      const cartResponse = getCartResponse(cartId);
      return jsonResponse(res, 200, { ok: true, data: cartResponse });
    } catch (e) {
      console.error(e);
      return jsonResponse(res, 400, { ok: false, error: '수정 실패' });
    }
  }

  // ---- 장바구니 삭제 (쿼리 파라미터) ----------------------------
  if (pathname === '/api/cart/remove' && method === 'DELETE') {
    const productId = parsedUrl.query.productId;
    if (!productId) return jsonResponse(res, 400, { ok: false, error: 'productId 누락' });
    try {
      let cartRow = execSql(`SELECT id FROM carts WHERE user_id = ?`, [userId]);
      if (!cartRow) return jsonResponse(res, 400, { ok: false, error: '카트가 없음' });
      const cartId = cartRow.split('|')[0];
      execSql(`DELETE FROM cart_items WHERE cart_id = ? AND product_id = ?`, [cartId, productId]);
      const cartResponse = getCartResponse(cartId);
      return jsonResponse(res, 200, { ok: true, data: cartResponse });
    } catch (e) {
      console.error(e);
      return jsonResponse(res, 400, { ok: false, error: '삭제 실패' });
    }
  }

  // ---- 문의 폼 -------------------------------------------------
  if (pathname === '/api/contact' && method === 'POST') {
    try {
      const body = await parseBody(req);
      const { name, email, subject, message } = body;
      if (!name || !email || !subject || !message) {
        return jsonResponse(res, 400, { ok: false, error: '필수 항목이 비어 있습니다' });
      }
      execSql(`INSERT INTO inquiries (name, email, subject, message) VALUES (?,?,?,?)`, [name, email, subject, message]);
      return jsonResponse(res, 200, { ok: true, data: {} });
    } catch (e) {
      console.error(e);
      return jsonResponse(res, 400, { ok: false, error: '전송 실패' });
    }
  }

  // 기타 미지원 엔드포인트
  jsonResponse(res, 404, { ok: false, error: '존재하지 않는 API 경로입니다' });
});

function getCartResponse(cartId) {
  const itemRows = execSql(`SELECT ci.id, p.id as productId, p.name, p.price, ci.quantity FROM cart_items ci JOIN products p ON ci.product_id = p.id WHERE ci.cart_id = ?`, [cartId]);
  const items = [];
  if (itemRows) {
    itemRows.split('\n').filter(Boolean).forEach(line => {
      const [ciId, productId, name, priceStr, qtyStr] = line.split('|');
      const price = Number(priceStr);
      const quantity = Number(qtyStr);
      items.push({ cartItemId: Number(ciId), productId: Number(productId), name, price, quantity, subtotal: price * quantity });
    });
  }
  const total = items.reduce((sum, it) => sum + it.subtotal, 0);
  return { items, total };
}

server.listen(PORT, () => {
  console.log(`서버가 http://localhost:${PORT} 에서 실행 중입니다.`);
});
