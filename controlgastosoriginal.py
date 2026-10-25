import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import re
import mysql.connector
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

try:
    from sklearn.linear_model import LinearRegression
    from sklearn.cluster import KMeans
except ImportError:
    LinearRegression = None  # La regresión se informa como no disponible si falta scikit-learn.
    KMeans = None


# ============================================================
# CONFIGURACIÓN
# ============================================================

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "control_gastos_alumnos",
    "connection_timeout": 5
}

# Únicamente estas seis personas pueden crear una cuenta de administrador.
ADMINISTRADORES_AUTORIZADOS = {
    "yazmin", "lizbeth", "erika", "francisco", "leonardo", "danitzia"
}


def nombre_admin_autorizado(texto):
    """Devuelve un nombre autorizado encontrado como palabra completa, o None."""
    palabras = re.findall(r"[a-záéíóúüñ]+", (texto or "").casefold())
    for palabra in palabras:
        if palabra in ADMINISTRADORES_AUTORIZADOS:
            return palabra
    return None


# ============================================================
# UTILIDADES DE BASE DE DATOS
# ============================================================

def conectar_bd():
    return mysql.connector.connect(**DB_CONFIG)


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def obtener_lunes(fecha=None):
    fecha = fecha or date.today()
    return fecha - timedelta(days=fecha.weekday())


def leer_dataframe(query, cn, params=None):
    """Ejecuta SQL con mysql.connector y devuelve un DataFrame."""
    cur = cn.cursor(dictionary=True, buffered=True)
    try:
        cur.execute(query, params or ())
        filas = cur.fetchall()
        return pd.DataFrame(filas)
    finally:
        cur.close()


def obtener_columnas(tabla):
    """Devuelve las columnas existentes de una tabla."""
    cn = conectar_bd()
    cur = cn.cursor(buffered=True)
    try:
        cur.execute(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = %s
            """,
            (DB_CONFIG["database"], tabla)
        )
        return {fila[0] for fila in cur.fetchall()}
    finally:
        cur.close()
        cn.close()


def agregar_columna_si_no_existe(tabla, columna, definicion):
    """Agrega una columna solo si la tabla existente todavía no la tiene."""
    columnas = obtener_columnas(tabla)
    if columna not in columnas:
        cn = conectar_bd()
        cur = cn.cursor(buffered=True)
        try:
            cur.execute(
                f"ALTER TABLE `{tabla}` ADD COLUMN `{columna}` {definicion}"
            )
            cn.commit()
        finally:
            cur.close()
            cn.close()


# ============================================================
# PREPARACIÓN Y MIGRACIÓN DE BASE DE DATOS
# ============================================================

def preparar_base_datos():
    """
    Crea las tablas si no existen y adapta la tabla usuarios
    de versiones anteriores sin borrar alumnos, gastos ni presupuestos.
    """

    cn = conectar_bd()
    cur = cn.cursor(buffered=True)

    try:
        # ----------------------------------------------------
        # ALUMNOS
        # ----------------------------------------------------
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS alumnos (
                id_alumno INT AUTO_INCREMENT PRIMARY KEY,
                nombre VARCHAR(120) NOT NULL,
                edad INT NOT NULL DEFAULT 0,
                carrera VARCHAR(120) NOT NULL DEFAULT 'Sin especificar',
                municipio VARCHAR(120) NOT NULL DEFAULT 'Sin especificar'
            )
            """
        )

        # ----------------------------------------------------
        # CATEGORÍAS
        # ----------------------------------------------------
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS categorias (
                id_categoria INT AUTO_INCREMENT PRIMARY KEY,
                nombre_categoria VARCHAR(100) NOT NULL UNIQUE,
                descripcion VARCHAR(255),
                tipo_categoria VARCHAR(80)
            )
            """
        )

        # ----------------------------------------------------
        # GASTOS
        # ----------------------------------------------------
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS gastos (
                id_gasto INT AUTO_INCREMENT PRIMARY KEY,
                id_alumno INT NOT NULL,
                id_categoria INT NOT NULL,
                descripcion VARCHAR(255) NOT NULL,
                monto DECIMAL(10,2) NOT NULL,
                fecha DATE NOT NULL,
                FOREIGN KEY (id_alumno)
                    REFERENCES alumnos(id_alumno)
                    ON UPDATE CASCADE
                    ON DELETE CASCADE,
                FOREIGN KEY (id_categoria)
                    REFERENCES categorias(id_categoria)
                    ON UPDATE CASCADE
                    ON DELETE RESTRICT
            )
            """
        )

        # ----------------------------------------------------
        # PRESUPUESTOS
        # ----------------------------------------------------
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS presupuestos_semanales (
                id_presupuesto INT AUTO_INCREMENT PRIMARY KEY,
                id_alumno INT NOT NULL,
                semana_inicio DATE NOT NULL,
                monto_inicial DECIMAL(10,2) NOT NULL,
                UNIQUE KEY uq_alumno_semana
                    (id_alumno, semana_inicio),
                FOREIGN KEY (id_alumno)
                    REFERENCES alumnos(id_alumno)
                    ON UPDATE CASCADE
                    ON DELETE CASCADE
            )
            """
        )

        # ----------------------------------------------------
        # AHORROS (movimientos históricos, no se sobreescriben)
        # ----------------------------------------------------
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ahorros (
                id_ahorro INT AUTO_INCREMENT PRIMARY KEY,
                id_alumno INT NOT NULL,
                semana_inicio DATE NOT NULL,
                monto DECIMAL(10,2) NOT NULL,
                fecha_registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (id_alumno) REFERENCES alumnos(id_alumno)
                    ON UPDATE CASCADE ON DELETE CASCADE
            )
            """
        )

        # ----------------------------------------------------
        # USUARIOS
        # ----------------------------------------------------
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id_usuario INT AUTO_INCREMENT PRIMARY KEY,
                usuario VARCHAR(150) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                rol VARCHAR(20) NOT NULL,
                id_alumno INT NULL,
                nombre_usuario VARCHAR(120) NULL,
                edad INT NULL,
                municipio VARCHAR(120) NULL,
                FOREIGN KEY (id_alumno)
                    REFERENCES alumnos(id_alumno)
                    ON UPDATE CASCADE
                    ON DELETE SET NULL
            )
            """
        )

        cn.commit()

    finally:
        cur.close()
        cn.close()

    # Migración compatible con alumnos registrados en versiones anteriores.
    agregar_columna_si_no_existe(
        "alumnos", "municipio", "VARCHAR(120) NOT NULL DEFAULT 'Sin especificar'"
    )

    # --------------------------------------------------------
    # MIGRACIÓN DE USUARIOS DE VERSIONES ANTERIORES
    # --------------------------------------------------------
    # Algunas versiones anteriores usaban "password" en lugar
    # de "password_hash". También se agrega el nombre del usuario.
    agregar_columna_si_no_existe(
        "usuarios",
        "password_hash",
        "VARCHAR(255) NULL"
    )

    agregar_columna_si_no_existe(
        "usuarios",
        "nombre_usuario",
        "VARCHAR(120) NULL"
    )

    # Datos personales para cuentas de administrador.
    agregar_columna_si_no_existe("usuarios", "edad", "INT NULL")
    agregar_columna_si_no_existe("usuarios", "municipio", "VARCHAR(120) NULL")

    # Si existe la columna antigua "password", intentamos copiar
    # su contenido a password_hash cuando password_hash esté vacío.
    columnas_usuarios = obtener_columnas("usuarios")

    cn = conectar_bd()
    cur = cn.cursor(dictionary=True, buffered=True)

    try:
        if "password" in columnas_usuarios:
            cur.execute(
                """
                SELECT id_usuario, password, password_hash
                FROM usuarios
                """
            )

            filas = cur.fetchall()

            for fila in filas:
                antiguo = fila.get("password")
                actual = fila.get("password_hash")

                if antiguo and not actual:
                    # Si ya parece SHA-256, se conserva.
                    if (
                        len(str(antiguo)) == 64
                        and all(
                            c in "0123456789abcdefABCDEF"
                            for c in str(antiguo)
                        )
                    ):
                        nuevo_hash = str(antiguo)
                    else:
                        nuevo_hash = hash_password(str(antiguo))

                    cur.execute(
                        """
                        UPDATE usuarios
                        SET password_hash = %s
                        WHERE id_usuario = %s
                        """,
                        (nuevo_hash, fila["id_usuario"])
                    )

        # Las columnas antiguas pueden ser NOT NULL. Las cuentas nuevas
        # usarán password_hash; no se modifica ni se elimina la columna vieja.
        cn.commit()

    finally:
        cur.close()
        cn.close()

    # --------------------------------------------------------
    # CATEGORÍAS INICIALES
    # --------------------------------------------------------
    categorias_iniciales = [
        ("Alimentación", "Comidas y bebidas", "Necesidad"),
        ("Transporte", "Pasajes y transporte", "Necesidad"),
        ("Escuela", "Material escolar", "Educación"),
        ("Entretenimiento", "Diversión y ocio", "Ocio"),
        ("Salud", "Medicamentos y consultas", "Salud"),
        ("Otros", "Otros gastos", "General")
    ]

    cn = conectar_bd()
    cur = cn.cursor(buffered=True)

    try:
        for nombre, descripcion, tipo in categorias_iniciales:
            cur.execute(
                """
                SELECT id_categoria
                FROM categorias
                WHERE nombre_categoria = %s
                LIMIT 1
                """,
                (nombre,)
            )

            if cur.fetchone() is None:
                cur.execute(
                    """
                    INSERT INTO categorias
                    (nombre_categoria, descripcion, tipo_categoria)
                    VALUES (%s, %s, %s)
                    """,
                    (nombre, descripcion, tipo)
                )

        # No se crean alumnos, usuarios ni gastos de prueba.
        # Se eliminan únicamente las credenciales de prueba que
        # creó una versión anterior del programa.
        cur.execute(
            """
            DELETE FROM usuarios
            WHERE usuario IN (
                'admin@controlgastos.com',
                'alumno@controlgastos.com'
            )
            """
        )

        cn.commit()

    finally:
        cur.close()
        cn.close()


# ============================================================
# APLICACIÓN
# ============================================================

class Aplicacion:

    def __init__(self, root):
        self.root = root

        self.root.title(
            "Control Inteligente de Gastos de Alumnos"
        )

        self.root.geometry("1250x780")
        self.root.minsize(1050, 680)

        # Apariencia visual: paleta moderna en azul, turquesa y violeta.
        self.configurar_estilos()

        self.usuario_id = None
        self.usuario = None
        self.rol = None
        self.id_alumno = None
        self.nombre_usuario = None
        self.nombre_alumno = None
        self.categorias_map = {}

        self.mostrar_login()

    # ========================================================
    # GENERAL
    # ========================================================

    def configurar_estilos(self):
        """Define la apariencia general sin modificar la lógica del sistema."""
        self.colores = {
            "fondo": "#FFF4E8",          # crema cálido para toda la aplicación
            "blanco": "#FFFCF8",
            "primario": "#E87932",        # naranja
            "primario_hover": "#C85B20",
            "turquesa": "#D95D8A",        # rosa
            "verde": "#B86B35",           # caramelo
            "rojo": "#C94F63",
            "violeta": "#A64D79",
            "texto": "#573344",           # vino oscuro para buen contraste
            "texto_suave": "#805C68",
            "borde": "#F0CDBB",
            "seleccion": "#FCE0D4",
        }

        self.root.configure(bg=self.colores["fondo"])
        estilo = ttk.Style(self.root)

        # "clam" permite personalizar los colores en la mayoría de sistemas.
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass

        estilo.configure(
            "TFrame",
            background=self.colores["fondo"]
        )
        estilo.configure(
            "TLabelframe",
            background=self.colores["fondo"],
            bordercolor=self.colores["borde"],
            relief="solid"
        )
        estilo.configure(
            "TLabelframe.Label",
            background=self.colores["fondo"],
            foreground=self.colores["primario"],
            font=("Segoe UI", 10, "bold")
        )
        estilo.configure(
            "DatosAlumno.TLabelframe.Label",
            background=self.colores["fondo"],
            foreground=self.colores["primario"],
            font=("Segoe UI", 13, "bold")
        )
        estilo.configure(
            "TLabel",
            background=self.colores["fondo"],
            foreground=self.colores["texto"],
            font=("Segoe UI", 10)
        )
        # Barra de presupuesto del alumno: verde visible y de buen contraste.
        estilo.configure(
            "Presupuesto.Horizontal.TProgressbar",
            troughcolor="#E5E7EB",
            background="#25A85A",
            lightcolor="#25A85A",
            darkcolor="#25A85A",
            bordercolor="#C8D9CC",
            thickness=22
        )
        # Texto de advertencia del presupuesto.
        estilo.configure(
            "AlertaPresupuesto.TLabel",
            background=self.colores["fondo"],
            foreground="#D00000",
            font=("Segoe UI", 11, "bold")
        )
        estilo.configure(
            "PresupuestoNormal.TLabel",
            background=self.colores["fondo"],
            foreground="#218838",
            font=("Segoe UI", 11, "bold")
        )
        estilo.configure(
            "TEntry",
            fieldbackground=self.colores["blanco"],
            foreground=self.colores["texto"],
            insertcolor=self.colores["texto"],
            padding=7,
            bordercolor=self.colores["borde"]
        )
        estilo.configure(
            "TCombobox",
            fieldbackground=self.colores["blanco"],
            background=self.colores["blanco"],
            foreground=self.colores["texto"],
            padding=6,
            arrowsize=14
        )
        estilo.configure(
            "TButton",
            background=self.colores["primario"],
            foreground="#FFFFFF",
            font=("Segoe UI", 11, "bold"),
            padding=(14, 10),
            borderwidth=0,
            focusthickness=0
        )
        estilo.map(
            "TButton",
            background=[
                ("disabled", "#B8C4D6"),
                ("pressed", self.colores["primario_hover"]),
                ("active", self.colores["primario_hover"])
            ],
            foreground=[("disabled", "#F5F7FA"), ("!disabled", "#FFFFFF")]
        )

        # Estilos de botones por función.
        estilos_boton = {
            "Verde.TButton": self.colores["verde"],
            "Rojo.TButton": self.colores["rojo"],
            "Turquesa.TButton": self.colores["turquesa"],
            "Violeta.TButton": self.colores["violeta"],
            "Gris.TButton": "#64748B",
            "Azul.TButton": self.colores["primario"],
        }
        for nombre, color in estilos_boton.items():
            estilo.configure(
                nombre,
                background=color,
                foreground="#FFFFFF",
                font=("Segoe UI", 11, "bold"),
                padding=(14, 10),
                borderwidth=0
            )
            estilo.map(
                nombre,
                background=[
                    ("pressed", "#26364F"),
                    ("active", "#334B70")
                ],
                foreground=[("!disabled", "#FFFFFF")]
            )

        estilo.configure(
            "TNotebook",
            background=self.colores["fondo"],
            borderwidth=0,
            tabmargins=(4, 5, 4, 0)
        )
        estilo.configure(
            "TNotebook.Tab",
            background="#F8DCCB",
            foreground=self.colores["texto"],
            padding=(16, 11),
            font=("Segoe UI", 10, "bold")
        )
        estilo.map(
            "TNotebook.Tab",
            background=[("selected", "#C85B20")],
            foreground=[("selected", "#FFFFFF")]
        )
        estilo.configure(
            "Treeview",
            background=self.colores["blanco"],
            fieldbackground=self.colores["blanco"],
            foreground=self.colores["texto"],
            rowheight=32,
            bordercolor=self.colores["borde"],
            font=("Segoe UI", 10)
        )
        estilo.configure(
            "Treeview.Heading",
            background="#B95732",
            foreground="#FFFFFF",
            font=("Segoe UI", 10, "bold"),
            padding=10
        )
        estilo.map(
            "Treeview",
            background=[("selected", self.colores["seleccion"])],
            foreground=[("selected", self.colores["texto"])]
        )
        estilo.configure(
            "Vertical.TScrollbar",
            background="#F1C5AD",
            troughcolor=self.colores["fondo"],
            arrowcolor=self.colores["primario"]
        )

        # Tablas con acentos diferentes para distinguir cada sección.
        estilo.configure(
            "GastosAdmin.Treeview",
            background="#FFFBF5",
            fieldbackground="#FFFBF5",
            foreground="#573344",
            rowheight=33,
            font=("Segoe UI", 10)
        )
        estilo.configure(
            "GastosAdmin.Treeview.Heading",
            background="#B95732",
            foreground="#FFFFFF",
            font=("Segoe UI", 10, "bold"),
            padding=10
        )
        estilo.map(
            "GastosAdmin.Treeview",
            background=[("selected", "#F8C9A8")],
            foreground=[("selected", "#573344")]
        )
        estilo.configure(
            "GastosAlumno.Treeview",
            background="#FFF7F8",
            fieldbackground="#FFF7F8",
            foreground="#573344",
            rowheight=34,
            font=("Segoe UI", 10)
        )
        estilo.configure(
            "GastosAlumno.Treeview.Heading",
            background="#C64F78",
            foreground="#FFFFFF",
            font=("Segoe UI", 10, "bold"),
            padding=10
        )
        estilo.map(
            "GastosAlumno.Treeview",
            background=[("selected", "#F7C8D7")],
            foreground=[("selected", "#573344")]
        )

    def aplicar_estilos_widgets(self):
        """Asigna colores a botones según la acción que realizan."""
        def recorrer(contenedor):
            for widget in contenedor.winfo_children():
                if isinstance(widget, ttk.Button):
                    try:
                        texto_original = str(widget.cget("text"))
                        widget.configure(
                            text=texto_original.upper(),
                            style="Azul.TButton"
                        )
                        texto = texto_original.lower()
                        if any(p in texto for p in (
                            "eliminar", "borrar", "cancelar"
                        )):
                            widget.configure(style="Rojo.TButton")
                        elif any(p in texto for p in (
                            "crear cuenta", "crear alumno", "guardar",
                            "registrar", "agregar", "insertar"
                        )):
                            widget.configure(style="Verde.TButton")
                        elif any(p in texto for p in (
                            "estadística", "gráfica", "grafica",
                            "regresión", "agrupar", "predicción",
                            "prediccion"
                        )):
                            widget.configure(style="Violeta.TButton")
                        elif any(p in texto for p in (
                            "cerrar sesión", "cerrar sesion", "regresar",
                            "volver", "salir"
                        )):
                            widget.configure(style="Gris.TButton")
                        elif any(p in texto for p in (
                            "buscar", "aplicar", "mostrar todo"
                        )):
                            widget.configure(style="Turquesa.TButton")
                        else:
                            widget.configure(style="Azul.TButton")
                    except tk.TclError:
                        pass
                elif isinstance(widget, ttk.Label):
                    try:
                        texto_label = str(widget.cget("text"))
                        # Labels de campos/formularios: terminan en dos puntos
                        # o coinciden con nombres habituales de campos.
                        campos_formulario = {
                            "correo electrónico", "contraseña",
                            "confirmar contraseña", "tipo de cuenta",
                            "nombre completo", "apellido paterno",
                            "apellido materno", "nombre(s)", "edad",
                            "carrera", "municipio", "presupuesto inicial",
                            "categoría", "descripción", "fecha", "monto"
                        }
                        if texto_label.strip().rstrip(":").lower() in campos_formulario or texto_label.strip().endswith(":"):
                            widget.configure(
                                text=texto_label.upper(),
                                foreground="#A64D59",
                                font=("Segoe UI", 10, "bold")
                            )
                    except tk.TclError:
                        pass
                recorrer(widget)

        recorrer(self.root)

    def limpiar(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        # Se ejecuta cuando la pantalla nueva ya terminó de construirse.
        self.root.after_idle(self.aplicar_estilos_widgets)

    def cerrar_sesion(self):
        self.usuario_id = None
        self.usuario = None
        self.rol = None
        self.id_alumno = None
        self.nombre_usuario = None
        self.nombre_alumno = None
        self.categorias_map = {}
        self.mostrar_login()

    def crear_area_desplazable(self, padre):
        """Crea un área con desplazamiento vertical para pantallas largas."""
        exterior = ttk.Frame(padre)
        canvas = tk.Canvas(
            exterior,
            background=self.colores["fondo"],
            highlightthickness=0,
            borderwidth=0
        )
        barra = ttk.Scrollbar(
            exterior, orient="vertical", command=canvas.yview
        )
        contenido = ttk.Frame(canvas)
        ventana = canvas.create_window((0, 0), window=contenido, anchor="nw")

        def actualizar_region(_evento=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def ajustar_ancho(evento):
            canvas.itemconfigure(ventana, width=evento.width)

        contenido.bind("<Configure>", actualizar_region)
        canvas.bind("<Configure>", ajustar_ancho)
        canvas.configure(yscrollcommand=barra.set)
        canvas.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")

        # Permite desplazarse con la rueda del ratón sobre el área.
        def rueda(evento):
            canvas.yview_scroll(int(-1 * (evento.delta / 120)), "units")

        canvas.bind("<MouseWheel>", rueda)
        contenido.bind("<MouseWheel>", rueda)
        return exterior, contenido

    def alternar_visibilidad_password(self, entrada, boton):
        """Muestra u oculta la contraseña al pulsar el botón del ojo."""
        visible = entrada.cget("show") == "*"
        entrada.configure(show="" if visible else "*")
        boton.configure(text="🙈" if visible else "👁")

    # ========================================================
    # LOGIN ÚNICO
    # ========================================================

    def mostrar_login(self):
        self.limpiar()

        contenedor = ttk.Frame(self.root, padding=40)
        contenedor.pack(expand=True)

        ttk.Label(
            contenedor,
            text="CONTROL INTELIGENTE DE GASTOS",
            font=("Segoe UI", 27, "bold"), foreground="#7B3155"
        ).pack(pady=20)

        ttk.Label(
            contenedor,
            text="Inicia sesión con el correo y contraseña que tú registraste.",
            font=("Arial", 13)
        ).pack(pady=10)

        ttk.Label(
            contenedor,
            text="Correo electrónico",
            font=("Segoe UI", 12, "bold")
        ).pack(anchor="w", pady=(20, 5))

        self.entry_usuario = ttk.Entry(
            contenedor,
            width=42,
            font=("Segoe UI", 13)
        )
        self.entry_usuario.pack()

        ttk.Label(
            contenedor,
            text="Contraseña",
            font=("Segoe UI", 12, "bold")
        ).pack(anchor="w", pady=(15, 5))

        fila_password = ttk.Frame(contenedor)
        fila_password.pack(anchor="w")
        self.entry_password = ttk.Entry(
            fila_password,
            width=38,
            show="*",
            font=("Segoe UI", 13)
        )
        self.entry_password.pack(side="left")
        self.boton_ver_password = ttk.Button(
            fila_password, text="👁", width=4,
            command=lambda: self.alternar_visibilidad_password(
                self.entry_password, self.boton_ver_password
            )
        )
        self.boton_ver_password.pack(side="left", padx=(5, 0))

        ttk.Button(
            contenedor,
            text="Iniciar sesión",
            command=self.iniciar_sesion
        ).pack(pady=20, ipadx=30, ipady=5)

        ttk.Button(
            contenedor,
            text="Crear una cuenta nueva",
            command=self.mostrar_registro
        ).pack(pady=5)

        ttk.Label(
            contenedor,
            text="No hay correo ni contraseña predeterminados.",
            foreground="gray"
        ).pack(pady=15)

        self.entry_usuario.focus_set()

    # ========================================================
    # REGISTRO
    # ========================================================

    def mostrar_registro(self):
        self.limpiar()

        contenedor = ttk.Frame(
            self.root,
            padding=25
        )
        contenedor.pack(expand=True)

        ttk.Label(
            contenedor,
            text="CREAR CUENTA",
            font=("Segoe UI", 25, "bold"), foreground="#7B3155"
        ).grid(
            row=0,
            column=0,
            columnspan=2,
            pady=(0, 20)
        )

        ttk.Label(
            contenedor,
            text="TIPO DE CUENTA:",
            font=("Segoe UI", 12, "bold")
        ).grid(
            row=1,
            column=0,
            sticky="w",
            padx=8,
            pady=7
        )

        self.combo_rol_registro = ttk.Combobox(
            contenedor,
            values=["Alumno", "Administrador"],
            state="readonly",
            width=38,
            font=("Segoe UI", 12)
        )
        self.combo_rol_registro.grid(
            row=1,
            column=1,
            padx=8,
            pady=7
        )
        self.combo_rol_registro.current(0)
        self.combo_rol_registro.bind(
            "<<ComboboxSelected>>",
            self.actualizar_campos_registro
        )

        ttk.Label(contenedor, text="Nombre completo:").grid(
            row=2, column=0, sticky="w", padx=8, pady=7
        )
        nombres_frame = ttk.Frame(contenedor)
        nombres_frame.grid(row=2, column=1, sticky="ew", padx=8, pady=7)

        # Campos separados y etiquetados para alumnos y administradores.
        campo_paterno = ttk.Frame(nombres_frame)
        campo_paterno.pack(side="left", padx=(0, 4))
        ttk.Label(campo_paterno, text="Apellido Paterno").pack(anchor="w")
        self.entry_reg_apellido_paterno = ttk.Entry(campo_paterno, width=13)
        self.entry_reg_apellido_paterno.pack()

        campo_materno = ttk.Frame(nombres_frame)
        campo_materno.pack(side="left", padx=4)
        ttk.Label(campo_materno, text="Apellido Materno").pack(anchor="w")
        self.entry_reg_apellido_materno = ttk.Entry(campo_materno, width=13)
        self.entry_reg_apellido_materno.pack()

        campo_nombres = ttk.Frame(nombres_frame)
        campo_nombres.pack(side="left", padx=(4, 0))
        ttk.Label(campo_nombres, text="Nombre(s)").pack(anchor="w")
        self.entry_reg_nombre_persona = ttk.Entry(campo_nombres, width=13)
        self.entry_reg_nombre_persona.pack()

        ttk.Label(
            contenedor,
            text="Correo electrónico:"
        ).grid(
            row=3,
            column=0,
            sticky="w",
            padx=8,
            pady=7
        )

        self.entry_reg_correo = ttk.Entry(
            contenedor,
            width=41,
            font=("Segoe UI", 12)
        )
        self.entry_reg_correo.grid(
            row=3,
            column=1,
            padx=8,
            pady=7
        )

        ttk.Label(
            contenedor,
            text="Contraseña:"
        ).grid(
            row=4,
            column=0,
            sticky="w",
            padx=8,
            pady=7
        )

        self.entry_reg_password = ttk.Entry(
            contenedor,
            width=36,
            show="*",
            font=("Segoe UI", 12)
        )
        self.entry_reg_password.grid(
            row=4,
            column=1,
            padx=8,
            pady=7,
            sticky="w"
        )
        self.boton_ver_reg_password = ttk.Button(
            contenedor, text="👁", width=4,
            command=lambda: self.alternar_visibilidad_password(
                self.entry_reg_password, self.boton_ver_reg_password
            )
        )
        self.boton_ver_reg_password.grid(row=4, column=2, padx=(0, 8), pady=7)

        ttk.Label(
            contenedor,
            text="Confirmar contraseña:"
        ).grid(
            row=5,
            column=0,
            sticky="w",
            padx=8,
            pady=7
        )

        self.entry_reg_confirm = ttk.Entry(
            contenedor,
            width=36,
            show="*",
            font=("Segoe UI", 12)
        )
        self.entry_reg_confirm.grid(
            row=5,
            column=1,
            padx=8,
            pady=7,
            sticky="w"
        )
        self.boton_ver_reg_confirm = ttk.Button(
            contenedor, text="👁", width=4,
            command=lambda: self.alternar_visibilidad_password(
                self.entry_reg_confirm, self.boton_ver_reg_confirm
            )
        )
        self.boton_ver_reg_confirm.grid(row=5, column=2, padx=(0, 8), pady=7)

        self.frame_datos_alumno = ttk.LabelFrame(
            contenedor,
            text="DATOS DEL ALUMNO",
            padding=10,
            labelanchor="nw",
            style="DatosAlumno.TLabelframe"
        )
        self.frame_datos_alumno.grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=10
        )

        ttk.Label(
            self.frame_datos_alumno,
            text="Edad:"
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=5,
            pady=5
        )

        self.entry_reg_edad = ttk.Entry(
            self.frame_datos_alumno,
            width=39
        )
        self.entry_reg_edad.grid(
            row=0,
            column=1,
            padx=5,
            pady=5
        )

        self.lbl_reg_carrera = ttk.Label(
            self.frame_datos_alumno,
            text="Carrera:"
        )
        self.lbl_reg_carrera.grid(
            row=1,
            column=0,
            sticky="w",
            padx=5,
            pady=5
        )

        self.entry_reg_carrera = ttk.Entry(
            self.frame_datos_alumno,
            width=39
        )
        self.entry_reg_carrera.grid(
            row=1,
            column=1,
            padx=5,
            pady=5
        )

        self.lbl_reg_municipio = ttk.Label(
            self.frame_datos_alumno,
            text="Municipio:"
        )
        self.lbl_reg_municipio.grid(
            row=2, column=0, sticky="w", padx=5, pady=5
        )

        self.entry_reg_municipio = ttk.Entry(
            self.frame_datos_alumno, width=39
        )
        self.entry_reg_municipio.grid(row=2, column=1, padx=5, pady=5)

        ttk.Button(
            contenedor,
            text="Crear cuenta",
            command=self.registrar_usuario
        ).grid(
            row=7,
            column=0,
            columnspan=2,
            pady=15,
            ipadx=30,
            ipady=5
        )

        ttk.Button(
            contenedor,
            text="← Regresar al inicio de sesión",
            command=self.mostrar_login
        ).grid(
            row=8,
            column=0,
            columnspan=2,
            pady=5
        )

        self.actualizar_campos_registro()

    def actualizar_campos_registro(self, event=None):
        es_alumno = self.combo_rol_registro.get() == "Alumno"

        # Edad y municipio se solicitan en ambos tipos de cuenta.
        # El campo Carrera solo se muestra al registrar un alumno.
        self.entry_reg_edad.configure(state="normal")
        self.entry_reg_municipio.configure(state="normal")

        if es_alumno:
            self.lbl_reg_carrera.grid()
            self.entry_reg_carrera.grid()
            self.lbl_reg_municipio.grid(row=2, column=0, sticky="w", padx=5, pady=5)
            self.entry_reg_municipio.grid(row=2, column=1, padx=5, pady=5)
        else:
            self.lbl_reg_carrera.grid_remove()
            self.entry_reg_carrera.grid_remove()
            self.lbl_reg_municipio.grid(row=1, column=0, sticky="w", padx=5, pady=5)
            self.entry_reg_municipio.grid(row=1, column=1, padx=5, pady=5)

        self.frame_datos_alumno.configure(
            text="DATOS DEL ALUMNO" if es_alumno else "DATOS DEL ADMINISTRADOR"
        )

    def registrar_usuario(self):
        rol_texto = self.combo_rol_registro.get()

        apellido_paterno = self.entry_reg_apellido_paterno.get().strip()
        apellido_materno = self.entry_reg_apellido_materno.get().strip()
        nombres = self.entry_reg_nombre_persona.get().strip()
        nombre = " ".join(x for x in (apellido_paterno, apellido_materno, nombres) if x)
        correo = self.entry_reg_correo.get().strip().lower()
        password = self.entry_reg_password.get()
        confirmacion = self.entry_reg_confirm.get()

        if not apellido_paterno or not apellido_materno or not nombres:
            messagebox.showwarning(
                "Dato faltante",
                "Completa apellido paterno, apellido materno y nombre(s)."
            )
            return

        if not correo or not password or not confirmacion:
            messagebox.showwarning(
                "Datos faltantes",
                "Completa correo, contraseña y confirmación."
            )
            return

        if "@" not in correo or " " in correo:
            messagebox.showwarning(
                "Correo inválido",
                "Escribe un correo electrónico válido."
            )
            return

        if len(password) < 4:
            messagebox.showwarning(
                "Contraseña inválida",
                "La contraseña debe tener al menos 4 caracteres."
            )
            return

        if password != confirmacion:
            messagebox.showwarning(
                "Contraseñas diferentes",
                "Las contraseñas no coinciden."
            )
            return

        rol = (
            "alumno"
            if rol_texto == "Alumno"
            else "admin"
        )

        # Para administradores, el primer nombre capturado en "Nombre(s)"
        # debe pertenecer a la lista autorizada de seis personas.
        nombre_autorizado = None
        if rol == "admin":
            nombre_autorizado = nombre_admin_autorizado(nombres.split()[0])
            if nombre_autorizado is None:
                messagebox.showerror(
                    "Registro de administrador no autorizado",
                    "Solo pueden registrarse como administradores estas seis personas: "
                    "Yazmin, Lizbeth, Erika, Francisco, Leonardo y Danitzia. "
                    "Escribe el nombre autorizado en el campo Nombre(s)."
                )
                return

        edad = None
        carrera = None
        municipio = self.entry_reg_municipio.get().strip()
        texto_edad = self.entry_reg_edad.get().strip()

        # Edad y municipio son obligatorios para alumno y administrador.
        if not municipio or not texto_edad:
            messagebox.showwarning(
                "Datos personales",
                "Escribe la edad y el municipio."
            )
            return

        try:
            edad = int(texto_edad)
        except ValueError:
            messagebox.showwarning(
                "Edad inválida",
                "La edad debe ser un número entero."
            )
            return

        if edad < 1 or edad > 120:
            messagebox.showwarning(
                "Edad inválida",
                "La edad debe estar entre 1 y 120."
            )
            return

        if rol == "alumno":
            carrera = self.entry_reg_carrera.get().strip()
            if not carrera:
                messagebox.showwarning(
                    "Datos del alumno",
                    "Escribe la carrera."
                )
                return

        cn = None
        cur = None

        try:
            cn = conectar_bd()
            cur = cn.cursor(buffered=True)

            # Evita que una misma identidad autorizada cree varias cuentas admin.
            if rol == "admin":
                cur.execute(
                    """
                    SELECT nombre_usuario
                    FROM usuarios
                    WHERE rol = 'admin'
                    """
                )
                for fila_admin in cur.fetchall():
                    nombre_existente = nombre_admin_autorizado(
                        fila_admin[0] if fila_admin[0] else ""
                    )
                    if nombre_existente == nombre_autorizado:
                        messagebox.showwarning(
                            "Administrador ya registrado",
                            f"Ya existe una cuenta de administrador registrada para "
                            f"{nombre_autorizado.capitalize()}. Cada una de las seis "
                            "personas autorizadas puede registrar una sola cuenta."
                        )
                        return

            cur.execute(
                """
                SELECT id_usuario
                FROM usuarios
                WHERE usuario = %s
                """,
                (correo,)
            )

            if cur.fetchone() is not None:
                messagebox.showwarning(
                    "Correo ya registrado",
                    "Ese correo ya tiene una cuenta. Utiliza otro correo."
                )
                return

            id_alumno = None

            if rol == "alumno":
                cur.execute(
                    """
                    INSERT INTO alumnos
                    (nombre, edad, carrera, municipio)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (nombre, edad, carrera, municipio)
                )

                id_alumno = cur.lastrowid

            # Compatible con la tabla usuarios de versiones anteriores:
            # algunas versiones tenían una columna "password" obligatoria.
            columnas_usuarios = obtener_columnas("usuarios")

            columnas_insertar = [
                "usuario",
                "password_hash",
                "rol",
                "id_alumno",
                "nombre_usuario"
            ]

            valores_insertar = [
                correo,
                hash_password(password),
                rol,
                id_alumno,
                nombre
            ]

            # Guardar edad y municipio del administrador en usuarios.
            if rol == "admin":
                columnas_insertar.extend(["edad", "municipio"])
                valores_insertar.extend([edad, municipio])

            if "password" in columnas_usuarios:
                columnas_insertar.append("password")
                valores_insertar.append(hash_password(password))

            nombres_sql = ", ".join(
                f"`{col}`" for col in columnas_insertar
            )

            marcadores_sql = ", ".join(
                ["%s"] * len(valores_insertar)
            )

            cur.execute(
                f"""
                INSERT INTO usuarios
                ({nombres_sql})
                VALUES ({marcadores_sql})
                """,
                tuple(valores_insertar)
            )

            cn.commit()

            messagebox.showinfo(
                "Cuenta creada",
                "La cuenta se creó correctamente.\n\n"
                "Ahora inicia sesión con el correo y la contraseña "
                "que tú elegiste."
            )

            self.mostrar_login()

        except mysql.connector.Error as e:
            if cn is not None:
                cn.rollback()

            messagebox.showerror(
                "No se pudo crear la cuenta",
                f"La información no se guardó.\n\nDetalle:\n{e}"
            )

        except Exception as e:
            if cn is not None:
                cn.rollback()

            messagebox.showerror(
                "Error",
                str(e)
            )

        finally:
            if cur is not None:
                cur.close()

            if cn is not None and cn.is_connected():
                cn.close()

    # ========================================================
    # INICIAR SESIÓN
    # ========================================================

    def iniciar_sesion(self):
        correo = self.entry_usuario.get().strip().lower()
        password = self.entry_password.get()

        if not correo or not password:
            messagebox.showwarning(
                "Datos faltantes",
                "Escribe correo y contraseña."
            )
            return

        cn = None
        cur = None

        try:
            cn = conectar_bd()
            cur = cn.cursor(dictionary=True, buffered=True)

            cur.execute(
                """
                SELECT
                    u.id_usuario,
                    u.usuario,
                    u.rol,
                    u.id_alumno,
                    u.nombre_usuario,
                    a.nombre AS nombre_alumno
                FROM usuarios u
                LEFT JOIN alumnos a
                    ON u.id_alumno = a.id_alumno
                WHERE u.usuario = %s
                  AND u.password_hash = %s
                """,
                (
                    correo,
                    hash_password(password)
                )
            )

            fila = cur.fetchone()

            if not fila:
                messagebox.showerror(
                    "Acceso denegado",
                    "El correo o la contraseña no son correctos."
                )
                return

            # Bloqueo adicional al iniciar sesión: una cuenta admin antigua o
            # no autorizada tampoco puede entrar al panel del administrador.
            if fila["rol"] == "admin":
                nombre_autorizado_login = nombre_admin_autorizado(
                    fila.get("nombre_usuario") or ""
                )
                if nombre_autorizado_login is None:
                    messagebox.showerror(
                        "Acceso de administrador denegado",
                        "Esta cuenta no pertenece a las seis personas autorizadas "
                        "para ingresar al panel del administrador."
                    )
                    return

            self.usuario_id = fila["id_usuario"]
            self.usuario = fila["usuario"]
            self.rol = fila["rol"]
            self.id_alumno = fila["id_alumno"]
            self.nombre_usuario = (
                fila["nombre_usuario"]
                or fila["nombre_alumno"]
                or fila["usuario"]
            )
            self.nombre_alumno = fila["nombre_alumno"]

            if self.rol == "admin":
                self.mostrar_admin()

            elif self.rol == "alumno":
                if self.id_alumno is None:
                    messagebox.showerror(
                        "Cuenta incompleta",
                        "La cuenta no está relacionada con un alumno."
                    )
                    return

                self.mostrar_alumno()

            else:
                messagebox.showerror(
                    "Rol inválido",
                    "La cuenta tiene un rol no reconocido."
                )

        except mysql.connector.Error as e:
            messagebox.showerror(
                "Error de conexión",
                str(e)
            )

        except Exception as e:
            messagebox.showerror(
                "Error",
                str(e)
            )

        finally:
            if cur is not None:
                cur.close()

            if cn is not None and cn.is_connected():
                cn.close()

    # ========================================================
    # PANEL ADMINISTRADOR
    # ========================================================

    def mostrar_admin(self):
        self.limpiar()

        encabezado = ttk.Frame(self.root)
        encabezado.pack(
            fill="x",
            padx=20,
            pady=15
        )

        ttk.Label(
            encabezado,
            text="PANEL DEL ADMINISTRADOR",
            font=("Segoe UI", 24, "bold"), foreground="#7B3155"
        ).pack(side="left")

        ttk.Label(
            encabezado,
            text=f"Administrador: {self.nombre_usuario}",
            font=("Arial", 12, "bold")
        ).pack(
            side="left",
            padx=25
        )

        ttk.Button(
            encabezado,
            text="Cerrar sesión",
            command=self.cerrar_sesion
        ).pack(side="right")

        self.resumen = ttk.Frame(self.root)
        self.resumen.pack(
            fill="x",
            padx=20,
            pady=5
        )

        self.lbl_alumnos = ttk.Label(
            self.resumen,
            text="Alumnos: 0",
            font=("Arial", 12, "bold")
        )
        self.lbl_alumnos.pack(
            side="left",
            padx=20
        )

        self.lbl_gastos = ttk.Label(
            self.resumen,
            text="Gastos: 0",
            font=("Arial", 12, "bold")
        )
        self.lbl_gastos.pack(
            side="left",
            padx=20
        )

        self.lbl_total = ttk.Label(
            self.resumen,
            text="Total: $0.00",
            font=("Arial", 12, "bold")
        )
        self.lbl_total.pack(
            side="left",
            padx=20
        )

        self.lbl_promedio = ttk.Label(
            self.resumen,
            text="Promedio: $0.00",
            font=("Arial", 12, "bold")
        )
        self.lbl_promedio.pack(
            side="left",
            padx=20
        )

        self.notebook_admin = ttk.Notebook(self.root)
        self.notebook_admin.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=15
        )

        self.crear_tab_gastos_admin()
        self.crear_tab_alumnos_admin()
        self.crear_tab_categorias_admin()
        self.crear_tab_estadisticas_admin()

        self.actualizar_todo_admin()

    # ========================================================
    # TAB GASTOS ADMIN
    # ========================================================

    def crear_tab_gastos_admin(self):
        tab = ttk.Frame(
            self.notebook_admin,
            padding=10
        )
        self.notebook_admin.add(
            tab,
            text="💸 GASTOS"
        )

        buscador = ttk.Frame(tab)
        buscador.pack(
            fill="x",
            pady=5
        )

        ttk.Label(
            buscador,
            text="Buscar:"
        ).pack(
            side="left",
            padx=5
        )

        self.entry_buscar_gasto = ttk.Entry(
            buscador,
            width=40
        )
        self.entry_buscar_gasto.pack(
            side="left",
            padx=5
        )

        ttk.Button(
            buscador,
            text="Buscar",
            command=self.buscar_gastos_admin
        ).pack(
            side="left",
            padx=5
        )

        ttk.Button(
            buscador,
            text="Mostrar todo",
            command=self.mostrar_todos_gastos_admin
        ).pack(
            side="left",
            padx=5
        )

        ttk.Button(
            buscador,
            text="Eliminar gasto seleccionado",
            command=self.eliminar_gasto_admin
        ).pack(
            side="right",
            padx=5
        )

        frame = ttk.Frame(tab)
        frame.pack(
            fill="both",
            expand=True,
            pady=10
        )

        columnas = (
            "id",
            "alumno",
            "carrera",
            "categoria",
            "descripcion",
            "monto",
            "fecha"
        )

        self.tabla_admin = ttk.Treeview(
            frame,
            columns=columnas,
            show="headings",
            style="GastosAdmin.Treeview"
        )

        encabezados = {
            "id": "ID",
            "alumno": "Alumno",
            "carrera": "Carrera",
            "categoria": "Categoría",
            "descripcion": "Descripción",
            "monto": "Monto",
            "fecha": "Fecha"
        }

        anchos = {
            "id": 60,
            "alumno": 180,
            "carrera": 170,
            "categoria": 150,
            "descripcion": 270,
            "monto": 110,
            "fecha": 110
        }

        for col in columnas:
            self.tabla_admin.heading(
                col,
                text=encabezados[col]
            )
            self.tabla_admin.column(
                col,
                width=anchos[col],
                anchor="center"
            )

        self.tabla_admin.pack(
            side="left",
            fill="both",
            expand=True
        )

        scroll = ttk.Scrollbar(
            frame,
            orient="vertical",
            command=self.tabla_admin.yview
        )
        scroll.pack(
            side="right",
            fill="y"
        )

        scroll_x = ttk.Scrollbar(frame, orient="horizontal", command=self.tabla_admin.xview)
        scroll_x.pack(side="bottom", fill="x")
        self.tabla_admin.configure(yscrollcommand=scroll.set, xscrollcommand=scroll_x.set)

    def cargar_datos_admin(self, texto_busqueda=""):
        """Carga todos los gastos o aplica el buscador."""
        cn = None

        try:
            cn = conectar_bd()

            query = """
                SELECT
                    g.id_gasto,
                    a.nombre,
                    a.carrera,
                    c.nombre_categoria,
                    g.descripcion,
                    g.monto,
                    g.fecha
                FROM gastos g
                INNER JOIN alumnos a
                    ON g.id_alumno = a.id_alumno
                INNER JOIN categorias c
                    ON g.id_categoria = c.id_categoria
            """

            params = ()

            texto = texto_busqueda.strip()

            if texto:
                query += """
                    WHERE
                        a.nombre LIKE %s
                        OR a.carrera LIKE %s
                        OR c.nombre_categoria LIKE %s
                        OR g.descripcion LIKE %s
                """
                patron = f"%{texto}%"
                params = (
                    patron,
                    patron,
                    patron,
                    patron
                )

            query += """
                ORDER BY
                    g.fecha DESC,
                    g.id_gasto DESC
            """

            df = leer_dataframe(
                query,
                cn,
                params
            )

            for item in self.tabla_admin.get_children():
                self.tabla_admin.delete(item)

            for _, r in df.iterrows():
                self.tabla_admin.insert(
                    "",
                    "end",
                    values=(
                        int(r["id_gasto"]),
                        r["nombre"],
                        r["carrera"],
                        r["nombre_categoria"],
                        r["descripcion"],
                        f"${float(r['monto']):,.2f}",
                        str(r["fecha"])
                    )
                )

            self.actualizar_resumen_admin(df)

        except Exception as e:
            messagebox.showerror(
                "Error al cargar gastos",
                str(e)
            )

        finally:
            if cn is not None and cn.is_connected():
                cn.close()

    def buscar_gastos_admin(self):
        texto = self.entry_buscar_gasto.get().strip()
        self.cargar_datos_admin(texto)

        if texto:
            cantidad = len(
                self.tabla_admin.get_children()
            )

            if cantidad == 0:
                messagebox.showinfo(
                    "Sin resultados",
                    "No se encontraron gastos con ese criterio."
                )

    def mostrar_todos_gastos_admin(self):
        self.entry_buscar_gasto.delete(0, "end")
        self.cargar_datos_admin()

    def actualizar_resumen_admin(self, df):
        if df.empty:
            cantidad_alumnos = 0
            cantidad_gastos = 0
            total = 0
            promedio = 0
        else:
            cantidad_alumnos = df["nombre"].nunique()
            cantidad_gastos = len(df)
            total = df["monto"].astype(float).sum()
            promedio = df["monto"].astype(float).mean()

        self.lbl_alumnos.config(
            text=f"Alumnos con gastos: {cantidad_alumnos}"
        )
        self.lbl_gastos.config(
            text=f"Gastos: {cantidad_gastos}"
        )
        self.lbl_total.config(
            text=f"Total: ${total:,.2f}"
        )
        self.lbl_promedio.config(
            text=f"Promedio: ${promedio:,.2f}"
        )

    def eliminar_gasto_admin(self):
        seleccion = self.tabla_admin.selection()

        if not seleccion:
            messagebox.showwarning(
                "Selecciona un gasto",
                "Selecciona primero un gasto de la tabla."
            )
            return

        valores = self.tabla_admin.item(
            seleccion[0],
            "values"
        )

        id_gasto = valores[0]

        if not messagebox.askyesno(
            "Confirmar",
            f"¿Deseas eliminar el gasto ID {id_gasto}?"
        ):
            return

        cn = None
        cur = None

        try:
            cn = conectar_bd()
            cur = cn.cursor(buffered=True)

            cur.execute(
                """
                DELETE FROM gastos
                WHERE id_gasto = %s
                """,
                (id_gasto,)
            )

            cn.commit()

            messagebox.showinfo(
                "Correcto",
                "El gasto fue eliminado correctamente."
            )

            self.actualizar_todo_admin()

        except Exception as e:
            if cn is not None:
                cn.rollback()

            messagebox.showerror(
                "Error",
                str(e)
            )

        finally:
            if cur is not None:
                cur.close()

            if cn is not None and cn.is_connected():
                cn.close()

    # ========================================================
    # TAB ALUMNOS ADMIN
    # ========================================================

    def crear_tab_alumnos_admin(self):
        tab = ttk.Frame(
            self.notebook_admin,
            padding=10
        )

        self.notebook_admin.add(
            tab,
            text="👥 ALUMNOS"
        )

        ttk.Label(
            tab,
            text="Alumnos registrados en la base de datos",
            font=("Arial", 15, "bold")
        ).pack(
            anchor="w",
            pady=(0, 10)
        )

        frame = ttk.Frame(tab)
        frame.pack(
            fill="both",
            expand=True
        )

        columnas = (
            "id",
            "nombre",
            "edad",
            "carrera",
            "municipio",
            "correo"
        )

        self.tabla_alumnos_admin = ttk.Treeview(
            frame,
            columns=columnas,
            show="headings"
        )

        encabezados = {
            "id": "ID",
            "nombre": "Nombre",
            "edad": "Edad",
            "carrera": "Carrera",
            "municipio": "Municipio",
            "correo": "Correo"
        }

        anchos = {
            "id": 70,
            "nombre": 230,
            "edad": 80,
            "carrera": 190,
            "municipio": 160,
            "correo": 260
        }

        for col in columnas:
            self.tabla_alumnos_admin.heading(
                col,
                text=encabezados[col]
            )
            self.tabla_alumnos_admin.column(
                col,
                width=anchos[col],
                anchor="center"
            )

        self.tabla_alumnos_admin.pack(
            side="left",
            fill="both",
            expand=True
        )

        scroll = ttk.Scrollbar(
            frame,
            orient="vertical",
            command=self.tabla_alumnos_admin.yview
        )
        scroll.pack(
            side="right",
            fill="y"
        )

        scroll_x = ttk.Scrollbar(frame, orient="horizontal", command=self.tabla_alumnos_admin.xview)
        scroll_x.pack(side="bottom", fill="x")
        self.tabla_alumnos_admin.configure(yscrollcommand=scroll.set, xscrollcommand=scroll_x.set)

        botones_crud = ttk.Frame(tab)
        botones_crud.pack(pady=8)
        ttk.Button(botones_crud, text="Crear alumno", command=self.crear_alumno_crud).pack(side="left", padx=5)
        ttk.Button(botones_crud, text="Editar alumno seleccionado", command=self.editar_alumno_crud).pack(side="left", padx=5)
        ttk.Button(botones_crud, text="Eliminar alumno seleccionado", command=self.eliminar_alumno_crud).pack(side="left", padx=5)

    def _dialogo_datos_alumno(self, titulo, datos=None):
        datos = datos or {}
        win = tk.Toplevel(self.root); win.title(titulo); win.transient(self.root); win.grab_set()
        campos = [("Apellido paterno", "paterno"), ("Apellido materno", "materno"), ("Nombre(s)", "nombres"), ("Edad", "edad"), ("Carrera", "carrera"), ("Municipio", "municipio")]
        entradas = {}
        partes = str(datos.get("nombre", "")).split()
        valores = {"paterno": partes[0] if len(partes)>0 else "", "materno": partes[1] if len(partes)>1 else "", "nombres": " ".join(partes[2:]) if len(partes)>2 else "", "edad": datos.get("edad", ""), "carrera": datos.get("carrera", ""), "municipio": datos.get("municipio", "")}
        for i,(etiqueta, clave) in enumerate(campos):
            ttk.Label(win, text=etiqueta+":").grid(row=i,column=0,sticky="w",padx=8,pady=5)
            e=ttk.Entry(win,width=32); e.grid(row=i,column=1,padx=8,pady=5); e.insert(0,str(valores[clave] or "")); entradas[clave]=e
        resultado = {"ok": False}
        def aceptar():
            if any(not entradas[k].get().strip() for k in entradas):
                messagebox.showwarning("Datos faltantes", "Completa todos los campos.", parent=win); return
            try: edad=int(entradas["edad"].get().strip())
            except ValueError:
                messagebox.showwarning("Edad inválida", "La edad debe ser un número entero.", parent=win); return
            if edad < 1 or edad > 120:
                messagebox.showwarning("Edad inválida", "La edad debe estar entre 1 y 120.", parent=win); return
            resultado.update(ok=True, nombre=" ".join(entradas[k].get().strip() for k in ("paterno","materno","nombres")), edad=edad, carrera=entradas["carrera"].get().strip(), municipio=entradas["municipio"].get().strip())
            win.destroy()
        ttk.Button(win,text="Guardar",command=aceptar).grid(row=len(campos),column=0,columnspan=2,pady=10)
        self.root.wait_window(win)
        return resultado

    def crear_alumno_crud(self):
        d=self._dialogo_datos_alumno("Crear alumno")
        if not d.get("ok"): return
        cn=None
        try:
            cn=conectar_bd(); cur=cn.cursor()
            cur.execute("INSERT INTO alumnos (nombre, edad, carrera, municipio) VALUES (%s,%s,%s,%s)",(d["nombre"],d["edad"],d["carrera"],d["municipio"]))
            cn.commit(); cur.close(); self.cargar_alumnos_admin(); self.actualizar_opciones_alumnos_estadisticas()
            messagebox.showinfo("CRUD", "Alumno creado. Para que inicie sesión, debe registrarse con su correo y contraseña.")
        except Exception as e: messagebox.showerror("Crear alumno",str(e))
        finally:
            if cn is not None and cn.is_connected(): cn.close()

    def editar_alumno_crud(self):
        sel=self.tabla_alumnos_admin.selection()
        if not sel: messagebox.showwarning("Selecciona alumno","Selecciona un alumno de la tabla."); return
        v=self.tabla_alumnos_admin.item(sel[0],"values"); d=self._dialogo_datos_alumno("Editar alumno",{"nombre":v[1],"edad":v[2],"carrera":v[3],"municipio":v[4]})
        if not d.get("ok"): return
        cn=None
        try:
            cn=conectar_bd(); cur=cn.cursor(); cur.execute("UPDATE alumnos SET nombre=%s, edad=%s, carrera=%s, municipio=%s WHERE id_alumno=%s",(d["nombre"],d["edad"],d["carrera"],d["municipio"],int(v[0]))); cur.execute("UPDATE usuarios SET nombre_usuario=%s WHERE id_alumno=%s",(d["nombre"],int(v[0]))); cn.commit(); cur.close(); self.cargar_alumnos_admin(); self.actualizar_opciones_alumnos_estadisticas(); messagebox.showinfo("CRUD","Alumno actualizado.")
        except Exception as e: messagebox.showerror("Editar alumno",str(e))
        finally:
            if cn is not None and cn.is_connected(): cn.close()

    def eliminar_alumno_crud(self):
        sel=self.tabla_alumnos_admin.selection()
        if not sel: messagebox.showwarning("Selecciona alumno","Selecciona un alumno de la tabla."); return
        v=self.tabla_alumnos_admin.item(sel[0],"values"); ident=int(v[0])
        if not messagebox.askyesno("Confirmar eliminación",f"¿Eliminar al alumno {v[1]}? Esta acción puede afectar sus gastos y ahorros."): return
        cn=None
        try:
            cn=conectar_bd(); cur=cn.cursor()
            # Se borran primero registros dependientes para evitar referencias huérfanas.
            for tabla,columna in (("ahorros","id_alumno"),("gastos","id_alumno"),("presupuestos_semanales","id_alumno"),("usuarios","id_alumno")):
                try: cur.execute(f"DELETE FROM `{tabla}` WHERE `{columna}`=%s",(ident,))
                except mysql.connector.Error: pass
            cur.execute("DELETE FROM alumnos WHERE id_alumno=%s",(ident,)); cn.commit(); cur.close(); self.cargar_alumnos_admin(); self.actualizar_opciones_alumnos_estadisticas(); messagebox.showinfo("CRUD","Alumno eliminado.")
        except Exception as e: messagebox.showerror("Eliminar alumno",str(e))
        finally:
            if cn is not None and cn.is_connected(): cn.close()

    def actualizar_lista_alumnos_admin(self):
        """Recarga la tabla de alumnos y el selector del análisis estadístico."""
        self.cargar_alumnos_admin()
        self.actualizar_opciones_alumnos_estadisticas()

    def cargar_alumnos_admin(self):
        cn = None

        try:
            cn = conectar_bd()

            df = leer_dataframe(
                """
                SELECT
                    a.id_alumno,
                    a.nombre,
                    a.edad,
                    a.carrera,
                    a.municipio,
                    COALESCE(
                        u.usuario,
                        'Sin cuenta'
                    ) AS correo
                FROM alumnos a
                LEFT JOIN usuarios u
                    ON u.id_alumno = a.id_alumno
                ORDER BY a.nombre
                """,
                cn
            )

            for item in self.tabla_alumnos_admin.get_children():
                self.tabla_alumnos_admin.delete(item)

            for _, r in df.iterrows():
                self.tabla_alumnos_admin.insert(
                    "",
                    "end",
                    values=(
                        int(r["id_alumno"]),
                        r["nombre"],
                        int(r["edad"]),
                        r["carrera"],
                        r.get("municipio", "Sin especificar"),
                        r["correo"]
                    )
                )

        except Exception as e:
            messagebox.showerror(
                "Error al cargar alumnos",
                str(e)
            )

        finally:
            if cn is not None and cn.is_connected():
                cn.close()

    # ========================================================
    # TAB CATEGORÍAS
    # ========================================================

    def crear_tab_categorias_admin(self):
        tab = ttk.Frame(
            self.notebook_admin,
            padding=10
        )

        self.notebook_admin.add(
            tab,
            text="🏷️ CATEGORÍAS"
        )

        frame = ttk.Frame(tab)
        frame.pack(
            fill="both",
            expand=True
        )

        columnas = (
            "id",
            "nombre",
            "descripcion",
            "tipo"
        )

        self.tabla_categorias_admin = ttk.Treeview(
            frame,
            columns=columnas,
            show="headings"
        )

        encabezados = {
            "id": "ID",
            "nombre": "Categoría",
            "descripcion": "Descripción",
            "tipo": "Tipo"
        }

        for col in columnas:
            self.tabla_categorias_admin.heading(
                col,
                text=encabezados[col]
            )
            self.tabla_categorias_admin.column(
                col,
                width=250
            )

        self.tabla_categorias_admin.pack(
            side="left",
            fill="both",
            expand=True
        )

        scroll = ttk.Scrollbar(
            frame,
            orient="vertical",
            command=self.tabla_categorias_admin.yview
        )
        scroll.pack(
            side="right",
            fill="y"
        )

        scroll_x = ttk.Scrollbar(frame, orient="horizontal", command=self.tabla_categorias_admin.xview)
        scroll_x.pack(side="bottom", fill="x")
        self.tabla_categorias_admin.configure(yscrollcommand=scroll.set, xscrollcommand=scroll_x.set)


    def cargar_categorias_admin(self):
        cn = None

        try:
            cn = conectar_bd()

            df = leer_dataframe(
                """
                SELECT
                    id_categoria,
                    nombre_categoria,
                    descripcion,
                    tipo_categoria
                FROM categorias
                ORDER BY nombre_categoria
                """,
                cn
            )

            for item in self.tabla_categorias_admin.get_children():
                self.tabla_categorias_admin.delete(item)

            for _, r in df.iterrows():
                self.tabla_categorias_admin.insert(
                    "",
                    "end",
                    values=(
                        int(r["id_categoria"]),
                        r["nombre_categoria"],
                        r["descripcion"] or "",
                        r["tipo_categoria"] or ""
                    )
                )

        except Exception as e:
            messagebox.showerror(
                "Error al cargar categorías",
                str(e)
            )

        finally:
            if cn is not None and cn.is_connected():
                cn.close()

    # ========================================================
    # ESTADÍSTICAS ADMIN
    # ========================================================

    def crear_tab_estadisticas_admin(self):
        tab = ttk.Frame(
            self.notebook_admin,
            padding=20
        )

        self.notebook_admin.add(
            tab,
            text="📊 ESTADÍSTICAS"
        )

        zona_scroll, contenido = self.crear_area_desplazable(tab)
        zona_scroll.pack(fill="both", expand=True)
        tab = contenido

        self.lbl_titulo_estadisticas = ttk.Label(
            tab,
            text="ANÁLISIS GENERAL DE LOS GASTOS",
            font=("Segoe UI", 22, "bold"), foreground="#A64D59"
        )
        self.lbl_titulo_estadisticas.pack(pady=15)

        selector = ttk.Frame(tab)
        selector.pack(fill="x", pady=5)
        ttk.Label(selector, text="ESTADÍSTICAS DE:", font=("Segoe UI", 16, "bold")).pack(side="left", padx=5)
        self.combo_est_alumno = ttk.Combobox(selector, state="readonly", width=35, values=["General"], font=("Segoe UI", 12))
        self.combo_est_alumno.pack(side="left", padx=5)
        self.combo_est_alumno.current(0)
        ttk.Button(selector, text="Aplicar", command=self.aplicar_filtro_estadisticas).pack(side="left", padx=5)
        self.combo_est_alumno.bind("<<ComboboxSelected>>", lambda _e: self._ajustar_botones_estadisticas())

        self.lbl_est_total = ttk.Label(
            tab,
            text="Total: $0.00",
            font=("Arial", 16, "bold")
        )
        self.lbl_est_total.pack(anchor="w", pady=5)

        self.lbl_est_promedio = ttk.Label(
            tab,
            text="Promedio: $0.00",
            font=("Arial", 16, "bold")
        )
        self.lbl_est_promedio.pack(anchor="w", pady=5)

        self.lbl_est_mediana = ttk.Label(tab, text="Mediana: $0.00", font=("Arial", 16, "bold"))
        self.lbl_est_mediana.pack(anchor="w", pady=5)

        self.lbl_est_moda = ttk.Label(tab, text="Moda: Sin datos", font=("Arial", 16, "bold"))
        self.lbl_est_moda.pack(anchor="w", pady=5)

        self.lbl_est_minimo = ttk.Label(
            tab,
            text="Mínimo: $0.00",
            font=("Arial", 16, "bold")
        )
        self.lbl_est_minimo.pack(anchor="w", pady=5)

        self.lbl_est_maximo = ttk.Label(
            tab,
            text="Máximo: $0.00",
            font=("Arial", 16, "bold")
        )
        self.lbl_est_maximo.pack(anchor="w", pady=5)

        self.lbl_est_rango = ttk.Label(
            tab,
            text="Rango: $0.00",
            font=("Arial", 16, "bold")
        )
        self.lbl_est_rango.pack(anchor="w", pady=5)

        self.lbl_est_varianza = ttk.Label(
            tab,
            text="Varianza: 0.00",
            font=("Arial", 16, "bold")
        )
        self.lbl_est_varianza.pack(anchor="w", pady=5)

        self.lbl_est_desviacion = ttk.Label(
            tab,
            text="Desviación estándar: 0.00",
            font=("Arial", 16, "bold")
        )
        self.lbl_est_desviacion.pack(anchor="w", pady=5)

        ttk.Label(tab, text=(
            "¿QUÉ SIGNIFICA CADA MEDIDA?  Total: suma de todos los gastos registrados. "
            "Promedio: gasto medio por registro. Mediana: valor central de los gastos ordenados. "
            "Moda: monto(s) que más se repiten. Mínimo y máximo: menor y mayor gasto individual. "
            "Rango: diferencia entre el gasto máximo y el mínimo. Varianza: promedio de las "
            "diferencias al cuadrado respecto al promedio (en pesos cuadrados). Desviación estándar: "
            "dispersión típica respecto al promedio, expresada en pesos. Se calculan sobre los montos "
            "de gastos del alumno seleccionado o de todos los alumnos si eliges General."
        ), wraplength=1050, justify="left", font=("Segoe UI", 13)).pack(anchor="w", padx=5, pady=10)

        botones = ttk.Frame(tab)
        botones.pack(pady=20)

        self.botones_estadisticas = botones
        self.btn_grafica_categoria_est = ttk.Button(
            botones, text="Gráfica por categoría", command=self.grafica_categorias
        )
        self.btn_grafica_categoria_est.pack(side="left", padx=5)
        self.btn_grafica_carrera_est = ttk.Button(
            botones, text="Gráfica por carrera", command=self.grafica_carreras
        )
        self.btn_grafica_carrera_est.pack(side="left", padx=5)
        self.btn_agrupar_tabla_est = ttk.Button(
            botones, text="Agrupar alumnos: tabla", command=self.agrupar_alumnos
        )
        self.btn_agrupar_tabla_est.pack(side="left", padx=5)
        self.btn_agrupar_grafica_est = ttk.Button(
            botones, text="Agrupar alumnos: gráfica", command=self.grafica_agrupacion_alumnos
        )
        self.btn_agrupar_grafica_est.pack(side="left", padx=5)
        self.btn_regresion_est = ttk.Button(
            botones, text="Regresión: estimar siguiente semana", command=self.ejecutar_regresion
        )
        self.btn_regresion_est.pack(side="left", padx=5)
        self.btn_tendencia_alumno_est = ttk.Button(
            botones, text="Gráfica: tendencia central", command=self.grafica_tendencia_central_alumno
        )
        self.btn_dispersion_alumno_est = ttk.Button(
            botones, text="Gráfica: medidas de dispersión", command=self.grafica_dispersion_alumno
        )
        self._ajustar_botones_estadisticas()

    def _ajustar_botones_estadisticas(self):
        """En General muestra todos los análisis; por alumno deja categoría y resumen estadístico."""
        if not hasattr(self, "combo_est_alumno"):
            return
        general = self.combo_est_alumno.get() in ("", "General")
        for boton in (self.btn_grafica_carrera_est, self.btn_agrupar_tabla_est,
                      self.btn_agrupar_grafica_est, self.btn_regresion_est):
            boton.pack_forget()
        self.btn_tendencia_alumno_est.pack_forget()
        self.btn_dispersion_alumno_est.pack_forget()
        if general:
            self.btn_grafica_carrera_est.pack(side="left", padx=5)
            self.btn_agrupar_tabla_est.pack(side="left", padx=5)
            self.btn_agrupar_grafica_est.pack(side="left", padx=5)
            self.btn_regresion_est.pack(side="left", padx=5)
        else:
            self.btn_tendencia_alumno_est.pack(side="left", padx=5)
            self.btn_dispersion_alumno_est.pack(side="left", padx=5)

    def aplicar_filtro_estadisticas(self):
        self._ajustar_botones_estadisticas()
        self.actualizar_estadisticas()

    def _obtener_gastos_alumno_estadisticas(self):
        """Obtiene los montos del alumno seleccionado para sus gráficas estadísticas."""
        seleccionado = self.combo_est_alumno.get()
        if not seleccionado or seleccionado == "General":
            messagebox.showinfo("Selecciona un alumno", "Elige un alumno para ver sus estadísticas individuales.")
            return None, None
        cn = None
        try:
            id_sel = int(seleccionado.split(" | ", 1)[0])
            cn = conectar_bd()
            df = leer_dataframe(
                "SELECT monto FROM gastos WHERE id_alumno = %s AND monto IS NOT NULL ORDER BY fecha",
                cn, (id_sel,)
            )
            serie = pd.to_numeric(df.get("monto", pd.Series(dtype=float)), errors="coerce").dropna()
            if serie.empty:
                messagebox.showinfo("Sin datos", "Este alumno todavía no tiene gastos registrados.")
                return None, None
            return serie, seleccionado.split(" | ", 1)[1]
        except Exception as e:
            messagebox.showerror("Error estadístico", f"No se pudieron consultar los gastos.\n\n{e}")
            return None, None
        finally:
            if cn is not None and cn.is_connected():
                cn.close()

    def _mostrar_grafica_medidas_alumno(self, titulo, nombres, valores, unidades, color_titulo):
        """Muestra una gráfica independiente y legible de medidas estadísticas."""
        win = tk.Toplevel(self.root)
        win.title(titulo)
        win.geometry("800x500")
        win.transient(self.root)
        cont = ttk.Frame(win, padding=14)
        cont.pack(fill="both", expand=True)
        ttk.Label(cont, text=titulo, font=("Arial", 16, "bold")).pack(pady=(0, 5))
        ttk.Label(cont, text=f"Alumno: {self.combo_est_alumno.get().split(' | ', 1)[-1]}",
                  font=("Arial", 11)).pack(pady=(0, 8))
        fig, ax = plt.subplots(figsize=(7.0, 4.0), facecolor="#FFF4E8")
        ax.set_facecolor("#FFFCF8")
        posiciones = list(range(len(nombres)))
        paleta_calida = ["#E87932", "#D95D8A", "#E9A23B", "#A64D79", "#F28C68"]
        barras = ax.bar(posiciones, valores, color=paleta_calida[:len(valores)])
        ax.set_xticks(posiciones)
        ax.set_xticklabels(nombres, rotation=12, ha="right", fontsize=9)
        ax.set_ylabel("Valor ($)" if unidades == "pesos" else "Valor (pesos²)")
        ax.set_title(titulo, fontsize=12)
        ax.tick_params(axis="y", labelsize=9)
        ax.grid(axis="y", alpha=0.25)
        ax.bar_label(barras, labels=[f"${v:,.2f}" if unidades == "pesos" else f"{v:,.2f}" for v in valores], padding=3, fontsize=9)
        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=cont)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        def cerrar():
            plt.close(fig)
            win.destroy()
        ttk.Button(cont, text="Cerrar gráfica", command=cerrar).pack(pady=(8, 0))
        win.protocol("WM_DELETE_WINDOW", cerrar)

    def grafica_tendencia_central_alumno(self):
        """Grafica por separado promedio, mediana, moda, mínimo y máximo."""
        serie, nombre = self._obtener_gastos_alumno_estadisticas()
        if serie is None:
            return
        moda = serie.mode()
        nombres = ["Promedio", "Mediana", "Moda", "Mínimo", "Máximo"]
        valores = [float(serie.mean()), float(serie.median()),
                   float(moda.iloc[0]) if not moda.empty else 0.0,
                   float(serie.min()), float(serie.max())]
        self._mostrar_grafica_medidas_alumno(
            "Medidas de tendencia central y extremos", nombres, valores, "pesos", "#D95D8A"
        )

    def grafica_dispersion_alumno(self):
        """Muestra rango, desviación estándar y varianza juntos en una gráfica."""
        serie, nombre = self._obtener_gastos_alumno_estadisticas()
        if serie is None:
            return

        rango = float(serie.max() - serie.min())
        desviacion = float(serie.std(ddof=0))
        varianza = float(serie.var(ddof=0))

        win = tk.Toplevel(self.root)
        win.title("Medidas de dispersión del alumno")
        win.geometry("820x520")
        win.minsize(680, 440)
        win.transient(self.root)

        cont = ttk.Frame(win, padding=12)
        cont.pack(fill="both", expand=True)
        ttk.Label(
            cont,
            text="Medidas de dispersión",
            font=("Arial", 14, "bold")
        ).pack(pady=(0, 3))
        ttk.Label(
            cont,
            text=f"Alumno: {nombre}",
            font=("Arial", 10)
        ).pack(pady=(0, 6))

        fig, ax = plt.subplots(figsize=(7.0, 4.0), facecolor="#FFF4E8")
        ax.set_facecolor("#FFFCF8")
        nombres = ["Rango", "Desviación estándar", "Varianza"]
        valores = [rango, desviacion, varianza]
        barras = ax.bar(nombres, valores, color=["#E87932", "#D95D8A", "#E9A23B"])
        ax.set_title("Rango, desviación estándar y varianza", fontsize=12, pad=10)
        ax.set_ylabel("Valor numérico")
        ax.tick_params(axis="x", labelsize=9)
        ax.tick_params(axis="y", labelsize=9)
        ax.grid(axis="y", alpha=0.25)
        ax.bar_label(
            barras,
            labels=[f"${v:,.2f}" for v in valores],
            padding=3,
            fontsize=9
        )
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=cont)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

        def cerrar():
            plt.close(fig)
            win.destroy()

        ttk.Button(cont, text="Cerrar gráfica", command=cerrar).pack(pady=(6, 0))
        win.protocol("WM_DELETE_WINDOW", cerrar)

    def actualizar_opciones_alumnos_estadisticas(self):
        if not hasattr(self, "combo_est_alumno"):
            return
        cn = None
        try:
            cn = conectar_bd()
            df = leer_dataframe("SELECT id_alumno, nombre FROM alumnos ORDER BY nombre", cn)
            opciones = ["General"] + [f"{int(r.id_alumno)} | {r.nombre}" for r in df.itertuples()]
            actual = self.combo_est_alumno.get()
            self.combo_est_alumno["values"] = opciones
            self.combo_est_alumno.set(actual if actual in opciones else "General")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar la lista de alumnos: {e}")
        finally:
            if cn is not None and cn.is_connected():
                cn.close()

    def _filtro_alumno_estadisticas(self, alias="g"):
        """Devuelve filtro SQL y parámetros según General o el alumno elegido."""
        seleccionado = self.combo_est_alumno.get() if hasattr(self, "combo_est_alumno") else "General"
        if seleccionado and seleccionado != "General":
            return f"WHERE {alias}.id_alumno = %s", (int(seleccionado.split(" | ", 1)[0]),)
        return "", ()

    def agrupar_alumnos(self):
        """Clasificación interpretable según el gasto acumulado de cada alumno."""
        cn = None
        try:
            cn = conectar_bd()
            seleccionado = self.combo_est_alumno.get() if hasattr(self, "combo_est_alumno") else "General"
            filtro = "WHERE a.id_alumno = %s" if seleccionado and seleccionado != "General" else ""
            params = (int(seleccionado.split(" | ", 1)[0]),) if filtro else ()
            df = leer_dataframe(f"""
                SELECT a.id_alumno, a.nombre, COALESCE(SUM(g.monto),0) AS total_gastado
                FROM alumnos a LEFT JOIN gastos g ON g.id_alumno=a.id_alumno
                {filtro}
                GROUP BY a.id_alumno, a.nombre ORDER BY total_gastado
            """, cn, params)
            if df.empty:
                messagebox.showinfo("Agrupación", "No hay alumnos registrados.")
                return
            if KMeans is None:
                messagebox.showerror("Falta dependencia", "Instala scikit-learn: pip install scikit-learn")
                return
            # K-means real sobre gasto acumulado; los grupos se renombran por centroide:
            # 1 = bajo, 2 = medio, 3 = alto. Con menos de 3 alumnos se usan menos grupos.
            k = min(3, len(df))
            modelo = KMeans(n_clusters=k, random_state=42, n_init=10)
            etiquetas = modelo.fit_predict(df[["total_gastado"]].astype(float))
            orden = sorted(range(k), key=lambda i: float(modelo.cluster_centers_[i][0]))
            equivalencia = {etiqueta: posicion + 1 for posicion, etiqueta in enumerate(orden)}
            df["grupo"] = [equivalencia[e] for e in etiquetas]
            ventana = tk.Toplevel(self.root)
            ventana.title("Agrupación de alumnos por gasto")
            ventana.geometry("850x560")
            ventana.minsize(700, 450)
            marco_principal = ttk.Frame(ventana, padding=8)
            marco_principal.pack(fill="both", expand=True)
            ttk.Label(marco_principal, text="Tabla de valores de agrupación", font=("Arial", 11, "bold")).pack(padx=10, pady=(8, 2))
            marco_valores = ttk.Frame(marco_principal)
            marco_valores.pack(fill="x", padx=10, pady=(0, 8))
            tabla_valores = ttk.Treeview(marco_valores, columns=("valor", "significado"), show="headings", height=3)
            tabla_valores.heading("valor", text="Valor")
            tabla_valores.heading("significado", text="Significado")
            tabla_valores.column("valor", width=80, anchor="center")
            tabla_valores.column("significado", width=560, anchor="w")
            for valor, significado in [(1, "Gasto acumulado menor; alumnos cercanos al centroide más bajo"), (2, "Gasto acumulado intermedio; alumnos cercanos al centroide medio"), (3, "Gasto acumulado mayor; alumnos cercanos al centroide más alto")]:
                tabla_valores.insert("", "end", values=(valor, significado))
            tabla_valores.pack(side="left", fill="x", expand=True)
            scroll_valores_y = ttk.Scrollbar(marco_valores, orient="vertical", command=tabla_valores.yview)
            scroll_valores_y.pack(side="right", fill="y")
            tabla_valores.configure(yscrollcommand=scroll_valores_y.set)
            ttk.Label(marco_principal, text="K-means agrupa por similitud del gasto acumulado. Bajo/medio/alto se determina comparando los centroides calculados en estos datos; si hay menos de 3 alumnos, se forman menos grupos.", wraplength=1100).pack(padx=10, pady=2, anchor="w")
            marco_tabla = ttk.Frame(marco_principal)
            marco_tabla.pack(fill="both", expand=True, padx=10, pady=10)
            tabla = ttk.Treeview(marco_tabla, columns=("id", "nombre", "total", "grupo"), show="headings")
            for col, label, width in [("id","ID",70),("nombre","Alumno",300),("total","Gasto acumulado",160),("grupo","Grupo",100)]:
                tabla.heading(col, text=label); tabla.column(col, width=width, anchor="center")
            tabla.pack(side="left", fill="both", expand=True)
            tabla_scroll_y = ttk.Scrollbar(marco_tabla, orient="vertical", command=tabla.yview)
            tabla_scroll_y.pack(side="right", fill="y")
            tabla_scroll_x = ttk.Scrollbar(marco_principal, orient="horizontal", command=tabla.xview)
            tabla_scroll_x.pack(fill="x", padx=10)
            tabla.configure(yscrollcommand=tabla_scroll_y.set, xscrollcommand=tabla_scroll_x.set)
            for r in df.itertuples():
                tabla.insert("", "end", values=(r.id_alumno, r.nombre, f"${float(r.total_gastado):,.2f}", int(r.grupo)))
        except Exception as e:
            messagebox.showerror("Error de agrupación", str(e))
        finally:
            if cn is not None and cn.is_connected(): cn.close()

    def grafica_agrupacion_alumnos(self):
        """Muestra en una gráfica los grupos 1, 2 y 3 calculados con la misma técnica."""
        cn = None
        try:
            cn = conectar_bd()
            seleccionado = self.combo_est_alumno.get() if hasattr(self, "combo_est_alumno") else "General"
            filtro = "WHERE a.id_alumno = %s" if seleccionado and seleccionado != "General" else ""
            params = (int(seleccionado.split(" | ", 1)[0]),) if filtro else ()
            df = leer_dataframe(f"""
                SELECT a.id_alumno, a.nombre, COALESCE(SUM(g.monto),0) AS total_gastado
                FROM alumnos a LEFT JOIN gastos g ON g.id_alumno=a.id_alumno
                {filtro}
                GROUP BY a.id_alumno, a.nombre ORDER BY total_gastado
            """, cn, params)
            if df.empty:
                messagebox.showinfo("Agrupación", "No hay alumnos registrados.")
                return
            if KMeans is None:
                messagebox.showerror("Falta dependencia", "Instala scikit-learn: pip install scikit-learn")
                return
            k = min(3, len(df))
            modelo = KMeans(n_clusters=k, random_state=42, n_init=10)
            etiquetas = modelo.fit_predict(df[["total_gastado"]].astype(float))
            orden = sorted(range(k), key=lambda i: float(modelo.cluster_centers_[i][0]))
            equivalencia = {etiqueta: posicion + 1 for posicion, etiqueta in enumerate(orden)}
            df["grupo"] = [equivalencia[e] for e in etiquetas]
            # Gráfica de dispersión: cada punto representa un alumno; X es su gasto
            # acumulado y Y identifica el grupo K-means. Los centroides se señalan aparte.
            fig, ax = plt.subplots(figsize=(7.5, 4.8), facecolor="#FFF4E8")
            ax.set_facecolor("#FFFCF8")
            for grupo in sorted(df["grupo"].unique()):
                datos = df[df["grupo"] == grupo]
                ax.scatter(datos["total_gastado"], [grupo] * len(datos), s=65, alpha=0.8,
                           label={1: "Grupo 1: gasto bajo", 2: "Grupo 2: gasto medio", 3: "Grupo 3: gasto alto"}[int(grupo)])
            centros_ordenados = [float(modelo.cluster_centers_[i][0]) for i in orden]
            for grupo, centro in enumerate(centros_ordenados, start=1):
                ax.scatter([centro], [grupo], marker="X", s=180, edgecolors="black", linewidths=1.2)
            ax.set_title("K-means: agrupación de alumnos por gasto acumulado")
            ax.set_xlabel("Gasto acumulado por alumno ($)")
            ax.set_ylabel("Grupo asignado por K-means")
            ax.set_yticks([1, 2, 3], ["Bajo (1)", "Medio (2)", "Alto (3)"])
            ax.grid(True, axis="x", alpha=0.25)
            ax.legend(loc="best", fontsize=8)
            fig.tight_layout()
            ventana = tk.Toplevel(self.root)
            ventana.title("Gráfica de agrupación de alumnos")
            ventana.geometry("820x540")
            ventana.minsize(680, 440)
            marco_scroll = ttk.Frame(ventana)
            marco_scroll.pack(fill="both", expand=True)
            lienzo = tk.Canvas(marco_scroll, highlightthickness=0)
            barra_vertical = ttk.Scrollbar(marco_scroll, orient="vertical", command=lienzo.yview)
            lienzo.configure(yscrollcommand=barra_vertical.set)
            lienzo.pack(side="left", fill="both", expand=True)
            barra_vertical.pack(side="right", fill="y")
            contenido = ttk.Frame(lienzo)
            id_contenido = lienzo.create_window((0, 0), window=contenido, anchor="nw")
            contenido.bind("<Configure>", lambda e: lienzo.configure(scrollregion=lienzo.bbox("all")))
            lienzo.bind("<Configure>", lambda e: lienzo.itemconfigure(id_contenido, width=e.width))
            canvas = FigureCanvasTkAgg(fig, master=contenido)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)
            plt.close(fig)
        except Exception as e:
            messagebox.showerror("Error de agrupación", str(e))
        finally:
            if cn is not None and cn.is_connected(): cn.close()

    def ejecutar_regresion(self):
        if LinearRegression is None:
            messagebox.showerror("Falta dependencia", "Para la regresión instala scikit-learn: pip install scikit-learn")
            return
        cn = None
        try:
            cn = conectar_bd()
            seleccionado = self.combo_est_alumno.get() if hasattr(self, "combo_est_alumno") else "General"
            filtro = ""; params = ()
            if seleccionado and seleccionado != "General":
                filtro = "WHERE id_alumno = %s"; params = (int(seleccionado.split(" | ",1)[0]),)
            df = leer_dataframe(f"""
                SELECT YEARWEEK(fecha, 3) AS semana, SUM(monto) AS total
                FROM gastos {filtro} GROUP BY YEARWEEK(fecha, 3) ORDER BY semana
            """, cn, params)
            if len(df) < 2:
                messagebox.showinfo("Datos insuficientes", "La regresión requiere gastos registrados en al menos dos semanas distintas.")
                return
            X = list(range(len(df)))
            modelo = LinearRegression().fit([[x] for x in X], df["total"].astype(float).tolist())
            pred = max(0.0, float(modelo.predict([[len(df)]])[0]))
            messagebox.showinfo("Regresión lineal", f"Estimación para la siguiente semana: ${pred:,.2f}\n\nModelo entrenado con {len(df)} semanas de datos históricos. Es una estimación, no una garantía.")
        except Exception as e:
            messagebox.showerror("Error de regresión", str(e))
        finally:
            if cn is not None and cn.is_connected(): cn.close()

    def actualizar_estadisticas(self):
        """Actualiza las estadísticas generales del administrador."""
        cn = None

        try:
            cn = conectar_bd()

            seleccionado = self.combo_est_alumno.get() if hasattr(self, "combo_est_alumno") else "General"
            if hasattr(self, "lbl_titulo_estadisticas"):
                self.lbl_titulo_estadisticas.config(
                    text=("ANÁLISIS GENERAL DE LOS GASTOS" if not seleccionado or seleccionado == "General"
                          else f"ANÁLISIS DE GASTOS: {seleccionado.split(' | ', 1)[1]}")
                )
            if seleccionado and seleccionado != "General":
                id_sel = int(seleccionado.split(" | ", 1)[0])
                df = leer_dataframe(
                    "SELECT monto FROM gastos WHERE monto IS NOT NULL AND id_alumno = %s", cn, (id_sel,)
                )
            else:
                df = leer_dataframe("SELECT monto FROM gastos WHERE monto IS NOT NULL", cn)

            if df.empty:
                total = promedio = minimo = maximo = mediana = 0.0
                moda_texto = "Sin datos"
                rango = varianza = desviacion = 0.0
            else:
                serie = pd.to_numeric(
                    df["monto"],
                    errors="coerce"
                ).dropna()

                if serie.empty:
                    total = promedio = minimo = maximo = mediana = 0.0
                    moda_texto = "Sin datos"
                    rango = varianza = desviacion = 0.0
                else:
                    total = float(serie.sum())
                    promedio = float(serie.mean())
                    mediana = float(serie.median())
                    modas = serie.mode()
                    moda_texto = ", ".join(f"${float(v):,.2f}" for v in modas.tolist()) if not modas.empty else "Sin moda"
                    minimo = float(serie.min())
                    maximo = float(serie.max())
                    rango = maximo - minimo
                    varianza = float(serie.var(ddof=0))
                    desviacion = float(serie.std(ddof=0))

            self.lbl_est_total.config(
                text=f"Total: ${total:,.2f}"
            )
            self.lbl_est_promedio.config(
                text=f"Promedio: ${promedio:,.2f}"
            )
            self.lbl_est_mediana.config(text=f"Mediana: ${mediana:,.2f}")
            self.lbl_est_moda.config(text=f"Moda: {moda_texto}")
            self.lbl_est_minimo.config(
                text=f"Mínimo: ${minimo:,.2f}"
            )
            self.lbl_est_maximo.config(
                text=f"Máximo: ${maximo:,.2f}"
            )
            self.lbl_est_rango.config(
                text=f"Rango: ${rango:,.2f}"
            )
            self.lbl_est_varianza.config(
                text=f"Varianza: {varianza:,.2f}"
            )
            self.lbl_est_desviacion.config(
                text=f"Desviación estándar: {desviacion:,.2f}"
            )

        except Exception as e:
            messagebox.showerror(
                "Error al actualizar estadísticas",
                f"No se pudieron actualizar las estadísticas.\n\n{e}"
            )

        finally:
            if cn is not None and cn.is_connected():
                cn.close()

    def _mostrar_grafica_admin(self, titulo, etiquetas, valores,
                               etiqueta_x):
        """Muestra una gráfica dentro de una ventana de Tkinter.

        Se evita plt.show() para que las gráficas funcionen correctamente
        aunque Spyder esté configurado para mostrar las figuras en su panel
        de Plots.
        """
        ventana = tk.Toplevel(self.root)
        ventana.title(titulo)
        ventana.geometry("820x540")
        ventana.minsize(680, 440)
        ventana.transient(self.root)

        marco = ttk.Frame(ventana, padding=10)
        marco.pack(fill="both", expand=True)
        marco_scroll = ttk.Frame(marco)
        marco_scroll.pack(fill="both", expand=True)
        lienzo = tk.Canvas(marco_scroll, highlightthickness=0)
        barra_vertical = ttk.Scrollbar(marco_scroll, orient="vertical", command=lienzo.yview)
        lienzo.configure(yscrollcommand=barra_vertical.set)
        lienzo.pack(side="left", fill="both", expand=True)
        barra_vertical.pack(side="right", fill="y")
        contenido = ttk.Frame(lienzo)
        id_contenido = lienzo.create_window((0, 0), window=contenido, anchor="nw")
        contenido.bind("<Configure>", lambda e: lienzo.configure(scrollregion=lienzo.bbox("all")))
        lienzo.bind("<Configure>", lambda e: lienzo.itemconfigure(id_contenido, width=e.width))

        fig, ax = plt.subplots(figsize=(7.5, 4.8), facecolor="#FFF4E8")
        ax.set_facecolor("#FFFCF8")

        posiciones = list(range(len(etiquetas)))
        paleta_graficas = {
            "Gastos por categoría": ["#E87932", "#D95D8A", "#E9A23B", "#A64D79", "#F28C68", "#B86B35"],
            "Gastos por carrera": ["#D95D8A", "#E87932", "#A64D79", "#E9A23B", "#F28C68", "#B86B35"],
        }
        colores_barras = paleta_graficas.get(
            titulo, ["#E87932", "#D95D8A", "#E9A23B", "#A64D79", "#F28C68"]
        )
        ax.bar(
            posiciones,
            [float(v) for v in valores],
            color=[colores_barras[i % len(colores_barras)] for i in posiciones]
        )
        ax.set_title(titulo, fontsize=16, fontweight="bold")
        ax.set_xlabel(etiqueta_x)
        ax.set_ylabel("Monto ($)")
        ax.set_xticks(posiciones)
        ax.set_xticklabels(
            [str(x) for x in etiquetas],
            rotation=30,
            ha="right"
        )
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=contenido)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

        ttk.Button(
            marco,
            text="Cerrar gráfica",
            command=ventana.destroy
        ).pack(pady=(8, 0))

        def cerrar_grafica():
            plt.close(fig)
            ventana.destroy()

        ventana.protocol("WM_DELETE_WINDOW", cerrar_grafica)

    def grafica_categorias(self):
        """Genera una gráfica con el gasto total por categoría."""
        cn = None

        try:
            cn = conectar_bd()

            filtro, params = self._filtro_alumno_estadisticas("g")
            df = leer_dataframe(
                f"""
                SELECT c.nombre_categoria AS categoria, SUM(g.monto) AS total
                FROM gastos g
                INNER JOIN categorias c ON g.id_categoria = c.id_categoria
                {filtro}
                GROUP BY c.nombre_categoria
                ORDER BY total DESC
                """,
                cn, params
            )

            if df.empty:
                messagebox.showinfo(
                    "Sin datos",
                    "No hay gastos registrados para generar la gráfica por categoría."
                )
                return

            self._mostrar_grafica_admin(
                "Gastos por categoría",
                df["categoria"].tolist(),
                df["total"].tolist(),
                "Categoría"
            )

        except Exception as e:
            messagebox.showerror(
                "Error en gráfica por categoría",
                f"No se pudo generar la gráfica.\n\n{e}"
            )

        finally:
            if cn is not None and cn.is_connected():
                cn.close()

    def grafica_carreras(self):
        """Genera una gráfica con el gasto total por carrera."""
        cn = None

        try:
            cn = conectar_bd()

            filtro, params = self._filtro_alumno_estadisticas("g")
            df = leer_dataframe(
                f"""
                SELECT a.carrera AS carrera, SUM(g.monto) AS total
                FROM gastos g
                INNER JOIN alumnos a ON g.id_alumno = a.id_alumno
                {filtro}
                GROUP BY a.carrera
                ORDER BY total DESC
                """,
                cn, params
            )

            if df.empty:
                messagebox.showinfo(
                    "Sin datos",
                    "No hay gastos registrados para generar la gráfica por carrera."
                )
                return

            self._mostrar_grafica_admin(
                "Gastos por carrera",
                df["carrera"].tolist(),
                df["total"].tolist(),
                "Carrera"
            )

        except Exception as e:
            messagebox.showerror(
                "Error en gráfica por carrera",
                f"No se pudo generar la gráfica.\n\n{e}"
            )

        finally:
            if cn is not None and cn.is_connected():
                cn.close()

    def actualizar_todo_admin(self):
        self.cargar_datos_admin()
        self.cargar_alumnos_admin()
        self.cargar_categorias_admin()
        self.actualizar_opciones_alumnos_estadisticas()
        self.actualizar_estadisticas()

    # ========================================================
    # PANEL ALUMNO
    # ========================================================

    def mostrar_alumno(self):
        self.limpiar()

        zona_scroll, contenido = self.crear_area_desplazable(self.root)
        zona_scroll.pack(fill="both", expand=True)

        encabezado = ttk.Frame(contenido)
        encabezado.pack(
            fill="x",
            padx=20,
            pady=15
        )

        ttk.Label(
            encabezado,
            text="MI CONTROL DE GASTOS",
            font=("Segoe UI", 24, "bold"),
            foreground="#2457A7"
        ).pack(side="left")

        ttk.Label(
            encabezado,
            text=f"ALUMNO: {self.nombre_alumno}",
            font=("Segoe UI", 16, "bold"),
            foreground="#C64F78"
        ).pack(
            side="left",
            padx=25
        )

        ttk.Button(
            encabezado,
            text="Cerrar sesión",
            command=self.cerrar_sesion
        ).pack(side="right")

        # ----------------------------------------------------
        # INFORMACIÓN PERSONAL
        # ----------------------------------------------------
        info = ttk.LabelFrame(
            contenido,
            text="MI INFORMACIÓN",
            padding=10
        )
        info.pack(
            fill="x",
            padx=20,
            pady=5
        )

        self.lbl_info_nombre = ttk.Label(info, font=("Segoe UI", 13, "bold"))
        self.lbl_info_nombre.pack(
            side="left",
            padx=15
        )

        self.lbl_info_edad = ttk.Label(info, font=("Segoe UI", 13, "bold"))
        self.lbl_info_edad.pack(
            side="left",
            padx=15
        )

        self.lbl_info_carrera = ttk.Label(info, font=("Segoe UI", 13, "bold"))
        self.lbl_info_carrera.pack(side="left", padx=15)
        self.lbl_info_municipio = ttk.Label(info, font=("Segoe UI", 13, "bold"))
        self.lbl_info_municipio.pack(side="left", padx=15)

        self.cargar_info_alumno()

        # ----------------------------------------------------
        # PRESUPUESTO
        # ----------------------------------------------------
        panel = ttk.LabelFrame(
            contenido,
            text="PRESUPUESTO SEMANAL",
            padding=15
        )
        panel.pack(
            fill="x",
            padx=20,
            pady=10
        )

        ttk.Label(
            panel,
            text="Presupuesto inicial:", font=("Segoe UI", 12, "bold")
        ).grid(
            row=0,
            column=0,
            padx=5,
            pady=5
        )

        self.entry_presupuesto = ttk.Entry(
            panel,
            width=18
        )
        self.entry_presupuesto.grid(
            row=0,
            column=1,
            padx=5,
            pady=5
        )

        ttk.Button(
            panel,
            text="Guardar presupuesto",
            command=self.guardar_presupuesto
        ).grid(
            row=0,
            column=2,
            padx=10,
            pady=5
        )

        self.lbl_presupuesto = ttk.Label(
            panel,
            text="Inicial: $0.00",
            font=("Arial", 14, "bold")
        )
        self.lbl_presupuesto.grid(
            row=1,
            column=0,
            padx=15,
            pady=8
        )

        self.lbl_gastado = ttk.Label(
            panel,
            text="Gastado: $0.00",
            font=("Arial", 14, "bold")
        )
        self.lbl_gastado.grid(
            row=1,
            column=1,
            padx=15,
            pady=8
        )

        self.lbl_disponible = ttk.Label(
            panel,
            text="Disponible: $0.00",
            font=("Arial", 14, "bold")
        )
        self.lbl_disponible.grid(
            row=1,
            column=2,
            padx=15,
            pady=8
        )

        self.lbl_porcentaje = ttk.Label(
            panel,
            text="Restante: 0%",
            font=("Arial", 14, "bold")
        )
        self.lbl_porcentaje.grid(
            row=1,
            column=3,
            padx=15,
            pady=8
        )

        self.barra_progreso = ttk.Progressbar(
            panel,
            length=650,
            maximum=100,
            style="Presupuesto.Horizontal.TProgressbar"
        )
        self.barra_progreso.grid(
            row=2,
            column=0,
            columnspan=4,
            padx=10,
            pady=10
        )

        self.lbl_alerta = ttk.Label(
            panel,
            text="Primero establece tu presupuesto semanal.",
            style="AlertaPresupuesto.TLabel"
        )
        self.lbl_alerta.grid(
            row=3,
            column=0,
            columnspan=4,
            pady=5
        )

        # ----------------------------------------------------
        # AHORRO SEMANAL
        # ----------------------------------------------------
        ahorro = ttk.LabelFrame(contenido, text="MI AHORRO", padding=12)
        ahorro.pack(fill="x", padx=20, pady=5)
        ttk.Label(ahorro, text="Guardar ahorro ($):", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, padx=5, pady=5)
        self.entry_ahorro = ttk.Entry(ahorro, width=18)
        self.entry_ahorro.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(ahorro, text="Guardar ahorro", command=self.guardar_ahorro).grid(row=0, column=2, padx=8, pady=5)
        self.lbl_ahorro_semana = ttk.Label(ahorro, text="Ahorrado esta semana: $0.00", font=("Arial", 13, "bold"))
        self.lbl_ahorro_semana.grid(row=0, column=3, padx=12, pady=5)
        self.lbl_ahorro_total = ttk.Label(ahorro, text="Ahorro acumulado: $0.00", font=("Arial", 13, "bold"))
        self.lbl_ahorro_total.grid(row=0, column=4, padx=12, pady=5)

        # ----------------------------------------------------
        # REGISTRAR GASTO
        # ----------------------------------------------------
        form = ttk.LabelFrame(
            contenido,
            text="REGISTRAR GASTO",
            padding=15
        )
        form.pack(
            fill="x",
            padx=20,
            pady=10
        )

        ttk.Label(
            form,
            text="Categoría:", font=("Segoe UI", 12, "bold")
        ).grid(
            row=0,
            column=0,
            padx=5,
            pady=5
        )

        self.combo_categoria = ttk.Combobox(
            form,
            state="readonly",
            width=22,
            font=("Segoe UI", 13)
        )
        self.combo_categoria.grid(
            row=0,
            column=1,
            padx=5,
            pady=5
        )

        ttk.Label(
            form,
            text="Descripción:", font=("Segoe UI", 12, "bold")
        ).grid(
            row=0,
            column=2,
            padx=5,
            pady=5
        )

        self.entry_descripcion = ttk.Entry(
            form,
            width=35
        )
        self.entry_descripcion.grid(
            row=0,
            column=3,
            padx=5,
            pady=5
        )

        ttk.Label(
            form,
            text="Monto:", font=("Segoe UI", 12, "bold")
        ).grid(
            row=0,
            column=4,
            padx=5,
            pady=5
        )

        self.entry_monto = ttk.Entry(
            form,
            width=15
        )
        self.entry_monto.grid(
            row=0,
            column=5,
            padx=5,
            pady=5
        )

        ttk.Button(
            form,
            text="REGISTRAR GASTO",
            command=self.registrar_gasto
        ).grid(
            row=0,
            column=6,
            padx=10,
            pady=5
        )

        # ----------------------------------------------------
        # TABLA DE GASTOS
        # ----------------------------------------------------
        tabla_frame = ttk.LabelFrame(
            contenido,
            text="MIS GASTOS",
            padding=10
        )
        tabla_frame.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=10
        )

        columnas = (
            "id",
            "categoria",
            "descripcion",
            "monto",
            "fecha"
        )

        self.tabla_alumno = ttk.Treeview(
            tabla_frame,
            columns=columnas,
            show="headings",
            style="GastosAlumno.Treeview")

        encabezados = {
            "id": "ID",
            "categoria": "Categoría",
            "descripcion": "Descripción",
            "monto": "Monto",
            "fecha": "Fecha"
        }

        anchos = {
            "id": 60,
            "categoria": 180,
            "descripcion": 350,
            "monto": 120,
            "fecha": 120
        }

        for col in columnas:
            self.tabla_alumno.heading(
                col,
                text=encabezados[col]
            )
            self.tabla_alumno.column(
                col,
                width=anchos[col],
                anchor="center"
            )

        self.tabla_alumno.pack(
            side="left",
            fill="both",
            expand=True
        )

        scroll = ttk.Scrollbar(
            tabla_frame,
            orient="vertical",
            command=self.tabla_alumno.yview
        )
        scroll.pack(
            side="right",
            fill="y"
        )

        self.tabla_alumno.configure(
            yscrollcommand=scroll.set
        )

        # Cargar información real desde MySQL.
        self.cargar_categorias()
        self.cargar_presupuesto_actual(mostrar_alertas=False)
        self.cargar_ahorros()
        self.cargar_gastos_alumno()

    def cargar_info_alumno(self):
        cn = None
        cur = None

        try:
            cn = conectar_bd()
            cur = cn.cursor(dictionary=True, buffered=True)

            cur.execute(
                """
                SELECT nombre, edad, carrera, municipio
                FROM alumnos
                WHERE id_alumno = %s
                """,
                (self.id_alumno,)
            )

            datos = cur.fetchone()

            if datos:
                self.lbl_info_nombre.config(
                    text=f"Nombre: {datos['nombre']}"
                )
                self.lbl_info_edad.config(
                    text=f"Edad: {datos['edad']}"
                )
                self.lbl_info_carrera.config(
                    text=f"Carrera: {datos['carrera']}"
                )
                # Municipio se muestra en el mismo apartado de información.
                self.lbl_info_municipio.config(
                    text=f"Municipio: {datos.get('municipio', 'Sin especificar')}"
                )

        except Exception as e:
            messagebox.showerror(
                "Error",
                str(e)
            )

        finally:
            if cur is not None:
                cur.close()
            if cn is not None and cn.is_connected():
                cn.close()

    # ========================================================
    # CATEGORÍAS DEL ALUMNO
    # ========================================================

    def cargar_categorias(self):
        cn = None
        cur = None

        try:
            cn = conectar_bd()
            cur = cn.cursor(buffered=True)

            cur.execute(
                """
                SELECT id_categoria, nombre_categoria
                FROM categorias
                ORDER BY nombre_categoria
                """
            )

            datos = cur.fetchall()

            self.categorias_map = {
                nombre: id_categoria
                for id_categoria, nombre in datos
            }

            self.combo_categoria["values"] = list(
                self.categorias_map.keys()
            )

            if datos:
                self.combo_categoria.current(0)

        except Exception as e:
            messagebox.showerror(
                "Error al cargar categorías",
                str(e)
            )

        finally:
            if cur is not None:
                cur.close()
            if cn is not None and cn.is_connected():
                cn.close()

    # ========================================================
    # GUARDAR PRESUPUESTO
    # ========================================================

    def guardar_presupuesto(self):
        texto = (
            self.entry_presupuesto
            .get()
            .strip()
            .replace(",", "")
            .replace("$", "")
        )

        if not texto:
            messagebox.showwarning(
                "Dato faltante",
                "Escribe el presupuesto semanal."
            )
            return

        try:
            monto = Decimal(texto)

            if monto <= 0:
                raise InvalidOperation

            monto = monto.quantize(
                Decimal("0.01")
            )

        except (InvalidOperation, ValueError):
            messagebox.showwarning(
                "Monto inválido",
                "Escribe un número mayor que 0."
            )
            return

        cn = None
        cur = None

        try:
            cn = conectar_bd()
            cur = cn.cursor(buffered=True)

            semana = obtener_lunes()

            # Primero verificamos que el alumno exista.
            cur.execute(
                """
                SELECT id_alumno
                FROM alumnos
                WHERE id_alumno = %s
                """,
                (self.id_alumno,)
            )

            if cur.fetchone() is None:
                raise ValueError(
                    "El alumno no existe en la base de datos."
                )

            # INSERT + UPDATE en una sola operación.
            cur.execute(
                """
                INSERT INTO presupuestos_semanales
                (id_alumno, semana_inicio, monto_inicial)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    monto_inicial = VALUES(monto_inicial)
                """,
                (
                    self.id_alumno,
                    semana,
                    monto
                )
            )

            cn.commit()

            self.entry_presupuesto.delete(
                0,
                "end"
            )

            # Se actualizan inmediatamente:
            # Inicial, Gastado, Disponible, Restante y barra.
            self.cargar_presupuesto_actual(
                mostrar_alertas=False
            )

            messagebox.showinfo(
                "Presupuesto guardado",
                f"Tu presupuesto semanal de ${monto:,.2f} "
                "se guardó correctamente."
            )

        except mysql.connector.Error as e:
            if cn is not None:
                cn.rollback()

            messagebox.showerror(
                "Error al guardar presupuesto",
                f"No se pudo guardar el presupuesto.\n\n{e}"
            )

        except Exception as e:
            if cn is not None:
                cn.rollback()

            messagebox.showerror(
                "Error al guardar presupuesto",
                str(e)
            )

        finally:
            if cur is not None:
                cur.close()

            if cn is not None and cn.is_connected():
                cn.close()

    # ========================================================
    # AHORRO SEMANAL PERSISTENTE
    # ========================================================

    def guardar_ahorro(self):
        texto = self.entry_ahorro.get().strip().replace(",", "").replace("$", "")
        try:
            monto = Decimal(texto).quantize(Decimal("0.01"))
            if monto <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            messagebox.showwarning("Monto inválido", "Escribe un ahorro mayor que $0.00.")
            return

        cn = None
        cur = None
        try:
            cn = conectar_bd()
            cur = cn.cursor(buffered=True)
            semana = obtener_lunes()
            cur.execute("SELECT monto_inicial FROM presupuestos_semanales WHERE id_alumno=%s AND semana_inicio=%s", (self.id_alumno, semana))
            fila = cur.fetchone()
            if not fila:
                messagebox.showwarning("Presupuesto requerido", "Primero guarda tu presupuesto semanal.")
                return
            presupuesto = Decimal(str(fila[0]))
            cur.execute("SELECT COALESCE(SUM(monto),0) FROM gastos WHERE id_alumno=%s AND fecha >= %s AND fecha < %s", (self.id_alumno, semana, semana + timedelta(days=7)))
            gastado = Decimal(str(cur.fetchone()[0] or 0))
            cur.execute("SELECT COALESCE(SUM(monto),0) FROM ahorros WHERE id_alumno=%s AND semana_inicio=%s", (self.id_alumno, semana))
            ahorrado = Decimal(str(cur.fetchone()[0] or 0))
            disponible = presupuesto - gastado - ahorrado
            if monto > disponible:
                messagebox.showwarning("Ahorro excedido", f"Solo tienes ${max(disponible, Decimal('0')):,.2f} disponibles para ahorrar esta semana.")
                return
            cur.execute("INSERT INTO ahorros (id_alumno, semana_inicio, monto) VALUES (%s,%s,%s)", (self.id_alumno, semana, monto))
            cn.commit()
            self.entry_ahorro.delete(0, "end")
            self.cargar_ahorros()
            self.cargar_presupuesto_actual(mostrar_alertas=False)
            messagebox.showinfo("Ahorro guardado", f"Se guardaron ${monto:,.2f} en tu ahorro.")
        except Exception as e:
            if cn is not None:
                cn.rollback()
            messagebox.showerror("Error al guardar ahorro", str(e))
        finally:
            if cur is not None:
                cur.close()
            if cn is not None and cn.is_connected():
                cn.close()

    def cargar_ahorros(self):
        cn = None
        cur = None
        try:
            cn = conectar_bd()
            cur = cn.cursor(buffered=True)
            semana = obtener_lunes()
            cur.execute("SELECT COALESCE(SUM(monto),0) FROM ahorros WHERE id_alumno=%s AND semana_inicio=%s", (self.id_alumno, semana))
            semanal = Decimal(str(cur.fetchone()[0] or 0))
            cur.execute("SELECT COALESCE(SUM(monto),0) FROM ahorros WHERE id_alumno=%s", (self.id_alumno,))
            total = Decimal(str(cur.fetchone()[0] or 0))
            self.lbl_ahorro_semana.config(text=f"Ahorrado esta semana: ${semanal:,.2f}")
            self.lbl_ahorro_total.config(text=f"Ahorro acumulado: ${total:,.2f}")
        except Exception as e:
            messagebox.showerror("Error al consultar ahorros", str(e))
        finally:
            if cur is not None:
                cur.close()
            if cn is not None and cn.is_connected():
                cn.close()

    # ========================================================
    # ACTUALIZAR PRESUPUESTO Y DISPONIBLE
    # ========================================================

    def cargar_presupuesto_actual(
        self,
        mostrar_alertas=True
    ):
        cn = None
        cur = None

        try:
            semana = obtener_lunes()

            cn = conectar_bd()
            cur = cn.cursor(buffered=True)

            cur.execute(
                """
                SELECT monto_inicial
                FROM presupuestos_semanales
                WHERE id_alumno = %s
                  AND semana_inicio = %s
                """,
                (
                    self.id_alumno,
                    semana
                )
            )

            fila = cur.fetchone()

            presupuesto = (
                Decimal(str(fila[0]))
                if fila
                else Decimal("0.00")
            )

            cur.execute(
                """
                SELECT COALESCE(SUM(monto), 0)
                FROM gastos
                WHERE id_alumno = %s
                  AND fecha >= %s
                  AND fecha <= %s
                """,
                (
                    self.id_alumno,
                    semana,
                    date.today()
                )
            )

            fila_gasto = cur.fetchone()

            gastado = (
                Decimal(str(fila_gasto[0]))
                if fila_gasto and fila_gasto[0] is not None
                else Decimal("0.00")
            )

            # El ahorro semanal también se separa del presupuesto disponible.
            cur.execute(
                "SELECT COALESCE(SUM(monto), 0) FROM ahorros WHERE id_alumno = %s AND semana_inicio = %s",
                (self.id_alumno, semana)
            )
            fila_ahorro = cur.fetchone()
            ahorrado_semana = Decimal(str(fila_ahorro[0] or 0))
            disponible = presupuesto - gastado - ahorrado_semana

            if presupuesto > 0:
                restante = (
                    disponible / presupuesto * 100
                )
                usado = 100 - restante
            else:
                restante = Decimal("0")
                usado = Decimal("0")

            self.lbl_presupuesto.config(
                text=f"Inicial: ${presupuesto:,.2f}"
            )

            self.lbl_gastado.config(
                text=f"Gastado: ${gastado:,.2f}"
            )

            self.lbl_disponible.config(
                text=f"Disponible: ${disponible:,.2f}"
            )

            self.lbl_porcentaje.config(
                text=f"Restante: {max(restante, Decimal('0')):.1f}%"
            )

            self.barra_progreso["value"] = float(
                min(
                    max(usado, Decimal("0")),
                    Decimal("100")
                )
            )

            if presupuesto <= 0:
                mensaje = (
                    "Primero establece tu presupuesto semanal."
                )

            elif disponible <= 0:
                mensaje = (
                    "⚠ Presupuesto agotado."
                )

            elif restante <= 10:
                mensaje = (
                    "⚠ CUIDADO: te queda 10% o menos "
                    "de tu presupuesto."
                )

            elif restante <= 25:
                mensaje = (
                    "Aviso: te queda 25% o menos "
                    "de tu presupuesto."
                )

            else:
                mensaje = (
                    "Tu presupuesto se encuentra "
                    "en un nivel normal."
                )

            # Las alertas por presupuesto bajo/agotado aparecen en rojo;
            # el estado normal se muestra en verde.
            estilo_alerta = (
                "PresupuestoNormal.TLabel"
                if presupuesto > 0 and disponible > 0 and restante > 25
                else "AlertaPresupuesto.TLabel"
            )
            self.lbl_alerta.config(
                text=mensaje,
                style=estilo_alerta
            )

            if (
                mostrar_alertas
                and presupuesto > 0
                and restante <= 10
            ):
                messagebox.showwarning(
                    "Alerta de presupuesto",
                    mensaje
                )

        except Exception as e:
            messagebox.showerror(
                "Error al actualizar presupuesto",
                str(e)
            )

        finally:
            if cur is not None:
                cur.close()
            if cn is not None and cn.is_connected():
                cn.close()

    # ========================================================
    # REGISTRAR GASTO
    # ========================================================

    def registrar_gasto(self):
        categoria = self.combo_categoria.get().strip()
        descripcion = self.entry_descripcion.get().strip()
        texto_monto = (
            self.entry_monto
            .get()
            .strip()
            .replace(",", "")
            .replace("$", "")
        )

        if not categoria:
            messagebox.showwarning(
                "Dato faltante",
                "Selecciona una categoría."
            )
            return

        if not descripcion:
            messagebox.showwarning(
                "Dato faltante",
                "Escribe una descripción."
            )
            return

        if not texto_monto:
            messagebox.showwarning(
                "Dato faltante",
                "Escribe el monto."
            )
            return

        try:
            monto = Decimal(texto_monto)

            if monto <= 0:
                raise InvalidOperation

            monto = monto.quantize(
                Decimal("0.01")
            )

        except (InvalidOperation, ValueError):
            messagebox.showwarning(
                "Monto inválido",
                "El monto debe ser un número mayor que 0."
            )
            return

        if categoria not in self.categorias_map:
            messagebox.showerror(
                "Categoría inválida",
                "La categoría seleccionada no existe."
            )
            return

        cn = None
        cur = None

        try:
            cn = conectar_bd()
            cur = cn.cursor(buffered=True)

            # Confirmar alumno.
            cur.execute(
                """
                SELECT id_alumno
                FROM alumnos
                WHERE id_alumno = %s
                """,
                (self.id_alumno,)
            )

            if cur.fetchone() is None:
                raise ValueError(
                    "El alumno no existe en la base de datos."
                )

            # Confirmar categoría.
            cur.execute(
                """
                SELECT id_categoria
                FROM categorias
                WHERE id_categoria = %s
                """,
                (self.categorias_map[categoria],)
            )

            if cur.fetchone() is None:
                raise ValueError(
                    "La categoría no existe en la base de datos."
                )

            cur.execute(
                """
                INSERT INTO gastos
                (
                    id_alumno,
                    id_categoria,
                    descripcion,
                    monto,
                    fecha
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    self.id_alumno,
                    self.categorias_map[categoria],
                    descripcion,
                    monto,
                    date.today()
                )
            )

            cn.commit()

            # Limpiar formulario después de guardar.
            self.combo_categoria.current(0)
            self.entry_descripcion.delete(
                0,
                "end"
            )
            self.entry_monto.delete(
                0,
                "end"
            )

            # Actualizar inmediatamente el dashboard.
            self.cargar_presupuesto_actual(
                mostrar_alertas=True
            )
            self.cargar_gastos_alumno()

            messagebox.showinfo(
                "Gasto registrado",
                f"Se guardó el gasto de ${monto:,.2f} "
                "correctamente."
            )

        except mysql.connector.Error as e:
            if cn is not None:
                cn.rollback()

            messagebox.showerror(
                "Error al guardar gasto",
                f"El gasto no se guardó.\n\nDetalle:\n{e}"
            )

        except Exception as e:
            if cn is not None:
                cn.rollback()

            messagebox.showerror(
                "Error al guardar gasto",
                str(e)
            )

        finally:
            if cur is not None:
                cur.close()

            if cn is not None and cn.is_connected():
                cn.close()

    # ========================================================
    # CARGAR GASTOS DEL ALUMNO
    # ========================================================

    def cargar_gastos_alumno(self):
        cn = None

        try:
            cn = conectar_bd()

            df = leer_dataframe(
                """
                SELECT
                    g.id_gasto,
                    c.nombre_categoria,
                    g.descripcion,
                    g.monto,
                    g.fecha
                FROM gastos g
                INNER JOIN categorias c
                    ON g.id_categoria = c.id_categoria
                WHERE g.id_alumno = %s
                ORDER BY
                    g.fecha DESC,
                    g.id_gasto DESC
                """,
                cn,
                (self.id_alumno,)
            )

            for item in self.tabla_alumno.get_children():
                self.tabla_alumno.delete(item)

            for _, r in df.iterrows():
                self.tabla_alumno.insert(
                    "",
                    "end",
                    values=(
                        int(r["id_gasto"]),
                        r["nombre_categoria"],
                        r["descripcion"],
                        f"${float(r['monto']):,.2f}",
                        str(r["fecha"])
                    )
                )

        except Exception as e:
            messagebox.showerror(
                "Error al cargar gastos",
                str(e)
            )

        finally:
            if cn is not None and cn.is_connected():
                cn.close()


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":

    print("1. Iniciando programa...")

    try:
        print("2. Preparando base de datos...")
        preparar_base_datos()
        print("3. Base de datos preparada correctamente")

    except Exception as e:
        print("ERROR EN BASE DE DATOS:", e)

        root_error = tk.Tk()
        root_error.withdraw()

        messagebox.showerror(
            "Error de base de datos",
            "No se pudo preparar la base de datos.\n\n"
            + str(e)
        )

        root_error.destroy()
        raise SystemExit

    print("4. Creando ventana...")

    root = tk.Tk()

    app = Aplicacion(root)

    print("5. Abriendo aplicación...")
    print(
        "6. No existen cuentas predeterminadas. "
        "Cada persona crea su propia cuenta."
    )

    root.mainloop()
