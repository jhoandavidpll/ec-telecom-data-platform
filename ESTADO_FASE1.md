# Bitácora de Estado y Próximos Pasos — Fase 1: Ingesta ARCOTEL

**Rama de Trabajo:** `feat/jhoan/issue-1-ingesta-arcotel`  
**Issue Asociado:** [#1 — Implementar pipeline de ingesta ARCOTEL (scraper + parser + uploader)](https://github.com/jhoandavidpll/ec-telecom-data-platform/issues/1)  
**Fecha de Corte:** 19 de noviembre de 2026  

---

## 1. Resumen de lo Realizado en esta Sesión

En esta sesión se establecieron los cimientos de la **Fase 1 (Ingesta Dinámica, Web Scraping y Conversión a Parquet en DBFS)**, resolviendo las particularidades técnicas de los archivos de estadísticas públicas de ARCOTEL (Ecuador).

### A. Configuración del Entorno de Desarrollo
* **Gestor de Paquetes `uv` + Python 3.12:**
  * Se configuró el entorno virtual `.venv` utilizando `uv` con **Python 3.12** (evitando la incompatibilidad de Python 3.14 que carece de binarios precompilados de `pandas` y `pyarrow`).
  * Dependencias fijadas y listas en `requirements.txt` (`dbt-databricks`, `pandas`, `pyarrow`, `requests`, `beautifulsoup4`, `openpyxl`, `pytest`, `sqlfluff`, `pre-commit`).
* **Protección del Repositorio:**
  * `.gitignore` blindado para proteger credenciales (`.env`), carpetas de datos locales (`data/`), artefactos de MLOps y carpetas de notas internas.
  * Validador de Conventional Commits y hooks de formato en `.pre-commit-config.yaml`.
  * Workflow de CI inicial (`.github/workflows/ci_pr.yml`) adaptado con validación de ramas (`issue-X`, `task-X`) y modo seguro (*Zero-Cloud*) para colaboradores externos en forks.

---

### B. Módulos Desarrollados en `pipelines/arcotel/`

1. **Catálogo Metadata-Driven (`config/sources.yml`):**
   * Desacoplamiento total de URLs y reglas de extracción para los 3 reportes iniciales de Servicio Móvil Avanzado (SMA):
     * `1.1.1` — `sma_lineas_servicio` (Líneas activas por operadora y servicio).
     * `1.1.2` — `sma_lineas_modalidad` (Modalidad pospago vs. prepago).
     * `1.1.3` — `sma_lineas_tecnologia` (Tecnologías 2G, 3G, 4G, 5G).
2. **Web Scraper Dinámico (`pipelines/arcotel/scraper.py`):**
   * Descubre enlaces `.xlsx` directamente en el DOM de WordPress.
   * **Desempaqueta URLs de Office Apps:** Resuelve el envoltorio `view.officeapps.live.com/op/view.aspx?src=...` mediante decodificación URL para obtener el enlace directo al archivo binario.
   * Descarga los archivos directamente a memoria RAM (`io.BytesIO`) sin ensuciar el disco con archivos `.xlsx` temporales.
3. **Parser y Normalizador a Parquet (`pipelines/arcotel/parser.py`):**
   * **Soporte de Cabeceras Jerárquicas Multinivel:** Detecta estructuras de 2 niveles (Fila 1: Operadoras como `CONECEL S.A.`, `OTECEL S.A.`, `CNT EP` con celdas combinadas; Fila 2: Subcolumnas de servicios como `TELEFONIA`, `TELEFONIA E INTERNET`, `INTERNET`, `DATOS`). Aplica *forward-fill* y fusiona ambos niveles en columnas semánticas limpias: `conecel_telefonia`, `conecel_telefonia_e_internet`, `otecel_telefonia`, etc.
   * **Saneamiento de Tipos Mixtos:** Resuelve el error de PyArrow (`ArrowInvalid: Could not convert 'Ene 2009' with type str: tried to convert to int64`) estandarizando columnas heterogéneas a `string` de forma segura.
   * **Deduplicación Robusta de Columnas:** Garantiza unicidad absoluta de columnas cuando existen raíces repetidas.
   * **Inyección de Metadatos de Auditoría:** Agrega `load_date`, `record_source` y `source_file` requeridos por la arquitectura Medallón / Data Vault.
   * **Generación de Parquet en Memoria:** Conversión con `pyarrow` y compresión `snappy`.
4. **Uploader DBFS / Local (`pipelines/arcotel/databricks_uploader.py`):**
   * Sube a Databricks DBFS (`/FileStore/{env}/bronze/arcotel/sma/{target_table}/year=YYYY/month=MM/day=DD/`) mediante API REST con streaming en bloques.
   * Verifica existencia previa para garantizar **idempotencia**.
   * Modo *fallback* local transparente (`./data/bronze/{env}/...`) con particionamiento jerárquico Hive.
5. **Orquestador CLI (`pipelines/arcotel/main.py`):**
   * Modo `--latest-only` por defecto: detecta que el archivo mensual más reciente ya contiene **todo el acumulado histórico** (más de 208 meses desde 2008), evitando procesar 58 archivos redundantes.
   * Particionamiento automático por fecha de ejecución `year=YYYY/month=MM/day=DD`.
   * Banderas disponibles: `--env dev|qas|prd`, `--local`, `--dry-run`, `--source <id>`, `--all-history`.

---

### C. Suite de Pruebas Unitarias (Zero-Cloud)
* Ubicación: `tests/test_scraper.py` y `tests/test_parser.py`.
* **7 pruebas unitarias pasando al 100% en ~0.8 segundos con 0 warnings**:
  * Desempaquetado de URLs de OfficeApps.
  * Extracción y filtrado por regex en HTML simulado.
  * Normalización a `snake_case`.
  * Conversión de Excel a Parquet con columnas de auditoría.
  * Deduplicación de columnas repetidas.
  * Saneamiento de tipos mixtos (años enteros vs. meses texto).
  * Fusión de cabeceras multinivel (Operadora + Servicio).

---

## 2. Hallazgos Críticos de Dominio (ARCOTEL)

1. **Acumulado Total:** El archivo del corte más reciente de cada reporte contiene toda la serie temporal histórica (2008–presente). No es necesario descargar los 58 archivos del portal.
2. **Evolución Tecnológica (Julio 2014):** En el reporte `1.1.1` (`Líneas por servicio`), antes de julio de 2014 solo existían `Telefonía` e `Internet`. A partir de julio de 2014 aparecen `Telefonía e Internet` y `Datos` debido a la masificación de smartphones y planes combinados en Ecuador. Nuestra cabecera multinivel preserva esta transición sin perder datos históricos.
3. **Pestaña Correcta en `1.1.1`:** La serie temporal acumulada reside en la segunda pestaña (`Líneas por servicio`), la cual quedó fijada en `config/sources.yml`.
4. **Tratamiento de Diciembre y Meses en la Serie Histórica:**
   * Al final de cada ciclo anual, diciembre no se nombra como `Dic YYYY`, sino únicamente con los 4 dígitos del año (`'2008'`, `'2009'`, `'2025'`).
   * Los meses presentan variabilidad de espaciado (`'Ene 2025'` vs. `'Ene2026'`).
   * **Decisión de Arquitectura:** En la capa Bronze se preserva el texto crudo 1:1; la resolución a fechas estándar `DATE` (`YYYY-MM-01`) se delega a una macro dbt en la capa Silver / Raw Vault Staging (`v_stg_*`).

---

## 3. Estado de Entregables y Próximos Pasos (Cierre de Fase 1)

1. **Validación en Terminal de la Ingesta Local:** [COMPLETADO]
   * Estructura jerárquica estilo Hive (`data/bronze/{env}/arcotel/sma/{tabla}/year=YYYY/month=MM/day=DD/`).
   * Verificados 3 archivos Parquet generados (208 filas acumuladas 2008–2026, con metadatos de auditoría `load_date`, `record_source`, `source_file`).
2. **Script para Registro de Tablas Delta (Capa Bronze en Databricks):** [COMPLETADO]
   * Creado `databricks_notebooks/01_register_bronze_delta.py` con parametrización de entorno (`ENV`) y modo offline/simulación.
   * Catálogo simétrico por ambiente: `{env}_bronze_arcotel` (`dev_bronze_arcotel`, `qas_bronze_arcotel`, `prd_bronze_arcotel`).
3. **Estructura Empresarial de Proyecto:** [COMPLETADO]
   * Ingesta encapsulada en `pipelines/arcotel/`.
   * dbt posicionado en la raíz (`dbt_project.yml`, `packages.yml`, `macros/`, `models/`, `docker/profiles.yml`).
   * Paquetes `automate_dv` (0.11.5) y `dbt_utils` instalados y validados con `dbt parse`.
   * `Dockerfile` reproducible para ejecución con o sin contenedores.
4. **Automatización Mensual en GitHub Actions:** [COMPLETADO]
   * Creado `.github/workflows/monthly_pipeline.yml` con Cron mensual (`0 6 2 * *`) y trigger manual `workflow_dispatch`.
   * Workflow CI (`.github/workflows/ci_pr.yml`) actualizado con tests pytest, validación de ramas y `dbt parse`.
5. **Cierre de Issue #1 y Merge a `main`:** [EN PROGRESO]
   * Hacer commit y push de la rama: `git push origin feat/jhoan/issue-1-ingesta-arcotel`.
   * Abrir Pull Request hacia `main` con la descripción `Closes #1`.
   * Aprobar el merge en GitHub.
6. **Inicio de Fase 2 (dbt + Data Vault 2.0):** [SIGUIENTE SESIÓN]
   * Crear rama `feat/jhoan/issue-2-dbt-datavault`.
   * Implementar macro de parseo de fechas `parse_arcotel_date.sql`.
   * Implementar modelos Raw Vault (`v_stg_*`, `hub_*`, `link_*`, `sat_*`).
