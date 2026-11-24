# Databricks notebook source
# ==============================================================================
# 01 — Registro de Tablas Bronze (Delta Lake) para ARCOTEL
# ==============================================================================
#
# Propósito:
#   Lee los archivos Parquet depositados en DBFS por la ingesta de ARCOTEL y los
#   registra/actualiza como tablas Delta Lake en el catálogo de Databricks.
#
# Convención de esquemas simétricos por ambiente:
#   - DEV: `dev_bronze_arcotel`
#   - QAS: `qas_bronze_arcotel`
#   - PRD: `prd_bronze_arcotel`
#
# Tablas registradas:
#   - {env}_bronze_arcotel.sma_lineas_servicio   (Reporte 1.1.1)
#   - {env}_bronze_arcotel.sma_lineas_modalidad  (Reporte 1.1.2)
#   - {env}_bronze_arcotel.sma_lineas_tecnologia (Reporte 1.1.3)
# ==============================================================================

import logging
import os

# Configuración de logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("register_bronze_delta")

# COMMAND ----------
# 1. Obtener ambiente de ejecución (Widget interactivo o variable de entorno)
try:
    dbutils.widgets.text("ENV", "dev", "Ambiente (dev, qas, prd)")  # noqa: F821
    env = dbutils.widgets.get("ENV").strip().lower()  # noqa: F821
except NameError:
    # Fallback si se ejecuta fuera de Databricks (CLI / tests / scripts externos)
    env = os.getenv("ENV", "dev").strip().lower()

VALID_ENVS = ("dev", "qas", "prd")
if env not in VALID_ENVS:
    raise ValueError(f"Ambiente no válido: '{env}'. Opciones permitidas: {VALID_ENVS}")

schema_name = f"{env}_bronze_arcotel"
logger.info("Iniciando registro Bronze Delta para ambiente: %s en esquema: %s", env.upper(), schema_name)

# COMMAND ----------
# 2. Crear el esquema si no existe
try:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {schema_name} COMMENT 'Capa Bronze cruda de ARCOTEL ({env.upper()})'")  # noqa: F821
    logger.info("Esquema '%s' verificado / creado exitosamente.", schema_name)
except NameError:
    logger.warning("Sesión 'spark' no detectada. Modo offline/simulación.")

# COMMAND ----------
# 3. Definición de fuentes y metadatos de tablas Bronze
BRONZE_TABLES = [
    {
        "table_name": "sma_lineas_servicio",
        "dbfs_path": f"dbfs:/FileStore/{env}/bronze/arcotel/sma/sma_lineas_servicio/",
        "comment": "Líneas activas del SMA por servicio y densidad de mercado (ARCOTEL 1.1.1)",
    },
    {
        "table_name": "sma_lineas_modalidad",
        "dbfs_path": f"dbfs:/FileStore/{env}/bronze/arcotel/sma/sma_lineas_modalidad/",
        "comment": "Líneas activas del SMA por modalidad pospago/prepago (ARCOTEL 1.1.2)",
    },
    {
        "table_name": "sma_lineas_tecnologia",
        "dbfs_path": f"dbfs:/FileStore/{env}/bronze/arcotel/sma/sma_lineas_tecnologia/",
        "comment": "Líneas activas del SMA por tecnología 2G/3G/4G/5G (ARCOTEL 1.1.3)",
    },
]

# COMMAND ----------
# 4. Ingesta / Conversión a Delta Lake
results = []

for item in BRONZE_TABLES:
    tbl = item["table_name"]
    path = item["dbfs_path"]
    full_table_name = f"{schema_name}.{tbl}"

    logger.info("Procesando tabla %s desde %s...", full_table_name, path)

    try:
        # Lectura de los archivos Parquet generados por el pipeline de ingesta
        df = spark.read.parquet(path)  # noqa: F821
        row_count = df.count()
        col_count = len(df.columns)

        # Escritura en formato Delta con evolución de esquema
        (
            df.write.format("delta")
            .mode("overwrite")
            .option("overwriteSchema", "true")
            .saveAsTable(full_table_name)
        )

        # Registrar comentario semántico en la tabla
        spark.sql(f"COMMENT ON TABLE {full_table_name} IS '{item['comment']}'")  # noqa: F821

        logger.info(
            "Tabla Delta %s registrada: %d filas, %d columnas.",
            full_table_name,
            row_count,
            col_count,
        )
        results.append(
            {
                "table": full_table_name,
                "status": "SUCCESS",
                "rows": row_count,
                "cols": col_count,
            }
        )

    except NameError:
        # Ejecución fuera del runtime de Databricks Spark
        results.append(
            {
                "table": full_table_name,
                "status": "OFFLINE_SKIPPED",
                "note": "Runtime Spark no disponible fuera de Databricks",
            }
        )
    except Exception as exc:
        logger.error("Error al registrar %s: %s", full_table_name, exc)
        results.append({"table": full_table_name, "status": "FAILED", "error": str(exc)})

# COMMAND ----------
# 5. Resumen final de ejecución
print("\n" + "=" * 70)
print(f" RESUMEN DE REGISTRO BRONZE DELTA — AMBIENTE: {env.upper()} ")
print("=" * 70)
for res in results:
    status = res["status"]
    tbl = res["table"]
    if status == "SUCCESS":
        print(f" [OK] {tbl} -> {res['rows']} filas, {res['cols']} columnas")
    elif status == "OFFLINE_SKIPPED":
        print(f" [INFO] {tbl} -> Simulación offline (sin runtime Spark activo)")
    else:
        print(f" [ERROR] {tbl} -> {res.get('error')}")
print("=" * 70)
