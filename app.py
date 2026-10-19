"""Plataforma web de reembolso de viaticos - Cementos del Norte (CENOSA)."""
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

ORDEN_PUESTOS = ["Gerente General", "Jefe", "Ingeniero Senior",
                 "Ingeniero Junior", "Ejecutivo de Ventas Senior",
                 "Ejecutivo de Ventas"]

def _rango_puesto(p):
    p = (p or "").strip()
    try:
        return ORDEN_PUESTOS.index(p)
    except ValueError:
        return len(ORDEN_PUESTOS)

def empleados_ordenados():
    return sorted(db.listar_empleados(), key=lambda e: (_rango_puesto(e.get("puesto")), (e.get("nombre") or "").lower()))

def get_limites_puestos():
    c_str = db.obtener_config("limites_puestos", "")
    if c_str:
        try: return json.loads(c_str)
        except: pass
    
    default = {}
    for p in ORDEN_PUESTOS:
        default[p] = {cat: 300.0 for cat in CATEGORIAS}
    return default

def get_centros_costos():
    c_str = db.obtener_config("centros_costos", "")
    if c_str:
        try: return json.loads(c_str)
        except: pass
    return ["Ventas V60140", "Administración", "Planta / Producción", "Logística / Bodega", "Recursos Humanos", "Contabilidad / Finanzas", "Gerencia General", "Mercadeo", "Sistemas / TI"]

app = FastAPI(title="Viaticos CENOSA")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

db.init_db()
seed.sembrar()

@app.on_event("startup")
def cargar_presupuestos_al_iniciar():
    try:
        limites = db.listar_limites()
        if len(limites) < 5:
            datos_2026 = {
                "Cindy Artola": 5000.00, "Mario Doblado": 5000.00, "Maria Josee Coto": 11000.00, "Christopher Midence": 17000.00, "Carlos Humberto Mejia": 35000.00, "Eduardo Lopez Lopez": 15000.00, "Luis Fernando Ponce": 33000.00, "Olga Elizabeth Osorto": 35000.00, "Eduardo Rene Mejia Rodriguez": 35000.00, "Steven Garcia": 33000.00, "Marco Smith": 33000.00, "Yeni Yamilet Castellanos": 25000.00, "Jose Samuel Lopez": 30000.00, "Linda de Jesus Notasco": 35000.00, "Oscar Ivan Sierra Linares": 24000.00, "Mario Jose Urquia": 35000.00, "Joan Jorge Pineda": 35000.00, "Rafael Alberto Perez": 10000.00, "Martha Julissa Perla (Caja Chica)": 10000.00, "Martha Julissa Perla (Gastos Mercadeo)": 10000.00, "Nolvin Roel Rivera": 15000.00, "Carlos Enrique Jallu": 10000.00, "Beverly Yasmira Rivera": 25000.00, "Renato Miguel Gonzales": 35000.00, "Edwin Geovani Samayoa": 35000.00, "Cindy Julissa Guevara": 20000.00, "Manuel Alejandro Reyes": 30000.00, "Kevin Wilfredo Villela": 35000.00, "Saul Edgardo Herrera": 35000.00, "Luis Gerardo de Jesus": 30000.00
            }
            for nombre, monto in datos_2026.items(): db.guardar_limite("empleado", nombre, monto)
    except Exception as e: print(f"Error: {e}")

def _es_admin(request: Request) -> bool:
    return bool(request.session.get("admin")) and request.session.get("rol") == "admin"

# ------------------------------------------------------------------ Portal
@app.get("/", response_class=HTMLResponse)
def portal(request: Request, token: str = ""):
    if PORTAL_TOKEN and token != PORTAL_TOKEN:
        return HTMLResponse("<h3>Enlace invalido.</h3>", status_code=403)
    return templates.TemplateResponse(request, "portal.html", {
        "categorias": CATEGORIAS, "zonas": ZONAS, "centros_costos": get_centros_costos(),
        "empresa": NOMBRE_EMPRESA_DEFAULT, "token": token,
        "empleados": empleados_ordenados(), "limites_puestos": get_limites_puestos(),
        "orden_puestos": ORDEN_PUESTOS
    })

@app.post("/api/validar")
async def api_validar(
    request: Request, archivo: UploadFile = File(...), empleado: str = Form(...),
    departamento: str = Form(""), zona: str = Form("tierra_firme"),
    categoria: str = Form("Alimentacion"), negocio: str = Form(""), num_factura: str = Form(""),
):
    ext = Path(archivo.filename or "factura").suffix.lower() or ".png"
    nombre = f"{secrets.token_hex(6)}{ext}"
    destino = Path(FACTURAS_DIR) / nombre
    with open(destino, "wb") as f: shutil.copyfileobj(archivo.file, f)

    datos = {"rtn": "", "cai": "", "fecha_compra": "", "monto": 0.0, "texto_ocr": ""}
    try:
        leido = ocr.analizar(str(destino))
        for k in ("rtn", "cai", "fecha_compra", "monto"):
            if leido.get(k): datos[k] = leido.get(k)
        datos["texto_ocr"] = leido.get("texto_ocr", "")
    except Exception as e: datos["texto_ocr"] = f"[OCR no disponible: {e}]"

    emp_info = next((e for e in db.listar_empleados() if e["nombre"].lower() == empleado.lower()), None)
    puesto = emp_info.get("puesto", "Ejecutivo de Ventas") if emp_info else "Ejecutivo de Ventas"
    if not puesto or puesto not in ORDEN_PUESTOS: puesto = ORDEN_PUESTOS[-1]

    limites_db = get_limites_puestos()
    limite_categoria = limites_db.get(puesto, {}).get(categoria, 300.0)
    
    # Si el límite es -1, significa ILIMITADO. Ponemos un número gigante para que pase la validación.
    if limite_categoria == -1.0:
        limite_categoria = 99999999.0

    datos.update({"empleado": empleado, "departamento": departamento, "zona": zona, "categoria": categoria, "limite_manual": limite_categoria})
    veredicto = validacion.validar(datos, datos.get("texto_ocr", ""))

    db.asegurar_empleado(empleado, departamento)
    reg = db.crear_solicitud({
        "empleado": empleado, "departamento": departamento, "zona": zona, "categoria": categoria,
        "archivo": nombre, "rtn": datos.get("rtn"), "cai": datos.get("cai"),
        "fecha_compra": datos.get("fecha_compra"), "monto": veredicto["monto"],
        "monto_reembolsable": veredicto["monto_reembolsable"], "limite_aplicado": veredicto["limite_aplicado"],
        "cumple": veredicto["cumple"], "estado": veredicto["estado"], "motivos": veredicto["motivos"],
        "texto_ocr": datos.get("texto_ocr", ""),
    })
    return JSONResponse({"estado": veredicto["estado"], "cumple": veredicto["cumple"], "motivos": veredicto["motivos"], "monto_extraido": veredicto["monto"], "folio": reg["folio"]})

# ------------------------------------------------------------------ Panel Admin
@app.get("/panel/limites", response_class=HTMLResponse)
def limites_form(request: Request, msg: str = ""):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "limites.html", {
        "usuario": request.session.get("admin"), "rol": "admin",
        "orden_puestos": ORDEN_PUESTOS, "categorias": CATEGORIAS,
        "limites": get_limites_puestos(), "msg": msg
    })

@app.post("/panel/limites/guardar")
async def limites_guardar(request: Request):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    form_data = await request.form()
    
    nuevos_limites = {}
    for key, value in form_data.items():
        if key.startswith("limite|"):
            partes = key.split("|")
            puesto, categoria = partes[1], partes[2]
            if puesto not in nuevos_limites: nuevos_limites[puesto] = {}
            
            # Verificamos si la casilla de "Ilimitado" para este puesto/categoría fue marcada
            if f"ilimitado|{puesto}|{categoria}" in form_data:
                nuevos_limites[puesto][categoria] = -1.0
            else:
                try: nuevos_limites[puesto][categoria] = float(value) if value.strip() else 0.0
                except: nuevos_limites[puesto][categoria] = 0.0

    db.guardar_config("limites_puestos", json.dumps(nuevos_limites))
    return RedirectResponse("/panel/limites?msg=ok", status_code=303)

# (Las demás rutas se mantienen igual, por brevedad solo incluyo las afectadas. 
# Si necesitas el app.py completo de nuevo, dímelo, pero este código ya contiene todo lo de arriba funcionando).
# ... [Aquí va el resto del app.py que ya tenías] ...
