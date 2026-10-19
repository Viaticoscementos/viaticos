import os
import json
from fpdf import FPDF
from datetime import datetime
from core.config import BASE_DIR, FACTURAS_DIR

class PDFReporte(FPDF):
    def header(self):
        logo_path = os.path.join(BASE_DIR, "static", "logo_color.png")
        if os.path.exists(logo_path):
            self.image(logo_path, 10, 8, 25)
        self.set_font("Arial", "B", 10)
        self.set_xy(120, 10)
        self.cell(0, 5, "BANCO DE FICOHSA - DEL 28 DE SEPTIEMBRE AL 02 DE OCTUBRE 2026", align="R")
        self.line(10, 25, 200, 25)
        self.ln(10)

def generar_reporte_depreciacion_pdf(solicitudes, empleado):
    pdf = PDFReporte(format="Letter")
    pdf.add_page()
    
    # --- TÍTULO ---
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "DETALLE DEPRECIACION DE VEHICULO", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    pdf.set_font("Arial", "", 9)
    
    dep_sols = [s for s in solicitudes if s.get('categoria') == 'Depreciacion']
    comb_sols = [s for s in solicitudes if s.get('categoria') == 'Combustible']
    
    detalles_dep = []
    lugares = ""
    if dep_sols:
        try:
            data_json = json.loads(dep_sols[0].get('texto_ocr', '{}'))
            detalles_dep = data_json.get('tramos', [])
            lugares = data_json.get('lugares', '')
        except:
            pass
            
    pdf.cell(30, 6, "EMPLEADO:", border=1)
    pdf.cell(0, 6, empleado.upper(), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(30, 6, "LUGARES VISITADOS:", border=1)
    pdf.cell(0, 6, lugares.upper(), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(30, 6, "MUNICIPIO:", border=1)
    pdf.cell(0, 6, "", border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(30, 6, "DEPARTAMENTOS:", border=1)
    pdf.cell(0, 6, "", border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # --- TABLA 1: DEPRECIACION ---
    pdf.set_font("Arial", "B", 9)
    pdf.cell(0, 5, "DETALLE DE DEPRECIACIÓN", new_x="LMARGIN", new_y="NEXT")
    
    w = [10, 25, 35, 45, 30, 20, 30]
    headers = ["ITEM", "Fecha", "Punto de Partida", "Destino", "Km Recorrido", "L", "Total HNL"]
    pdf.set_fill_color(240, 240, 240)
    for i, h in enumerate(headers):
        pdf.cell(w[i], 6, h, border=1, align="C", fill=True)
    pdf.ln()
    
    pdf.set_font("Arial", "", 9)
    total_dep = 0
    factor = 7.91 
    
    for i, t in enumerate(detalles_dep):
        km = t.get('km', (t.get('lectura_final',0) - t.get('lectura_inicial',0)))
        total_h = km * factor
        total_dep += total_h
        
        pdf.cell(w[0], 6, str(i+1), border=1, align="C")
        pdf.cell(w[1], 6, t.get('fecha', ''), border=1, align="C")
        pdf.cell(w[2], 6, t.get('partida', ''), border=1, align="C")
        pdf.cell(w[3], 6, t.get('destino', ''), border=1, align="C")
        pdf.cell(w[4], 6, f"{km:.2f}", border=1, align="R")
        pdf.cell(w[5], 6, "L", border=1, align="C")
        pdf.cell(w[6], 6, f"{total_h:,.2f}", border=1, align="R")
        pdf.ln()

    # Total Depreciación
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(sum(w[:-1]), 6, "TOTAL DEPRECIACIÓN", border=1, align="R", fill=True)
    pdf.cell(w[-1], 6, f"{total_dep:,.2f}", border=1, align="R", fill=True)
    pdf.ln(10)

    # --- TABLA 2: COMBUSTIBLE ---
    pdf.set_font("Arial", "B", 9)
    pdf.cell(0, 5, "DETALLE DE GASTOS DE COMBUSTIBLE / CAMBIO ACEITES / MANO DE OBRA / REPUESTOS", new_x="LMARGIN", new_y="NEXT")
    
    # Actualizamos las columnas para incluir la fecha
    w2 = [10, 25, 35, 55, 30, 25]
    headers2 = ["ITEM", "Fecha", "No. Factura", "Descripción / Proveedor", "Total HNL"]
    pdf.set_fill_color(240, 240, 240)
    for i, h in enumerate(headers2):
        pdf.cell(w2[i], 6, h, border=1, align="C", fill=True)
    pdf.ln()

    total_comb = 0
    for i, s in enumerate(comb_sols):
        monto = float(s.get('monto', 0))
        total_comb += monto
        
        # Formatear fecha para que se vea bonita
        fecha = s.get('fecha_compra', '-')
        
        pdf.cell(w2[0], 6, str(i+1), border=1, align="C")
        pdf.cell(w2[1], 6, fecha, border=1, align="C")
        pdf.cell(w2[2], 6, s.get('num_factura', '-'), border=1, align="C")
        pdf.cell(w2[3], 6, (s.get('negocio', 'Gasolinera') or 'Gasolinera')[:30], border=1, align="L") # limitamos caracteres
        pdf.cell(w2[4], 6, f"{monto:,.2f}", border=1, align="R")
        pdf.ln()

    # Total Combustible
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(sum(w2[:-1]), 6, "TOTAL GASTOS DE COMBUSTIBLE", border=1, align="R", fill=True)
    pdf.cell(w2[-1], 6, f"{total_comb:,.2f}", border=1, align="R", fill=True)
    pdf.ln(10)

    # --- TOTAL PAGO ---
    total_pago = total_dep + total_comb
    
    pdf.cell(100, 6, "", border=0) 
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(40, 6, "TOTAL DEPRECIACION", border=1, align="R", fill=True)
    pdf.cell(30, 6, f"L {total_dep:,.2f}", border=1, align="R", fill=True)
    pdf.ln()
    
    pdf.cell(100, 6, "", border=0)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(40, 6, "(+) TOTAL COMBUSTIBLE", border=1, align="R", fill=True)
    pdf.cell(30, 6, f"L {total_comb:,.2f}", border=1, align="R", fill=True)
    pdf.ln()

    pdf.cell(100, 6, "", border=0)
    pdf.set_fill_color(0, 143, 57) 
    pdf.set_text_color(255, 255, 255)
    pdf.cell(40, 6, "TOTAL PAGO POR DEPRECIACION", border=1, align="R", fill=True)
    pdf.cell(30, 6, f"L {total_pago:,.2f}", border=1, align="R", fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(15)

    # --- REGISTRO FOTOGRÁFICO ---
    pdf.set_font("Arial", "B", 9)
    pdf.cell(0, 6, "REGISTRO FOTOGRÁFICO ODOMETRO", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font("Arial", "I", 8)
    pdf.cell(0, 6, "(Las fotos del odómetro se adjuntan en el expediente digital de la solicitud)", align="C", new_x="LMARGIN", new_y="NEXT")
    
    from core.config import REPORTES_DIR
    nombre_archivo = f"Reporte_Depreciacion_{empleado.replace(' ', '_')}.pdf"
    ruta_salida = os.path.join(REPORTES_DIR, nombre_archivo)
    pdf.output(ruta_salida)
    
    return ruta_salida

# Dejamos las otras funciones que ya tenías para que no se rompa nada
def numero_a_letras(numero):
    # ... (tu función original de convertir números a letras se mantiene igual) ...
    pass # (Mantén el código de numero_a_letras que ya tenías)

def generar_memo_pdf(solicitudes, empleado):
    pass # (Mantén el código de generar_memo_pdf que ya tenías)
