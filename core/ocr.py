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

# --- LECTURA DE ODÓMETRO EXTREMA (PARA PANTALLAS LED) ---
def leer_odometro(ruta_imagen):
    try:
        # 1. Leer imagen
        img = cv2.imread(ruta_imagen)
        if img is None:
            return {"valor": None, "texto": "No se pudo cargar"}

        # 2. Convertir a escala de grises
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 3. Recortar el 10% de los bordes para eliminar el texto "mi" o el marco del tablero
        h, w = gray.shape
        gray = gray[int(h*0.1):int(h*0.9), int(w*0.1):int(w*0.9)]

        # 4. Ampliar la imagen (x4) para que los números sean gigantes
        gray = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)

        # 5. Aplicar filtro de ruido (suaviza el resplandor LED)
        gray = cv2.medianBlur(gray, 5)

        # 6. Umbralización: Los LEDs son muy brillantes, cortamos a partir de 150
        # Esto deja los números en blanco puro y el fondo en negro puro
        _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

        # 7. Rellenar huecos (Morfología): Los números de 7 segmentos tienen cortes. 
        # Esto los hace sólidos para que Tesseract no los confunda.
        kernel = np.ones((5, 5), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        # 8. Invertir (fondo blanco, números negros)
        thresh = cv2.bitwise_not(thresh)

        # 9. Agregar borde blanco
        thresh = cv2.copyMakeBorder(thresh, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=[255, 255, 255])

        # 10. Configurar Tesseract
        # PSM 7: Trata la imagen como una sola línea de texto.
        # Whitelist: SOLO busca números (ignora la 'm' y la 'i' de "mi")
        config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789'
        texto_extraido = pytesseract.image_to_string(thresh, config=config)

        # 11. Limpiar y buscar el número
        texto_limpio = texto_extraido.strip().replace(" ", "")
        numeros = re.findall(r'\d{4,8}', texto_limpio)

        if numeros:
            # Tomamos el número más largo que encontró
            valor_final = max(numeros, key=len)
            return {"valor": valor_final, "texto": texto_extraido}
        else:
            return {"valor": None, "texto": texto_extraido}
            
    except Exception as e:
        return {"valor": None, "texto": f"Error: {e}"}
