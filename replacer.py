"""
Замена QR-кода в PDF-счёте на новый платёжный QR.
"""

from io import BytesIO
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image
import pdf2image
import numpy as np
from scipy import ndimage


def find_qr_bbox(page_image: Image.Image, dpi: int = 150) -> tuple[float, float, float]:
    """
    Находит приблизительный bounding box QR на отрендеренной странице.
    Возвращает (x_pdf, y_pdf, size_pdf) в пунктах PDF.
    """
    arr = np.array(page_image.convert("L"))
    binary = (arr < 120).astype(np.uint8)

    # Соединяем модули QR
    struct = np.ones((3, 3))
    dilated = ndimage.binary_dilation(binary, structure=struct, iterations=2)
    labeled, num = ndimage.label(dilated)

    candidates = []
    for i in range(1, num + 1):
        ys, xs = np.where(labeled == i)
        if len(xs) < 5000:
            continue
        w = xs.max() - xs.min() + 1
        h = ys.max() - ys.min() + 1
        # QR почти квадратный и достаточно большой
        if abs(w - h) < max(w, h) * 0.15 and 80 < w < 400:
            candidates.append((xs.min(), ys.min(), w, h, len(xs)))

    if not candidates:
        # fallback: правый верхний угол (типичное место QR на счетах)
        h, w = arr.shape
        return (w * 0.62 * 72 / dpi, h * 0.55 * 72 / dpi, 130.0)

    # Берём самый "плотный" квадрат справа
    candidates.sort(key=lambda c: (-c[0], -c[4]))  # правее и плотнее
    x, y, w, h, _ = candidates[0]

    scale = 72.0 / dpi
    pdf_x = x * scale
    pdf_size = max(w, h) * scale
    page_h_pts = page_image.height * scale
    pdf_y = page_h_pts - (y * scale) - pdf_size

    return pdf_x, pdf_y, pdf_size


def replace_qr_in_pdf(pdf_bytes: bytes, new_qr_png: bytes) -> bytes:
    """
    Накладывает новый QR поверх старого в PDF.
    """
    # Рендерим первую страницу для поиска позиции
    pages = pdf2image.convert_from_bytes(pdf_bytes, dpi=150, first_page=1, last_page=1)
    page_img = pages[0]

    x, y, size = find_qr_bbox(page_img, dpi=150)

    # Создаём оверлей
    packet = BytesIO()
    reader = PdfReader(BytesIO(pdf_bytes))
    page = reader.pages[0]
    page_w = float(page.mediabox.width)
    page_h = float(page.mediabox.height)

    c = canvas.Canvas(packet, pagesize=(page_w, page_h))

    # Белый фон, чтобы полностью перекрыть старый QR
    margin = 3
    c.setFillColorRGB(1, 1, 1)
    c.rect(x - margin, y - margin, size + 2 * margin, size + 2 * margin, fill=1, stroke=0)

    # Новый QR
    img = ImageReader(BytesIO(new_qr_png))
    c.drawImage(img, x, y, width=size, height=size, mask="auto")
    c.save()
    packet.seek(0)

    # Мержим
    overlay = PdfReader(packet)
    writer = PdfWriter()
    page.merge_page(overlay.pages[0])
    writer.add_page(page)

    # Копируем остальные страницы если есть
    for p in reader.pages[1:]:
        writer.add_page(p)

    out = BytesIO()
    writer.write(out)
    out.seek(0)
    return out.read()
