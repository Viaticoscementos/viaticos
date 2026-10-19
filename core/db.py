"""Base de datos SQLite de la plataforma de viaticos.

Una sola tabla principal 'solicitudes' guarda cada factura/solicitud subida
desde el portal, con su estado de validacion. Tablas auxiliares: empleados,
limites, config_app, folios.
"""
import sqlite3
from datetime import datetime
from core.config import DB_PATH, PREFIJO_FOLIO, LIMITE_DEFAULT


def conectar():
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db():
    con = conectar()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS solicitudes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT UNIQUE,
            empleado TEXT NOT NULL,
            departamento TEXT,
            zona TEXT DEFAULT 'tierra_firme',
            categoria TEXT,
            archivo TEXT,
            rtn TEXT,
            cai TEXT,
            fecha_compra TEXT,
            fecha_limite TEXT,
            negocio TEXT,
            num_factura TEXT,
            monto REAL DEFAULT 0,
            monto_reembolsable REAL DEFAULT 0,
            limite_aplicado REAL,
            cumple INTEGER DEFAULT 0,
            estado TEXT DEFAULT 'NO_CUMPLE',
            motivos TEXT,
            texto_ocr TEXT,
            observaciones TEXT,
            fecha_registro TEXT,
            fecha_decision TEXT
        );

        CREATE TABLE IF NOT EXISTS empleados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL COLLATE NOCASE UNIQUE,
            puesto TEXT,
            departamento TEXT,
            correo TEXT,
            deprecia_vehiculo INTEGER DEFAULT 0,
            fondo_rotativo REAL DEFAULT 0,
            fecha_registro TEXT
        );

        CREATE TABLE IF NOT EXISTS limites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            limite REAL NOT NULL,
            UNIQUE(tipo, nombre)
        );

        CREATE TABLE IF NOT EXISTS config_app (
            clave TEXT PRIMARY KEY,
            valor TEXT
        );

        CREATE TABLE IF NOT EXISTS folios (
            anio INTEGER PRIMARY KEY,
            ultimo INTEGER NOT NULL DEFAULT 0
        );
    """)
    con.commit()
    con.close()


def siguiente_folio(anio=None):
    anio = anio or datetime.now().year
    con = conectar()
    fila = con.execute("SELECT ultimo FROM folios WHERE anio=?", (anio,)).fetchone()
    if fila:
        nuevo = fila["ultimo"] + 1
        con.execute("UPDATE folios SET ultimo=? WHERE anio=?", (nuevo, anio))
    else:
        nuevo = 1
        con.execute("INSERT INTO folios (anio, ultimo) VALUES (?,?)", (anio, nuevo))
    con.commit()
    con.close()
    return f"{PREFIJO_FOLIO}-{anio}-{nuevo:04d}"


# ---------- config clave/valor ----------
def obtener_config(clave, por_defecto=None):
    con = conectar()
    fila = con.execute("SELECT valor FROM config_app WHERE clave=?", (clave,)).fetchone()
    con.close()
    return fila["valor"] if fila and fila["valor"] is not None else por_defecto


def guardar_config(clave, valor):
    con = conectar()
    con.execute(
        "INSERT INTO config_app (clave,valor) VALUES (?,?) "
        "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
        (clave, str(valor)))
    con.commit()
    con.close()


# ---------- limites ----------
def obtener_limite(tipo, nombre):
    if not nombre:
        return None
    con = conectar()
    fila = con.execute("SELECT limite FROM limites WHERE tipo=? AND nombre=? COLLATE NOCASE",
                       (tipo, nombre)).fetchone()
    con.close()
    return fila["limite"] if fila else None


def limite_aplicable(empleado, departamento):
    lim = obtener_limite("empleado", empleado)
    if lim is not None:
        return lim, f"limite del empleado ({empleado})"
    lim = obtener_limite("departamento", departamento)
    if lim is not None:
        return lim, f"limite del departamento ({departamento})"
    return LIMITE_DEFAULT, "limite por defecto"


def guardar_limite(tipo, nombre, limite):
    con = conectar()
    con.execute(
        "INSERT INTO limites (tipo,nombre,limite) VALUES (?,?,?) "
        "ON CONFLICT(tipo,nombre) DO UPDATE SET limite=excluded.limite",
        (tipo, nombre, float(limite)))
    con.commit()
    con.close()


def listar_limites():
    con = conectar()
    filas = con.execute("SELECT * FROM limites ORDER BY tipo, nombre").fetchall()
    con.close()
    return [dict(f) for f in filas]


import re as _re


def _norm(nombre):
    return _re.sub(r"\s+", " ", (nombre or "")).strip()


# ---------- empleados ----------
def listar_empleados():
    con = conectar()
    filas = con.execute("SELECT * FROM empleados ORDER BY nombre COLLATE NOCASE").fetchall()
    con.close()
    return [dict(f) for f in filas]


def buscar_empleado(nombre):
    nombre = _norm(nombre)
    if not nombre:
        return None
    con = conectar()
    fila = con.execute("SELECT * FROM empleados WHERE nombre=? COLLATE NOCASE LIMIT 1",
                       (nombre,)).fetchone()
    con.close()
    return dict(fila) if fila else None


def agregar_empleado(nombre, puesto="", departamento="", correo="",
                     deprecia_vehiculo=False, fondo_rotativo=0):
    nombre = _norm(nombre)
    if not nombre:
        return {"ok": False, "mensaje": "El nombre esta vacio."}
    if buscar_empleado(nombre):
        return {"ok": False, "duplicado": True,
                "mensaje": f'El empleado "{nombre}" ya existe.'}
    con = conectar()
    cur = con.execute(
        "INSERT INTO empleados (nombre,puesto,departamento,correo,"
        "deprecia_vehiculo,fondo_rotativo,fecha_registro) VALUES (?,?,?,?,?,?,?)",
        (nombre, puesto or "", departamento or "", correo or "",
         1 if deprecia_vehiculo else 0, float(fondo_rotativo or 0),
         datetime.now().isoformat()))
    con.commit()
    nid = cur.lastrowid
    con.close()
    return {"ok": True, "id": nid, "mensaje": f'Empleado "{nombre}" agregado.'}


def asegurar_empleado(nombre, departamento=""):
    """Si quien sube la factura no esta en el catalogo, lo crea en automatico."""
    ex = buscar_empleado(nombre)
    if ex:
        return ex
    agregar_empleado(nombre, departamento=departamento)
    return buscar_empleado(nombre)


def eliminar_empleado(emp_id):
    con = conectar()
    con.execute("DELETE FROM empleados WHERE id=?", (emp_id,))
    con.commit()
    con.close()
    return True


def obtener_empleado(emp_id):
    con = conectar()
    fila = con.execute("SELECT * FROM empleados WHERE id=?", (emp_id,)).fetchone()
    con.close()
    return dict(fila) if fila else None


def actualizar_empleado(emp_id, nombre=None, puesto=None, departamento=None,
                        correo=None, deprecia_vehiculo=None, fondo_rotativo=None):
    """Modifica los datos de un empleado existente (solo los campos enviados)."""
    actual = obtener_empleado(emp_id)
    if not actual:
        return {"ok": False, "mensaje": "El empleado no existe."}
    nuevo_nombre = _norm(nombre) if nombre is not None else actual["nombre"]
    if not nuevo_nombre:
        return {"ok": False, "mensaje": "El nombre no puede quedar vacio."}
    # evitar choque de nombre con otro registro
    otro = buscar_empleado(nuevo_nombre)
    if otro and otro["id"] != emp_id:
        return {"ok": False, "mensaje": f'Ya existe otro empleado "{nuevo_nombre}".'}
    con = conectar()
    con.execute(
        "UPDATE empleados SET nombre=?, puesto=?, departamento=?, correo=?, "
        "deprecia_vehiculo=?, fondo_rotativo=? WHERE id=?",
        (nuevo_nombre,
         puesto if puesto is not None else actual["puesto"],
         departamento if departamento is not None else actual["departamento"],
         correo if correo is not None else actual["correo"],
         (1 if deprecia_vehiculo else 0) if deprecia_vehiculo is not None else actual["deprecia_vehiculo"],
         float(fondo_rotativo) if fondo_rotativo not in (None, "") else actual["fondo_rotativo"],
         emp_id))
    con.commit()
    con.close()
    return {"ok": True, "mensaje": f'Empleado "{nuevo_nombre}" actualizado.',
            "nombre_anterior": actual["nombre"], "nombre_nuevo": nuevo_nombre}


def eliminar_limite(tipo, nombre):
    con = conectar()
    con.execute("DELETE FROM limites WHERE tipo=? AND nombre=? COLLATE NOCASE",
                (tipo, nombre))
    con.commit()
    con.close()


# ---------- solicitudes ----------
_CAMPOS_EDIT = ("empleado", "departamento", "zona", "categoria", "rtn", "cai",
                "fecha_compra", "fecha_limite", "negocio", "num_factura",
                "monto", "monto_reembolsable", "limite_aplicado")


def crear_solicitud(datos):
    init_db()
    folio = siguiente_folio()
    ahora = datetime.now().isoformat()
    con = conectar()
    cur = con.execute("""
        INSERT INTO solicitudes (folio, empleado, departamento, zona, categoria,
            archivo, rtn, cai, fecha_compra, fecha_limite, negocio, num_factura,
            monto, monto_reembolsable, limite_aplicado, cumple, estado, motivos,
            texto_ocr, fecha_registro)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        folio, datos.get("empleado", ""), datos.get("departamento", ""),
        datos.get("zona", "tierra_firme"), datos.get("categoria", ""),
        datos.get("archivo"), datos.get("rtn"), datos.get("cai"),
        datos.get("fecha_compra"), datos.get("fecha_limite"),
        datos.get("negocio"), datos.get("num_factura"),
        float(datos.get("monto") or 0), float(datos.get("monto_reembolsable") or 0),
        datos.get("limite_aplicado"), 1 if datos.get("cumple") else 0,
        datos.get("estado", "NO_CUMPLE"), datos.get("motivos", ""),
        (datos.get("texto_ocr") or "")[:6000], ahora))
    sid = cur.lastrowid
    con.commit()
    con.close()
    return {"id": sid, "folio": folio}


def listar_solicitudes(estado=None, cumple=None):
    con = conectar()
    q = "SELECT * FROM solicitudes WHERE 1=1"
    params = []
    if estado:
        q += " AND estado=?"
        params.append(estado)
    if cumple is not None:
        q += " AND cumple=?"
        params.append(1 if cumple else 0)
    q += " ORDER BY id DESC"
    filas = con.execute(q, params).fetchall()
    con.close()
    return [dict(f) for f in filas]


def obtener_solicitud(sid):
    con = conectar()
    fila = con.execute("SELECT * FROM solicitudes WHERE id=?", (sid,)).fetchone()
    con.close()
    return dict(fila) if fila else None


def actualizar_solicitud(sid, campos):
    sets, params = [], []
    for c in _CAMPOS_EDIT:
        if c in campos:
            sets.append(f"{c}=?")
            params.append(campos[c])
    if not sets:
        return
    params.append(sid)
    con = conectar()
    con.execute(f"UPDATE solicitudes SET {', '.join(sets)} WHERE id=?", params)
    con.commit()
    con.close()


def decidir_solicitud(sid, decision, observaciones=""):
    estado = "APROBADO" if decision == "APROBAR" else "RECHAZADO"
    con = conectar()
    con.execute("UPDATE solicitudes SET estado=?, observaciones=?, fecha_decision=? WHERE id=?",
                (estado, observaciones, datetime.now().isoformat(), sid))
    con.commit()
    con.close()
    return estado


def eliminar_solicitud(sid):
    con = conectar()
    con.execute("DELETE FROM solicitudes WHERE id=?", (sid,))
    con.commit()
    con.close()
    return True


def resumen_conteos():
    con = conectar()
    filas = con.execute("SELECT estado, COUNT(*) n FROM solicitudes GROUP BY estado").fetchall()
    con.close()
    return {f["estado"]: f["n"] for f in filas}
