import os
import re
import pdfplumber
from PIL import Image
import pytesseract

def extraer_texto_pdf(ruta_pdf):
    texto = ""
    try:
        with pdfplumber.open(ruta_pdf) as pdf:
            for pagina in pdf.pages:
                texto_pag = pagina.extract_text()
                if texto_pag:
                    texto += texto_pag + "\n"
    except Exception as e:
        print(f"Error leyendo PDF: {e}")
    return texto

def extraer_texto_imagen(ruta_img):
    try:
        img = Image.open(ruta_img)
        # Usamos el idioma español para leer mejor
        return pytesseract.image_to_string(img, lang='spa')
    except Exception as e:
        print(f"Error OCR: {e}")
        return ""

def analizar(ruta_archivo):
    ext = os.path.splitext(ruta_archivo)[1].lower()
    texto = ""
    
    if ext == ".pdf":
        texto = extraer_texto_pdf(ruta_archivo)
        # Si el PDF es una imagen escaneada y no sacó texto, podríamos convertir a imagen, 
        # pero para este caso, pdfplumber funciona bien.
    else:
        texto = extraer_texto_imagen(ruta_archivo)

    # --- PATRONES DE BÚSQUEDA INTELIGENTES ---
    
    # 1. RTN: Buscamos "RTN:" seguido de 14 números (puede tener espacios)
    rtns = re.findall(r'RTN:?\s*([0-9]{14})', texto, re.IGNORECASE)
    # El primer RTN suele ser el del emisor (la gasolinera/proveedor)
    rtn_emisor = rtns[0] if rtns else ""

    # 2. CAI: Buscamos "CAI:" seguido del formato de bloques alfanuméricos (ej. 492C7-17C9A6-...)
    cai_match = re.search(r'CAI:?\s*([A-Z0-9]{5,6}-[A-Z0-9]{5,6}-[A-Z0-9]{5,6}-[A-Z0-9]{5,6}-[A-Z0-9]{5,6}-[A-Z0-9]{5,6})', texto, re.IGNORECASE)
    cai = cai_match.group(1) if cai_match else ""

    # 3. Fecha: Buscamos "Fecha:" seguido del formato DD-MM-YYYY o DD/MM/YYYY
    fecha_match = re.search(r'Fecha:?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', texto, re.IGNORECASE)
    fecha = fecha_match.group(1) if fecha_match else ""
    
    # 4. Monto Total: Buscamos "Total Facturada:" o "Total:" seguido de "L." y números con comas
    monto_match = re.search(r'Total Facturada:?\s*L\.?\s*([\d,]+\.\d{2})', texto, re.IGNORECASE)
    if not monto_match:
        monto_match = re.search(r'Total:?\s*L\.?\s*([\d,]+\.\d{2})', texto, re.IGNORECASE)
    if not monto_match:
        # A veces las facturas solo dicen "Total" y el número sin la L.
        monto_match = re.search(r'Total Facturada:?\s*([\d,]+\.\d{2})', texto, re.IGNORECASE)
        
    monto_str = monto_match.group(1) if monto_match else "0.00"
    
    # Limpiamos el monto: quitamos las comas de los miles (ej. 1,622.00 -> 1622.00)
    try:
        monto = float(monto_str.replace(',', ''))
    except ValueError:
        monto = 0.0

    return {
        "rtn": rtn_emisor,
        "cai": cai,
        "fecha_compra": fecha,
        "monto": monto,
        "texto_ocr": texto
    }

def leer_odometro(ruta_imagen):
    # (Mantenemos tu función original de odómetro por si acaso)
    try:
        img = Image.open(ruta_imagen)
        texto = pytesseract.image_to_string(img, lang='spa')
        # Buscar números de 3 a 6 dígitos
        numeros = re.findall(r'\b\d{3,6}\b', texto)
        if numeros:
            return {"valor": numeros[-1], "texto": texto}
        return {"valor": None, "texto": texto}
    except Exception as e:
        return {"valor": None, "texto": f"Error: {e}"}
