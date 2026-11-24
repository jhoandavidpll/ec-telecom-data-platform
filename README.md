# ARCOTEL Data Platform — Lakehouse, Data Vault 2.0 & MLOps

## Descripción General

Este repositorio implementa una plataforma de datos **End-to-End a costo cero (\$0)** sobre las estadísticas públicas de telecomunicaciones de **ARCOTEL (Ecuador)**. Automatiza la extracción web de archivos Excel publicados mensualmente, los aterriza en formato Parquet en **Databricks (Delta Lake)** con particionamiento jerárquico estilo Hive, y construye un Data Warehouse escalable bajo una arquitectura **Medallón + Data Vault 2.0** con **dbt-core** y **AutomateDV**, alimentando dashboards en **Power BI** y modelos predictivos con **MLflow**.

### Arquitectura de Capas y Ambientes

* **Ingesta (`pipelines/arcotel/`):** Python (`requests`, `BeautifulSoup`, `pandas`, `pyarrow`) orquestado por **GitHub Actions** $\rightarrow$ Parquet particionado jerárquicamente por fecha de ejecución (`year=YYYY/month=MM/day=DD/`) en DBFS (`/FileStore/{env}/bronze/arcotel/sma/...`) y local (`data/bronze/{env}/arcotel/sma/...`).
* **Bronze (`sma_*`):** Tablas Delta en esquemas simétricos (`dev_bronze_arcotel`, `qas_bronze_arcotel`, `prd_bronze_arcotel`) con metadatos de auditoría (`load_date`, `record_source`, `source_file`).
* **Silver Raw Vault (`rv/`):** Staging (`v_stg_*`), `hub_*`, `link_*` y `sat_*` generados declarativamente con **AutomateDV**.
* **Silver Business Vault (`bv/`):** Tablas `as_of_date`, `pit_*` y `bsat_*` con reglas de negocio reutilizables.
* **Gold (`dim_*`, `fct_*`, `ml_*`):** Esquema Estrella para Power BI y tablas de features para Machine Learning.
* **Aislamiento de Ambientes (`DEV / QAS / PRD`):** Gestionado a costo \$0 mediante prefijos dinámicos simétricos en Databricks (`macros/custom_schema.sql`).
* **Contenedores y DataOps:** Contenedor reproducible mediante [Dockerfile](Dockerfile) y configuración de perfiles centralizada en [docker/profiles.yml](docker/profiles.yml).

---

## Prerrequisitos

1. [Visual Studio Code](https://code.visualstudio.com/download) (recomendado con extensiones de Python y dbt Power User).
2. [Python 3.12](https://www.python.org/downloads/) (o Docker).
3. Cuenta en **Databricks Free / Community Edition** con un Token de Acceso Personal (PAT) y un SQL Warehouse / Cluster HTTP Path (o modo local Zero-Cloud).
4. Configuración de perfiles dbt en `docker/profiles.yml`:

```yaml
ec_telecom:
  target: dev
  outputs:
    dev:
      type: databricks
      host: "{{ env_var('DATABRICKS_HOST') }}"
      http_path: "{{ env_var('DATABRICKS_HTTP_PATH') }}"
      token: "{{ env_var('DATABRICKS_TOKEN') }}"
      schema: dev_bronze_arcotel
      threads: 4
    qas:
      type: databricks
      host: "{{ env_var('DATABRICKS_HOST') }}"
      http_path: "{{ env_var('DATABRICKS_HTTP_PATH') }}"
      token: "{{ env_var('DATABRICKS_TOKEN') }}"
      schema: qas_bronze_arcotel
      threads: 4
    prd:
      type: databricks
      host: "{{ env_var('DATABRICKS_HOST') }}"
      http_path: "{{ env_var('DATABRICKS_HTTP_PATH') }}"
      token: "{{ env_var('DATABRICKS_TOKEN') }}"
      schema: prd_bronze_arcotel
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
   uv venv .venv --python 3.12
   source .venv/bin/activate        # En macOS / Linux
   # .venv\Scripts\activate         # En Windows

   uv pip install -r requirements.txt
   ```

   *Opción Tradicional (`venv` + `pip`):*
   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Activar los Git Hooks (`pre-commit`):**
   ```bash
   pre-commit install --hook-type commit-msg --hook-type pre-commit
   ```

4. **Configurar variables de entorno:**
   Crea un archivo `.env` en la raíz del proyecto a partir de `.env.example`:
   ```bash
   cp .env.example .env
   ```

5. **Instalar paquetes de dbt y validar proyecto:**
   ```bash
   dbt deps --profiles-dir docker
   dbt parse --profiles-dir docker
   ```

---

## Ejecución con Docker (Opcional)

Si prefieres ejecutar todo en un contenedor reproducible sin instalar dependencias locales:

```bash
# Construir la imagen
docker build -t ec-telecom-platform .

# Ejecutar la ingesta mensual en modo local
docker run --rm -v $(pwd)/data:/usr/app/telecom_platform/data ec-telecom-platform \
    python -m pipelines.arcotel.main --env dev --local

# Compilar modelos dbt
docker run --rm --env-file .env ec-telecom-platform \
    dbt parse --profiles-dir docker
```

---

## Comandos Útiles

```bash
# Ejecutar ingesta local con particionamiento Hive en ambiente DEV
python -m pipelines.arcotel.main --env dev --local

# Correr pruebas unitarias (100% Zero-Cloud)
pytest tests/

# Compilar y validar sintaxis de modelos dbt
dbt parse --profiles-dir docker

# Construir y probar un modelo específico y sus dependencias en DEV
dbt build --select +hub_operadora --profiles-dir docker --target dev

# Construir por capa Medallón
dbt build --select "tag:layer:silver_rv" --profiles-dir docker --target dev
dbt build --select "tag:layer:gold" --profiles-dir docker --target dev

# Generar y visualizar documentación + grafo de linaje
dbt docs generate --profiles-dir docker --target dev
dbt docs serve --profiles-dir docker
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