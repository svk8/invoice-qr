#!/usr/bin/env python3
"""
Микросервис замены QR-кода на счетах.
Веб-интерфейс для бухгалтера.
"""

import os
import tempfile
from flask import Flask, request, render_template_string, send_file, jsonify
from extractor import extract, InvoiceData
from qr_generator import generate_qr_png, generate_qr_payload, build_st00012
from replacer import replace_qr_in_pdf
from io import BytesIO

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Счёт → QR для оплаты</title>
  <style>
    :root { --bg: #0f172a; --card: #1e293b; --accent: #38bdf8; --text: #e2e8f0; --muted: #94a3b8; }
    * { box-sizing: border-box; }
    body { font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 2rem; }
    .container { max-width: 720px; margin: 0 auto; }
    h1 { font-size: 1.6rem; margin-bottom: 0.3rem; }
    .sub { color: var(--muted); margin-bottom: 2rem; }
    .card { background: var(--card); border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }
    label { display: block; font-weight: 600; margin-bottom: 0.5rem; }
    input[type=file] { width: 100%; padding: 0.8rem; background: #0f172a; border: 1px dashed var(--muted); border-radius: 8px; color: var(--text); }
    button { background: var(--accent); color: #0f172a; border: none; padding: 0.9rem 1.8rem; border-radius: 8px; font-weight: 700; cursor: pointer; font-size: 1rem; width: 100%; margin-top: 1rem; }
    button:hover { filter: brightness(1.1); }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    .steps { display: flex; gap: 0.5rem; margin: 1.5rem 0; }
    .step { flex: 1; text-align: center; padding: 0.6rem; border-radius: 8px; background: #0f172a; font-size: 0.85rem; color: var(--muted); }
    .step.active { background: var(--accent); color: #0f172a; font-weight: 600; }
    .result { display: none; }
    table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    td { padding: 0.4rem 0; border-bottom: 1px solid #334155; }
    td:first-child { color: var(--muted); width: 40%; }
    .qr-preview { text-align: center; margin: 1rem 0; }
    .qr-preview img { max-width: 220px; border-radius: 8px; background: white; padding: 8px; }
    .error { background: #7f1d1d; color: #fecaca; padding: 1rem; border-radius: 8px; margin-top: 1rem; }
    .success { background: #14532d; color: #bbf7d0; padding: 1rem; border-radius: 8px; margin-top: 1rem; }
    a.download { display: inline-block; background: #22c55e; color: #052e16; padding: 0.8rem 1.5rem; border-radius: 8px; text-decoration: none; font-weight: 700; margin-top: 1rem; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Счёт → QR для оплаты</h1>
    <p class="sub">Загрузите счёт (PDF/DOCX). Получите тот же счёт с правильным платёжным QR-кодом ST00012.</p>

    <div class="steps">
      <div class="step" id="s1">1. Распознавание</div>
      <div class="step" id="s2">2. QR для оплаты</div>
      <div class="step" id="s3">3. Замена в счёте</div>
    </div>

    <div class="card">
      <form id="form" enctype="multipart/form-data">
        <label for="file">Файл счёта</label>
        <input type="file" id="file" name="file" accept=".pdf,.docx" required>
        <button type="submit" id="btn">Обработать счёт</button>
      </form>
      <div id="error" class="error" style="display:none"></div>
    </div>

    <div id="result" class="result">
      <div class="card">
        <h3>Извлечённые реквизиты</h3>
        <table id="details"></table>
      </div>
      <div class="card">
        <h3>Платёжный QR</h3>
        <div class="qr-preview"><img id="qrimg" alt="QR"></div>
        <p style="font-size:0.8rem;color:var(--muted);word-break:break-all" id="payload"></p>
      </div>
      <div class="card success">
        <strong>Готово!</strong> Счёт с новым QR-кодом подготовлен.
        <br>
        <a class="download" id="download" href="#" download="schet_with_qr.pdf">Скачать счёт с правильным QR</a>
      </div>
    </div>
  </div>

  <script>
    const form = document.getElementById('form');
    const btn = document.getElementById('btn');
    const errorBox = document.getElementById('error');
    const result = document.getElementById('result');

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      errorBox.style.display = 'none';
      result.style.display = 'none';
      btn.disabled = true;
      btn.textContent = 'Обрабатываю…';

      document.getElementById('s1').classList.add('active');
      document.getElementById('s2').classList.remove('active');
      document.getElementById('s3').classList.remove('active');

      const fd = new FormData(form);
      try {
        const resp = await fetch('/process', { method: 'POST', body: fd });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Ошибка сервера');

        document.getElementById('s1').classList.add('active');
        document.getElementById('s2').classList.add('active');
        document.getElementById('s3').classList.add('active');

        // Реквизиты
        const t = document.getElementById('details');
        t.innerHTML = '';
        const fields = [
          ['Получатель', data.recipient_name],
          ['ИНН', data.inn],
          ['КПП', data.kpp],
          ['Расчётный счёт', data.account],
          ['БИК', data.bik],
          ['Корр. счёт', data.corr_account],
          ['Банк', data.bank_name],
          ['Сумма', data.amount.toLocaleString('ru-RU', {minimumFractionDigits:2}) + ' ₽'],
          ['Назначение', data.purpose],
        ];
        fields.forEach(([k,v]) => {
          const tr = document.createElement('tr');
          tr.innerHTML = `<td>${k}</td><td>${v || '—'}</td>`;
          t.appendChild(tr);
        });

        document.getElementById('qrimg').src = 'data:image/png;base64,' + data.qr_base64;
        document.getElementById('payload').textContent = data.payload;

        const downloadBtn = document.getElementById('download');
        const successCard = downloadBtn.closest('.card');
        if (data.pdf_base64) {
          downloadBtn.href = 'data:application/pdf;base64,' + data.pdf_base64;
          downloadBtn.download = data.filename || 'schet_with_qr.pdf';
          downloadBtn.style.display = 'inline-block';
          successCard.querySelector('strong').textContent = 'Готово! Счёт с новым QR-кодом подготовлен.';
          const oldWarn = successCard.querySelector('.docx-warn');
          if (oldWarn) oldWarn.remove();
        } else {
          downloadBtn.style.display = 'none';
          successCard.querySelector('strong').textContent = 'Реквизиты и QR готовы';
          let warn = successCard.querySelector('.docx-warn');
          if (!warn) {
            warn = document.createElement('p');
            warn.className = 'docx-warn';
            warn.style.marginTop = '0.8rem';
            warn.style.color = '#fbbf24';
            successCard.appendChild(warn);
          }
          warn.textContent = data.warning || 'Для файлов Word (DOCX) автоматическая замена QR внутри документа пока не поддерживается. Используйте QR выше или конвертируйте счёт в PDF.';
        }

        result.style.display = 'block';
      } catch (err) {
        errorBox.textContent = err.message;
        errorBox.style.display = 'block';
      } finally {
        btn.disabled = false;
        btn.textContent = 'Обработать счёт';
      }
    });
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/process", methods=["POST"])
def process():
    if "file" not in request.files:
        return jsonify({"error": "Файл не передан"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Пустое имя файла"}), 400

    try:
        file_bytes = f.read()
        data: InvoiceData = extract(file_bytes, f.filename)

        if not data.is_valid():
            return jsonify({
                "error": "Не удалось извлечь достаточные реквизиты. "
                         "Проверьте, что это счёт на оплату с ИНН, р/с, БИК и суммой."
            }), 400

        # QR
        qr_png = generate_qr_png(data)
        payload = generate_qr_payload(data)

        # Замена (только для PDF)
        if f.filename.lower().endswith(".pdf"):
            new_pdf = replace_qr_in_pdf(file_bytes, qr_png)
            out_name = f.filename.rsplit(".", 1)[0] + "_qr.pdf"
        else:
            # Для DOCX пока просто возвращаем QR + реквизиты (замена изображений сложнее)
            new_pdf = None
            out_name = None

        import base64
        resp = {
            "recipient_name": data.recipient_name,
            "inn": data.inn,
            "kpp": data.kpp,
            "account": data.account,
            "bik": data.bik,
            "corr_account": data.corr_account,
            "bank_name": data.bank_name,
            "amount": data.amount,
            "purpose": data.purpose,
            "payload": payload,
            "qr_base64": base64.b64encode(qr_png).decode(),
        }
        if new_pdf:
            resp["pdf_base64"] = base64.b64encode(new_pdf).decode()
            resp["filename"] = out_name
        else:
            resp["pdf_base64"] = None
            resp["warning"] = "Для DOCX замена QR пока не поддерживается — скачайте QR отдельно"

        return jsonify(resp)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("Запуск сервиса: http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
