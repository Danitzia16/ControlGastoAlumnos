
import flet as ft


def main(page: ft.Page):
    page.title = "Control Inteligente de Gastos"
    page.padding = 20
    page.theme_mode = ft.ThemeMode.LIGHT

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
            "Nueva aplicación Flet iniciada correctamente.",
            size=18,
        ),
        ft.Text(
            "En el siguiente paso conectaremos la base de datos."
        ),
    )


ft.app(target=main)
