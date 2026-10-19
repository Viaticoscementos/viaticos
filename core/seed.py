"""Carga inicial de los empleados de CENOSA (lista \"Viaticos Asignados 2026\").

Solo corre si la tabla de empleados esta vacia, para no pisar los cambios que
haga la encargada. Despues todo se edita/elimina/agrega desde el panel.

El puesto se deja en blanco a proposito: la encargada lo define por persona
(Ingeniero Senior/Junior, Ejecutivo de Ventas, Gerente General, Jefe...), y de
ese puesto depende si lleva o no limite.
"""
from core import db

# (nombre, fondo_rotativo_2026)
EMPLEADOS_2026 = [
    ("Cindy Artola", 5000),
    ("Mario Doblado", 5000),
    ("Maria Josee Coto", 11000),
    ("Christopher Midence", 17000),
    ("Carlos Humberto Mejia", 35000),
    ("Eduardo Lopez Lopez", 15000),
    ("Luis Fernando Ponce", 33000),
    ("Olga Elizabeth Osorto", 35000),
    ("Eduardo Rene Mejia Rodriguez", 35000),
    ("Steven Garcia", 33000),
    ("Marco Smith", 33000),
    ("Yeni Yamilet Castellanos", 25000),
    ("Jose Samuel Lopez", 30000),
    ("Linda de Jesus Nolasco", 35000),
    ("Oscar Ivan Sierra Linares", 24000),
    ("Mario Jose Urquia", 35000),
    ("Sergio Siwady", 0),
    ("Joan Jorge Pineda", 35000),
    ("Rafael Alberto Perez", 10000),
    ("Mauricio Boesch Carrillo", 0),
    ("Martha Julissa Perla (Caja Chica)", 10000),
    ("Martha Julissa Perla (Gastos Mercadeo)", 10000),
    ("Nolvin Roel Rivera", 15000),
    ("Carlos Enrique Jallu", 10000),
    ("Beverly Yasmira Rivera", 25000),
    ("Renato Miguel Gonzales", 35000),
    ("Edwin Geovani Samayoa", 35000),
    ("Cindy Julissa Guevara", 20000),
    ("Manuel Alejandro Reyes", 30000),
    ("Kevin Wilfredo Villela", 35000),
    ("Saul Edgardo Herrera", 35000),
    ("Luis Gerardo de Jesus", 30000),
]


def sembrar(forzar=False):
    """Inserta los empleados base si la tabla esta vacia.

    Devuelve cuantos se insertaron.
    """
    db.init_db()
    if not forzar and db.listar_empleados():
        return 0
    insertados = 0
    for nombre, fondo in EMPLEADOS_2026:
        r = db.agregar_empleado(nombre, puesto="", departamento="",
                                fondo_rotativo=fondo)
        if r.get("ok"):
            insertados += 1
    return insertados


if __name__ == "__main__":
    print("Empleados cargados:", sembrar(forzar=True))
