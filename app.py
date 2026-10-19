"""Plataforma web de reembolso de viaticos - Cementos del Norte (CENOSA).

Dos caras:
  - Portal publico (con enlace): el empleado sube su factura y el sistema le
    dice al instante si CUMPLE o NO CUMPLE.
  - Panel de la encargada (con login): pestañas Cumplen / No cumplen /
    Pendientes / Historial, para aprobar o rechazar y generar el memo.
"""
import os
import json
import shutil
import secrets
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from core import db, ocr, validacion, reportes, depreciacion, seed
from core.config import (BASE_DIR, FACTURAS_DIR, REPORTES_DIR, ZONAS,
                         ADMIN_USUARIO, ADMIN_PASSWORD, SECRET_KEY, PORTAL_TOKEN,
                         RTN_EMPRESA_DEFAULT, NOMBRE_EMPRESA_DEFAULT)

CATEGORIAS = ["Alimentacion", "Hotel", "Asistencia Tecnica", "Representacion",
              "Mercadeo", "Combustible", "Depreciacion", "Otros Gastos"]

# Orden jerarquico de los cargos (de mayor a menor). Lo que no tiene puesto
# definido queda al final.
ORDEN_PUESTOS = ["Gerente General", "Jefe", "Ingeniero Senior",
                 "Ingeniero Junior", "Ejecutivo de Ventas Senior",
                 "Ejecutivo de Ventas"]


def _rango_puesto(p):
    p = (p or "").strip()
    try:
        return ORDEN_PUESTOS.index(p)
    except ValueError:
        return len(ORDEN_PUESTOS)  # sin definir -> al final


def empleados_ordenados():
    """Empleados agrupados/ordenados por cargo y luego por nombre."""
    return sorted(db.listar_empleados(),
                  key=lambda e: (_rango_puesto(e.get("puesto")),
                                 (e.get("nombre") or "").lower()))

app = FastAPI(title="Viaticos CENOSA")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

db.init_db()
seed.sembrar()  # carga los empleados base solo si la tabla esta vacia


def _es_admin(request: Request) -> bool:
    return bool(request.session.get("admin"))


def requiere_admin(request: Request):
    if not _es_admin(request):
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return True


# ------------------------------------------------------------------ Portal
@app.get("/", response_class=HTMLResponse)
def portal(request: Request, token: str = ""):
    if PORTAL_TOKEN and token != PORTAL_TOKEN:
        return HTMLResponse("<h3>Enlace invalido. Solicite el enlace correcto "
                            "a la encargada de viaticos.</h3>", status_code=403)
    return templates.TemplateResponse(request, "portal.html", {
        "categorias": CATEGORIAS, "zonas": ZONAS,
        "empresa": NOMBRE_EMPRESA_DEFAULT, "token": token,
        "empleados": [e["nombre"] for e in db.listar_empleados()],
    })


@app.post("/api/validar")
async def api_validar(
    request: Request,
    archivo: UploadFile = File(...),
    empleado: str = Form(...),
    departamento: str = Form(""),
    zona: str = Form("tierra_firme"),
    categoria: str = Form(""),
    negocio: str = Form(""),
    num_factura: str = Form(""),
    rtn: str = Form(""),
    cai: str = Form(""),
    fecha_compra: str = Form(""),
    monto: str = Form(""),
    guardar: str = Form("1"),
):
    ext = Path(archivo.filename or "factura").suffix.lower() or ".png"
    nombre = f"{secrets.token_hex(6)}{ext}"
    destino = Path(FACTURAS_DIR) / nombre
    with open(destino, "wb") as f:
        shutil.copyfileobj(archivo.file, f)

    # OCR solo si el navegador no mando ya los datos leidos.
    datos = {"rtn": rtn, "cai": cai, "fecha_compra": fecha_compra,
             "monto": monto, "texto_ocr": ""}
    if not (rtn and cai and monto):
        try:
            leido = ocr.analizar(str(destino))
            for k in ("rtn", "cai", "fecha_compra", "monto"):
                if not datos.get(k):
                    datos[k] = leido.get(k) or datos.get(k)
            datos["texto_ocr"] = leido.get("texto_ocr", "")
            if not datos.get("fecha_limite"):
                datos["fecha_limite"] = leido.get("fecha_limite")
        except Exception as e:
            datos["texto_ocr"] = f"[OCR no disponible: {e}]"

    datos.update({"empleado": empleado, "departamento": departamento,
                  "zona": zona, "categoria": categoria})
    veredicto = validacion.validar(datos, datos.get("texto_ocr", ""))

    resultado = {
        "estado": veredicto["estado"],
        "cumple": veredicto["cumple"],
        "checklist": veredicto["checklist"],
        "motivos": veredicto["motivos"],
        "limite": veredicto["limite_aplicado"],
        "monto": veredicto["monto"],
        "reembolsable": veredicto["monto_reembolsable"],
        "datos": {k: datos.get(k) for k in ("rtn", "cai", "fecha_compra", "monto")},
    }

    if guardar in ("1", "true", "on"):
        db.asegurar_empleado(empleado, departamento)
        reg = db.crear_solicitud({
            "empleado": empleado, "departamento": departamento, "zona": zona,
            "categoria": categoria, "archivo": nombre, "rtn": datos.get("rtn"),
            "cai": datos.get("cai"), "fecha_compra": datos.get("fecha_compra"),
            "fecha_limite": datos.get("fecha_limite"), "negocio": negocio,
            "num_factura": num_factura, "monto": veredicto["monto"],
            "monto_reembolsable": veredicto["monto_reembolsable"],
            "limite_aplicado": veredicto["limite_aplicado"],
            "cumple": veredicto["cumple"], "estado": veredicto["estado"],
            "motivos": veredicto["motivos"], "texto_ocr": datos.get("texto_ocr", ""),
        })
        resultado["folio"] = reg["folio"]
    else:
        destino.unlink(missing_ok=True)
    return JSONResponse(resultado)


# ------------------------------------------------------------------ Depreciacion de vehiculo
@app.get("/depreciacion", response_class=HTMLResponse)
def depreciacion_portal(request: Request, token: str = ""):
    if PORTAL_TOKEN and token != PORTAL_TOKEN:
        return HTMLResponse("<h3>Enlace invalido.</h3>", status_code=403)
    p = depreciacion.obtener_parametros()
    return templates.TemplateResponse(request, "depreciacion.html", {
        "zonas": ZONAS, "empresa": NOMBRE_EMPRESA_DEFAULT, "token": token,
        "empleados": [e["nombre"] for e in db.listar_empleados()],
        "factor": p["factor_lps_km"], "milla_km": depreciacion.MILLA_A_KM,
    })


@app.post("/api/leer-odometro")
async def api_leer_odometro(archivo: UploadFile = File(...)):
    """Lee el numero del odometro de una foto (para autollenar la lectura)."""
    ext = Path(archivo.filename or "odo").suffix.lower() or ".png"
    tmp = Path(FACTURAS_DIR) / f"odo_{secrets.token_hex(5)}{ext}"
    with open(tmp, "wb") as f:
        shutil.copyfileobj(archivo.file, f)
    try:
        r = ocr.leer_odometro(str(tmp))
    except Exception as e:
        r = {"valor": None, "texto": f"[OCR no disponible: {e}]"}
    finally:
        tmp.unlink(missing_ok=True)
    return JSONResponse(r)


@app.post("/api/depreciacion")
async def api_depreciacion(
    empleado: str = Form(...),
    departamento: str = Form(""),
    zona: str = Form("tierra_firme"),
    deducciones: str = Form("0"),
    tramos: str = Form("[]"),
    guardar: str = Form("1"),
):
    try:
        lista = json.loads(tramos or "[]")
    except json.JSONDecodeError:
        lista = []
    if not lista:
        return JSONResponse({"error": "No se enviaron tramos de kilometraje."},
                            status_code=400)
    res = depreciacion.calcular(lista, deducciones=deducciones)
    resumen = "; ".join(
        f"{t.get('fecha','')} {t.get('vehiculo','')} "
        f"{t['lectura_inicial']:.0f}->{t['lectura_final']:.0f} {t['unidad']} "
        f"({t['km']:.1f} km)" for t in res["detalle"])
    if guardar in ("1", "true", "on"):
        db.asegurar_empleado(empleado, departamento)
        reg = db.crear_solicitud({
            "empleado": empleado, "departamento": departamento, "zona": zona,
            "categoria": "Depreciacion", "negocio": "Depreciacion de vehiculo",
            "monto": res["pago_neto"], "monto_reembolsable": res["pago_neto"],
            "limite_aplicado": None, "cumple": True, "estado": "CUMPLE",
            "motivos": f"{res['num_tramos']} tramo(s), {res['total_km']:.1f} km "
                       f"x L{res['factor_lps_km']}/km",
            "texto_ocr": resumen,
        })
        res["folio"] = reg["folio"]
    return JSONResponse(res)


# ------------------------------------------------------------------ Login
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "login.html", {"error": error})


@app.post("/login")
def login(request: Request, usuario: str = Form(...), password: str = Form(...)):
    if secrets.compare_digest(usuario, ADMIN_USUARIO) and \
       secrets.compare_digest(password, ADMIN_PASSWORD):
        request.session["admin"] = usuario
        return RedirectResponse("/panel", status_code=303)
    return RedirectResponse("/login?error=1", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ------------------------------------------------------------------ Panel
@app.get("/panel", response_class=HTMLResponse)
def panel(request: Request, tab: str = "cumplen"):
    if not _es_admin(request):
        return RedirectResponse("/login", status_code=303)
    cumplen = db.listar_solicitudes(estado="CUMPLE")
    revisar = db.listar_solicitudes(estado="REVISAR")
    nocumplen = db.listar_solicitudes(estado="NO_CUMPLE")
    pendientes = cumplen + revisar
    historial = (db.listar_solicitudes(estado="APROBADO") +
                 db.listar_solicitudes(estado="RECHAZADO"))
    return templates.TemplateResponse(request, "panel.html", {
        "tab": tab, "usuario": request.session.get("admin"),
        "cumplen": cumplen, "revisar": revisar, "nocumplen": nocumplen,
        "pendientes": pendientes, "historial": historial,
        "conteos": {"cumplen": len(cumplen), "revisar": len(revisar),
                    "nocumplen": len(nocumplen), "pendientes": len(pendientes),
                    "historial": len(historial)},
        "empresa": NOMBRE_EMPRESA_DEFAULT,
    })


@app.post("/panel/decidir")
def decidir(request: Request, sid: int = Form(...), decision: str = Form(...),
            observaciones: str = Form("")):
    if not _es_admin(request):
        return RedirectResponse("/login", status_code=303)
    db.decidir_solicitud(sid, decision.upper(), observaciones)
    return RedirectResponse("/panel?tab=historial", status_code=303)


@app.get("/panel/factura/{sid}")
def ver_factura(request: Request, sid: int):
    if not _es_admin(request):
        return RedirectResponse("/login", status_code=303)
    s = db.obtener_solicitud(sid)
    if not s or not s.get("archivo"):
        raise HTTPException(404)
    ruta = Path(FACTURAS_DIR) / s["archivo"]
    if not ruta.exists():
        raise HTTPException(404)
    return FileResponse(str(ruta))


@app.get("/panel/memo/{sid}")
def memo(request: Request, sid: int):
    if not _es_admin(request):
        return RedirectResponse("/login", status_code=303)
    s = db.obtener_solicitud(sid)
    if not s:
        raise HTTPException(404)
    ruta = reportes.generar_memo(s)
    return FileResponse(str(ruta), filename=Path(ruta).name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/panel/memo-empleado/{empleado}")
def memo_empleado(request: Request, empleado: str):
    if not _es_admin(request):
        return RedirectResponse("/login", status_code=303)
    sols = [s for s in (db.listar_solicitudes(estado="APROBADO"))
            if (s.get("empleado") or "").lower() == empleado.lower()]
    if not sols:
        raise HTTPException(404, "Sin facturas aprobadas para ese empleado")
    ruta = reportes.generar_memo(sols, empleado=empleado)
    return FileResponse(str(ruta), filename=Path(ruta).name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/panel/tabla")
def tabla(request: Request, estado: str = ""):
    if not _es_admin(request):
        return RedirectResponse("/login", status_code=303)
    sols = db.listar_solicitudes(estado=estado or None)
    ruta = reportes.generar_tabla(sols)
    return FileResponse(str(ruta), filename=Path(ruta).name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ----- Catalogo de empleados y configuracion -----
@app.get("/panel/empleados", response_class=HTMLResponse)
def empleados_form(request: Request, msg: str = ""):
    if not _es_admin(request):
        return RedirectResponse("/login", status_code=303)
    cfg = {"rtn_empresa": db.obtener_config("rtn_empresa", RTN_EMPRESA_DEFAULT),
           "nombre_empresa": db.obtener_config("nombre_empresa", NOMBRE_EMPRESA_DEFAULT)}
    dep = depreciacion.obtener_parametros()
    return templates.TemplateResponse(request, "empleados.html", {
        "empleados": empleados_ordenados(),
        "orden_puestos": ORDEN_PUESTOS,
        "limites": db.listar_limites(), "zonas": ZONAS, "cfg": cfg,
        "dep": dep, "msg": msg,
    })


@app.post("/panel/empleados/agregar")
def empleados_agregar(request: Request, nombre: str = Form(...),
                      puesto: str = Form(""), departamento: str = Form(""),
                      limite: str = Form(""), deprecia: str = Form("")):
    if not _es_admin(request):
        return RedirectResponse("/login", status_code=303)
    db.agregar_empleado(nombre, puesto, departamento,
                        deprecia_vehiculo=bool(deprecia))
    if limite.strip():
        try:
            db.guardar_limite("empleado", nombre, float(limite))
        except ValueError:
            pass
    return RedirectResponse("/panel/empleados?msg=ok", status_code=303)


@app.post("/panel/empleados/eliminar")
def empleados_eliminar(request: Request, emp_id: int = Form(...)):
    if not _es_admin(request):
        return RedirectResponse("/login", status_code=303)
    db.eliminar_empleado(emp_id)
    return RedirectResponse("/panel/empleados?msg=del", status_code=303)


@app.get("/panel/empleados/editar/{emp_id}", response_class=HTMLResponse)
def empleados_editar_form(request: Request, emp_id: int):
    if not _es_admin(request):
        return RedirectResponse("/login", status_code=303)
    emp = db.obtener_empleado(emp_id)
    if not emp:
        raise HTTPException(404, "Empleado no encontrado")
    lim = db.obtener_limite("empleado", emp["nombre"])
    return templates.TemplateResponse(request, "editar_empleado.html", {
        "emp": emp, "limite": lim,
    })


@app.post("/panel/empleados/editar")
def empleados_editar(request: Request, emp_id: int = Form(...),
                     nombre: str = Form(...), puesto: str = Form(""),
                     departamento: str = Form(""), correo: str = Form(""),
                     fondo_rotativo: str = Form(""), deprecia: str = Form(""),
                     limite: str = Form(""), sin_limite: str = Form("")):
    if not _es_admin(request):
        return RedirectResponse("/login", status_code=303)
    r = db.actualizar_empleado(emp_id, nombre=nombre, puesto=puesto,
                               departamento=departamento, correo=correo,
                               deprecia_vehiculo=bool(deprecia),
                               fondo_rotativo=fondo_rotativo)
    if r.get("ok"):
        # si cambio el nombre, mover el limite al nombre nuevo
        viejo = r.get("nombre_anterior")
        nuevo = r.get("nombre_nuevo")
        if viejo and nuevo and viejo.lower() != nuevo.lower():
            db.eliminar_limite("empleado", viejo)
        if sin_limite:
            db.eliminar_limite("empleado", nuevo or nombre)
        elif limite.strip():
            try:
                db.guardar_limite("empleado", nuevo or nombre, float(limite))
            except ValueError:
                pass
    return RedirectResponse("/panel/empleados?msg=edit", status_code=303)


@app.post("/panel/config")
def guardar_config(request: Request, rtn_empresa: str = Form(""),
                   nombre_empresa: str = Form(""),
                   factor_lps_km: str = Form(""),
                   factor_conversion: str = Form(""),
                   restar_deducciones: str = Form("")):
    if not _es_admin(request):
        return RedirectResponse("/login", status_code=303)
    if rtn_empresa.strip():
        db.guardar_config("rtn_empresa", rtn_empresa.strip())
    if nombre_empresa.strip():
        db.guardar_config("nombre_empresa", nombre_empresa.strip())
    depreciacion.guardar_parametros(factor_lps_km or depreciacion.obtener_parametros()["factor_lps_km"],
                                    factor_conversion or depreciacion.obtener_parametros()["factor_conversion"],
                                    bool(restar_deducciones))
    return RedirectResponse("/panel/empleados?msg=cfg", status_code=303)


@app.get("/salud")
def salud():
    return {"ok": True, "tesseract": bool(ocr.pytesseract.pytesseract.tesseract_cmd)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=int(os.environ.get("PORT", 8000)),
                reload=False)
