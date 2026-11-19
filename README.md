# ARCOTEL Data Platform — Lakehouse, Data Vault 2.0 & MLOps

## Descripción General

Este repositorio implementa una plataforma de datos **End-to-End a costo cero (\$0)** sobre las estadísticas públicas de telecomunicaciones de **ARCOTEL (Ecuador)**. Automatiza la extracción web de archivos Excel publicados mensualmente, los aterriza en formato Parquet en **Databricks (Delta Lake)** y construye un Data Warehouse escalable bajo una arquitectura **Medallón + Data Vault 2.0** con **dbt-core** y **AutomateDV**, alimentando dashboards en **Power BI** y modelos predictivos con **MLflow**.

### Arquitectura de Capas y Ambientes

* **Ingesta:** Python (`requests`, `BeautifulSoup`, `pandas`, `pyarrow`) orquestado por **GitHub Actions** $\rightarrow$ Parquet en DBFS (`/FileStore/{ENV}/bronze/...`).
* **Bronze (`raw_*`):** Vistas crudas con renombrado ligero a `snake_case` y metadatos de auditoría.
* **Silver Raw Vault (`rv/`):** Staging (`v_stg_*`), `hub_*`, `link_*` y `sat_*` generados declarativamente con **AutomateDV**.
* **Silver Business Vault (`bv/`):** Tablas `as_of_date`, `pit_*` y `bsat_*` con reglas de negocio reutilizables.
* **Gold (`dim_*`, `fct_*`, `ml_*`):** Esquema Estrella para Power BI y tablas de features para Machine Learning.
* **Aislamiento de Ambientes (`DEV / QAS / PRD`):** Gestionado a costo \$0 mediante prefijos dinámicos de esquema en Databricks (`macros/custom_schema.sql`).

---

## Prerrequisitos

1. [Visual Studio Code](https://code.visualstudio.com/download) (recomendado con extensiones de Python y dbt Power User).
2. [Python 3.10+](https://www.python.org/downloads/).
3. Cuenta en **Databricks Free / Community Edition** con un Token de Acceso Personal (PAT) y un SQL Warehouse / Cluster HTTP Path.
4. Configurar `dbt_project/profiles.yml` (usa variables de entorno para `dev`, `qas` y `prd`):

```yaml
arcotel_dv:
  target: dev
  outputs:
    dev:
      type: databricks
      host: "{{ env_var('DATABRICKS_HOST') }}"
      http_path: "{{ env_var('DATABRICKS_HTTP_PATH') }}"
      token: "{{ env_var('DATABRICKS_TOKEN') }}"
      schema: dev_default
      threads: 2
    qas:
      type: databricks
      host: "{{ env_var('DATABRICKS_HOST') }}"
      http_path: "{{ env_var('DATABRICKS_HTTP_PATH') }}"
      token: "{{ env_var('DATABRICKS_TOKEN') }}"
      schema: qas_default
      threads: 2
    prd:
      type: databricks
      host: "{{ env_var('DATABRICKS_HOST') }}"
      http_path: "{{ env_var('DATABRICKS_HTTP_PATH') }}"
      token: "{{ env_var('DATABRICKS_TOKEN') }}"
      schema: prd_default
      threads: 4
```

---

## Primeros Pasos (Getting Started)

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/jhoandavidpll/ec-telecom-data-platform.git
   cd ec-telecom-data-platform
   ```

2. **Crear entorno virtual e instalar dependencias:**

   *Opción Recomendada (con [`uv`](https://docs.astral.sh/uv/) — ultra rápido):*
   ```bash
   uv venv .venv
   source .venv/bin/activate        # En macOS / Linux
   # .venv\Scripts\activate         # En Windows

   uv pip install -r requirements.txt
   ```

   *Opción Tradicional (`venv` + `pip`):*
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python3 -m pip install -r requirements.txt
   ```

3. **Activar los Git Hooks (`pre-commit`):**
   ```bash
   pre-commit install --hook-type commit-msg --hook-type pre-commit
   ```

4. **Configurar variables de entorno:**
   Crea un archivo `.env` en la raíz del proyecto (ver sección siguiente) y cárgualo en tu sesión.

5. **Instalar paquetes de dbt y validar conexión a Databricks:**
   ```bash
   dbt deps --project-dir dbt_project
   dbt debug --project-dir dbt_project --profiles-dir dbt_project --target dev
   ```

---

## Archivo `.env`

Crea un archivo `.env` en la raíz del proyecto (este archivo está ignorado por `.gitignore` y nunca debe subirse al repositorio):

```env
# Conexión Databricks
DATABRICKS_HOST=https://community.cloud.databricks.com
DATABRICKS_HTTP_PATH=/sql/protocolv1/o/0/xxxx-xxxxxx-xxxxxxxx
DATABRICKS_TOKEN=dapi_tu_token_personal_aqui

# Ambiente de ejecución para ingesta DBFS (dev | prd)
ENV=dev
```

---

## Comandos Útiles

```bash
# Ejecutar ingesta local en ambiente DEV
python ingestion/main.py

# Construir y probar un modelo específico y sus dependencias en DEV
dbt build --select +hub_operadora --project-dir dbt_project --profiles-dir dbt_project --target dev

# Construir por capa Medallón
dbt build --select "tag:layer:silver_rv" --project-dir dbt_project --profiles-dir dbt_project --target dev
dbt build --select "tag:layer:gold" --project-dir dbt_project --profiles-dir dbt_project --target dev

# Generar y visualizar documentación + grafo de linaje
dbt docs generate --project-dir dbt_project --profiles-dir dbt_project --target dev
dbt docs serve --project-dir dbt_project --profiles-dir dbt_project
```

---

## Guía de Contribución

Este proyecto utiliza **Trunk-Based Development**, nombres de rama estandarizados y **Conventional Commits**. Consulta `CONTRIBUTING.md` para todos los detalles.

Resumen rápido:
```bash
git checkout main && git pull
git checkout -b feat/<usuario>/TASK001-lineas-activas
# ... realizar cambios y probar con dbt build --target dev ...
git commit -m "feat(lineas-activas): agregar hub_operadora y sat_lineas_servicio"
git push origin feat/<usuario>/TASK001-lineas-activas
# Abrir Pull Request hacia main para disparar CI en QAS
```