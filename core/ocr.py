import os
import re
import cv2
import numpy as np
import pdfplumber
import pymupdf
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
        print(f"Error leyendo PDF con pdfplumber: {e}")
    
    if len(texto.strip()) < 50:
        try:
            doc = pymupdf.open(ruta_pdf)
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            texto = pytesseract.image_to_string(img, lang='spa')
        except Exception as e:
            print(f"Error con PyMuPDF OCR: {e}")
            
    return texto

def extraer_texto_imagen(ruta_img):
    try:
        img = cv2.imread(ruta_img)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        return pytesseract.image_to_string(thresh, lang='spa')
    except Exception as e:
        print(f"Error OCR imagen: {e}")
        return ""

def analizar(ruta_archivo):
    ext = os.path.splitext(ruta_archivo)[1].lower()
    texto = ""
    
    if ext == ".pdf":
        texto = extraer_texto_pdf(ruta_archivo)
    else:
        texto = extraer_texto_imagen(ruta_archivo)

    texto_limpio = texto.replace('\n', ' ').replace('\r', ' ')
    texto_limpio = re.sub(r'\s+', ' ', texto_limpio)

    # 1. RTN
    rtns = re.findall(r'RTN:?\s*([0-9]{14})', texto_limpio, re.IGNORECASE)
    rtn_emisor = rtns[0] if rtns else ""

    # 2. CAI
    cai_match = re.search(r'CAI:?\s*([A-Z0-9-]{20,40})', texto_limpio, re.IGNORECASE)
    cai = cai_match.group(1) if cai_match else ""
    cai = cai.replace(" ", "")

    # 3. Fecha
    fecha_match = re.search(r'Fecha:?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', texto_limpio, re.IGNORECASE)
    fecha = fecha_match.group(1) if fecha_match else ""
    
    # 4. Monto Total
    monto_match = re.search(r'Total Facturada:?\s*L\.?\s*([\d,]+\.\d{2})', texto_limpio, re.IGNORECASE)
    if not monto_match:
        monto_match = re.search(r'Total:?\s*L\.?\s*([\d,]+\.\d{2})', texto_limpio, re.IGNORECASE)
    if not monto_match:
        monto_match = re.search(r'Total Facturada:?\s*([\d,]+\.\d{2})', texto_limpio, re.IGNORECASE)
        
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

# --- LECTURA DE ODÓMETRO VERSIÓN 5.0 (DETECCIÓN DE CONTORNOS) ---
def leer_odometro(ruta_imagen):
    try:
        # 1. Leer imagen
        img = cv2.imread(ruta_imagen)
        if img is None:
            return {"valor": None, "texto": "No se pudo cargar"}

        # 2. Convertir a escala de grises
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 3. Umbralizar para aislar las zonas brillantes (los LEDs encendidos)
        # Usamos 150 como corte para ignorar el fondo oscuro del tablero
        _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

        # 4. Dilatar horizontalmente para unir los números separados y que formen un solo bloque
        kernel = np.ones((5, 25), np.uint8) # Kernel ancho para unir dígitos
        dilated = cv2.dilate(thresh, kernel, iterations=1)

        # 5. Encontrar los contornos (los bloques blancos)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return {"valor": None, "texto": "No se encontraron zonas brillantes"}

        # 6. Buscar el contorno más grande (que deberían ser los números del odómetro)
        mejor_contorno = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(mejor_contorno)

        # Si el bloque es muy pequeño, probablemente sea ruido
        if w < 30 or h < 10:
            return {"valor": None, "texto": "Bloque de texto muy pequeño"}

        # 7. Recortar la imagen original usando ese contorno (con un pequeño margen)
        margen = 10
        x1 = max(0, x - margen)
        y1 = max(0, y - margen)
        x2 = min(gray.shape[1], x + w + margen)
        y2 = min(gray.shape[0], y + h + margen)
        recorte = gray[y1:y2, x1:x2]

        # 8. Procesar el recorte para que Tesseract lo lea perfecto
        # Ampliar x6 (los números serán gigantes)
        recorte = cv2.resize(recorte, None, fx=6, fy=6, interpolation=cv2.INTER_CUBIC)
        
        # Aplicar umbralización Otsu al recorte (fondo blanco, números negros)
        _, thresh_final = cv2.threshold(recorte, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Agregar un borde blanco grueso para que Tesseract no se confunda
        thresh_final = cv2.copyMakeBorder(thresh_final, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=[255, 255, 255])

        # 9. Configurar Tesseract
        config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789'
        texto_extraido = pytesseract.image_to_string(thresh_final, config=config)

        # 10. Limpiar y buscar el número
        texto_limpio = texto_extraido.strip().replace(" ", "")
        numeros = re.findall(r'\d{3,8}', texto_limpio)

        if numeros:
            valor_final = max(numeros, key=len)
            return {"valor": valor_final, "texto": texto_extraido}
        else:
            return {"valor": None, "texto": texto_extraido}
            
    except Exception as e:
        return {"valor": None, "texto": f"Error: {e}"}
