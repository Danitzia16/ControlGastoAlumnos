import flet as ft
import mysql.connector
from decimal import Decimal

# Control Inteligente de Gastos
# Esta primera versión de migración consulta MySQL sin modificar registros.
# Conserva las credenciales locales que ya probaste. Para publicar en móviles,
# la conexión deberá trasladarse a una API segura; no se deben incluir estas
# credenciales directamente en una app distribuida.

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "control_gastos_alumnos",
    "connection_timeout": 5,
}

COLORES = {
    "fondo": "#FFF4E8",
    "tarjeta": "#FFFCF8",
    "primario": "#E87932",
    "rosa": "#D95D8A",
    "texto": "#573344",
    "suave": "#805C68",
    "borde": "#F0CDBB",
}


def consultar(sql, params=None):
    """Lee datos de MySQL y siempre cierra la conexión."""
    cn = mysql.connector.connect(**DB_CONFIG)
    try:
        cur = cn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        filas = cur.fetchall()
        cur.close()
        return filas
    finally:
        cn.close()


def moneda(valor):
    try:
        return f"${Decimal(str(valor or 0)):,.2f}"
    except Exception:
        return "$0.00"


def main(page: ft.Page):
    page.title = "Control Inteligente de Gastos"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = COLORES["fondo"]
    page.padding = 18
    page.scroll = ft.ScrollMode.AUTO
    page.window.width = 1100
    page.window.height = 760

    contenido = ft.Column(expand=True, spacing=12, scroll=ft.ScrollMode.AUTO)
    mensaje = ft.Text("", color=COLORES["suave"])

    def tarjeta(titulo, subtitulo=None):
        controles = [ft.Text(titulo, size=20, weight=ft.FontWeight.BOLD, color=COLORES["texto"])]
        if subtitulo:
            controles.append(ft.Text(subtitulo, color=COLORES["suave"]))
        return ft.Container(
            content=ft.Column(controls, spacing=5),
            bgcolor=COLORES["tarjeta"],
            border=ft.border.all(1, COLORES["borde"]),
            border_radius=14,
            padding=16,
        )

    def mostrar_error(e):
        contenido.controls.clear()
        contenido.controls.append(
            tarjeta("No se pudo cargar la información", str(e))
        )
        page.update()

    def cargar_tabla(titulo, subtitulo, columnas, filas):
        contenido.controls.clear()
        contenido.controls.append(tarjeta(titulo, subtitulo))
        if not filas:
            contenido.controls.append(ft.Text("No hay registros para mostrar."))
        else:
            # Una tarjeta por registro se adapta mejor a pantallas pequeñas que una tabla ancha.
            for fila in filas:
                lineas = []
                for clave, etiqueta in columnas:
                    valor = fila.get(clave, "")
                    lineas.append(
                        ft.Row(
                            [
                                ft.Text(etiqueta, weight=ft.FontWeight.BOLD, color=COLORES["suave"], width=150),
                                ft.Text("—" if valor is None else str(valor), color=COLORES["texto"], expand=True),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        )
                    )
                contenido.controls.append(
                    ft.Container(
                        content=ft.Column(lineas, spacing=6),
                        bgcolor=COLORES["tarjeta"],
                        border=ft.border.all(1, COLORES["borde"]),
                        border_radius=10,
                        padding=12,
                    )
                )
        page.update()

    def ver_inicio(e=None):
        contenido.controls.clear()
        contenido.controls.extend([
            tarjeta(
                "Control Inteligente de Gastos",
                "Administración de gastos y ahorros de alumnos",
            ),
            ft.Text(
                "Esta es la base de la migración a Flet. Los apartados de abajo consultan tu base de datos existente.",
                color=COLORES["texto"],
            ),
            ft.ResponsiveRow([
                ft.Container(
                    content=ft.Column([
                        ft.Text("Alumnos", size=17, weight=ft.FontWeight.BOLD),
                        ft.Text("Consulta de registros", color=COLORES["suave"]),
                    ]),
                    bgcolor=COLORES["tarjeta"], padding=18, border_radius=12,
                    col={"xs": 12, "md": 6},
                ),
                ft.Container(
                    content=ft.Column([
                        ft.Text("Gastos y ahorros", size=17, weight=ft.FontWeight.BOLD),
                        ft.Text("Consulta de movimientos", color=COLORES["suave"]),
                    ]),
                    bgcolor=COLORES["tarjeta"], padding=18, border_radius=12,
                    col={"xs": 12, "md": 6},
                ),
            ], run_spacing=10),
            ft.Text(
                "Importante: todavía no se realizan altas, cambios ni eliminaciones desde esta versión.",
                color=COLORES["suave"],
                italic=True,
            ),
        ])
        page.update()

    def ver_alumnos(e=None):
        try:
            filas = consultar("""
                SELECT id_alumno, nombre, apellido_paterno, apellido_materno,
                       edad, carrera, municipio
                FROM alumnos
                ORDER BY apellido_paterno, apellido_materno, nombre
            """)
            cargar_tabla(
                "Alumnos",
                f"{len(filas)} registros encontrados en MySQL",
                [
                    ("id_alumno", "ID"),
                    ("apellido_paterno", "Apellido paterno"),
                    ("apellido_materno", "Apellido materno"),
                    ("nombre", "Nombre(s)"),
                    ("edad", "Edad"),
                    ("carrera", "Carrera"),
                    ("municipio", "Municipio"),
                ],
                filas,
            )
        except Exception as ex:
            mostrar_error(ex)

    def ver_gastos(e=None):
        try:
            filas = consultar("""
                SELECT g.id_gasto, a.nombre AS nombre,
                       g.descripcion, g.monto, g.fecha, g.nivel_gasto,
                       c.nombre_categoria
                FROM gastos g
                JOIN alumnos a ON a.id_alumno = g.id_alumno
                LEFT JOIN categorias c ON c.id_categoria = g.id_categoria
                ORDER BY g.fecha DESC, g.id_gasto DESC
            """)
            for fila in filas:
                fila["monto"] = moneda(fila.get("monto"))
            cargar_tabla(
                "Gastos",
                f"{len(filas)} registros encontrados",
                [
                    ("id_gasto", "ID gasto"),
                    ("nombre", "Alumno"),
                    ("descripcion", "Descripción"),
                    ("nombre_categoria", "Categoría"),
                    ("monto", "Monto"),
                    ("fecha", "Fecha"),
                    ("nivel_gasto", "Nivel"),
                ],
                filas,
            )
        except Exception as ex:
            mostrar_error(ex)

    def ver_categorias(e=None):
        try:
            filas = consultar("""
                SELECT id_categoria, nombre_categoria, descripcion, tipo_categoria
                FROM categorias ORDER BY nombre_categoria
            """)
            cargar_tabla(
                "Categorías",
                f"{len(filas)} categorías registradas",
                [
                    ("id_categoria", "ID"),
                    ("nombre_categoria", "Categoría"),
                    ("descripcion", "Descripción"),
                    ("tipo_categoria", "Tipo"),
                ],
                filas,
            )
        except Exception as ex:
            mostrar_error(ex)

    def ver_presupuestos(e=None):
        try:
            filas = consultar("""
                SELECT p.id_presupuesto, a.nombre AS alumno,
                       p.semana_inicio, p.monto_inicial, p.ahorro
                FROM presupuestos_semanales p
                JOIN alumnos a ON a.id_alumno = p.id_alumno
                ORDER BY p.semana_inicio DESC, a.nombre
            """)
            for fila in filas:
                fila["monto_inicial"] = moneda(fila.get("monto_inicial"))
                fila["ahorro"] = moneda(fila.get("ahorro"))
            cargar_tabla(
                "Presupuestos semanales",
                f"{len(filas)} registros encontrados",
                [
                    ("id_presupuesto", "ID presupuesto"),
                    ("alumno", "Alumno"),
                    ("semana_inicio", "Inicio de semana"),
                    ("monto_inicial", "Monto inicial"),
                    ("ahorro", "Ahorro en presupuesto"),
                ],
                filas,
            )
        except Exception as ex:
            mostrar_error(ex)

    def ver_ahorros(e=None):
        try:
            filas = consultar("""
                SELECT h.id_ahorro, a.nombre AS alumno, h.semana_inicio,
                       h.monto, h.fecha_registro
                FROM ahorros h
                JOIN alumnos a ON a.id_alumno = h.id_alumno
                ORDER BY h.fecha_registro DESC, h.id_ahorro DESC
            """)
            for fila in filas:
                fila["monto"] = moneda(fila.get("monto"))
            cargar_tabla(
                "Ahorros",
                f"{len(filas)} movimientos encontrados",
                [
                    ("id_ahorro", "ID ahorro"),
                    ("alumno", "Alumno"),
                    ("semana_inicio", "Inicio de semana"),
                    ("monto", "Monto"),
                    ("fecha_registro", "Fecha de registro"),
                ],
                filas,
            )
        except Exception as ex:
            mostrar_error(ex)

    def ver_estadisticas(e=None):
        try:
            alumnos = consultar("SELECT COUNT(*) AS total FROM alumnos")[0]["total"]
            gastos = consultar("SELECT COUNT(*) AS total, COALESCE(SUM(monto),0) AS suma FROM gastos")[0]
            categorias = consultar("SELECT COUNT(*) AS total FROM categorias")[0]["total"]
            presupuestos = consultar("SELECT COUNT(*) AS total FROM presupuestos_semanales")[0]["total"]
            ahorros = consultar("SELECT COUNT(*) AS total, COALESCE(SUM(monto),0) AS suma FROM ahorros")[0]
            contenido.controls.clear()
            contenido.controls.append(tarjeta("Resumen general", "Indicadores de la base de datos"))
            indicadores = [
                ("Alumnos registrados", str(alumnos)),
                ("Gastos registrados", str(gastos["total"])),
                ("Importe acumulado de gastos", moneda(gastos["suma"])),
                ("Categorías", str(categorias)),
                ("Presupuestos semanales", str(presupuestos)),
                ("Movimientos de ahorro", str(ahorros["total"])),
                ("Importe acumulado de ahorros", moneda(ahorros["suma"])),
            ]
            for etiqueta, valor in indicadores:
                contenido.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Text(etiqueta, expand=True, color=COLORES["suave"]),
                            ft.Text(valor, weight=ft.FontWeight.BOLD, color=COLORES["texto"]),
                        ]),
                        bgcolor=COLORES["tarjeta"], padding=14, border_radius=10,
                    )
                )
            page.update()
        except Exception as ex:
            mostrar_error(ex)

    botones = [
        ("Inicio", ver_inicio),
        ("Alumnos", ver_alumnos),
        ("Gastos", ver_gastos),
        ("Categorías", ver_categorias),
        ("Presupuestos", ver_presupuestos),
        ("Ahorros", ver_ahorros),
        ("Resumen", ver_estadisticas),
    ]

    encabezado = ft.Container(
        content=ft.Column([
            ft.Text("Control Inteligente de Gastos", size=25, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
            ft.Text("Administración de gastos y ahorros de alumnos", color="#FFFFFF"),
        ], spacing=4),
        bgcolor=COLORES["primario"],
        border_radius=14,
        padding=18,
    )
    menu = ft.Row(
        [ft.OutlinedButton(content=ft.Text(nombre), on_click=accion) for nombre, accion in botones],
        wrap=True,
        spacing=8,
        run_spacing=8,
    )
    page.add(encabezado, menu, mensaje, contenido)
    ver_inicio()


if __name__ == "__main__":
    ft.run(main)
