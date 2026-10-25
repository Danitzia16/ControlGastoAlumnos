

import flet as ft
import mysql.connector


DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "control_gastos_alumnos",
    "connection_timeout": 5,
}


def main(page: ft.Page):
    page.title = "Control Inteligente de Gastos"
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO

    estado = ft.Text(
        "Selecciona una sección para comenzar.",
        size=16,
    )

    def mostrar_menu(e=None):
        page.controls.clear()

        page.add(
            ft.Text(
                "Control Inteligente de Gastos",
                size=28,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Text(
                "Administración de gastos y ahorros de alumnos",
                size=16,
            ),
            ft.Divider(),
            ft.Text(
                "MENÚ PRINCIPAL",
                size=20,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Button(
                "Alumnos",
                on_click=mostrar_alumnos,
            ),
            ft.Button(
                "Gastos",
                on_click=lambda e: seleccionar_seccion("Gastos"),
            ),
            ft.Button(
                "Presupuestos semanales",
                on_click=lambda e: seleccionar_seccion(
                    "Presupuestos semanales"
                ),
            ),
            ft.Button(
                "Ahorros",
                on_click=lambda e: seleccionar_seccion("Ahorros"),
            ),
            ft.Button(
                "Estadísticas y gráficas",
                on_click=lambda e: seleccionar_seccion(
                    "Estadísticas y gráficas"
                ),
            ),
            ft.Button(
                "Predicciones y agrupamiento",
                on_click=lambda e: seleccionar_seccion(
                    "Predicciones y agrupamiento"
                ),
            ),
            ft.Divider(),
            estado,
        )
        page.update()

    def seleccionar_seccion(nombre):
        estado.value = (
            f"Sección seleccionada: {nombre}. "
            "Esta sección se conectará en un siguiente paso."
        )
        page.update()

    def mostrar_alumnos(e=None):
        page.controls.clear()

        page.add(
            ft.Text(
                "Alumnos registrados",
                size=26,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Text("Consultando la base de datos..."),
        )
        page.update()

        conexion = None
        cursor = None

        try:
            conexion = mysql.connector.connect(**DB_CONFIG)
            cursor = conexion.cursor()

            cursor.execute("""
                SELECT
                    id_alumno,
                    nombre,
                    apellido_paterno,
                    apellido_materno,
                    edad,
                    carrera,
                    municipio
                FROM alumnos
                ORDER BY id_alumno
            """)

            alumnos = cursor.fetchall()

            page.controls.clear()

            page.add(
                ft.Text(
                    "Alumnos registrados",
                    size=26,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(f"Total de alumnos: {len(alumnos)}"),
                ft.Button(
                    "Volver al menú",
                    on_click=mostrar_menu,
                ),
                ft.Divider(),
            )

            if not alumnos:
                page.add(ft.Text("No hay alumnos registrados."))
            else:
                for alumno in alumnos:
                    (
                        id_alumno,
                        nombre,
                        paterno,
                        materno,
                        edad,
                        carrera,
                        municipio,
                    ) = alumno

                    nombre_completo = (
                        f"{nombre} {paterno} {materno}"
                    )

                    page.add(
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    ft.Text(
                                        f"Alumno #{id_alumno}: "
                                        f"{nombre_completo}",
                                        weight=ft.FontWeight.BOLD,
                                        size=16,
                                    ),
                                    ft.Text(f"Edad: {edad}"),
                                    ft.Text(f"Carrera: {carrera}"),
                                    ft.Text(f"Municipio: {municipio}"),
                                ],
                                spacing=4,
                            ),
                            padding=10,
                            border=ft.Border.all(1, "#BDBDBD"),
                            border_radius=8,
                        )
                    )

            page.update()

        except mysql.connector.Error as error:
            page.controls.clear()
            page.add(
                ft.Text(
                    "No fue posible consultar los alumnos.",
                    size=20,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(f"Detalle del error: {error}"),
                ft.Button(
                    "Volver al menú",
                    on_click=mostrar_menu,
                ),
            )
            page.update()

        finally:
            if cursor is not None:
                cursor.close()

            if conexion is not None and conexion.is_connected():
                conexion.close()

    mostrar_menu()


ft.run(main)
