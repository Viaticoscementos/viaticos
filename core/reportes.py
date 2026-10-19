import os
from fpdf import FPDF
from datetime import datetime
from core.config import BASE_DIR

# Función para convertir números a letras en español (hasta millones)
def numero_a_letras(numero):
    unidades = ["", "UN", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE"]
    decenas = ["", "DIEZ", "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
    especiales = {11: "ONCE", 12: "DOCE", 13: "TRECE", 14: "CATORCE", 15: "QUINCE", 16: "DIECISEIS", 17: "DIECISIETE", 18: "DIECIOCHO", 19: "DIECINUEVE", 20: "VEINTE", 21: "VEINTIUNO", 22: "VEINTIDOS", 23: "VEINTITRES", 24: "VEINTICUATRO", 25: "VEINTICINCO", 26: "VEINTISEIS", 27: "VEINTISIETE", 28: "VEINTIOCHO", 29: "VEINTINUEVE"}
    centenas = ["", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS", "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS"]

    if numero == 0: return "CERO"
    if numero == 100: return "CIEN"
    
    texto = ""
    if numero >= 1000000:
        millones = numero // 1000000
        texto += numero_a_letras(millones) + " MILLONES "
        numero %= 1000000

    if numero >= 1000:
        miles = numero // 1000
        if miles == 1: texto += "MIL "
        else: texto += numero_a_letras(miles) + " MIL "
        numero %= 1000

    if numero >= 100:
        texto += centenas[numero // 100] + " "
        numero %= 100

    if numero > 0:
        if numero in especiales: texto += especiales[numero]
        elif numero < 10: texto += unidades[numero]
        else:
            d, u = numero // 10, numero % 10
            texto += decenas[d]
            if u > 0: texto += " Y " + unidades[u]
            
    return texto.strip()

class PDFMemorando(FPDF):
    def header(self):
        # Logo (Asegúrate de que la ruta sea correcta a tu carpeta static)
        logo_path = os.path.join(BASE_DIR, "static", "logo_color.png")
        if os.path.exists(logo_path):
            self.image(logo_path, 160, 10, 33)
        
    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(128)
        self.cell(0, 10, f"Página {self.page_no()}", align="C")

def generar_memo_pdf(solicitudes, empleado):
    pdf = PDFMemorando(format="Letter")
    pdf.add_page()
    
    # --- PÁGINA 1: MEMORANDO ---
    pdf.set_font("Arial", "B", 24)
    pdf.set_y(40)
    pdf.cell(0, 10, "Memorando", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(20)
    
    pdf.set_font("Arial", "B", 11)
    # Encabezados del memo
    pdf.cell(30, 8, "Para:", new_x="RIGHT", new_y="TOP")
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, "Lic. Ricardo Jovani Rosales - Gerente Financiero y Negocios", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Arial", "B", 11)
    pdf.cell(30, 8, "De:", new_x="RIGHT", new_y="TOP")
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, "Ing. Hugo Barascout - Gerente Comercial", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Arial", "B", 11)
    pdf.cell(30, 8, "CC:", new_x="RIGHT", new_y="TOP")
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, "Archivo", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Arial", "B", 11)
    pdf.cell(30, 8, "Fecha:", new_x="RIGHT", new_y="TOP")
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, datetime.now().strftime("%d de %B del %Y"), new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Arial", "B", 11)
    pdf.cell(30, 8, "Referencia:", new_x="RIGHT", new_y="TOP")
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, "Lo Descrito", new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(5)
    pdf.line(15, pdf.get_y(), 200, pdf.get_y()) # Línea divisoria
    pdf.ln(10)

    # Calcular totales
    total_general = sum(float(s['monto']) for s in solicitudes)
    monto_letras = numero_a_letras(int(total_general))
    monto_centavos = int(round((total_general - int(total_general)) * 100))
    
    # Cuerpo del texto
    pdf.set_font("Arial", "", 11)
    texto = (f"Muy atentamente solicito la transferencia bancaria a la cuenta de Banco de Occidente "
             f"a nombre de {empleado.upper()} por la cantidad de {monto_letras} CON {monto_centavos:02d}/100 "
             f"LEMPIRAS (L. {total_general:,.2f}) en concepto gastos de alimentación, transporte y hospedaje. "
             f"Se adjunta tabla con la descripción de lugares visitados y facturas.")
    pdf.multi_cell(0, 6, texto)
    pdf.ln(10)
    pdf.cell(0, 6, "Nota: Imputar a centro de costos V60140.", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(15)
    pdf.cell(0, 6, "Atentamente,", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(25)
    
    # Firmas
    pdf.line(120, pdf.get_y(), 190, pdf.get_y())
    pdf.set_font("Arial", "B", 10)
    pdf.set_x(120)
    pdf.cell(0, 6, "Vo. Bo. Ing. Edwin Argueta", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(120)
    pdf.cell(0, 6, "Gerente General", new_x="LMARGIN", new_y="NEXT")

    # --- PÁGINA 2: LIQUIDACIÓN DE VIÁTICOS ---
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "LIQUIDACIÓN DE VIÁTICOS", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, f"EMPLEADO: {empleado.upper()}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"TOTAL GASTADO: L. {total_general:,.2f}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # Definir anchos de columnas
    w = [10, 25, 25, 35, 50, 35, 20]
    headers = ["ITEM", "DIA", "FECHA", "DESCRIPCIÓN", "NOMBRE DEL NEGOCIO", "# FACTURA", "TOTAL"]

    def draw_header_row():
        pdf.set_fill_color(0, 143, 57) # Verde Cenosa
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 9)
        for i, h in enumerate(headers):
            pdf.cell(w[i], 8, h, border=1, align="C", fill=True)
        pdf.ln()
        pdf.set_text_color(0, 0, 0) # Volver a negro

    # Agrupar por categorías
    categorias = ["Alimentacion", "Hotel", "Asistencia Tecnica", "Representacion", "Mercadeo", "Combustible", "Otros Gastos"]
    
    pdf.set_font("Arial", "", 9)
    
    for cat in categorias:
        gastos_cat = [s for s in solicitudes if s.get('categoria') == cat]
        if not gastos_cat: continue

        # Título de la categoría
        pdf.set_fill_color(230, 246, 236) # Verde claro
        pdf.set_font("Arial", "B", 10)
        pdf.cell(sum(w), 8, cat.upper(), border=1, align="L", fill=True, new_x="LMARGIN", new_y="NEXT")
        
        draw_header_row()
        
        pdf.set_font("Arial", "", 9)
        for i, s in enumerate(gastos_cat):
            fecha = s.get('fecha_compra', '')
            try:
                # Intentar formatear fecha si viene en formato YYYY-MM-DD
                dt = datetime.strptime(fecha, "%Y-%m-%d")
                dia_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"][dt.weekday()]
                fecha_fmt = dt.strftime("%d/%m/%Y")
            except:
                dia_semana = "-"
                fecha_fmt = fecha or "-"

            pdf.cell(w[0], 7, str(i+1), border=1, align="C")
            pdf.cell(w[1], 7, dia_semana, border=1, align="C")
            pdf.cell(w[2], 7, fecha_fmt, border=1, align="C")
            pdf.cell(w[3], 7, s.get('categoria', 'VARIOS'), border=1, align="C")
            pdf.cell(w[4], 7, (s.get('negocio') or '-')[:25], border=1, align="L")
            pdf.cell(w[5], 7, (s.get('num_factura') or '-')[:15], border=1, align="C")
            pdf.cell(w[6], 7, f"L {float(s['monto']):,.2f}", border=1, align="R")
            pdf.ln()

    # Fila final de Total
    pdf.set_fill_color(0, 143, 57)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(sum(w[:-1]), 10, "TOTAL GASTADO EN LA SEMANA", border=1, align="R", fill=True)
    pdf.cell(w[-1], 10, f"L {total_general:,.2f}", border=1, align="R", fill=True)
    pdf.ln()

    # Guardar
    from core.config import REPORTES_DIR
    nombre_archivo = f"Memo_{empleado.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    ruta_salida = os.path.join(REPORTES_DIR, nombre_archivo)
    pdf.output(ruta_salida)
    
    return ruta_salida

# Dejamos un generar_memo genérico por retrocompatibilidad
def generar_memo(solicitud_o_lista, empleado=None):
    if isinstance(solicitud_o_lista, dict):
        solicitudes = [solicitud_o_lista]
        if not empleado: empleado = solicitudes[0].get('empleado', 'Empleado')
    else:
        solicitudes = solicitud_o_lista
        if not empleado: empleado = solicitudes[0].get('empleado', 'Empleado') if solicitudes else 'Empleado'
    
    return generar_memo_pdf(solicitudes, empleado)
