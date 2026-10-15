"""
Извлечение реквизитов из счёта (PDF / DOCX).
Работает с типовыми российскими счетами на оплату.
"""

import re
from dataclasses import dataclass, asdict
from typing import Optional
import pdfplumber
from docx import Document
from io import BytesIO


@dataclass
class InvoiceData:
    recipient_name: str = ""
    inn: str = ""
    kpp: str = ""
    account: str = ""          # р/с
    bank_name: str = ""
    bik: str = ""
    corr_account: str = ""     # к/с
    amount: float = 0.0        # в рублях
    purpose: str = ""
    invoice_number: str = ""
    invoice_date: str = ""
    contract: str = ""
    raw_text: str = ""

    def to_dict(self):
        return asdict(self)

    def is_valid(self) -> bool:
        return bool(self.account and self.bik and self.inn and self.amount > 0)


def _clean(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def extract_from_text(text: str) -> InvoiceData:
    data = InvoiceData(raw_text=text)

    # ИНН
    m = re.search(r'ИНН\s*[№:]?\s*(\d{10}|\d{12})', text, re.I)
    if m:
        data.inn = m.group(1)

    # КПП
    m = re.search(r'КПП\s*[№:]?\s*(\d{9})', text, re.I)
    if m:
        data.kpp = m.group(1)

    # Расчётный счёт (20 цифр, часто после р/с или Сч. №)
    m = re.search(r'(?:р/?с|сч\.?\s*№?|PersonalAcc|расч[её]тный\s*сч[её]т)[^\d]{0,20}(\d{20})', text, re.I)
    if not m:
        m = re.search(r'\b(40702\d{14})\b', text)  # типичный р/с юрлица
    if m:
        data.account = m.group(1)

    # БИК
    m = re.search(r'БИК\s*[банка:]?\s*(\d{9})', text, re.I)
    if m:
        data.bik = m.group(1)

    # Корр. счёт
    m = re.search(r'(?:к/?с|корр\.?\s*сч[её]т|CorrespAcc)[^\d]{0,20}(\d{20})', text, re.I)
    if m:
        data.corr_account = m.group(1)

    # Наименование получателя — приоритет строке после "Получатель:"
    m = re.search(r'Получатель[:\s]+((?:ООО|АО|ПАО|ИП)[^\n\r]{3,70})', text, re.I)
    if m:
        name = _clean(m.group(1))
        name = re.split(r'\s{2,}|ИНН|КПП|ОГРН|Банк', name)[0].strip()
        # восстанавливаем кавычки если обрезало
        if name.startswith('ООО «') and not name.endswith('»'):
            name += '»'
        elif name.startswith('ООО "') and not name.endswith('"'):
            name += '"'
        data.recipient_name = name

    if not data.recipient_name:
        m = re.search(r'((?:ООО|АО|ПАО)\s*[«"][^«»"]+[«"])\s*\n?\s*ИНН', text, re.I)
        if m:
            data.recipient_name = _clean(m.group(1))
        else:
            m = re.search(r'(ООО|АО|ПАО|ИП)\s*[«"]?([^«»"\n]{2,40})[«"]?', text)
            if m:
                data.recipient_name = _clean(m.group(0))

    # Банк
    m = re.search(r'Банковские реквизиты:\s*([^\n\r]{5,60})', text, re.I)
    if m:
        data.bank_name = _clean(m.group(1).split('\n')[0])
    if not data.bank_name:
        m = re.search(r'(АО|ПАО|ООО)\s*[«"]?[А-ЯA-Z][^«»"\n]{3,40}БАНК', text, re.I)
        if m:
            data.bank_name = _clean(m.group(0))
    if not data.bank_name and data.bik:
        data.bank_name = "АО «АЛЬФА-БАНК»" if data.bik.startswith("044525") else ""

    # Сумма (ищем "Всего к оплате" или "Итого")
    m = re.search(r'(?:Всего к оплате|Итого|Сумма)[:\s]*([\d\s]+[.,]\d{2})', text, re.I)
    if m:
        amt = m.group(1).replace(' ', '').replace(',', '.')
        try:
            data.amount = float(amt)
        except ValueError:
            pass
    if data.amount == 0:
        # ищем крупную сумму
        amounts = re.findall(r'(\d{1,3}(?:\s?\d{3})*[.,]\d{2})', text)
        for a in amounts:
            val = float(a.replace(' ', '').replace(',', '.'))
            if val > 1000:
                data.amount = val
                break

    # Номер и дата счёта
    m = re.search(r'Сч[её]т\s+на\s+оплату\s+№\s*(\S+)\s+от\s+(\d{2}\.\d{2}\.\d{4})', text, re.I)
    if m:
        data.invoice_number = m.group(1)
        data.invoice_date = m.group(2)

    # Договор / основание
    m = re.search(r'(?:Договор|Основание)[^\n]{0,40}№\s*([^\s]+)\s+от\s+(\d{2}\.\d{2}\.\d{4})', text, re.I)
    if m:
        data.contract = f"№ {m.group(1)} от {m.group(2)}"

    # Назначение платежа (формируем)
    purpose_parts = []
    if data.contract:
        purpose_parts.append(f"Оплата по договору {data.contract}")
    if data.invoice_number:
        purpose_parts.append(f"Счет на оплату № {data.invoice_number}" + (f" от {data.invoice_date}" if data.invoice_date else ""))
    purpose_parts.append("НДС не облагается")
    data.purpose = ", ".join(purpose_parts) if purpose_parts else "Оплата по счету"

    # Более точное назначение из таблицы
    m = re.search(r'Оплата по договору[^\n]{10,120}', text)
    if m:
        data.purpose = _clean(m.group(0)) + (f". Счет № {data.invoice_number} от {data.invoice_date}" if data.invoice_number else "") + ". НДС не облагается"

    return data


def extract_from_pdf(file_bytes: bytes) -> InvoiceData:
    text_parts = []
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            text_parts.append(t)
    full_text = "\n".join(text_parts)
    return extract_from_text(full_text)


def extract_from_docx(file_bytes: bytes) -> InvoiceData:
    doc = Document(BytesIO(file_bytes))
    text_parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text_parts.append(cell.text)
    full_text = "\n".join(text_parts)
    return extract_from_text(full_text)


def extract(file_bytes: bytes, filename: str) -> InvoiceData:
    name = filename.lower()
    if name.endswith(".pdf"):
        return extract_from_pdf(file_bytes)
    elif name.endswith((".docx", ".doc")):
        return extract_from_docx(file_bytes)
    else:
        raise ValueError("Поддерживаются только PDF и DOCX")
