"""
Módulo de Normalización y Conversión de Excels a Parquet.
Limpia tablas complejas de ARCOTEL: detecta automáticamente filas de encabezados reales,
descarta pestañas decorativas, estandariza columnas a snake_case y añade metadatos de auditoría.
"""

import io
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Union

import openpyxl
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class ExcelParser:
    """Procesador y normalizador de archivos Excel de estadísticas públicas."""

    IGNORE_SHEET_PATTERNS = ["(?i)indice", "(?i)índice", "(?i)grafic", "(?i)gráfico", "(?i)portada", "(?i)contenido"]

    def __init__(self):
        pass

    @staticmethod
    def to_snake_case(text: str) -> str:
        """Convierte una cadena a snake_case limpio: sin tildes, minúsculas y caracteres válidos."""
        if not text or not isinstance(text, str):
            return "columna_sin_nombre"

        # Normalizar tildes y caracteres especiales (NFKD)
        nfkd_form = unicodedata.normalize("NFKD", str(text))
        text_without_accents = "".join([c for c in nfkd_form if not unicodedata.combining(c)])

        # Reemplazar eñes si no fueron descompuestas
        text_without_accents = text_without_accents.replace("ñ", "n").replace("Ñ", "N")

        # Convertir caracteres no alfanuméricos a guiones bajos
        clean = re.sub(r"[^a-zA-Z0-9]+", "_", text_without_accents.lower())

        # Colapsar guiones bajos repetidos y recortar extremos
        clean = re.sub(r"_+", "_", clean).strip("_")

        # Asegurar que no empiece con un número
        if clean and clean[0].isdigit():
            clean = f"c_{clean}"

        return clean or "columna"

    def select_best_sheet(
        self, sheet_names: List[str], sheet_pattern: Optional[str] = None
    ) -> str:
        """Selecciona la mejor pestaña de datos descartando portadas, índices y gráficos."""
        # Filtrar pestañas a ignorar
        candidates = [
            s
            for s in sheet_names
            if not any(re.search(p, s) for p in self.IGNORE_SHEET_PATTERNS)
        ]

        if not candidates:
            logger.warning("Todas las pestañas coincidieron con patrones a ignorar. Usando la primera.")
            return sheet_names[0]

        # Si hay patrón deseado, buscar coincidencia
        if sheet_pattern:
            regex = re.compile(sheet_pattern, re.IGNORECASE)
            for sheet in candidates:
                if regex.search(sheet):
                    logger.info(f"Pestaña seleccionada por patrón '{sheet_pattern}': {sheet}")
                    return sheet

        # Si no hay patrón o no hubo coincidencia, tomar la primera candidata válida
        logger.info(f"Pestaña seleccionada por defecto: {candidates[0]}")
        return candidates[0]

    def detect_header_row(
        self, df_raw: pd.DataFrame, keywords: List[str], max_rows_to_scan: int = 15
    ) -> Tuple[int, List[str]]:
        """
        Escanea las primeras filas para identificar cuál es el encabezado real de la tabla
        basándose en la coincidencia con palabras clave esperadas.
        """
        best_row_idx = 0
        best_score = -1
        best_headers: List[str] = []

        clean_keywords = [self.to_snake_case(k) for k in keywords]
        rows_to_scan = min(len(df_raw), max_rows_to_scan)

        for i in range(rows_to_scan):
            row_values = df_raw.iloc[i].dropna().astype(str).tolist()
            normalized_row = [self.to_snake_case(v) for v in row_values]

            # Contar coincidencias con keywords esperadas
            score = 0
            for val in normalized_row:
                if any(kw in val for kw in clean_keywords):
                    score += 1

            # Ponderar también la cantidad de celdas no nulas en la fila
            score += len(row_values) * 0.1

            if score > best_score:
                best_score = score
                best_row_idx = i
                best_headers = normalized_row

        logger.info(
            f"Fila de encabezado detectada en índice {best_row_idx} (score de coincidencias: {best_score:.1f})"
        )
        return best_row_idx, best_headers

    def parse_excel_to_dataframe(
        self,
        excel_data: Union[io.BytesIO, bytes, str],
        source_id: str,
        source_filename: str,
        sheet_pattern: Optional[str] = None,
        header_keywords: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Lee un archivo Excel en memoria, normaliza sus encabezados, limpia filas basura
        y añade columnas técnicas para la arquitectura Medallón / Data Vault.
        """
        buffer = io.BytesIO(excel_data) if isinstance(excel_data, bytes) else excel_data

        # Cargar libro para listar pestañas
        wb = openpyxl.load_workbook(buffer, read_only=True, data_only=True)
        sheet_names = wb.sheetnames
        selected_sheet = self.select_best_sheet(sheet_names, sheet_pattern)
        wb.close()

        # Rebobinar buffer para leer con pandas
        if hasattr(buffer, "seek"):
            buffer.seek(0)

        # Leer primeras filas crudas para detectar encabezado
        df_preview = pd.read_excel(buffer, sheet_name=selected_sheet, header=None, nrows=20)

        keywords = header_keywords or ["anio", "mes", "operadora", "lineas", "total", "participacion"]
        header_row_idx, _ = self.detect_header_row(df_preview, keywords)

        # Rebobinar y leer datos a partir de la fila de encabezado detectada
        if hasattr(buffer, "seek"):
            buffer.seek(0)

        df = pd.read_excel(buffer, sheet_name=selected_sheet, skiprows=header_row_idx)

        # Normalizar nombres de columnas a snake_case
        clean_cols = []
        seen_cols: Dict[str, int] = {}
        for col in df.columns:
            base_col = self.to_snake_case(str(col))
            if base_col in seen_cols:
                seen_cols[base_col] += 1
                clean_cols.append(f"{base_col}_{seen_cols[base_col]}")
            else:
                seen_cols[base_col] = 0
                clean_cols.append(base_col)

        df.columns = clean_cols

        # Eliminar filas completamente vacías
        df.dropna(how="all", inplace=True)

        # Descartar filas que sean notas al pie o totales de resumen al final
        # (ej. filas donde casi todas las columnas son nulas o empiezan con "fuente", "nota", "total")
        first_col = df.columns[0]
        df = df[
            ~df[first_col]
            .astype(str)
            .str.lower()
            .str.contains(r"^(fuente|nota|elaborad|total general)", regex=True, na=False)
        ]

        # Inyectar columnas técnicas de auditoría para la capa Bronze
        now_utc = datetime.now(timezone.utc)
        df["load_date"] = now_utc
        df["record_source"] = f"arcotel_web_{source_id}"
        df["source_file"] = source_filename

        logger.info(
            f"Excel procesado exitosamente: {len(df)} filas, {len(df.columns)} columnas. Pestaña: '{selected_sheet}'"
        )
        return df

    def dataframe_to_parquet_buffer(self, df: pd.DataFrame) -> io.BytesIO:
        """Convierte un DataFrame normalizado a un buffer en memoria en formato Parquet."""
        parquet_buffer = io.BytesIO()
        table = pa.Table.from_pandas(df, preserve_index=False)
        pq.write_table(table, parquet_buffer, compression="snappy")
        parquet_buffer.seek(0)
        return parquet_buffer
