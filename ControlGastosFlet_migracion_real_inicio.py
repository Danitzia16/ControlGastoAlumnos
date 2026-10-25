import flet as ft
import mysql.connector
import hashlib
from datetime import date, timedelta
from decimal import Decimal

# Migración de la aplicación real ControlGastosFlet.py a Flet.
# Mantiene la base de datos existente. No ejecuta preparar_base_datos().
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "control_gastos_alumnos",
    "connection_timeout": 5,
}

FONDO, TARJETA, NARANJA, ROSA, VINO, SUAVE, BORDE = (
    "#FFF4E8", "#FFFCF8", "#E87932", "#D95D8A",
    "#573344", "#805C68", "#F0CDBB"
)


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def obtener_lunes(fecha=None):
    fecha = fecha or date.today()
    return fecha - timedelta(days=fecha.weekday())


def obtener_columnas(tabla):
    cn = mysql.connector.connect(**DB_CONFIG)
    try:
        cur = cn.cursor()
        cur.execute("""
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
        """, (DB_CONFIG["database"], tabla))
        return {r[0] for r in cur.fetchall()}
    finally:
        cn.close()


def consultar(sql, params=()):
    cn = mysql.connector.connect(**DB_CONFIG)
    try:
        cur = cn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        cn.close()


def ejecutar_transaccion(funcion):
    cn = mysql.connector.connect(**DB_CONFIG)
    try:
        cur = cn.cursor()
        resultado = funcion(cn, cur)
        cn.commit()
        return resultado
    except Exception:
        cn.rollback()
        raise
    finally:
        cn.close()


def moneda(valor):
    return f"${Decimal(str(valor or 0)):,.2f}"


def main(page: ft.Page):
    page.title = "Control Inteligente de Gastos"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = FONDO
    page.padding = 18
    page.scroll = ft.ScrollMode.AUTO
    page.window.width = 1100
    page.window.height = 780

    sesion = {"id_usuario": None, "usuario": None, "rol": None,
              "id_alumno": None, "nombre": None}
    mensaje = ft.Text("", color=SUAVE)
    zona = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)

    def aviso(texto, error=False):
        mensaje.value = texto
        mensaje.color = "#B42332" if error else SUAVE
        page.update()

    def tarjeta(titulo, subtitulo=None, controles=None):
        items = [ft.Text(titulo, size=20, weight=ft.FontWeight.BOLD, color=VINO)]
        if subtitulo:
            items.append(ft.Text(subtitulo, color=SUAVE))
        if controles:
            items.extend(controles if isinstance(controles, list) else [controles])
        return ft.Container(
            content=ft.Column(items, spacing=8),
            bgcolor=TARJETA, border=ft.border.all(1, BORDE),
            border_radius=14, padding=16
        )

    def boton(texto, accion, principal=False):
        if principal:
            return ft.Button(texto, on_click=accion, bgcolor=NARANJA, color="#FFFFFF")
        return ft.OutlinedButton(content=ft.Text(texto), on_click=accion)

    def mostrar_error(contexto, exc):
        aviso(f"{contexto}: {exc}", True)

    def cambiar_pantalla(*controles):
        page.controls.clear()
        page.add(*controles)
        page.update()

    def mostrar_login(e=None):
        correo = ft.TextField(label="Correo electrónico", width=390,
                              prefix_icon=ft.Icons.EMAIL_OUTLINED)
        clave = ft.TextField(label="Contraseña", password=True,
                             can_reveal_password=True, width=390,
                             prefix_icon=ft.Icons.LOCK_OUTLINE)

        def entrar(ev=None):
            email = (correo.value or "").strip().lower()
            password = clave.value or ""
            if not email or not password:
                aviso("Escribe tu correo y contraseña.", True)
                return
            try:
                filas = consultar("""
                    SELECT u.id_usuario, u.usuario, u.rol, u.id_alumno,
                           u.nombre_usuario, a.nombre AS nombre_alumno
                    FROM usuarios u
                    LEFT JOIN alumnos a ON a.id_alumno=u.id_alumno
                    WHERE LOWER(u.usuario)=%s AND u.password_hash=%s
                    LIMIT 1
                """, (email, hash_password(password)))
                if not filas:
                    aviso("El correo o la contraseña no son correctos.", True)
                    return
                f = filas[0]
                rol = str(f["rol"]).lower()
                if rol not in ("admin", "alumno"):
                    aviso("El rol de la cuenta no es reconocido.", True)
                    return
                if rol == "alumno" and f["id_alumno"] is None:
                    aviso("Esta cuenta no está vinculada a un alumno.", True)
                    return
                sesion.update({
                    "id_usuario": f["id_usuario"], "usuario": f["usuario"],
                    "rol": rol, "id_alumno": f["id_alumno"],
                    "nombre": f["nombre_usuario"] or f["nombre_alumno"] or f["usuario"]
                })
                mostrar_panel()
            except Exception as ex:
                mostrar_error("No se pudo iniciar sesión", ex)

        cambiar_pantalla(
            ft.Container(
                content=ft.Column([
                    ft.Text("CONTROL INTELIGENTE DE GASTOS", size=26,
                            weight=ft.FontWeight.BOLD, color=VINO),
                    ft.Text("Administración de gastos y ahorros de alumnos", color=SUAVE),
                    ft.Divider(color=BORDE),
                    correo, clave,
                    boton("Iniciar sesión", entrar, True),
                    boton("Crear una cuenta nueva", mostrar_registro),
                    ft.Text("Utiliza una cuenta existente o crea una cuenta nueva.",
                            size=12, color=SUAVE),
                    mensaje,
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=14, tight=True),
                bgcolor=TARJETA, border=ft.border.all(1, BORDE),
                border_radius=18, padding=28, width=520
            )
        )

    def mostrar_registro(e=None):
        rol = ft.Dropdown(label="Tipo de cuenta", width=390, value="Alumno",
                          options=[ft.dropdown.Option("Alumno"), ft.dropdown.Option("Administrador")])
        ap = ft.TextField(label="Apellido paterno", width=390)
        am = ft.TextField(label="Apellido materno", width=390)
        nombres = ft.TextField(label="Nombre(s)", width=390)
        email = ft.TextField(label="Correo electrónico", width=390)
        password = ft.TextField(label="Contraseña (mínimo 4 caracteres)", password=True,
                                 can_reveal_password=True, width=390)
        confirm = ft.TextField(label="Confirmar contraseña", password=True,
                               can_reveal_password=True, width=390)
        edad = ft.TextField(label="Edad", width=390, keyboard_type=ft.KeyboardType.NUMBER)
        municipio = ft.TextField(label="Municipio", width=390)
        carrera = ft.TextField(label="Carrera (solo alumno)", width=390)

        def guardar(ev=None):
            apv, amv, nv = [(x.value or "").strip() for x in (ap, am, nombres)]
            emailv = (email.value or "").strip().lower()
            passv, confv = password.value or "", confirm.value or ""
            munv, edadv = (municipio.value or "").strip(), (edad.value or "").strip()
            carrv = (carrera.value or "").strip()
            if not all([apv, amv, nv, emailv, passv, confv, munv, edadv]):
                aviso("Completa apellidos, nombre, correo, contraseña, edad y municipio.", True)
                return
            if "@" not in emailv or " " in emailv:
                aviso("Escribe un correo electrónico válido.", True)
                return
            if len(passv) < 4:
                aviso("La contraseña debe tener al menos 4 caracteres.", True)
                return
            if passv != confv:
                aviso("Las contraseñas no coinciden.", True)
                return
            try:
                edad_num = int(edadv)
                if not 1 <= edad_num <= 120:
                    raise ValueError()
            except ValueError:
                aviso("La edad debe ser un número entre 1 y 120.", True)
                return
            es_alumno = rol.value == "Alumno"
            if es_alumno and not carrv:
                aviso("Escribe la carrera del alumno.", True)
                return
            nombre_completo = " ".join([apv, amv, nv])
            rol_db = "alumno" if es_alumno else "admin"

            def transaccion(cn, cur):
                cur.execute("SELECT id_usuario FROM usuarios WHERE usuario=%s", (emailv,))
                if cur.fetchone():
                    raise ValueError("Ese correo ya tiene una cuenta.")
                id_alumno = None
                if es_alumno:
                    cur.execute("""
                        INSERT INTO alumnos (nombre, edad, carrera, municipio)
                        VALUES (%s,%s,%s,%s)
                    """, (nombre_completo, edad_num, carrv, munv))
                    id_alumno = cur.lastrowid
                cols = obtener_columnas("usuarios")
                columnas = ["usuario", "password_hash", "rol", "id_alumno", "nombre_usuario"]
                valores = [emailv, hash_password(passv), rol_db, id_alumno, nombre_completo]
                if not es_alumno:
                    if "edad" in cols:
                        columnas.append("edad"); valores.append(edad_num)
                    if "municipio" in cols:
                        columnas.append("municipio"); valores.append(munv)
                # Algunas versiones antiguas tienen una columna password adicional.
                if "password" in cols:
                    columnas.append("password"); valores.append(hash_password(passv))
                sql_cols = ", ".join(f"`{c}`" for c in columnas)
                marcas = ", ".join(["%s"] * len(valores))
                cur.execute(f"INSERT INTO usuarios ({sql_cols}) VALUES ({marcas})", tuple(valores))
                return None

            try:
                ejecutar_transaccion(transaccion)
                aviso("Cuenta creada correctamente. Ya puedes iniciar sesión.")
                mostrar_login()
            except Exception as ex:
                mostrar_error("No se pudo crear la cuenta", ex)

        cambiar_pantalla(
            tarjeta("Crear cuenta", "Formulario adaptado del registro original", [
                rol, ap, am, nombres, email, password, confirm, edad, municipio, carrera,
                ft.Row([boton("Guardar registro", guardar, True),
                        boton("Volver al inicio de sesión", mostrar_login)], wrap=True),
                mensaje
            ])
        )

    def tabla_registros(titulo, filas, campos):
        zona.controls.clear()
        zona.controls.append(tarjeta(titulo, f"{len(filas)} registro(s)"))
        for fila in filas:
            lineas = []
            for campo, etiqueta in campos:
                valor = fila.get(campo)
                if valor is None or valor == "":
                    valor = "—"
                lineas.append(ft.Row([
                    ft.Text(etiqueta, width=155, color=SUAVE, weight=ft.FontWeight.BOLD),
                    ft.Text(str(valor), color=VINO, expand=True)
                ], vertical_alignment=ft.CrossAxisAlignment.START))
            zona.controls.append(ft.Container(
                content=ft.Column(lineas, spacing=5), bgcolor=TARJETA,
                border=ft.border.all(1, BORDE), border_radius=10, padding=12
            ))
        page.update()

    def alumnos_admin(e=None):
        try:
            filas = consultar("""
                SELECT id_alumno, apellido_paterno, apellido_materno, nombre,
                       edad, carrera, municipio
                FROM alumnos ORDER BY apellido_paterno, apellido_materno, nombre
            """)
            tabla_registros("Alumnos", filas, [
                ("id_alumno", "ID"), ("apellido_paterno", "Apellido paterno"),
                ("apellido_materno", "Apellido materno"), ("nombre", "Nombre(s)"),
                ("edad", "Edad"), ("carrera", "Carrera"), ("municipio", "Municipio")
            ])
        except Exception as ex:
            mostrar_error("No se pudieron cargar los alumnos", ex)

    def gastos_admin(e=None):
        try:
            filas = consultar("""
                SELECT g.id_gasto, CONCAT_WS(' ',a.nombre) AS alumno,
                       g.descripcion, g.monto, g.fecha, g.nivel_gasto,
                       c.nombre_categoria
                FROM gastos g JOIN alumnos a ON a.id_alumno=g.id_alumno
                LEFT JOIN categorias c ON c.id_categoria=g.id_categoria
                ORDER BY g.fecha DESC, g.id_gasto DESC
            """)
            for f in filas:
                f["monto"] = moneda(f["monto"])
            tabla_registros("Gastos generales", filas, [
                ("id_gasto", "ID"), ("alumno", "Alumno"), ("descripcion", "Descripción"),
                ("nombre_categoria", "Categoría"), ("monto", "Monto"),
                ("fecha", "Fecha"), ("nivel_gasto", "Nivel")
            ])
        except Exception as ex:
            mostrar_error("No se pudieron cargar los gastos", ex)

    def categorias_admin(e=None):
        try:
            filas = consultar("SELECT id_categoria,nombre_categoria,descripcion,tipo_categoria FROM categorias ORDER BY nombre_categoria")
            tabla_registros("Categorías", filas, [
                ("id_categoria", "ID"), ("nombre_categoria", "Categoría"),
                ("descripcion", "Descripción"), ("tipo_categoria", "Tipo")
            ])
        except Exception as ex:
            mostrar_error("No se pudieron cargar las categorías", ex)

    def presupuestos_admin(e=None):
        try:
            filas = consultar("""
                SELECT p.id_presupuesto, a.nombre AS alumno, p.semana_inicio,
                       p.monto_inicial, p.ahorro
                FROM presupuestos_semanales p JOIN alumnos a ON a.id_alumno=p.id_alumno
                ORDER BY p.semana_inicio DESC
            """)
            for f in filas:
                f["monto_inicial"] = moneda(f["monto_inicial"])
                f["ahorro"] = moneda(f.get("ahorro"))
            tabla_registros("Presupuestos semanales", filas, [
                ("id_presupuesto", "ID"), ("alumno", "Alumno"),
                ("semana_inicio", "Semana"), ("monto_inicial", "Monto inicial"),
                ("ahorro", "Ahorro registrado")
            ])
        except Exception as ex:
            mostrar_error("No se pudieron cargar los presupuestos", ex)

    def ahorros_admin(e=None):
        try:
            filas = consultar("""
                SELECT h.id_ahorro, a.nombre AS alumno, h.semana_inicio,
                       h.monto, h.fecha_registro
                FROM ahorros h JOIN alumnos a ON a.id_alumno=h.id_alumno
                ORDER BY h.fecha_registro DESC
            """)
            for f in filas:
                f["monto"] = moneda(f["monto"])
            tabla_registros("Ahorros", filas, [
                ("id_ahorro", "ID"), ("alumno", "Alumno"), ("semana_inicio", "Semana"),
                ("monto", "Monto"), ("fecha_registro", "Fecha de registro")
            ])
        except Exception as ex:
            mostrar_error("No se pudieron cargar los ahorros", ex)

    def resumen_admin(e=None):
        try:
            n_alumnos = consultar("SELECT COUNT(*) n FROM alumnos")[0]["n"]
            gastos = consultar("SELECT COUNT(*) n, COALESCE(SUM(monto),0) suma FROM gastos")[0]
            n_cat = consultar("SELECT COUNT(*) n FROM categorias")[0]["n"]
            n_pres = consultar("SELECT COUNT(*) n FROM presupuestos_semanales")[0]["n"]
            ahorros = consultar("SELECT COUNT(*) n, COALESCE(SUM(monto),0) suma FROM ahorros")[0]
            zona.controls.clear()
            zona.controls.append(tarjeta("Resumen general", "Información de tu base de datos actual"))
            for label, value in [
                ("Alumnos registrados", n_alumnos), ("Gastos registrados", gastos["n"]),
                ("Importe de gastos", moneda(gastos["suma"])), ("Categorías", n_cat),
                ("Presupuestos semanales", n_pres), ("Movimientos de ahorro", ahorros["n"]),
                ("Importe acumulado de ahorros", moneda(ahorros["suma"]))
            ]:
                zona.controls.append(tarjeta(label, str(value)))
            page.update()
        except Exception as ex:
            mostrar_error("No se pudo calcular el resumen", ex)

    def mis_gastos(e=None):
        try:
            filas = consultar("""
                SELECT g.id_gasto,g.descripcion,g.monto,g.fecha,g.nivel_gasto,c.nombre_categoria
                FROM gastos g LEFT JOIN categorias c ON c.id_categoria=g.id_categoria
                WHERE g.id_alumno=%s ORDER BY g.fecha DESC,g.id_gasto DESC
            """, (sesion["id_alumno"],))
            for f in filas:
                f["monto"] = moneda(f["monto"])
            tabla_registros("Mis gastos", filas, [
                ("id_gasto", "ID"), ("descripcion", "Descripción"), ("nombre_categoria", "Categoría"),
                ("monto", "Monto"), ("fecha", "Fecha"), ("nivel_gasto", "Nivel")
            ])
        except Exception as ex:
            mostrar_error("No se pudieron cargar tus gastos", ex)

    def mi_presupuesto(e=None):
        try:
            ident, lunes = sesion["id_alumno"], obtener_lunes()
            presupuesto = consultar("""
                SELECT monto_inicial FROM presupuestos_semanales
                WHERE id_alumno=%s AND semana_inicio=%s
            """, (ident, lunes))
            gasto = consultar("""
                SELECT COALESCE(SUM(monto),0) total FROM gastos
                WHERE id_alumno=%s AND fecha >= %s AND fecha < %s
            """, (ident, lunes, lunes + timedelta(days=7)))[0]["total"]
            ahorro = consultar("""
                SELECT COALESCE(SUM(monto),0) total FROM ahorros
                WHERE id_alumno=%s AND semana_inicio=%s
            """, (ident, lunes))[0]["total"]
            inicial = Decimal(str(presupuesto[0]["monto_inicial"])) if presupuesto else Decimal("0")
            gasto, ahorro = Decimal(str(gasto or 0)), Decimal(str(ahorro or 0))
            zona.controls.clear()
            zona.controls.append(tarjeta("Mi presupuesto semanal", f"Semana del {lunes}"))
            for label, value in [
                ("Presupuesto inicial", moneda(inicial)), ("Gastado esta semana", moneda(gasto)),
                ("Ahorro de esta semana", moneda(ahorro)),
                ("Disponible estimado", moneda(inicial - gasto - ahorro))
            ]:
                zona.controls.append(tarjeta(label, value))
            page.update()
        except Exception as ex:
            mostrar_error("No se pudo cargar tu presupuesto", ex)

    def mis_ahorros(e=None):
        try:
            filas = consultar("""
                SELECT id_ahorro,semana_inicio,monto,fecha_registro
                FROM ahorros WHERE id_alumno=%s ORDER BY fecha_registro DESC
            """, (sesion["id_alumno"],))
            for f in filas:
                f["monto"] = moneda(f["monto"])
            tabla_registros("Mi ahorro", filas, [
                ("id_ahorro", "ID"), ("semana_inicio", "Semana"),
                ("monto", "Monto"), ("fecha_registro", "Fecha")
            ])
        except Exception as ex:
            mostrar_error("No se pudieron cargar tus ahorros", ex)

    def cerrar_sesion(e=None):
        sesion.update({"id_usuario": None, "usuario": None, "rol": None,
                       "id_alumno": None, "nombre": None})
        mostrar_login()

    def mostrar_panel():
        rol = sesion["rol"]
        titulo = "CONTROL INTELIGENTE DE GASTOS"
        encabezado = ft.Container(
            content=ft.Column([
                ft.Text(titulo, size=24, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                ft.Text(f"Sesión: {sesion['nombre']} · Perfil: {rol}", color="#FFFFFF")
            ], spacing=4),
            bgcolor=NARANJA, border_radius=14, padding=18
        )
        if rol == "admin":
            opciones = [
                ("Resumen", resumen_admin), ("Alumnos", alumnos_admin),
                ("Gastos", gastos_admin), ("Categorías", categorias_admin),
                ("Presupuestos", presupuestos_admin), ("Ahorros", ahorros_admin)
            ]
        else:
            opciones = [
                ("Mis gastos", mis_gastos), ("Mi presupuesto", mi_presupuesto),
                ("Mi ahorro", mis_ahorros)
            ]
        menu = ft.Row([boton(nombre, fn) for nombre, fn in opciones] +
                      [boton("Cerrar sesión", cerrar_sesion)], wrap=True, spacing=8, run_spacing=8)
        cambiar_pantalla(encabezado, menu, mensaje, zona)
        if rol == "admin":
            resumen_admin()
        else:
            mi_presupuesto()

    mostrar_login()


if __name__ == "__main__":
    ft.run(main)
