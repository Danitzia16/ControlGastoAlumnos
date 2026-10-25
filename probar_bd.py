
import mysql.connector

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "control_gastos_alumnos",
    "connection_timeout": 5,
}

try:
    conexion = mysql.connector.connect(**DB_CONFIG)
    print("CONEXION A MYSQL: CORRECTA")

    cursor = conexion.cursor()

    tablas = (
        "alumnos",
        "gastos",
        "categorias",
        "presupuestos_semanales",
        "ahorros",
        "usuarios",
    )

    for tabla in tablas:
        cursor.execute(f"SELECT COUNT(*) FROM `{tabla}`")
        cantidad = cursor.fetchone()[0]
        print(f"{tabla}: {cantidad} registros")

    cursor.close()
    conexion.close()

    print("Prueba terminada sin modificar datos.")

except mysql.connector.Error as error:
    print("NO SE PUDO CONECTAR A MYSQL")
    print("Detalle:", error)
