# Plataforma de Viaticos - Cementos del Norte (CENOSA)

Aplicacion web **gratuita** para automatizar las solicitudes de reembolso de
viaticos. Funciona 100% en el navegador (no depende de ninguna PC en
particular) y se hospeda en **Oracle Cloud Always Free** sin costo.

## Que hace

- **Portal para empleados** (enlace que se comparte): el empleado sube la foto
  o PDF de su factura y el sistema le dice al instante **CUMPLE** o
  **NO CUMPLE**, revisando:
  - RTN del emisor (14 digitos)
  - CAI presente
  - Fecha de la factura (presente y no futura)
  - Vigencia (si trae fecha limite de emision)
  - Que la factura este a nombre del **RTN de la empresa**
  - Monto **dentro del limite** del empleado / zona
- **Panel de la encargada** (con usuario y contraseña) con pestañas:
  - **Cumplen** - listas para aprobar
  - **No cumplen** - con el motivo exacto
  - **Pendientes** - todo lo que espera decision
  - **Historial** - aprobadas / rechazadas
  Desde ahi aprueba o rechaza y **descarga el memorandum y la tabla de
  liquidacion** en el formato real de la empresa (.xlsx).
- **Catalogo de empleados y configuracion**: RTN de la empresa, limites por
  empleado/zona y el **factor de depreciacion** (editable, cambia con el
  precio del combustible).

## Empleados precargados y edicion

- Las **32 personas** de la hoja "Viaticos Asignados 2026" vienen **cargadas**
  automaticamente la primera vez que arranca (con su fondo rotativo 2026).
- Desde el panel (pestaña *Empleados y config*) la encargada puede
  **agregar, modificar y eliminar** personas: nombre, puesto, departamento,
  correo, fondo rotativo, limite propio y si deprecia vehiculo.
- Al **modificar** puede marcar "Sin restriccion" para jefes/gerentes (se les
  quita el limite) o fijar un limite propio para ejecutivos/ingenieros.
- La carga inicial solo ocurre si la tabla esta vacia, para no pisar cambios.
  Si alguna vez quiere recargar la lista base: `python -m core.seed`.

## Depreciacion de vehiculo (kilometros y millas, varios dias/vehiculos)

- En el portal hay una seccion **"Depreciacion de vehiculo"**.
- El empleado agrega **un tramo por cada dia o vehiculo** usado; puede mezclar
  **kilometros y millas** (el sistema convierte 1 milla = 1.609344 km).
- Soporta usar **vehiculos distintos** (por ejemplo si un dia se daño uno y usa
  otro): suma todas las distancias y aplica el factor L/km.
- Puede subir la **foto del odometro** y el sistema intenta leer el numero
  automaticamente (siempre revisar el valor leido).
- El resultado queda registrado como solicitud de categoria *Depreciacion*
  para que la encargada lo apruebe.

## Lectura de la factura (OCR)

- En el navegador se hace una primera lectura rapida con Tesseract.js.
- En el servidor se vuelve a leer con Tesseract (español) para mayor precision,
  incluyendo PDFs.

---

## Despliegue en Oracle Cloud Always Free (gratis)

### 1. Crear la maquina (una sola vez)

1. Cuenta en https://www.oracle.com/cloud/free/ (tarjeta solo para verificar,
   no cobran en el tier Always Free).
2. Crear una instancia **VM.Standard.A1.Flex** (Ampere ARM, gratis) o
   **VM.Standard.E2.1.Micro**, con **Ubuntu 22.04**.
3. En la red (VCN), abrir los puertos **80** y **443** (Ingress Rules).
4. Guardar la llave SSH y conectarse:
   ```bash
   ssh ubuntu@IP_DE_LA_INSTANCIA
   ```

### 2. Instalar dependencias del sistema

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip tesseract-ocr tesseract-ocr-spa nginx
```

> `tesseract-ocr-spa` instala el idioma español. Con esto NO se necesita la
> carpeta `tessdata` incluida.

### 3. Subir la aplicacion

Copiar la carpeta del proyecto al servidor (por ejemplo con `scp`):

```bash
scp -r viaticos_web ubuntu@IP_DE_LA_INSTANCIA:/home/ubuntu/
```

En el servidor:

```bash
cd /home/ubuntu/viaticos_web
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Configurar claves y datos (variables de entorno)

Crear el archivo `/home/ubuntu/viaticos_web/.env` (o exportar variables):

```bash
export ADMIN_USUARIO="encargada"
export ADMIN_PASSWORD="UNA_CLAVE_FUERTE"
export SECRET_KEY="cadena-larga-y-aleatoria"
export PORTAL_TOKEN="cenosa2026"   # opcional: el enlace sera /?token=cenosa2026
```

- **ADMIN_USUARIO / ADMIN_PASSWORD**: acceso al panel de la encargada.
- **PORTAL_TOKEN**: si lo define, el portal solo abre con
  `http://SU_DOMINIO/?token=cenosa2026`; dejelo vacio para portal abierto.
- El **RTN de la empresa**, los limites y el factor de depreciacion tambien se
  editan desde el panel (pestaña *Empleados y config*).

### 5. Probar

```bash
source .venv/bin/activate
uvicorn app:app --host 127.0.0.1 --port 8000
```

### 6. Dejarlo corriendo siempre (servicio systemd)

Crear `/etc/systemd/system/viaticos.service`:

```ini
[Unit]
Description=Viaticos CENOSA
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/viaticos_web
EnvironmentFile=/home/ubuntu/viaticos_web/.env
ExecStart=/home/ubuntu/viaticos_web/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

> Si usa `.env` con `export`, quite esa palabra `export` (systemd lo lee como
> `CLAVE=valor`). O deje el `EnvironmentFile` y escriba las variables sin
> `export`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now viaticos
sudo systemctl status viaticos
```

### 7. Nginx como puerta de entrada (puerto 80)

Crear `/etc/nginx/sites-available/viaticos`:

```nginx
server {
    listen 80;
    server_name _;
    client_max_body_size 25M;   # para fotos/PDF grandes
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/viaticos /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
# abrir el firewall del sistema
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
```

Ya puede entrar desde cualquier celular o PC a `http://IP_DE_LA_INSTANCIA/`.

### 8. (Opcional) Dominio y HTTPS gratis

Si tiene un dominio apuntando a la IP:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d viaticos.sudominio.com
```

---

## Enlaces una vez desplegado

- **Portal de empleados:** `http://SU_DOMINIO/`  (o con token
  `http://SU_DOMINIO/?token=cenosa2026`)
- **Panel de la encargada:** `http://SU_DOMINIO/login`

## Datos

- Todo se guarda en `datos/viaticos.db` (SQLite) y las facturas en
  `datos/facturas/`. Respalde esa carpeta periodicamente.
- Los memos y tablas se generan en `datos/reportes/`.

## Primeros pasos recomendados

1. Entrar al panel con su usuario/clave.
2. En *Empleados y config*: confirmar el RTN de la empresa y el factor de
   depreciacion; cargar las 31 personas de "Viaticos Asignados 2026" con su
   puesto y limite (jefes/gerentes sin limite, ejecutivos/ingenieros con tope).
3. Compartir el enlace del portal con los empleados.

> Nota: la regla "alcohol nunca se reembolsa" debe verificarla la encargada al
> revisar la factura; el sistema deja la observacion para rechazarla con un clic.
