"""Configuracion central de la plataforma web de viaticos (Cementos del Norte).

Todo lo editable (RTN de la empresa, limites, factor de depreciacion, clave de
la encargada) se puede cambiar por variables de entorno o desde el panel, sin
tocar el codigo.
"""
import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATOS_DIR = BASE_DIR / "datos"
FACTURAS_DIR = DATOS_DIR / "facturas"
REPORTES_DIR = DATOS_DIR / "reportes"
DB_PATH = Path(os.environ.get("VIATICOS_DB", DATOS_DIR / "viaticos.db"))

for d in (DATOS_DIR, FACTURAS_DIR, REPORTES_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---- OCR / Tesseract ----
# En el servidor (Oracle/Ubuntu) se instala con: apt install tesseract-ocr tesseract-ocr-spa
# Localmente se puede apuntar a una carpeta tessdata propia con TESSDATA_PREFIX.
TESSERACT_CMD = os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")
_tessdata_local = BASE_DIR / "tessdata"
TESSDATA_DIR = Path(os.environ.get("TESSDATA_PREFIX", str(_tessdata_local)))

# ---- Reglas de negocio (valores por defecto, editables) ----
MONEDA = "L"
PREFIJO_FOLIO = "VIA"
LIMITE_DEFAULT = float(os.environ.get("LIMITE_DEFAULT", 620.0))

# RTN y nombre de la empresa a cuyo nombre deben venir las facturas.
RTN_EMPRESA_DEFAULT = "05019004463363"
NOMBRE_EMPRESA_DEFAULT = "Cementos del Norte, S.A. (CENOSA)"

# ---- Seguridad del panel de la encargada ----
# Cambie estos valores en el servidor con variables de entorno.
ADMIN_USUARIO = os.environ.get("ADMIN_USUARIO", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "viaticos2026")
SECRET_KEY = os.environ.get("SECRET_KEY", "cambie-esta-clave-en-produccion-cenosa")

# Token del enlace para empleados (si se deja vacio, el portal es publico).
PORTAL_TOKEN = os.environ.get("PORTAL_TOKEN", "")

# ---- Zonas y topes de viaticos (del memorandum real) ----
# "Tierra firme" aplica el tope estandar; "fuera" (islas/zonas caras) es mayor.
ZONAS = {
    "tierra_firme": {"etiqueta": "Tierra firme", "alimentacion": 525.0, "hotel": 1500.0},
    "fuera": {"etiqueta": "Fuera de tierra firme", "alimentacion": 525.0, "hotel": 2000.0},
}

# Depreciacion de vehiculo (editable: el factor cambia con el combustible).
FACTOR_LPS_KM_DEFAULT = 7.91
FACTOR_CONVERSION_DEFAULT = 1.0  # odometro ya en km
RESTAR_DEDUCCIONES_DEFAULT = True
