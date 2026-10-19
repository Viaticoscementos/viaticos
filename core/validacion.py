from core.config import RTN_EMPRESA_DEFAULT, NOMBRE_EMPRESA_DEFAULT

def validar(datos, texto_ocr=""):
    checklist = []
    motivos = []
    cumple = True

    # 1. Validar RTN del Emisor
    rtn_extraido = datos.get("rtn", "")
    if not rtn_extraido:
        checklist.append({"item": "RTN del emisor", "ok": False, "msg": "No se detectó el RTN del emisor."})
        motivos.append("Falta el RTN del emisor o esta incompleto")
        cumple = False
    else:
        checklist.append({"item": "RTN del emisor", "ok": True, "msg": f"RTN detectado: {rtn_extraido}"})

    # 2. Validar CAI
    cai = datos.get("cai", "")
    if not cai:
        checklist.append({"item": "CAI", "ok": False, "msg": "No se detectó el CAI."})
        motivos.append("Falta el CAI")
        cumple = False
    else:
        checklist.append({"item": "CAI", "ok": True, "msg": f"CAI detectado: {cai}"})

    # 3. Validar Fecha
    fecha = datos.get("fecha_compra", "")
    if not fecha:
        checklist.append({"item": "Fecha de compra", "ok": False, "msg": "No se detectó la fecha."})
        motivos.append("Falta la fecha de la factura")
        cumple = False
    else:
        checklist.append({"item": "Fecha de compra", "ok": True, "msg": f"Fecha detectada: {fecha}"})

    # 4. Validar Monto
    monto = float(datos.get("monto", 0.0))
    if monto <= 0:
        checklist.append({"item": "Monto total", "ok": False, "msg": "El monto es 0 o no se detectó."})
        motivos.append("Falta el valor de la factura")
        cumple = False
    else:
        checklist.append({"item": "Monto total", "ok": True, "msg": f"Monto detectado: L {monto}"})

    # 5. Validar que la factura esté a nombre de Cementos del Norte
    # Buscamos el RTN de la empresa o parte de su nombre en el texto completo
    texto_upper = texto_ocr.upper()
    nombre_empresa_corto = NOMBRE_EMPRESA_DEFAULT.split(" S.A")[0].upper()
    
    if RTN_EMPRESA_DEFAULT and RTN_EMPRESA_DEFAULT in texto_ocr:
        checklist.append({"item": "Factura a nombre de la empresa", "ok": True, "msg": "RTN de la empresa encontrado."})
    elif nombre_empresa_corto in texto_upper:
        checklist.append({"item": "Factura a nombre de la empresa", "ok": True, "msg": "Nombre de la empresa encontrado."})
    else:
        checklist.append({"item": "Factura a nombre de la empresa", "ok": False, "msg": "No parece estar a nombre de Cementos del Norte."})
        motivos.append("La factura no parece estar a nombre del RTN de la empresa")
        cumple = False

    # 6. Validar límite por categoría (si fue enviado desde app.py)
    limite_aplicado = float(datos.get("limite_manual", 99999999.0))
    if monto > limite_aplicado:
        motivos.append(f"El monto L {monto} excede el límite permitido de L {limite_aplicado}.")
        cumple = False
        
    # Definir estado final
    estado = "CUMPLE" if cumple else "NO_CUMPLE"
    
    # Si la ÚNICA razón por la que no cumple es porque excede el límite (todo lo demás está bien)
    if not cumple and len(motivos) == 1 and "excede" in motivos[0]:
        estado = "REVISAR" # Lo mandamos a la pestaña de revisión en lugar de rechazo directo

    return {
        "cumple": cumple,
        "estado": estado,
        "checklist": checklist,
        "motivos": " | ".join(motivos),
        "limite_aplicado": limite_aplicado,
        "monto": monto,
        "monto_reembolsable": monto if cumple else 0.0
    }
