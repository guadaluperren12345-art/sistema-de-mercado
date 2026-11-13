"""Espera a que SQL Server esté listo y crea la base de datos si no existe.

Se ejecuta antes de iniciar Django, porque SQL Server tarda unos segundos
en arrancar y Django necesita que la base ya exista.
"""

import os
import sys
import time

import pyodbc

HOST = os.environ.get("DB_HOST", "db")
PORT = os.environ.get("DB_PORT", "1433")
USER = os.environ.get("DB_USER", "sa")
PASSWORD = os.environ["MSSQL_SA_PASSWORD"]
DB_NAME = os.environ.get("DB_NAME", "sistema_mercado")

CONEXION = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER={HOST},{PORT};DATABASE=master;UID={USER};PWD={PASSWORD};"
    "TrustServerCertificate=yes;"
)

for intento in range(1, 31):
    try:
        conn = pyodbc.connect(CONEXION, autocommit=True, timeout=5)
        break
    except pyodbc.Error:
        print(f"Esperando a SQL Server... (intento {intento}/30)")
        time.sleep(2)
else:
    print("No se pudo conectar a SQL Server.")
    sys.exit(1)

cursor = conn.cursor()
cursor.execute("SELECT 1 FROM sys.databases WHERE name = ?", DB_NAME)
if cursor.fetchone() is None:
    # Collation en español, sin distinguir mayúsculas ni acentos en búsquedas
    cursor.execute(f"CREATE DATABASE [{DB_NAME}] COLLATE Modern_Spanish_CI_AI")
    print(f"Base de datos '{DB_NAME}' creada.")
else:
    print(f"Base de datos '{DB_NAME}' ya existe.")
conn.close()
