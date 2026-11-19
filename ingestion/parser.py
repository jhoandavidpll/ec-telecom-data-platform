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

    def build_multilevel_columns(
        self, row_top: pd.Series, row_sub: pd.Series, num_cols: int
    ) -> List[str]:
        """
        Combina una cabecera jerárquica de 2 filas:
        Fila Superior (Operadora / Entidad) + Fila Inferior (Servicio / Tecnología / Modalidad).
        Propaga los valores combinados (ffill) y asegura nombres semánticos únicos.
        """
        s_top = pd.Series(row_top).iloc[:num_cols].ffill()
        s_sub = pd.Series(row_sub).iloc[:num_cols]

        combined = []
        used = set()

        for t_val, s_val in zip(s_top, s_sub):
            t_clean = self.to_snake_case(str(t_val)) if pd.notna(t_val) and str(t_val).strip() else ""
            s_clean = self.to_snake_case(str(s_val)) if pd.notna(s_val) and str(s_val).strip() else ""

            # Simplificar nombres de empresas largas (ej. conecel_s_a -> conecel, cnt_ep -> cnt)
            t_clean = re.sub(r"_(s_a|ep|s_a_s|e_p)$", "", t_clean)

            if t_clean and s_clean:
                if t_clean in s_clean:
                    cand = s_clean
                elif s_clean in t_clean:
                    cand = t_clean
                else:
                    cand = f"{t_clean}_{s_clean}"
            elif t_clean:
                cand = t_clean
            elif s_clean:
                cand = s_clean
            else:
                cand = "col"

            # Garantizar unicidad
            root = re.sub(r"_\d+$", "", cand)
            final = root
            counter = 1
            while final in used:
                final = f"{root}_{counter}"
                counter += 1
            used.add(final)
            combined.append(final)

        return combined

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
        df_preview = pd.read_excel(buffer, sheet_name=selected_sheet, header=None, nrows=25)

        keywords = header_keywords or ["anio", "mes", "operadora", "lineas", "total", "participacion"]
        header_row_idx, _ = self.detect_header_row(df_preview, keywords)

        # Verificar si la fila siguiente corresponde a un segundo nivel de encabezado (servicios / tecnologías)
        is_two_level = False
        sub_row_idx = header_row_idx + 1
        if sub_row_idx < len(df_preview):
            row_sub_vals = df_preview.iloc[sub_row_idx].dropna().astype(str).tolist()
            normalized_sub = [self.to_snake_case(v) for v in row_sub_vals]
            sub_keywords = [
                "telefonia", "internet", "datos", "prepago", "pospago",
                "ttup", "2g", "3g", "4g", "5g", "gsm", "cdma", "umts", "lte", "hspa"
            ]
            matches = sum(1 for val in normalized_sub if any(sk in val for sk in sub_keywords))
            # Si hay 2 o más subcolumnas típicas reconocidas, es una cabecera jerárquica
            if matches >= 2:
                is_two_level = True
                logger.info(
                    f"Detectada cabecera jerárquica multinivel (2 filas) en índices {header_row_idx} y {sub_row_idx}"
                )

        # Rebobinar y leer datos a partir de la fila de datos
        if hasattr(buffer, "seek"):
            buffer.seek(0)

        if is_two_level:
            # Leer datos saltando ambas filas de encabezado
            df = pd.read_excel(buffer, sheet_name=selected_sheet, skiprows=header_row_idx + 2, header=None)
            clean_cols = self.build_multilevel_columns(
                df_preview.iloc[header_row_idx], df_preview.iloc[sub_row_idx], num_cols=len(df.columns)
            )
            df.columns = clean_cols
        else:
            df = pd.read_excel(buffer, sheet_name=selected_sheet, skiprows=header_row_idx)

            # Normalizar nombres de columnas a snake_case garantizando unicidad absoluta
            clean_cols = []
            used_names = set()
            for col in df.columns:
                base_col = self.to_snake_case(str(col))
                # Quitar sufijos numéricos previos generados por pandas (ej. .1, _1) para agrupar raíces
                base_root = re.sub(r"_\d+$", "", base_col)
                candidate = base_root
                counter = 1
                while candidate in used_names:
                    candidate = f"{base_root}_{counter}"
                    counter += 1
                used_names.add(candidate)
                clean_cols.append(candidate)

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
            .str.contains(r"^(?:fuente|nota|elaborad|total general)", regex=True, na=False)
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

        # Sanear columnas de tipo object (mixtas) para evitar que PyArrow falle infiriendo tipos conflictivos
        # (ej. columnas con años numéricos mezclados con meses de texto como 'Ene 2009')
        df_clean = df.copy()
        for col in df_clean.select_dtypes(include=["object"]).columns:
            df_clean[col] = df_clean[col].apply(
                lambda x: str(int(x)) if isinstance(x, float) and x.is_integer() else (str(x) if pd.notna(x) else None)
            )

        table = pa.Table.from_pandas(df_clean, preserve_index=False)
        pq.write_table(table, parquet_buffer, compression="snappy")
        parquet_buffer.seek(0)
        return parquet_buffer
