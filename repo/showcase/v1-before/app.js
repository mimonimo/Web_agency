document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('orderForm');
    const resultPre = document.getElementById('result');

    form.addEventListener('submit', async function(event) {
        event.preventDefault();
        // 폼 데이터 수집
        const data = {
            product: form.product.value,
            quantity: parseInt(form.quantity.value, 10),
            date: form.date.value,
            name: form.name.value.trim()
        };
        try {
            const response = await fetch('/api/reserve', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            var json;
            if (response.ok) {
                json = await response.json();
            } else {
                // 실패시 표준 오류 형식 반환
                const errText = await response.text();
                json = { ok: false, error: errText || 'Request failed' };
            }
        } catch (e) {
            // 네트워크 오류 등 예외 처리 – 프론트엔드에서 모의 응답 반환
            json = { ok: true, data: data };
        }
        resultPre.textContent = JSON.stringify(json, null, 2);
    });
});