"""Reglas que deciden si una factura CUMPLE o NO CUMPLE.

Checklist de la SAR (lo que escuchamos en la grabacion):
  - RTN del emisor presente (14 digitos)
  - CAI presente
  - Fecha de compra presente y no futura
  - No vencida (si trae fecha limite)
  - Que venga a nombre del RTN de la empresa (CENOSA)
  - Monto dentro del limite autorizado del empleado/zona

Un requisito faltante o un error -> NO CUMPLE (con el detalle del motivo).
"""
import re
from datetime import datetime

from core import db
from core.config import RTN_EMPRESA_DEFAULT, NOMBRE_EMPRESA_DEFAULT, ZONAS, LIMITE_DEFAULT


def _solo_dig(s):
    return "".join(ch for ch in str(s or "") if ch.isdigit())


def rtn_empresa():
    rtn = db.obtener_config("rtn_empresa", RTN_EMPRESA_DEFAULT)
    nombre = db.obtener_config("nombre_empresa", NOMBRE_EMPRESA_DEFAULT)
    return _solo_dig(rtn), nombre


def _norm_fecha(f):
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y",
                "%d-%m-%y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(f, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def limite_zona(empleado, departamento, zona, categoria="alimentacion"):
    """Limite aplicable: primero el del empleado/departamento cargado a mano;
    si no hay, el tope de la zona segun la categoria (alimentacion/hotel)."""
    lim = db.obtener_limite("empleado", empleado)
    if lim is not None:
        return lim, f"limite del empleado ({empleado})"
    lim = db.obtener_limite("departamento", departamento)
    if lim is not None:
        return lim, f"limite del departamento ({departamento})"
    z = ZONAS.get(zona or "tierra_firme", ZONAS["tierra_firme"])
    cat = (categoria or "").lower()
    if "hotel" in cat or "hosped" in cat:
        return z["hotel"], f"tope de hotel {z['etiqueta']}"
    return z.get("alimentacion", LIMITE_DEFAULT), f"tope de alimentacion {z['etiqueta']}"


def validar(campos, texto_ocr=""):
    """Recibe los campos (del OCR o editados) y devuelve el veredicto.

    Devuelve dict con:
      cumple (bool), estado ('CUMPLE'|'NO_CUMPLE'|'REVISAR'),
      checklist (lista de {item, ok, nota}), motivos (texto),
      limite_aplicado, monto_reembolsable.
    """
    checklist = []
    motivos = []

    rtn = _solo_dig(campos.get("rtn"))
    ok_rtn = len(rtn) == 14
    checklist.append({"item": "RTN del emisor", "ok": ok_rtn,
                      "nota": ("RTN valido" if ok_rtn else
                               "RTN no detectado o incompleto (deben ser 14 digitos)")})
    if not ok_rtn:
        motivos.append("Falta el RTN del emisor o esta incompleto")

    cai = (campos.get("cai") or "").strip()
    ok_cai = len(cai) >= 10
    checklist.append({"item": "CAI", "ok": ok_cai,
                      "nota": ("CAI presente" if ok_cai else "CAI no detectado")})
    if not ok_cai:
        motivos.append("Falta el CAI")

    f_compra = _norm_fecha(campos.get("fecha_compra"))
    ok_fecha = f_compra is not None
    nota_fecha = "Fecha de compra presente"
    if not ok_fecha:
        nota_fecha = "Fecha de compra no detectada"
        motivos.append("Falta la fecha de la factura")
    elif f_compra > datetime.now().date():
        ok_fecha = False
        nota_fecha = f"Fecha futura ({campos.get('fecha_compra')})"
        motivos.append("La fecha de la factura es futura")
    checklist.append({"item": "Fecha de la factura", "ok": ok_fecha, "nota": nota_fecha})

    f_lim = _norm_fecha(campos.get("fecha_limite"))
    if f_lim is not None:
        ok_vig = f_lim >= datetime.now().date()
        checklist.append({"item": "Vigencia (fecha limite)", "ok": ok_vig,
                          "nota": ("Vigente" if ok_vig else f"Factura vencida (limite {f_lim})")})
        if not ok_vig:
            motivos.append("La factura esta vencida")

    # A nombre del RTN de la empresa
    objetivo, nombre_emp = rtn_empresa()
    presente = False
    if objetivo:
        dig_texto = _solo_dig(texto_ocr)
        if objetivo in dig_texto or objetivo in _solo_dig(campos.get("rtn_cliente")):
            presente = True
    checklist.append({"item": f"A nombre de la empresa ({nombre_emp})", "ok": presente,
                      "nota": ("La factura esta a nombre de la empresa" if presente else
                               "No se detecto el RTN de la empresa en la factura")})
    if not presente:
        motivos.append("La factura no parece estar a nombre del RTN de la empresa")

    # Monto vs limite
    try:
        monto = float(str(campos.get("monto") or 0).replace(",", ""))
    except (TypeError, ValueError):
        monto = 0.0
    ok_monto = monto > 0
    checklist.append({"item": "Monto / valor", "ok": ok_monto,
                      "nota": (f"L {monto:,.2f}" if ok_monto else "Monto no detectado")})
    if not ok_monto:
        motivos.append("Falta el valor de la factura")

    lim, fuente = limite_zona(campos.get("empleado"), campos.get("departamento"),
                              campos.get("zona"), campos.get("categoria"))
    excede = monto > lim
    reembolsable = lim if excede else monto
    checklist.append({"item": "Dentro del limite", "ok": not excede,
                      "nota": (f"Dentro del limite L {lim:,.2f} ({fuente})" if not excede else
                               f"Excede el limite L {lim:,.2f}: se reembolsa hasta el tope")})

    # Veredicto
    requisitos_ok = all(c["ok"] for c in checklist
                        if c["item"] not in ("Dentro del limite",))
    if not requisitos_ok:
        estado = "NO_CUMPLE"
        cumple = False
    elif excede:
        estado = "REVISAR"
        cumple = True
    else:
        estado = "CUMPLE"
        cumple = True

    return {
        "cumple": cumple,
        "estado": estado,
        "checklist": checklist,
        "motivos": "; ".join(motivos),
        "limite_aplicado": lim,
        "monto": monto,
        "monto_reembolsable": reembolsable,
        "excede_limite": excede,
    }
