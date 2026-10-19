"""Pago por depreciacion de vehiculo.

Formula base por tramo recorrido:
    distancia_km  = (lectura_final - lectura_inicial)  [convertida a km si viene en millas]
    depreciacion  = distancia_km * factor_lps_km

Soporta:
  - Unidad en KILOMETROS o MILLAS (se convierte todo a km internamente).
  - VARIOS tramos/dias y VARIOS vehiculos: se suman todas las distancias
    (por ejemplo, un dia usa un carro y al siguiente otro distinto).
  - Deduccion opcional al final.

El factor Lps/km cambia con el precio del combustible, por eso es editable
(se guarda en config_app).
"""
from core import db
from core.config import (FACTOR_LPS_KM_DEFAULT, FACTOR_CONVERSION_DEFAULT,
                         RESTAR_DEDUCCIONES_DEFAULT)

MILLA_A_KM = 1.609344  # 1 milla = 1.609344 km

_K_FACTOR = "dep_factor_lps_km"
_K_CONV = "dep_factor_conversion"
_K_RESTAR = "dep_restar_deducciones"


def _f(v, d=0.0):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return d


def obtener_parametros():
    factor = _f(db.obtener_config(_K_FACTOR), FACTOR_LPS_KM_DEFAULT)
    conv = _f(db.obtener_config(_K_CONV), FACTOR_CONVERSION_DEFAULT)
    r = db.obtener_config(_K_RESTAR)
    restar = RESTAR_DEDUCCIONES_DEFAULT if r is None else str(r).lower() in ("1", "true", "si", "s", "yes")
    return {"factor_lps_km": factor, "factor_conversion": conv, "restar_deducciones": restar}


def guardar_parametros(factor_lps_km, factor_conversion, restar_deducciones):
    db.guardar_config(_K_FACTOR, _f(factor_lps_km, FACTOR_LPS_KM_DEFAULT))
    db.guardar_config(_K_CONV, _f(factor_conversion, FACTOR_CONVERSION_DEFAULT))
    db.guardar_config(_K_RESTAR, "1" if restar_deducciones else "0")


def a_km(valor, unidad):
    """Convierte una distancia a kilometros segun la unidad ('km' o 'milla')."""
    v = _f(valor, 0.0)
    return v * MILLA_A_KM if (unidad or "").lower().startswith("mill") else v


def calcular_tramo(lectura_inicial, lectura_final, unidad="km", parametros=None):
    """Un solo tramo: diferencia de odometro -> km -> depreciacion."""
    p = parametros or obtener_parametros()
    li, lf = _f(lectura_inicial), _f(lectura_final)
    dif = max(lf - li, 0.0)
    km = a_km(dif, unidad) * p["factor_conversion"]
    dep = km * p["factor_lps_km"]
    return {
        "lectura_inicial": li, "lectura_final": lf, "unidad": unidad,
        "diferencia": dif, "km": round(km, 2), "depreciacion": round(dep, 2),
    }


def calcular(tramos, deducciones=0.0, parametros=None):
    """Suma varios tramos (dias/vehiculos distintos) y da el pago total.

    `tramos` es una lista de dicts con:
        fecha, vehiculo, unidad ('km'|'milla'), lectura_inicial, lectura_final
    """
    p = parametros or obtener_parametros()
    detalle, total_km, total_dep = [], 0.0, 0.0
    for t in (tramos or []):
        r = calcular_tramo(t.get("lectura_inicial"), t.get("lectura_final"),
                           t.get("unidad", "km"), p)
        r["fecha"] = t.get("fecha", "")
        r["vehiculo"] = t.get("vehiculo", "")
        total_km += r["km"]
        total_dep += r["depreciacion"]
        detalle.append(r)
    ded = _f(deducciones, 0.0)
    pago = total_dep - ded if p["restar_deducciones"] else total_dep
    return {
        "detalle": detalle,
        "total_km": round(total_km, 2),
        "total_depreciacion": round(total_dep, 2),
        "deducciones": ded,
        "factor_lps_km": p["factor_lps_km"],
        "pago_neto": round(max(pago, 0.0), 2),
        "num_tramos": len(detalle),
    }
