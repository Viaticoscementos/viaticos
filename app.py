"""Plataforma web de reembolso de viaticos - Cementos del Norte (CENOSA)."""
import os
import json
import shutil
import secrets
from pathlib import Path
from typing import List

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
    try: return ORDEN_PUESTOS.index(p)
    except ValueError: return len(ORDEN_PUESTOS)

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
@app.head("/")
def health_check():
    return {"status": "ok"}
def portal(request: Request, token: str = ""):
    if PORTAL_TOKEN and token != PORTAL_TOKEN:
        return HTMLResponse("<h3>Enlace invalido.</h3>", status_code=403)
    return templates.TemplateResponse(request, "portal.html", {
        "categorias": CATEGORIAS, "zonas": ZONAS, "centros_costos": get_centros_costos(),
        "empresa": NOMBRE_EMPRESA_DEFAULT, "token": token,
        "empleados": empleados_ordenados(), "limites_puestos": get_limites_puestos(),
        "orden_puestos": ORDEN_PUESTOS
    })

# --- RUTA API VALIDAR (CON SOPORTE PARA FOTOS DE KM INICIAL Y FINAL) ---
@app.post("/api/validar")
async def api_validar(
    request: Request, 
    archivos: List[UploadFile] = File(...), 
    km_inicial: str = Form(""), 
    km_final: str = Form(""),
    foto_km_inicial: UploadFile = File(None), # <-- Foto inicial opcional
    foto_km_final: UploadFile = File(None),   # <-- Foto final opcional
    empleado: str = Form(...),
    departamento: str = Form(""), 
    zona: str = Form("tierra_firme"),
    categoria: str = Form("Alimentacion"), 
    negocio: str = Form(""), 
    num_factura: str = Form(""),
):
    nombres_guardados = []
    primer_archivo_path = None
    info_km = ""

    # 1. Guardar archivos de factura
    for archivo in archivos:
        ext = Path(archivo.filename or "factura").suffix.lower() or ".png"
        nombre = f"{secrets.token_hex(6)}{ext}"
        destino = Path(FACTURAS_DIR) / nombre
        with open(destino, "wb") as f: 
            shutil.copyfileobj(archivo.file, f)
        
        nombres_guardados.append(nombre)
        if not primer_archivo_path:
            primer_archivo_path = str(destino)

    # 2. Guardar fotos de odómetro si existen
    if foto_km_inicial and foto_km_inicial.filename:
        ext_ini = Path(foto_km_inicial.filename).suffix.lower() or ".png"
        nombre_ini = f"odo_ini_{secrets.token_hex(6)}{ext_ini}"
        destino_ini = Path(FACTURAS_DIR) / nombre_ini
        with open(destino_ini, "wb") as f: shutil.copyfileobj(foto_km_inicial.file, f)
        nombres_guardados.append(nombre_ini)

    if foto_km_final and foto_km_final.filename:
        ext_fin = Path(foto_km_final.filename).suffix.lower() or ".png"
        nombre_fin = f"odo_fin_{secrets.token_hex(6)}{ext_fin}"
        destino_fin = Path(FACTURAS_DIR) / nombre_fin
        with open(destino_fin, "wb") as f: shutil.copyfileobj(foto_km_final.file, f)
        nombres_guardados.append(nombre_fin)

    # 3. Procesar kilometraje si es combustible
    if categoria == 'Combustible':
        try:
            ki = float(km_inicial) if km_inicial else 0.0
            kf = float(km_final) if km_final else 0.0
            if kf > ki:
                distancia = kf - ki
                info_km = f" [Km Inicial: {ki:.0f} | Km Final: {kf:.0f} | Recorrido: {distancia:.0f} km]"
            else:
                info_km = f" [Error en lecturas: Inicial {ki}, Final {kf}]"
        except ValueError:
            info_km = " [Error al leer los kilometrajes]"

    # 4. Hacemos el OCR sobre la factura
    datos = {"rtn": "", "cai": "", "fecha_compra": "", "monto": 0.0, "texto_ocr": ""}
    if primer_archivo_path:
        try:
            leido = ocr.analizar(primer_archivo_path)
            for k in ("rtn", "cai", "fecha_compra", "monto"):
                if leido.get(k): datos[k] = leido.get(k)
            datos["texto_ocr"] = leido.get("texto_ocr", "")
        except Exception as e: 
            datos["texto_ocr"] = f"[OCR no disponible: {e}]"

    # 5. Validar con reglas de negocio
    emp_info = next((e for e in db.listar_empleados() if e["nombre"].lower() == empleado.lower()), None)
    puesto = emp_info.get("puesto", "Ejecutivo de Ventas") if emp_info else "Ejecutivo de Ventas"
    if not puesto or puesto not in ORDEN_PUESTOS: puesto = ORDEN_PUESTOS[-1]

    limites_db = get_limites_puestos()
    limite_categoria = limites_db.get(puesto, {}).get(categoria, 300.0)
    if limite_categoria == -1.0: limite_categoria = 99999999.0

    datos.update({"empleado": empleado, "departamento": departamento, "zona": zona, "categoria": categoria, "limite_manual": limite_categoria})
    veredicto = validacion.validar(datos, datos.get("texto_ocr", ""))

    # 6. Guardar en BD
    db.asegurar_empleado(empleado, departamento)
    archivos_str = ",".join(nombres_guardados)
    
    motivos_finales = veredicto["motivos"] + info_km
    if info_km and veredicto["cumple"]:
        motivos_finales = f"Factura válida.{info_km}"

    reg = db.crear_solicitud({
        "empleado": empleado, "departamento": departamento, "zona": zona, "categoria": categoria,
        "archivo": archivos_str, "rtn": datos.get("rtn"), "cai": datos.get("cai"),
        "fecha_compra": datos.get("fecha_compra"), "monto": veredicto["monto"],
        "monto_reembolsable": veredicto["monto_reembolsable"], "limite_aplicado": veredicto["limite_aplicado"],
        "cumple": veredicto["cumple"], "estado": veredicto["estado"], "motivos": motivos_finales,
        "texto_ocr": datos.get("texto_ocr", ""),
    })
    
    return JSONResponse({
        "estado": veredicto["estado"], "cumple": veredicto["cumple"], "motivos": motivos_finales, 
        "monto_extraido": veredicto["monto"], "folio": reg["folio"]
    })

# ------------------------------------------------------------------ Login
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "login.html", {"error": error})

@app.post("/login")
def login(request: Request, usuario: str = Form(...), password: str = Form(...)):
    if secrets.compare_digest(usuario, ADMIN_USUARIO) and secrets.compare_digest(password, ADMIN_PASSWORD):
        request.session["admin"] = usuario
        request.session["rol"] = "admin"
        return RedirectResponse("/panel", status_code=303)
    empleados = [e["nombre"].lower() for e in db.listar_empleados()]
    if usuario.lower() in empleados:
        request.session["admin"] = usuario
        request.session["rol"] = "empleado"
        return RedirectResponse("/panel", status_code=303)
    return RedirectResponse("/login?error=1", status_code=303)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

# ------------------------------------------------------------------ Panel
@app.get("/panel", response_class=HTMLResponse)
def panel(request: Request, tab: str = "cumplen"):
    usuario = request.session.get("admin")
    rol = request.session.get("rol", "empleado" if usuario else None)
    if not usuario: return RedirectResponse("/login", status_code=303)

    presupuesto_actual = db.obtener_limite("empleado", usuario) or 0.0
    if rol == "admin":
        cumplen = db.listar_solicitudes(estado="CUMPLE")
        revisar = db.listar_solicitudes(estado="REVISAR")
        nocumplen = db.listar_solicitudes(estado="NO_CUMPLE")
        pendientes = cumplen + revisar
        historial = (db.listar_solicitudes(estado="APROBADO") + db.listar_solicitudes(estado="RECHAZADO"))
    else:
        todas = db.listar_solicitudes()
        mis_sols = [s for s in todas if s.get("empleado", "").lower() == usuario.lower()]
        cumplen = [s for s in mis_sols if s["estado"] == "CUMPLE"]
        revisar = [s for s in mis_sols if s["estado"] == "REVISAR"]
        nocumplen = [s for s in mis_sols if s["estado"] == "NO_CUMPLE"]
        pendientes = [s for s in mis_sols if s["estado"] in ("CUMPLE", "REVISAR")]
        historial = [s for s in mis_sols if s["estado"] in ("APROBADO", "RECHAZADO")]

    return templates.TemplateResponse(request, "panel.html", {
        "tab": tab, "usuario": usuario, "rol": rol, "presupuesto": presupuesto_actual,
        "cumplen": cumplen, "revisar": revisar, "nocumplen": nocumplen, "pendientes": pendientes, "historial": historial,
        "conteos": {"cumplen": len(cumplen), "revisar": len(revisar), "nocumplen": len(nocumplen), "pendientes": len(pendientes), "historial": len(historial)},
        "empresa": NOMBRE_EMPRESA_DEFAULT, "token": PORTAL_TOKEN, "chart_data": [0, 0, 0, 0, 0, 0]
    })

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
            if f"ilimitado|{puesto}|{categoria}" in form_data:
                nuevos_limites[puesto][categoria] = -1.0
            else:
                try: nuevos_limites[puesto][categoria] = float(value) if value.strip() else 0.0
                except: nuevos_limites[puesto][categoria] = 0.0
    db.guardar_config("limites_puestos", json.dumps(nuevos_limites))
    return RedirectResponse("/panel/limites?msg=ok", status_code=303)

@app.get("/panel/facturas", response_class=HTMLResponse)
def panel_facturas(request: Request, tab: str = "pendientes"):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    cumplen = db.listar_solicitudes(estado="CUMPLE")
    revisar = db.listar_solicitudes(estado="REVISAR")
    nocumplen = db.listar_solicitudes(estado="NO_CUMPLE")
    pendientes = cumplen + revisar
    historial = (db.listar_solicitudes(estado="APROBADO") + db.listar_solicitudes(estado="RECHAZADO"))
    return templates.TemplateResponse(request, "facturas.html", {
        "tab": tab, "usuario": request.session.get("admin"), "rol": "admin",
        "cumplen": cumplen, "revisar": revisar, "nocumplen": nocumplen, "pendientes": pendientes, "historial": historial,
        "conteos": {"cumplen": len(cumplen), "revisar": len(revisar), "nocumplen": len(nocumplen), "pendientes": len(pendientes), "historial": len(historial)},
        "empresa": NOMBRE_EMPRESA_DEFAULT, "token": PORTAL_TOKEN
    })

@app.post("/panel/decidir")
def decidir(request: Request, sid: int = Form(...), decision: str = Form(...), observaciones: str = Form("")):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    db.decidir_solicitud(sid, decision.upper(), observaciones)
    return RedirectResponse("/panel/facturas?tab=historial", status_code=303)

@app.get("/panel/factura/{sid}")
def ver_factura(request: Request, sid: int):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    s = db.obtener_solicitud(sid)
    if not s or not s.get("archivo"): raise HTTPException(404)
    
    primer_archivo = s["archivo"].split(",")[0]
    ruta = Path(FACTURAS_DIR) / primer_archivo
    if not ruta.exists(): raise HTTPException(404)
    return FileResponse(str(ruta))

# --- RUTAS DE REPORTES ---
@app.get("/panel/reporte-depreciacion/{empleado}")
def reporte_depreciacion(request: Request, empleado: str):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    sols = [s for s in db.listar_solicitudes(estado="APROBADO") if (s.get("empleado") or "").lower() == empleado.lower()]
    ruta = reportes.generar_reporte_depreciacion_pdf(sols, empleado=empleado)
    return FileResponse(str(ruta), filename=Path(ruta).name, media_type="application/pdf")

@app.get("/panel/memo-empleado/{empleado}")
def memo_empleado(request: Request, empleado: str):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    sols = [s for s in (db.listar_solicitudes(estado="APROBADO")) if (s.get("empleado") or "").lower() == empleado.lower()]
    if not sols: raise HTTPException(404, "Sin facturas aprobadas para ese empleado")
    ruta = reportes.generar_memo_pdf(sols, empleado=empleado)
    return FileResponse(str(ruta), filename=Path(ruta).name, media_type="application/pdf")

@app.get("/panel/tabla")
def tabla(request: Request, estado: str = ""):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    sols = db.listar_solicitudes(estado=estado or None)
    ruta = reportes.generar_tabla(sols)
    return FileResponse(str(ruta), filename=Path(ruta).name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
# ---------------------------------------

@app.get("/panel/empleados", response_class=HTMLResponse)
def empleados_form(request: Request, msg: str = ""):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    cfg = {"rtn_empresa": db.obtener_config("rtn_empresa", RTN_EMPRESA_DEFAULT), "nombre_empresa": db.obtener_config("nombre_empresa", NOMBRE_EMPRESA_DEFAULT)}
    dep = depreciacion.obtener_parametros()
    dict_limites = {}
    for l in db.listar_limites():
        if isinstance(l, dict): dict_limites[l.get("clave") or l.get("nombre")] = l.get("monto") or l.get("valor")
        else: dict_limites[str(l[0])] = l[1]
    return templates.TemplateResponse(request, "empleados.html", {
        "empleados": empleados_ordenados(), "orden_puestos": ORDEN_PUESTOS, "limites": dict_limites,
        "zonas": ZONAS, "cfg": cfg, "dep": dep, "msg": msg, "rol": "admin", "usuario": request.session.get("admin"),
        "centros_costos": get_centros_costos()
    })

@app.post("/panel/empleados/agregar")
def empleados_agregar(request: Request, nombre: str = Form(...), puesto: str = Form(""), departamento: str = Form(""), limite: str = Form(""), deprecia: str = Form("")):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    db.agregar_empleado(nombre, puesto, departamento, deprecia_vehiculo=bool(deprecia))
    if limite.strip():
        try: db.guardar_limite("empleado", nombre, float(limite))
        except: pass
    return RedirectResponse("/panel/empleados?msg=ok", status_code=303)

@app.post("/panel/empleados/eliminar")
def empleados_eliminar(request: Request, emp_id: int = Form(...)):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    db.eliminar_empleado(emp_id)
    return RedirectResponse("/panel/empleados?msg=del", status_code=303)

@app.get("/panel/empleados/editar/{emp_id}", response_class=HTMLResponse)
def empleados_editar_form(request: Request, emp_id: int):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    emp = db.obtener_empleado(emp_id)
    if not emp: raise HTTPException(404)
    return templates.TemplateResponse(request, "editar_empleado.html", {"emp": emp, "limite": db.obtener_limite("empleado", emp["nombre"])})

@app.post("/panel/empleados/editar")
def empleados_editar(request: Request, emp_id: int = Form(...), nombre: str = Form(...), puesto: str = Form(""), departamento: str = Form(""), correo: str = Form(""), fondo_rotativo: str = Form(""), deprecia: str = Form(""), limite: str = Form(""), sin_limite: str = Form("")):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    r = db.actualizar_empleado(emp_id, nombre=nombre, puesto=puesto, departamento=departamento, correo=correo, deprecia_vehiculo=bool(deprecia), fondo_rotativo=fondo_rotativo)
    if r.get("ok"):
        viejo, nuevo = r.get("nombre_anterior"), r.get("nombre_nuevo")
        if viejo and nuevo and viejo.lower() != nuevo.lower(): db.eliminar_limite("empleado", viejo)
        if sin_limite: db.eliminar_limite("empleado", nuevo or nombre)
        elif limite.strip():
            try: db.guardar_limite("empleado", nuevo or nombre, float(limite))
            except: pass
    return RedirectResponse("/panel/empleados?msg=edit", status_code=303)

@app.post("/panel/config")
def guardar_config(request: Request, rtn_empresa: str = Form(""), nombre_empresa: str = Form(""), factor_lps_km: str = Form(""), factor_conversion: str = Form(""), restar_deducciones: str = Form("")):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    if rtn_empresa.strip(): db.guardar_config("rtn_empresa", rtn_empresa.strip())
    if nombre_empresa.strip(): db.guardar_config("nombre_empresa", nombre_empresa.strip())
    depreciacion.guardar_parametros(factor_lps_km or 7.91, factor_conversion or 1.0, bool(restar_deducciones))
    return RedirectResponse("/panel/empleados?msg=cfg", status_code=303)

@app.post("/panel/config/centros/agregar")
def agregar_centro(request: Request, centro: str = Form(...)):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    centros = get_centros_costos()
    if centro.strip() and centro.strip() not in centros:
        centros.append(centro.strip()); db.guardar_config("centros_costos", json.dumps(centros))
    return RedirectResponse("/panel/empleados?msg=cfg", status_code=303)

@app.get("/panel/config/centros/eliminar/{centro}")
def eliminar_centro(request: Request, centro: str):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    centros = get_centros_costos()
    if centro in centros: centros.remove(centro); db.guardar_config("centros_costos", json.dumps(centros))
    return RedirectResponse("/panel/empleados?msg=cfg", status_code=303)

@app.get("/panel/presupuestos", response_class=HTMLResponse)
def presupuestos_form(request: Request, msg: str = ""):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    emps = empleados_ordenados()
    for e in emps: e["limite_actual"] = db.obtener_limite("empleado", e["nombre"]) or 0.0
    return templates.TemplateResponse(request, "presupuestos.html", {"empleados": emps, "msg": msg, "empresa": NOMBRE_EMPRESA_DEFAULT, "rol": "admin", "usuario": request.session.get("admin")})

@app.post("/panel/presupuestos/guardar")
async def presupuestos_guardar(request: Request):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    for key, value in (await request.form()).items():
        if key.startswith("limite_"):
            try: db.guardar_limite("empleado", key.replace("limite_", ""), float(value) if value.strip() else 0.0)
            except: pass
    return RedirectResponse("/panel/presupuestos?msg=ok", status_code=303)

@app.get("/panel/reportes", response_class=HTMLResponse)
def reportes_form(request: Request):
    if not _es_admin(request): return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "reportes.html", {"usuario": request.session.get("admin"), "rol": "admin", "empleados": empleados_ordenados(), "empresa": NOMBRE_EMPRESA_DEFAULT})

# --- RUTAS DE DEPRECIACIÓN ---
@app.get("/depreciacion", response_class=HTMLResponse)
def depreciacion_portal(request: Request, token: str = ""):
    if PORTAL_TOKEN and token != PORTAL_TOKEN:
        return HTMLResponse("<h3>Enlace invalido.</h3>", status_code=403)
    p = depreciacion.obtener_parametros()
    return templates.TemplateResponse(request, "depreciacion.html", {
        "zonas": ZONAS, "empresa": NOMBRE_EMPRESA_DEFAULT, "token": token,
        "centros_costos": get_centros_costos(),
        "empleados": [e["nombre"] for e in db.listar_empleados()],
        "factor": p["factor_lps_km"], "milla_km": depreciacion.MILLA_A_KM,
    })

@app.post("/api/leer-odometro")
async def api_leer_odometro(archivo: UploadFile = File(...)):
    ext = Path(archivo.filename or "odo").suffix.lower() or ".png"
    tmp = Path(FACTURAS_DIR) / f"odo_{secrets.token_hex(5)}{ext}"
    with open(tmp, "wb") as f: shutil.copyfileobj(archivo.file, f)
    try: r = ocr.leer_odometro(str(tmp))
    except Exception as e: r = {"valor": None, "texto": f"[OCR no disponible: {e}]"}
    finally: tmp.unlink(missing_ok=True)
    return JSONResponse(r)

@app.post("/api/depreciacion")
async def api_depreciacion(
    empleado: str = Form(...), departamento: str = Form(""), zona: str = Form("tierra_firme"),
    lugares: str = Form(""), tramos: str = Form("[]"), guardar: str = Form("1"),
):
    try: lista = json.loads(tramos or "[]")
    except json.JSONDecodeError: lista = []
    if not lista: return JSONResponse({"error": "No se enviaron tramos."}, status_code=400)
    
    res = depreciacion.calcular(lista)
    
    resumen_data = {
        "lugares": lugares,
        "tramos": res["detalle"],
        "total_km": res["total_km"],
        "total_depreciacion": res["pago_neto"]
    }
    
    if guardar in ("1", "true", "on"):
        db.asegurar_empleado(empleado, departamento)
        reg = db.crear_solicitud({
            "empleado": empleado, "departamento": departamento, "zona": zona, "categoria": "Depreciacion",
            "negocio": "Depreciacion de vehiculo", "monto": res["pago_neto"], "monto_reembolsable": res["pago_neto"],
            "limite_aplicado": None, "cumple": True, "estado": "APROBADO",
            "motivos": f"Depreciación registrada correctamente.",
            "texto_ocr": json.dumps(resumen_data),
        })
        res["folio"] = reg["folio"]
    return JSONResponse(res)

@app.get("/salud")
def salud():
    return {"ok": True, "tesseract": bool(ocr.pytesseract.pytesseract.tesseract_cmd)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=int(os.environ.get("PORT", 8000)), reload=False)
