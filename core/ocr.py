"""Lectura (OCR) y extraccion de datos de la factura.

Reutiliza la logica probada del proyecto original: corre Tesseract en varios
modos, elige el mejor resultado y extrae RTN, CAI, fechas y montos con
expresiones regulares tolerantes a errores del OCR.
"""
import os
import re
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps, ImageEnhance

from core.config import TESSERACT_CMD, TESSDATA_DIR

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
if TESSDATA_DIR and Path(TESSDATA_DIR).exists():
    os.environ["TESSDATA_PREFIX"] = str(TESSDATA_DIR)


PATRONES = {
    "rtn_con_prefijo": re.compile(
        r"(?:R\.?\s?T\.?\s?N\.?)[.:\s]*"
        r"([0-9OoIlD]{4}[\s\-]?[0-9OoIlD]{4}[\s\-]?[0-9OoIlD]{6})", re.I),
    "rtn_suelto": re.compile(r"\b([0-9OoIlD]{14})\b"),
    "rtn_con_guiones": re.compile(r"\b(\d{4}[\s\-]\d{4}[\s\-]\d{6})\b"),
    "cai_estricto": re.compile(
        r"(?:CA[I1Ll]|C\.?A\.?[I1Ll]\.?)[.:\s\-]*"
        r"([A-Z0-9]{4,8}(?:[\s\-][A-Z0-9]{4,8}){3,7})", re.I),
    "cai_suelto": re.compile(
        r"\b([A-Z0-9]{5,8}-[A-Z0-9]{5,8}-[A-Z0-9]{5,8}-[A-Z0-9]{4,8}"
        r"(?:-[A-Z0-9]{2,8}){0,3})\b"),
    "fecha": re.compile(r"\b(\d{1,2}\s?[/\-\.]\s?\d{1,2}\s?[/\-\.]\s?\d{2,4})\b"),
    "fecha_dma": re.compile(
        r"(?:D[I\u00cd]A|DIA)[:\s]*(\d{1,2})[\s\S]{0,20}?(?:M[E\u00c9]S|MES)[:\s]*"
        r"(\d{1,2})[\s\S]{0,20}?(?:A[\u00d1N]O|ANO|A)[:\s]*(\d{2,4})", re.I),
    "fecha_limite": re.compile(
        r"fecha\s+l[i\u00ed]mite\s+de\s+emisi[o\u00f3]n[:\s]*"
        r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})", re.I),
}


def _preprocesar(img):
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    if img.width > img.height * 1.15:
        img = img.rotate(-90, expand=True)
    if img.width < 2500:
        factor = 2500 / img.width
        img = img.resize((2500, int(img.height * factor)), Image.LANCZOS)
    img = img.convert("L")
    try:
        img = ImageEnhance.Contrast(img).enhance(1.5)
        img = ImageEnhance.Sharpness(img).enhance(2.0)
    except Exception:
        pass
    return img


def _score(t):
    s = 0
    u = t.upper()
    if re.search(r"R\.?T\.?N", u):
        s += 30
    if re.search(r"C\.?A\.?I", u):
        s += 30
    if "FACTURA" in u:
        s += 10
    if "TOTAL" in u:
        s += 10
    s += len(re.findall(r"\d", t)) / 3
    if len(t) < 50:
        s -= 50
    return s


def _ocr_pil(img_original):
    img = _preprocesar(img_original)
    res = []
    for psm in (3, 4, 6, 11, 12):
        try:
            cfg = f"--psm {psm} -c preserve_interword_spaces=1"
            t = pytesseract.image_to_string(img, lang="spa", config=cfg)
            if t.strip():
                res.append((_score(t), t))
        except Exception:
            continue
    if not res:
        try:
            t = pytesseract.image_to_string(img_original.convert("L"), lang="spa", config="--psm 6")
            if t.strip():
                res.append((_score(t), t))
        except Exception:
            pass
    if not res:
        return ""
    res.sort(reverse=True, key=lambda x: x[0])
    return res[0][1]


def _texto_pdf(ruta):
    textos = []
    try:
        import pdfplumber
        with pdfplumber.open(ruta) as pdf:
            for p in pdf.pages:
                textos.append(p.extract_text() or "")
    except Exception:
        textos = []
    if textos and all(t.strip() for t in textos):
        return "\n".join(textos)
    try:
        import fitz
        doc = fitz.open(ruta)
        imgs = []
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            modo = "RGBA" if pix.alpha else "RGB"
            imgs.append(Image.frombytes(modo, [pix.width, pix.height], pix.samples).convert("RGB"))
        doc.close()
    except Exception:
        return "\n".join(textos)
    if not textos:
        textos = [""] * len(imgs)
    for i in range(len(textos)):
        if not textos[i].strip() and i < len(imgs):
            textos[i] = _ocr_pil(imgs[i])
    return "\n".join(textos)


def extraer_texto(ruta):
    ruta = Path(ruta)
    if ruta.suffix.lower() == ".pdf":
        return _texto_pdf(str(ruta))
    return _ocr_pil(Image.open(ruta))


def _norm_dig(s):
    if not s:
        return s
    return (s.replace("O", "0").replace("o", "0").replace("I", "1")
             .replace("l", "1").replace("D", "0").replace("Q", "0"))


def _norm_cai(s):
    if not s:
        return s
    s = re.sub(r"\s+", "", s).upper()
    s = re.sub(r"-+", "-", s).strip("-")
    return s.replace("O", "0").replace("I", "1").replace("L", "1")


def parsear(texto):
    plano = re.sub(r"\s+", " ", texto).replace("\u00ba", "").replace("'", "").replace("`", "")
    rtn = None
    for pat in ("rtn_con_prefijo", "rtn_suelto", "rtn_con_guiones"):
        m = PATRONES[pat].search(plano)
        if m:
            rtn = m.group(1)
            break
    if rtn:
        rtn = re.sub(r"[\s\-]", "", _norm_dig(rtn))
    cai = None
    m = PATRONES["cai_estricto"].search(plano)
    if m:
        cai = m.group(1)
    if not cai:
        m = PATRONES["cai_suelto"].search(plano)
        if m:
            cai = m.group(1)
    if cai:
        cai = _norm_cai(cai)
    fechas = [re.sub(r"\s+", "", f) for f in PATRONES["fecha"].findall(plano)]
    if not fechas:
        m = PATRONES["fecha_dma"].search(plano)
        if m:
            d, mes, a = m.group(1), m.group(2), m.group(3)
            if len(a) == 2:
                a = "20" + a
            fechas = [f"{d}/{mes}/{a}"]
    montos = []
    patron = re.compile(
        r"[Ll]\.?\s?\d{1,3}(?:,\d{3})+\.\d{2}|[Ll]\.?\s?\d{4,}\.\d{2}"
        r"|[Ll]\.?\s?\d{1,3}\.\d{2}|[Ll]\.?\s?\d{1,3}(?:,\d{3})+")
    for mt in patron.finditer(plano):
        ini = max(0, mt.start() - 30)
        ctx = plano[ini:mt.start()].upper()
        if any(x in ctx for x in ("TEL", "CEL", "FAX", "TELEFONO", "WHATSAPP")):
            continue
        montos.append(mt.group(0))
    lim = PATRONES["fecha_limite"].search(plano)
    return {
        "rtn": rtn, "cai": cai, "fechas": fechas, "montos": montos,
        "fecha_limite": re.sub(r"\s+", "", lim.group(1)) if lim else None,
    }


def _monto(montos):
    nums = []
    for m in (montos or []):
        limpio = re.sub(r"[Ll]\.?\s?", "", m).replace(",", "").strip()
        try:
            nums.append(float(limpio))
        except ValueError:
            continue
    return max(nums) if nums else 0.0


def analizar(ruta_factura):
    """OCR + extraccion. Devuelve campos pre-llenados (sin tocar la BD)."""
    texto = extraer_texto(ruta_factura)
    d = parsear(texto)
    return {
        "texto_ocr": texto,
        "rtn": d.get("rtn"),
        "cai": d.get("cai"),
        "fecha_compra": d["fechas"][0] if d.get("fechas") else None,
        "fecha_limite": d.get("fecha_limite"),
        "monto": _monto(d.get("montos")),
    }


def leer_odometro(ruta):
    """Lee el numero del odometro/kilometraje de una foto.

    Devuelve el numero mas probable (el entero mas largo de 3+ digitos).
    Para tableros digitales usa un modo de OCR enfocado solo en digitos.
    """
    try:
        img = _preprocesar(Image.open(ruta))
    except Exception:
        return {"valor": None, "texto": ""}
    candidatos = []
    textos = []
    for cfg in ("--psm 7 -c tessedit_char_whitelist=0123456789",
                "--psm 6 -c tessedit_char_whitelist=0123456789",
                "--psm 11 -c tessedit_char_whitelist=0123456789",
                "--psm 6"):
        try:
            t = pytesseract.image_to_string(img, config=cfg)
        except Exception:
            continue
        textos.append(t)
        for n in re.findall(r"\d{3,7}", t.replace(" ", "")):
            candidatos.append(n)
    valor = None
    if candidatos:
        # el numero mas largo (y de mayor valor) suele ser el odometro
        candidatos.sort(key=lambda x: (len(x), int(x)), reverse=True)
        try:
            valor = float(candidatos[0])
        except ValueError:
            valor = None
    return {"valor": valor, "texto": " ".join(textos).strip()}
