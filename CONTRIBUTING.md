# Guía de Contribución — ARCOTEL Data Platform

Este documento establece los estándares de flujo de trabajo en Git, convenciones de nomenclatura y controles de calidad para contribuir a este proyecto de Ingeniería de Datos (**Python + Databricks + dbt-core + AutomateDV**).

**El objetivo principal de este flujo es garantizar que la rama `main` esté siempre estable y lista para desplegarse en producción (`PRD`).**

## Tabla de Contenidos
1. [Filosofía y Principios](#filosofía-y-principios)
2. [Flujo de Ramas (Trunk-Based Development)](#flujo-de-ramas-trunk-based-development)
3. [Convenciones de Nomenclatura Obligatorias](#convenciones-de-nomenclatura-obligatorias)
   - [Nombres de Ramas](#nombres-de-ramas)
   - [Mensajes de Commit](#mensajes-de-commit)
4. [Proceso de Pull Request (PR)](#proceso-de-pull-request-pr)
5. [Estándares de Calidad y Pruebas](#estándares-de-calidad-y-pruebas)

---

## Filosofía y Principios

* **La rama `main` es sagrada:** Nunca se integra código roto ni sin probar en `main`.
* **Integración Continua:** Se integran cambios pequeños y frecuentes para evitar conflictos complejos.
* **La calidad está automatizada:** GitHub Actions valida la salud técnica del código y los modelos en `QAS`; la revisión humana se enfoca en la lógica de negocio y el modelado Data Vault.
* **Trazabilidad:** Todo cambio debe estar vinculado a un Issue / Task en GitHub Projects (`TASKxxx`).

---

## Flujo de Ramas (Trunk-Based Development)

Adoptamos **Trunk-Based Development**, eliminando ramas de larga duración como `develop` o `qas` (los ambientes `dev`, `qas` y `prd` se aíslan a nivel de esquemas en Databricks, no mediante ramas permanentes).

El flujo estándar es:

1. **Crear un Issue / Task** en GitHub Issues para el cambio a realizar (ej. `TASK001`).
2. **Crear una nueva rama** directamente desde `main` actualizado (`git checkout main && git pull`). **Nunca** desde otra rama feature.
3. **Implementar los cambios** manteniendo el alcance pequeño y enfocado en un único objetivo.
4. **Hacer commits** siguiendo el estándar de Conventional Commits con alcance (*scope*).
5. **Abrir un Pull Request (PR)** hacia `main`. Esto disparará automáticamente el pipeline de CI contra el ambiente **`qas`**.
6. Una vez aprobado y completado el merge, **la rama se elimina automáticamente** y el pipeline de CD despliega los cambios en **`prd`**.

---

## Convenciones de Nomenclatura Obligatorias

### Nombres de Ramas

Las ramas deben seguir estrictamente el formato:
`type/user/(issue-<num>|task-<num>|<num>)-short-description`

* **`type`:**
  * `feat`: Nueva funcionalidad (ej. nuevo dominio ARCOTEL, nuevo Hub/Satélite, nuevo scraper).
  * `fix`: Corrección de un error en código Python o SQL/dbt.
  * `chore`: Tareas de mantenimiento (actualización de dependencias, configuración CI/CD).
  * `refactor`: Mejora de código o SQL sin alterar el comportamiento ni los resultados de negocio.
  * `docs`: Exclusivamente documentación (`README.md`, `PLAN.md`, `model_documentation.md`).
  * `test`: Adición o ajuste de pruebas unitarias o tests de dbt.
* **`user`:** Usuario de GitHub del creador (en minúsculas).
* **`issue-<num> / task-<num> / <num>`:** Identificador del ticket o **GitHub Issue** asociado (ej. `issue-1`, `task-1`, `1` o `TASK001`).
* **`short-description`:** De 2 a 4 palabras en `kebab-case` (minúsculas separadas por guiones).

✅ **Ejemplos Correctos:**
* `feat/jhoan/issue-1-ingesta-arcotel`
* `feat/jhoan/1-lineas-activas`
* `fix/jhoan/issue-14-nulos-operadora`
* `docs/jhoan/task-3-guia-data-vault`
* `chore/jhoan/issue-5-ci-github-actions`

❌ **Ejemplos Incorrectos:**
* `jhoan_branch`
* `feature/lineas_activas` (falta `user`, falta el identificador de issue y usa guion bajo)
* `feat/jhoan/fix-bug` (falta el identificador de issue)

### Mensajes de Commit

Usamos **Conventional Commits** con **scope** (alcance) para que el historial refleje exactamente qué módulo o dominio se modificó.

**Formato:** `type(scope): descripción del cambio`

* **`type`:** Permitidos: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.
* **`scope`:** Dominio, capa o componente afectado en `kebab-case` (ej. `lineas-activas`, `scraper`, `parser`, `silver-rv`, `gold`, `ci`, `mlops`).
* **`descripción`:** En minúsculas, tiempo presente e imperativo, sin punto final.

✅ **Ejemplos Correctos:**
* `feat(lineas-activas): agregar hub_operadora y sat_lineas_servicio`
* `fix(scraper): decodificar parametro src en enlaces de officeapps`
* `refactor(parser): normalizar encabezados a snake_case en memoria`
* `ci(github-actions): agregar ejecucion dbt build en target qas`
* `docs(contributing): definir convenciones de ramas y commits`

❌ **Ejemplos Incorrectos:**
* `Add lineas activas`
* `fix: Corregido el error.`
* `cambios varios`

---

## Proceso de Pull Request (PR)

El PR es el punto de control de calidad antes de llegar a producción:

1. **Vincular el Issue:** Incluir en la descripción `Closes #<numero>` o referencia al `TASKxxx`.
2. **Título claro:** El título del PR debe seguir el formato de Conventional Commits (ej. `feat(lineas-activas): implementar capa silver raw vault`).
3. **Descripción:** Explicar **qué** hace el cambio, **por qué** es necesario y qué modelos/tablas se ven afectados.
4. **Verificar el Pipeline de CI:** El workflow `ci_pr.yml` validará el nombre de la rama, linters y ejecutará `dbt build --target qas`. **Ningún PR puede mergearse si el CI falla.**

---

## Estándares de Calidad y Pruebas

* **Estándar `snake_case`:** Todos los campos de tablas, columnas técnicas (`hk_*`, `hd_*`, `load_date`, `record_source`) y nombres de modelos deben estar en `snake_case` sin tildes.
* **AutomateDV obligatorio:** Los modelos de Raw Vault (`hub_*`, `link_*`, `sat_*`) y PITs deben usar macros de `automate_dv` con bloques `fromyaml`. No escribir SQL de vault manual ni saltar Data Vault hacia Gold.
* **Tests de dbt:** Todo modelo nuevo o modificado debe incluir pruebas en su `schema.yml` (`unique`, `not_null`, `relationships`, `accepted_values`).
* **Validación local obligatoria:** Antes de hacer `git push`, ejecutar siempre en tu ambiente `dev`:
  ```bash
  dbt build --select +tu_modelo --project-dir dbt_project --profiles-dir dbt_project --target dev
  ```