import os
import re
import cv2
import numpy as np
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
        return pytesseract.image_to_string(img, lang='spa')
    except Exception as e:
        print(f"Error OCR: {e}")
        return ""

def analizar(ruta_archivo):
    ext = os.path.splitext(ruta_archivo)[1].lower()
    texto = ""
    
    if ext == ".pdf":
        texto = extraer_texto_pdf(ruta_archivo)
    else:
        texto = extraer_texto_imagen(ruta_archivo)

    # 1. RTN
    rtns = re.findall(r'RTN:?\s*([0-9]{14})', texto, re.IGNORECASE)
    rtn_emisor = rtns[0] if rtns else ""

    # 2. CAI
    cai_match = re.search(r'CAI:?\s*([A-Z0-9]{5,6}-[A-Z0-9]{5,6}-[A-Z0-9]{5,6}-[A-Z0-9]{5,6}-[A-Z0-9]{5,6}-[A-Z0-9]{5,6})', texto, re.IGNORECASE)
    cai = cai_match.group(1) if cai_match else ""

    # 3. Fecha
    fecha_match = re.search(r'Fecha:?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', texto, re.IGNORECASE)
    fecha = fecha_match.group(1) if fecha_match else ""
    
    # 4. Monto Total
    monto_match = re.search(r'Total Facturada:?\s*L\.?\s*([\d,]+\.\d{2})', texto, re.IGNORECASE)
    if not monto_match:
        monto_match = re.search(r'Total:?\s*L\.?\s*([\d,]+\.\d{2})', texto, re.IGNORECASE)
    if not monto_match:
        monto_match = re.search(r'Total Facturada:?\s*([\d,]+\.\d{2})', texto, re.IGNORECASE)
        
    monto_str = monto_match.group(1) if monto_match else "0.00"
    
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

# --- NUEVA FUNCIÓN MEJORADA PARA LEER EL ODÓMETRO ---
def leer_odometro(ruta_imagen):
    try:
        # 1. Leer la imagen con OpenCV
        img = cv2.imread(ruta_imagen)
        if img is None:
            return {"valor": None, "texto": "No se pudo cargar la imagen"}

        # 2. Convertir a escala de grises
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 3. Ampliar la imagen (x3) para que Tesseract lea mejor los dígitos
        gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        
        # 4. Aplicar umbralización (Thresholding) para dejar los números negros y el fondo blanco
        # Usamos Otsu's thresholding que encuentra el mejor valor automáticamente
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        
        # 5. Configurar Tesseract: 
        # --psm 7: Trata la imagen como una sola línea de texto
        # -c tessedit_char_whitelist=0123456789.: Solo permitimos números y punto decimal
        config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789.'
        
        texto_extraido = pytesseract.image_to_string(thresh, config=config)
        
        # 6. Limpiar el texto extraído (quitar espacios y letras raras)
        texto_limpio = texto_extraido.strip().replace(" ", "")
        
        # Buscar secuencias de números (de 3 a 8 dígitos, que es lo normal en un odómetro)
        numeros = re.findall(r'\d{3,8}', texto_limpio)
        
        if numeros:
            # Tomamos el número más largo que encontró
            valor_final = max(numeros, key=len)
            return {"valor": valor_final, "texto": texto_extraido}
        else:
            return {"valor": None, "texto": texto_extraido}
            
    except Exception as e:
        return {"valor": None, "texto": f"Error: {e}"}
