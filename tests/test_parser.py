"""Pruebas unitarias para el módulo ingestion.parser."""

import io
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from ingestion.parser import ExcelParser


def test_to_snake_case():
    parser = ExcelParser()

    assert parser.to_snake_case("Año") == "ano"
    assert parser.to_snake_case("Participación de Mercado (%)") == "participacion_de_mercado"
    assert parser.to_snake_case("Líneas Activas - PosPago") == "lineas_activas_pospago"
    assert parser.to_snake_case("  Espacios  Multiples  ") == "espacios_multiples"
    assert parser.to_snake_case("2G_Tecnología") == "c_2g_tecnologia"


def test_parse_excel_to_dataframe_and_parquet():
    parser = ExcelParser()

    # Crear un Excel sintético en memoria con formato típico gubernamental (filas basura arriba)
    mock_data = [
        ["AGENCIA DE REGULACIÓN Y CONTROL DE LAS TELECOMUNICACIONES", None, None],
        ["DIRECCIÓN DE ESTADÍSTICAS", None, None],
        ["Fecha de corte: 31 de mayo de 2024", None, None],
        ["Año", "Mes", "Operadora", "Líneas Activas", "Participación (%)"],  # Fila de encabezado real (índice 3)
        [2024, "Mayo", "CONECEL S.A.", 8500000, 52.3],
        [2024, "Mayo", "OTECEL S.A.", 4800000, 31.2],
        [2024, "Mayo", "CNT E.P.", 2200000, 16.5],
        ["TOTAL GENERAL", None, None, 15500000, 100.0],  # Fila de total a descartar
        ["Fuente: Operadoras de Servicio Móvil Avanzado", None, None, None, None],  # Fila de pie a descartar
    ]

    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        # Pestaña 1: Portada (debe ignorarse)
        pd.DataFrame([["Portada de Reporte"]]).to_excel(writer, sheet_name="Portada", index=False)
        # Pestaña 2: Datos (debe seleccionarse)
        pd.DataFrame(mock_data).to_excel(writer, sheet_name="1.1.1_Datos", header=False, index=False)

    excel_buffer.seek(0)

    # Parsear
    df = parser.parse_excel_to_dataframe(
        excel_data=excel_buffer,
        source_id="sma_lineas_servicio",
        source_filename="1.1.1-densidad.xlsx",
        sheet_pattern="(?i)datos",
        header_keywords=["ano", "mes", "operadora", "lineas"],
    )

    # Validaciones sobre el DataFrame
    assert len(df) == 3  # 3 operadoras (sin filas de títulos ni totales)
    assert "ano" in df.columns
    assert "mes" in df.columns
    assert "operadora" in df.columns
    assert "lineas_activas" in df.columns
    assert "participacion" in df.columns

    # Validar columnas técnicas de auditoría
    assert "load_date" in df.columns
    assert "record_source" in df.columns
    assert "source_file" in df.columns
    assert df["record_source"].iloc[0] == "arcotel_web_sma_lineas_servicio"
    assert df["source_file"].iloc[0] == "1.1.1-densidad.xlsx"

    # Validar conversión a Parquet
    parquet_buffer = parser.dataframe_to_parquet_buffer(df)
    assert parquet_buffer.getbuffer().nbytes > 0

    # Leer parquet para asegurar integridad binaria
    table = pq.read_table(parquet_buffer)
    assert table.num_rows == 3
    assert "ano" in table.column_names


def test_deduplicate_columns_edge_case():
    parser = ExcelParser()

    # Simular DataFrame con columnas duplicadas estilo ARCOTEL: HSPA, HSPA.1, HSPA (de nuevo)
    mock_data = [
        ["Mes", "CDMA", "GSM", "HSPA", "HSPA", "HSPA"],
        [2024, 10, 20, 30, 40, 50],
    ]
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        pd.DataFrame(mock_data).to_excel(writer, sheet_name="Tecnologia", header=False, index=False)
    excel_buffer.seek(0)

    df = parser.parse_excel_to_dataframe(
        excel_data=excel_buffer,
        source_id="sma_lineas_tecnologia",
        source_filename="test_tecnologia.xlsx",
        header_keywords=["mes", "cdma", "gsm"],
    )

    # Convertir a Parquet para asegurar que pyarrow no lance Duplicate column names
    parquet_buf = parser.dataframe_to_parquet_buffer(df)
    table = pq.read_table(parquet_buf)
    assert len(set(table.column_names)) == len(table.column_names)
    assert "hspa" in table.column_names
    assert "hspa_1" in table.column_names
    assert "hspa_2" in table.column_names


def test_mixed_types_arrow_conversion():
    parser = ExcelParser()

    # Simular una columna 'mes_ano' con tipos mixtos (números enteros de año y strings tipo 'Ene 2009')
    mock_data = [
        ["Mes_Ano", "Lineas"],
        [2008, 1000],
        ["Ene 2009", 1200],
        [None, 1500],
        ["Feb 2009", 1600],
    ]
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        pd.DataFrame(mock_data).to_excel(writer, sheet_name="Datos", header=False, index=False)
    excel_buffer.seek(0)

    df = parser.parse_excel_to_dataframe(
        excel_data=excel_buffer,
        source_id="sma_lineas_tecnologia",
        source_filename="test_mixed.xlsx",
        header_keywords=["mes", "lineas"],
    )

    # Validar que pyarrow no lance ArrowInvalid por tipos mixtos
    parquet_buf = parser.dataframe_to_parquet_buffer(df)
    table = pq.read_table(parquet_buf)
    assert "mes_ano" in table.column_names
    assert table.schema.field("mes_ano").type == pa.string()
