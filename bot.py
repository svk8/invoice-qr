#!/usr/bin/env python3
"""
Telegram-бот для замены QR на счетах.
Запуск: BOT_TOKEN=xxx python bot.py
"""

import os
import logging
import tempfile
from io import BytesIO

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from extractor import extract
from qr_generator import generate_qr_png, generate_qr_payload
from replacer import replace_qr_in_pdf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise SystemExit("Установите переменную окружения BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пришлите счёт в PDF или DOCX.\n"
        "Я извлеку реквизиты, сделаю платёжный QR (ST00012) и верну счёт с правильным QR-кодом."
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return

    filename = doc.file_name or "invoice.pdf"
    if not filename.lower().endswith((".pdf", ".docx")):
        await update.message.reply_text("Нужен файл PDF или DOCX.")
        return

    await update.message.reply_text("⏳ Получил файл. Распознаю реквизиты…")

    try:
        tg_file = await doc.get_file()
        file_bytes = bytes(await tg_file.download_as_bytearray())

        data = extract(file_bytes, filename)
        if not data.is_valid():
            await update.message.reply_text(
                "❌ Не удалось извлечь достаточные реквизиты.\n"
                "Убедитесь, что это счёт на оплату с ИНН, р/с, БИК и суммой."
            )
            return

        # Показываем что нашли
        text = (
            f"✅ Реквизиты:\n"
            f"Получатель: {data.recipient_name}\n"
            f"ИНН: {data.inn}  КПП: {data.kpp}\n"
            f"р/с: {data.account}\n"
            f"БИК: {data.bik}\n"
            f"Сумма: {data.amount:,.2f} ₽\n"
            f"Назначение: {data.purpose[:120]}…"
        )
        await update.message.reply_text(text)

        await update.message.reply_text("⏳ Генерирую платёжный QR и заменяю в счёте…")

        qr_png = generate_qr_png(data)

        # Отправляем QR отдельно (удобно)
        await update.message.reply_photo(
            photo=BytesIO(qr_png),
            caption="Платёжный QR (ST00012). Можно сканировать прямо из приложения банка."
        )

        if filename.lower().endswith(".pdf"):
            new_pdf = replace_qr_in_pdf(file_bytes, qr_png)
            out_name = filename.rsplit(".", 1)[0] + "_qr.pdf"
            await update.message.reply_document(
                document=BytesIO(new_pdf),
                filename=out_name,
                caption="Счёт с правильным QR-кодом. Можно отправлять контрагенту."
            )
        else:
            await update.message.reply_text(
                "Для DOCX пока возвращаю только QR. PDF поддерживается полностью."
            )

    except Exception as e:
        logger.exception("Ошибка обработки")
        await update.message.reply_text(f"❌ Ошибка: {e}")


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    print("Бот запущен…")
    app.run_polling()


if __name__ == "__main__":
    main()
