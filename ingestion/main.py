"""
Orquestador Principal del Pipeline de Ingesta ARCOTEL.
Lee la configuración metadata-driven (config/sources.yml), descubre los archivos Excel en la web,
los estandariza a formato Parquet y los carga a la capa Bronze en Databricks DBFS o almacenamiento local.
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import yaml
from dotenv import load_dotenv

from ingestion.databricks_uploader import DatabricksUploader
from ingestion.parser import ExcelParser
from ingestion.scraper import ArcotelScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ingestion.main")


def load_config(config_path: str = "config/sources.yml") -> Dict[str, Any]:
    """Carga y valida el archivo de configuración YAML de fuentes."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Archivo de configuración no encontrado: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "sources" not in data:
        raise ValueError(f"Estructura inválida en {config_path}: debe contener una clave 'sources'")

    return data


def run_pipeline(
    env: str = "dev",
    source_id_filter: str = None,
    config_path: str = "config/sources.yml",
    force_local: bool = False,
    dry_run: bool = False,
) -> None:
    """Ejecuta el ciclo de vida completo de ingesta para las fuentes configuradas."""
    start_time = time.time()
    load_dotenv()  # Cargar variables de entorno desde .env si existe

    logger.info("=" * 70)
    logger.info(f"INICIANDO PIPELINE DE INGESTA ARCOTEL — AMBIENTE: {env.upper()}")
    logger.info("=" * 70)

    config = load_config(config_path)
    sources: List[Dict[str, Any]] = config["sources"]

    if source_id_filter:
        sources = [s for s in sources if s.get("id") == source_id_filter]
        if not sources:
            logger.error(f"No se encontró la fuente con id: '{source_id_filter}'")
            return

    scraper = ArcotelScraper()
    parser = ExcelParser()
    uploader = DatabricksUploader(
        env=env,
        local_fallback_dir="data/bronze" if force_local else None,
    )

    total_processed = 0
    total_errors = 0

    for src in sources:
        src_id = src["id"]
        src_domain = src["domain"]
        portal_url = src["portal_url"]
        link_pattern = src.get("link_pattern")
        sheet_pattern = src.get("sheet_pattern")
        header_keywords = src.get("header_keywords", [])
        dbfs_path_template = src.get(
            "dbfs_path_template", "dbfs:/FileStore/{env}/bronze/arcotel/{domain}/{id}/"
        )

        logger.info("-" * 60)
        logger.info(f"Procesando Fuente: [{src_id}] — {src.get('title', '')}")
        logger.info(f"URL Objetivo: {portal_url}")

        try:
            # 1. Scraping del DOM
            html = scraper.fetch_html(portal_url)
            links = scraper.extract_download_links(html, base_url=portal_url, link_pattern=link_pattern)

            if not links:
                logger.warning(f"No se encontraron enlaces que coincidan para {src_id}")
                continue

            logger.info(f"Descargas candidatas encontradas: {len(links)}")

            # 2. Descargar y procesar cada archivo encontrado
            for item in links:
                file_url = item["url"]
                original_filename = item["filename"]

                # Generar nombre destino en Parquet
                parquet_filename = Path(original_filename).stem + ".parquet"

                logger.info(f"Descargando: {original_filename} ({file_url})")
                excel_buffer = scraper.download_file(file_url)

                if dry_run:
                    logger.info(f"[DRY-RUN] Simulación completa para {parquet_filename}. No se guardará.")
                    continue

                # 3. Parsear Excel en memoria y convertir a Parquet
                logger.info(f"Parseando y normalizando Excel en memoria...")
                df = parser.parse_excel_to_dataframe(
                    excel_data=excel_buffer,
                    source_id=src_id,
                    source_filename=original_filename,
                    sheet_pattern=sheet_pattern,
                    header_keywords=header_keywords,
                )

                parquet_buffer = parser.dataframe_to_parquet_buffer(df)

                # 4. Cargar a DBFS o almacenamiento local
                dest_path = uploader.upload(
                    file_buffer=parquet_buffer,
                    destination_path=dbfs_path_template,
                    domain=src_domain,
                    filename=parquet_filename,
                    overwrite=True,
                )

                logger.info(f"Destino final aterrizado: {dest_path}")
                total_processed += 1

        except Exception as e:
            logger.error(f"Error procesando fuente {src_id}: {e}", exc_info=True)
            total_errors += 1

    elapsed = time.time() - start_time
    logger.info("=" * 70)
    logger.info(
        f"RESUMEN DE INGESTA: {total_processed} archivos procesados con éxito | "
        f"{total_errors} errores | Tiempo total: {elapsed:.2f}s"
    )
    logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Pipeline de Ingesta ARCOTEL a Delta Lake / DBFS")
    parser.add_argument(
        "--env",
        default=os.getenv("ENV", "dev"),
        choices=["dev", "qas", "prd"],
        help="Ambiente de ejecución (dev | qas | prd)",
    )
    parser.add_argument(
        "--source",
        dest="source_id",
        default=None,
        help="Filtrar por ID específico de fuente en config/sources.yml",
    )
    parser.add_argument(
        "--config",
        default="config/sources.yml",
        help="Ruta al catálogo de configuración YAML",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Forzar almacenamiento local en ./data/bronze sin conectar a Databricks",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ejecutar descubrimiento y descarga sin escribir destino final",
    )

    args = parser.parse_args()
    run_pipeline(
        env=args.env,
        source_id_filter=args.source_id,
        config_path=args.config,
        force_local=args.local,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
