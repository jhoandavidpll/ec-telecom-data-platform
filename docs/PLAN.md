# PLAN.md — Ecosistema de Datos y MLOps (ARCOTEL)

Este archivo brinda contexto técnico, arquitectura, estándares de ingeniería y plan de desarrollo por fases para trabajar en este repositorio (`ec-telecom-data-platform`).

## 1. Resumen del Proyecto y Stack Tecnológico

Pipeline End-to-End de Ingeniería de Datos, Analítica y MLOps a **costo cero (\$0)** sobre las estadísticas públicas de telecomunicaciones de **ARCOTEL (Ecuador)**. Ingiere archivos Excel publicados mensualmente en la web de ARCOTEL y los refina progresivamente mediante una arquitectura **Medallón + Data Vault 2.0** construida con **dbt-core** y **AutomateDV** sobre **Databricks (Delta Lake)**.

| Capa / Rol | Tecnología | Justificación |
| :--- | :--- | :--- |
| **Orquestación & CI/CD** | **GitHub Actions** (Cron mensual + PR CI) | Cómputo Linux gratuito, caché de dependencias, pruebas automáticas y ejecución auditable. |
| **Extracción y Parseo** | **Python 3.10+** (`requests`, `beautifulsoup4`, `pandas`, `openpyxl`, `pyarrow`, `pyyaml`) | Scraping ligero sobre el DOM de WordPress y conversión en memoria a formato Parquet. |
| **Lakehouse (Storage & Compute)** | **Databricks Free / Community Edition** (Delta Lake + DBFS) | Estándar Lakehouse, transacciones ACID, soporte nativo de `QUALIFY` y tablas Delta. |
| **Modelado & Transformación** | **dbt-core** (`dbt-databricks`) + **AutomateDV** (`automate_dv`) + `dbt_utils` | Data Vault 2.0 declarativo, linaje automático, pruebas de calidad y cargas incrementales. |
| **Analítica (BI)** | **Power BI** | Consumo directo desde la capa Gold de `PRD` (Esquema Estrella), eliminando transformaciones manuales en Power Query. |
| **MLOps** | **MLflow** (Databricks) + **Scikit-learn / Prophet** + **FastAPI** (Docker/Portainer) | Tracking de experimentos en la nube, inferencia batch a Gold y despliegue de API en homelab. |

## 2. Configuración del Entorno y Comandos Comunes

### Requisitos Locales

* **Python 3.10+**, dependencias en `requirements.txt` (`dbt-core`, `dbt-databricks`, `pre-commit`, `python-dotenv`, `pandas`, `openpyxl`, `pyarrow`, `requests`, `beautifulsoup4`, `pyyaml`).
* Instalación: `python3 -m pip install -r requirements.txt`
* Activar hooks de Git (validación de Conventional Commits y formato):
  `pre-commit install --hook-type commit-msg --hook-type pre-commit`
* Credenciales y entorno vía variables (`.env` local, nunca versionado; en CI vía GitHub Secrets):
  * `DATABRICKS_HOST`
  * `DATABRICKS_HTTP_PATH` (SQL Warehouse / Cluster HTTP Path para `dbt-databricks`)
  * `DATABRICKS_TOKEN`
  * `DATABRICKS_CATALOG` (opcional según edición)
  * `ENV` (`dev` por defecto en local; `prd` en el pipeline mensual de producción)
* `profiles.yml` ubicado en `docker/profiles.yml` (usando `env_var(...)` con targets **`dev`**, **`qas`** y **`prd`**).

### Comandos dbt Frecuentes

```bash
# Instalar packages (automate_dv, dbt_utils)
dbt deps --profiles-dir docker

# Validar conexión a Databricks o validar sintaxis de modelos
dbt debug --profiles-dir docker --target dev
dbt parse --profiles-dir docker

# Build (run + test juntos — preferido antes de cada push)
dbt build --select +mi_modelo --profiles-dir docker --target dev

# Ejecución por capa medallion o dominio usando tags canónicos
dbt build --select "tag:layer:bronze" --profiles-dir docker --target dev
dbt build --select "tag:layer:silver_rv" --profiles-dir docker --target qas
dbt build --select "tag:layer:silver_bv" --profiles-dir docker --target prd
dbt build --select "tag:layer:gold" --profiles-dir docker --target prd
dbt build --select "tag:domain:sma" --profiles-dir docker --target dev
dbt build --select "tag:domain:sma,tag:layer:gold" --profiles-dir docker --target prd

# Documentación y linaje interactivo
dbt docs generate --profiles-dir docker --target dev
dbt docs serve --profiles-dir docker
```

## 3. Flujo de Trabajo Git y CI/CD (GitHub Actions)

Ver `CONTRIBUTING.md` para la guía detallada de contribución.

* **Desarrollo Trunk-Based:** Todas las ramas salen directamente de `main` (nunca desde otra rama feature) y `main` debe permanecer siempre desplegable.
* **Nomenclatura de ramas:** `<type>/<user>/<TASKxxx>-<descripcion-corta>` (ej. `feat/jhoan/TASK001-lineas-activas`, `fix/jhoan/TASK012-nulos-operadora`), donde:
  * `type` $\in$ `feat|fix|chore|refactor|docs|test`
  * `TASKxxx` corresponde al identificador del Issue / Task en GitHub Projects.
  * `descripcion-corta` en `kebab-case` (2 a 4 palabras).
* **Conventional Commits con Scope:** `<type>(<scope>): <descripción en minúsculas y tiempo presente>`
  * Ejemplos: `feat(lineas-activas): agregar hub_operadora y sat_lineas_servicio`, `fix(scraper): corregir decodificacion de enlaces officeapps`, `docs(architecture): actualizar estrategia de ambientes`.
  * Tipos permitidos: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`. Validado automáticamente con `pre-commit`.
* **Tests obligatorios:** Todo modelo nuevo o modificado debe incluir pruebas en su `schema.yml` (`unique`, `not_null`, `relationships`, `accepted_values`) y pasar `dbt build --select +tu_modelo --target dev` localmente antes del push.
* **Pipelines de GitHub Actions:**
  1. `.github/workflows/ci_pr.yml`: En cada PR hacia `main`, valida nombres de rama (`^(feat|fix|chore|docs|refactor|test)/[a-zA-Z0-9_-]+/TASK[0-9]+-[a-z0-9-]+$`), corre linters de Python/SQL y ejecuta `dbt build --target qas` (aislado en esquemas `qas_*`, leyendo la capa Bronze de `prd`).
  2. `.github/workflows/cd_prd.yml`: Al hacer **merge a `main`**, despliega los cambios de dbt contra `--target prd`.
  3. `.github/workflows/monthly_pipeline.yml`: Ejecución programada (Cron mensual + `workflow_dispatch` manual) con `ENV=prd` que corre:
     `Extracción Python -> Carga Parquet a DBFS (prd) -> Registro Bronze -> dbt build --target prd (Bronze -> Silver RV -> Silver BV -> Gold)`.

## 4. Análisis de la Fuente de Datos (ARCOTEL)

* **Portal Principal:** `https://www.arcotel.gob.ec/estadisticas2/`
* **Dominio Inicial (MVP — `sma`):** Servicio Móvil Avanzado $\rightarrow$ `https://www.arcotel.gob.ec/servicio-movil-avanzado-sma2/` $\rightarrow$ `https://www.arcotel.gob.ec/lineas-activas/`

### Hallazgos Críticos de Extracción

1. **Falsa predictibilidad de URLs:** WordPress guarda archivos en `/wp-content/uploads/YYYY/MM/archivo.xlsx`, donde `YYYY/MM` es el **mes de subida** y no necesariamente el mes de corte (ej. datos de marzo subidos en mayo). **Regla:** Nunca construir URLs por fecha; siempre descubrir enlaces parseando el HTML del DOM.
2. **Envoltorios del visor de Office:** Algunos enlaces apuntan a `https://view.officeapps.live.com/op/view.aspx?src=...`. El extractor debe detectar este prefijo y decodificar el parámetro `src` con `urllib.parse.unquote` para obtener el enlace directo al `.xlsx`.
3. **Estructura variable de los Excel:** Cada archivo contiene múltiples pestañas (`Indice`, `[Hoja de Datos]`, `Evolución`, `Participación`). Los nombres de las pestañas de datos varían y contienen encabezados/logos decorativos antes de la tabla real.

### Categorías Iniciales en `lineas-activas` (`domain: sma`)

1. `1.1.1` — Densidad de línea y participación de mercado (`sma_lineas_servicio`)
2. `1.1.2` — Densidad de líneas activas por modalidad (`sma_lineas_modalidad`)
3. `1.1.3` — Líneas activas por tecnología (`sma_lineas_tecnologia`)

## 5. Arquitectura de Datos (Medallón + Data Vault 2.0 con AutomateDV)

### Regla de Oro (Anti-patrón Prohibido)

> **Prohibido saltar la capa Data Vault:** Ningún modelo Gold puede leer directamente desde `source(...)` o Bronze. Todo dato nuevo debe fluir estrictamente por:
> `Landing (Parquet DBFS) -> Bronze (Raw Views) -> Silver RV (Staging + Hubs/Links/Sats) -> Silver BV (PITs/Bridges/Business Sats) -> Gold (Marts & ML Features)`.

### Estructura de Capas en `dbt_project/models/`

1. **`models/sources/sources.yml`**
   * Declaración centralizada de todas las tablas Delta aterrizadas en la zona raw/landing de Databricks.
2. **`models/bronze/<dominio>/...`**
   * **Materialización:** Vistas (`view`), casi 1:1 sobre las tablas `source(...)` (prefijo `raw_*` o `v_raw_*`).
   * **Responsabilidad:** Renombrado ligero de columnas a **`snake_case`** orientado a negocio, casteo básico de tipos de datos y preservación de columnas de auditoría (`load_date`, `record_source`, `source_file`). Sin filtros destructivos.
3. **`models/silver/<dominio>/rv/` (Raw Vault — `AutomateDV`)**
   * **`stg/` (`v_stg_*`, vista):** Usa `automate_dv.stage(...)` para derivar columnas técnicas, estandarizar llaves de negocio (ej. `UPPER(TRIM(...))`) y calcular **Hash Keys (`hk_*`)** y **Hashdiffs (`hd_*`)** con algoritmo SHA-256.
   * **`hubs/` (`hub_*`, incremental Delta):** Una fila única por llave de negocio (ej. `hub_operadora`, `hub_servicio`, `hub_modalidad`, `hub_tecnologia`).
   * **`links/` (`link_*`, incremental Delta):** Relaciones/transacciones entre hubs (ej. `link_operadora_servicio`, `link_operadora_modalidad`, `link_operadora_tecnologia`).
   * **`sats/` (`sat_*`, incremental Delta):** Atributos descriptivos e históricos de un hub o link (ej. `sat_lineas_servicio`, `sat_lineas_modalidad`, `sat_lineas_tecnologia`). Usar `automate_dv.eff_sat` o `automate_dv.ma_sat` solo si aparecen satélites de efectividad o multi-activos.
   * **Patrón obligatorio de AutomateDV:** Los modelos `hub_*`, `link_*` y `sat_*` deben ser envoltorios declarativos delgados: un bloque de metadata YAML (`src_pk`, `src_nk`/`src_fk`, `src_hashdiff`, `src_payload`, `src_ldts`, `src_source`, `source_model`) parseado con `fromyaml` y pasado directamente a `automate_dv.hub(...)`, `automate_dv.link(...)` o `automate_dv.sat(...)`. **Nunca escribir SQL de Data Vault a mano.**
4. **`models/silver/<dominio>/bv/` (Business Vault)**
   * **`as_of_date` (`as_of_date_mensual`):** Tabla calendario de fechas de corte requerida por los PITs.
   * **`pits/` (`pit_*`, tabla Delta):** Construidos con `automate_dv.pit(...)` para precalcular, para cada `as_of_date`, qué fila de cada satélite es la vigente para un hub.
   * **`bridges/` (`bridge_*`):** Jerarquías o cruces frecuentes aplanados (cuando aplique al añadir nuevos dominios como geografía/provincias).
   * **`bsats/` (`bsat_*`):** Satélites de negocio con reglas derivadas reutilizables (participación de mercado %, variación MoM/YoY, mapeo de razón social legal a marca comercial: `CONECEL` $\rightarrow$ `Claro`, `OTECEL` $\rightarrow$ `Movistar/Tuenti`, `CNT EP` $\rightarrow$ `CNT`).
5. **`models/gold/<dominio>/...` (Information Marts & ML Features)**
   * **Materialización:** Tablas Delta (`table`).
   * **Nomenclatura:** `dim_*` (dimensiones), `fct_*` (tablas de hechos), `dt_*` (tablas de detalle desnormalizadas si BI lo requiere) y `ml_*` (tablas de features consolidadas para Machine Learning).
   * **Patrón de lectura desde Silver:** Unir Hubs + Satellites mediante `pit_*` o, para snapshots simples del último estado, usar `QUALIFY ROW_NUMBER() OVER (PARTITION BY <hub_hk> ORDER BY load_date DESC) = 1`.
6. **`models/dq/` (Data Quality)**
   * Modelos y pruebas de validación de catálogos e integridad de negocio (ej. la suma de participación de mercado por mes debe ser $\approx 100\%$, detección de meses faltantes).

## 6. Convenciones Estrictas de Nomenclatura, Ambientes, Esquemas y Tags

### Nomenclatura (`snake_case` Obligatorio)

* **Campos/Columnas:** 100% en **`snake_case`** minúscula, sin tildes ni caracteres especiales (ej. `cantidad_lineas_activas`, `fecha_corte`, `densidad_porcentaje`).
* **Columnas Técnicas Data Vault (`snake_case`):**
  * Hash Keys de Hubs/Links: `hk_<entidad>` (ej. `hk_operadora`, `hk_operadora_servicio`).
  * Hashdiff de Satellites: `hd_<satelite>` (ej. `hd_lineas_servicio`).
  * Metadatos obligatorios: `load_date`, `record_source`, `source_file`, `effective_from`.
* **Prefijos de Modelos:**
  * Bronze: `raw_<dominio>_<tabla>`
  * Staging RV: `v_stg_<dominio>_<tabla>`
  * Raw Vault: `hub_<entidad>`, `link_<entidad1>_<entidad2>`, `sat_<entidad>_<descripcion>`
  * Business Vault: `pit_<entidad>`, `bridge_<descripcion>`, `bsat_<entidad>_<descripcion>`
  * Gold: `dim_<entidad>`, `fct_<proceso>`, `ml_<caso_uso>`

### Estrategia de Ambientes (`DEV / QAS / PRD`) y Gestión de Esquemas

Al operar en un **único workspace de Databricks (plan gratuito)**, el aislamiento de ambientes se logra **prefijando los esquemas según el `target` de dbt** a costo \$0:

| Ambiente | Target dbt | Ejemplo de Esquemas en Databricks | Cuándo se usa |
| :--- | :--- | :--- | :--- |
| **Desarrollo** | `dev` | `dev_bronze_arcotel`, `dev_silver_rv_sma`, `dev_gold_sma` | Pruebas locales desde la máquina de desarrollo. |
| **Calidad (CI)** | `qas` | `qas_bronze_arcotel`, `qas_silver_rv_sma`, `qas_gold_sma` | Automático en GitHub Actions al abrir un **Pull Request** a `main`. |
| **Producción** | `prd` | `prd_bronze_arcotel`, `prd_silver_rv_sma`, `prd_gold_sma` | Automático al hacer **merge a `main`** y en el cron mensual. Power BI solo lee de aquí. |

* **Nunca hardcodear nombres de esquema en los modelos.** Cada modelo debe usar `config(schema=var("..."))` apuntando a variables centralizadas en `dbt_project.yml` (`bronze_schema`, `silver_rv_schema`, `silver_bv_schema`, `gold_schema`, `dq_schema`).
* **Macro `macros/custom_schema.sql`:** Sobreescribe `generate_schema_name` para prefijar de manera simétrica y estricta con el `target.name` (`dev_`, `qas_`, `prd_`), eliminando cualquier ambigüedad en el catálogo compartido:

```sql
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- else -%}
        {{ target.name }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
```

* **Aislamiento en DBFS (Capa Bronze):** El script de ingesta Python respeta la variable de entorno `ENV` (`dev` por defecto, `prd` en producción):
  * `dbfs:/FileStore/dev/bronze/arcotel/<dominio>/<tabla>/`
  * `dbfs:/FileStore/prd/bronze/arcotel/<dominio>/<tabla>/`
  * *Nota sobre `QAS`:* Los modelos en `qas` leen directamente de la capa Bronze de `prd` para validar las transformaciones contra datos reales sin duplicar la descarga de Excels.

### Esquema Canónico de Tags (Unificado desde el Día 1)

Todo modelo debe declarar sus tags en `config(tags=[...])` siguiendo esta taxonomía estricta:

* `layer:<bronze|silver_rv|silver_bv|gold|dq>`
* `domain:<sma|internet_fijo|tv_pagada|telefonia_fija|glb>`
* `model:<nombre_entidad_o_proceso>` (ej. `model:lineas_activas`)

## 7. Estructura del Repositorio

```text
ec-telecom-data-platform/
├── .github/workflows/
│   ├── ci_pr.yml                       # Validación en PRs (ramas, linters, pytest + dbt parse / qas)
│   ├── cd_prd.yml                      # Despliegue en merge a main (dbt build --target prd)
│   └── monthly_pipeline.yml            # Orquestador mensual (ENV=prd: Scraping -> DBFS -> dbt prd)
├── config/
│   └── sources.yml                     # Catálogo metadata-driven de URLs y reglas Excel ARCOTEL
├── data/                               # Almacenamiento local simulación Lakehouse (.gitignore)
│   └── bronze/
│       └── {env}/
│           └── arcotel/
│               └── sma/
│                   └── {tabla}/
│                       └── year=YYYY/month=MM/day=DD/data.parquet
├── databricks_notebooks/
│   └── 01_register_bronze_delta.py     # Registra/actualiza tablas Delta sobre los Parquet en DBFS
├── docker/
│   └── profiles.yml                    # Conexión Databricks vía env_var() (targets: dev, qas, prd)
├── macros/
│   ├── custom_schema.sql               # Override de generate_schema_name para DEV/QAS/PRD
│   └── clean_null_or_empty.sql         # Helpers de limpieza reutilizables
├── models/
│   ├── sources/
│   │   └── sources.yml                 # Declaración central de tablas Delta de Databricks
│   ├── bronze/sma/                     # sma_*.sql (vistas sobre Delta)
│   ├── silver/sma/
│   │   ├── rv/
│   │   │   ├── stg/                    # v_stg_sma_*.sql
│   │   │   ├── hubs/                   # hub_*.sql
│   │   │   ├── links/                  # link_*.sql
│   │   │   └── sats/                   # sat_*.sql
│   │   └── bv/
│   │       ├── pits/                   # pit_*.sql + as_of_date_mensual.sql
│   │       └── bsats/                  # bsat_*.sql
│   ├── gold/sma/                       # dim_*.sql, fct_*.sql, ml_features_sma.sql
│   └── dq/                             # Validaciones de integridad de negocio
├── pipelines/
│   └── arcotel/
│       ├── __init__.py
│       ├── scraper.py                  # Descubrimiento dinámico de enlaces .xlsx en el DOM
│       ├── parser.py                   # Detección de hoja de datos, cabeceras multinivel y Parquet
│       ├── databricks_uploader.py      # Carga vía REST a DBFS / Local con Hive Partitioning
│       └── main.py                     # Orquestador CLI de la ingesta Python
├── tests/                              # Pruebas unitarias Python y tests singulares dbt
├── docs/
│   ├── guides/
│   │   └── guia_bronze_silver_gold.md  # Guía paso a paso con AutomateDV en Databricks
│   └── models/
│       └── model_documentation_template.md
├── mlops/
│   ├── train_forecast.py               # Entrenamiento y tracking en MLflow
│   └── api/                            # FastAPI + Dockerfile para despliegue en Portainer
├── .env.example
├── .pre-commit-config.yaml
├── CONTRIBUTING.md
├── dbt_project.yml                     # Configuración central dbt en la raíz
├── Dockerfile                          # Contenedor reproducible de la plataforma
├── package-lock.yml
├── packages.yml                        # automate_dv, dbt_utils
├── README.md
└── requirements.txt
```

## 8. Plan de Ejecución por Fases

### Fase 0: Cimientos del Repositorio y Entorno

* [x] Crear repositorio en GitHub con rama `main` protegida, `.pre-commit-config.yaml` (Conventional Commits), `CONTRIBUTING.md`, `README.md` y variables de entorno (`.env.example`).
* [x] Configurar entorno local (`uv` + Python 3.12), definir `docker/profiles.yml` con targets `dev`, `qas`, `prd` y validar proyecto con `dbt parse`.
* [x] Crear `config/sources.yml` con la metadata de las 3 categorías iniciales de `lineas-activas`.

### Fase 1: Ingesta Dinámica y Escalable (Web Scraping $\rightarrow$ Landing/Bronze)

* [x] Desarrollar `pipelines/arcotel/scraper.py`: descarga HTML, decodifica enlaces de `view.officeapps.live.com` y filtra por regex definida en `config/sources.yml`.
* [x] Validar que el Excel más reciente de ARCOTEL contiene todo el histórico acumulado (>208 meses desde 2008), evitando procesar archivos redundantes.
* [x] Desarrollar `pipelines/arcotel/parser.py`: lee Excel en memoria (`io.BytesIO`), detecta cabeceras jerárquicas multinivel combinadas, sanea tipos mixtos, normaliza a `snake_case`, añade metadatos (`load_date`, `record_source`, `source_file`) y convierte a Parquet (`pyarrow` con compresión `snappy`).
* [x] Desarrollar `pipelines/arcotel/databricks_uploader.py`: verifica archivos ya cargados (idempotencia), sube a DBFS (`/FileStore/{env}/bronze/arcotel/<dominio>/<tabla>/`) y soporta fallback local con particionamiento jerárquico Hive (`year=YYYY/month=MM/day=DD/`).
* [x] Crear script de registro Delta `databricks_notebooks/01_register_bronze_delta.py` y configurar `.github/workflows/monthly_pipeline.yml`.
* [x] Validar suite de pruebas unitarias (`pytest tests/`) al 100% en modo Zero-Cloud y compilar dbt en raíz.

### Fase 2: Capa Bronze y Silver Raw Vault (dbt + AutomateDV)

* [ ] Implementar macro de normalización de fechas `macros/parse_arcotel_date.sql` para sanear la inconsistencia de cierres anuales (`'2008'` = Diciembre) y meses compactos (`'Ene2026'`).
* [ ] Crear modelos Bronze (`models/bronze/sma/sma_*.sql`) como vistas sobre las tablas Delta de Databricks.
* [ ] Construir Staging (`v_stg_*`) usando `automate_dv.stage` para generar hash keys (`hk_*`) y hash diffs (`hd_*`).
* [ ] Construir `hub_operadora`, `hub_servicio`, `hub_modalidad`, `hub_tecnologia`, sus `link_*` y `sat_*` usando macros declarativas de `AutomateDV` con `fromyaml`.
* [ ] Agregar pruebas en `schema.yml` (`unique`, `not_null` y `relationships`), y validar con `dbt build --select tag:layer:silver_rv --profiles-dir docker --target dev`.

### Fase 3: Capa Silver Business Vault

* [ ] Crear `as_of_date_mensual.sql` y el primer PIT (`pit_operadora_mensual.sql`) con `automate_dv.pit(...)`.
* [ ] Construir Business Satellites (`bsat_*`) con cálculo de participación de mercado (%), variación MoM/YoY y catálogo de marcas comerciales.
* [ ] Implementar modelos de calidad en `models/dq/` (suma de participaciones $\approx 100\%$, continuidad temporal sin huecos).

### Fase 4: Capa Gold (Information Marts & Power BI)

* [ ] Construir Esquema Estrella en `models/gold/sma/`: `dim_fecha`, `dim_operadora`, `dim_servicio`, `dim_modalidad`, `dim_tecnologia`, `fct_lineas_activas_servicio`, `fct_lineas_activas_modalidad`, `fct_lineas_activas_tecnologia`.
* [ ] Construir la tabla desnormalizada `ml_features_sma` (grano `fecha_corte` + `operadora`).
* [ ] Reconectar el dashboard de Power BI a las tablas Gold de `PRD` en Databricks y documentar el dominio en `docs/models/sma/lineas_activas/model_documentation.md`.

### Fase 5: Ciencia de Datos y MLOps

* [ ] Entrenar modelos de series temporales (Prophet / SARIMAX / XGBoost) leyendo `gold.ml_features_sma` para pronosticar líneas activas y migración tecnológica (2G/3G $\rightarrow$ 4G/5G) a 6-12 meses.
* [ ] Registrar experimentos, parámetros y métricas (RMSE, MAPE) en **MLflow** dentro de Databricks.
* [ ] Escribir predicciones batch en `gold.fct_predicciones_sma` para graficar histórico vs. pronóstico en Power BI.
* [ ] (Opcional Portafolio) Empaquetar el mejor modelo en una API con **FastAPI** y desplegarla en contenedor Docker sobre tu homelab (Portainer).

## 9. Guía de Escalabilidad (Cómo Agregar Nuevos Reportes ARCOTEL)

Para incorporar futuros dominios (ej. *Internet Fijo*, *TV Pagada*, *Telefonía Fija*):

1. Añadir el nuevo bloque de configuración en `config/sources.yml` (sin tocar el código del scraper).
2. Declarar la tabla aterrizada en `models/sources/sources.yml`.
3. Crear la vista Bronze en `models/bronze/<nuevo_dominio>/`.
4. Reutilizar `hub_operadora` existente y crear únicamente los nuevos Hubs (ej. `hub_provincia`), Links y Satellites con `AutomateDV` copiando el patrón `fromyaml` de un modelo hermano.
5. Agregar la nueva `dim_*`/`fct_*` en Gold, validar en `dev` $\rightarrow$ PR a `qas` $\rightarrow$ merge a `prd` y actualizar tests + documentación.