const express = require('express');
const path = require('path');

const app = express();
app.use(express.json());
// 정적 파일 제공 (output 폴더 내 index.html, css, js)
app.use(express.static(__dirname));

// 예약 API 엔드포인트
app.post('/api/reserve', (req, res) => {
  const { product, quantity, date, name } = req.body;
  // 여기서 실제 비즈니스 로직을 구현 가능 – 현재는 에코 반환
  if (!product || !quantity || !date || !name) {
    return res.status(400).json({ ok: false, error: '필수 파라미터 누락' });
  }
  const response = { ok: true, data: { product, quantity, date, name } };
  res.json(response);
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Server listening on port ${PORT}`));
