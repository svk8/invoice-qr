"""
Генерация платёжного QR в формате ST00012 (ГОСТ Р 56042).
"""

import segno
from io import BytesIO
from extractor import InvoiceData


def build_st00012(data: InvoiceData) -> str:
    """Собирает строку ST00012 из реквизитов."""
    if not data.is_valid():
        raise ValueError("Недостаточно реквизитов для генерации QR")

    sum_kopecks = int(round(data.amount * 100))

    # Чистим название
    name = data.recipient_name.replace('"', '«').replace("'", "«")
    if not name.startswith(("ООО", "АО", "ПАО", "ИП")):
        name = f"ООО «{name}»" if "ИНВЕСТ" in name.upper() else name

    fields = [
        "ST00012",
        f"Name={name}",
        f"PersonalAcc={data.account}",
        f"BankName={data.bank_name or 'АО «АЛЬФА-БАНК»'}",
        f"BIC={data.bik}",
        f"CorrespAcc={data.corr_account}",
        f"PayeeINN={data.inn}",
    ]
    if data.kpp:
        fields.append(f"KPP={data.kpp}")
    fields.append(f"Sum={sum_kopecks}")
    fields.append(f"Purpose={data.purpose}")

    return "|".join(fields)


def generate_qr_png(data: InvoiceData, scale: int = 8) -> bytes:
    """Возвращает PNG-байты QR-кода."""
    payload = build_st00012(data)
    qr = segno.make(payload, error="m")
    buf = BytesIO()
    qr.save(buf, kind="png", scale=scale, border=2)
    buf.seek(0)
    return buf.read()


def generate_qr_payload(data: InvoiceData) -> str:
    return build_st00012(data)
