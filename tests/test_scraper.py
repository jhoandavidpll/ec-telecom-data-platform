"""Pruebas unitarias para el módulo ingestion.scraper."""

from ingestion.scraper import ArcotelScraper


def test_unwrap_officeapps_url():
    scraper = ArcotelScraper()

    # Caso 1: Enlace envuelto por Office Apps
    wrapped_url = (
        "https://view.officeapps.live.com/op/view.aspx?src="
        "https%3A%2F%2Fwww.arcotel.gob.ec%2Fwp-content%2Fuploads%2F2024%2F05%2F1.1.1-lineas.xlsx"
    )
    expected = "https://www.arcotel.gob.ec/wp-content/uploads/2024/05/1.1.1-lineas.xlsx"
    assert scraper.unwrap_officeapps_url(wrapped_url) == expected

    # Caso 2: Enlace normal sin envolver
    direct_url = "https://www.arcotel.gob.ec/wp-content/uploads/2024/05/1.1.1-lineas.xlsx"
    assert scraper.unwrap_officeapps_url(direct_url) == direct_url


def test_extract_download_links_from_mock_html():
    scraper = ArcotelScraper()
    mock_html = """
    <html>
        <body>
            <div class="content">
                <h2>Servicio Móvil Avanzado</h2>
                <a href="https://view.officeapps.live.com/op/view.aspx?src=https%3A%2F%2Fwww.arcotel.gob.ec%2Fwp-content%2Fuploads%2F2024%2F1.1.1-densidad.xlsx">
                    1.1.1 Densidad y Participación de Mercado
                </a>
                <a href="/wp-content/uploads/2024/1.1.2-modalidad.xlsx">
                    1.1.2 Líneas por Modalidad
                </a>
                <a href="https://www.arcotel.gob.ec/otra-pagina/">
                    Página informativa (no excel)
                </a>
                <a href="https://www.arcotel.gob.ec/docs/informe.pdf">
                    Informe PDF
                </a>
            </div>
        </body>
    </html>
    """
    base_url = "https://www.arcotel.gob.ec/lineas-activas/"

    # Sin filtro de regex: debe extraer los 2 excels
    all_links = scraper.extract_download_links(mock_html, base_url=base_url)
    assert len(all_links) == 2
    assert all_links[0]["filename"] == "1.1.1-densidad.xlsx"
    assert all_links[1]["filename"] == "1.1.2-modalidad.xlsx"
    assert all_links[1]["url"] == "https://www.arcotel.gob.ec/wp-content/uploads/2024/1.1.2-modalidad.xlsx"

    # Con filtro regex para 1.1.1
    pattern_111 = r"(?i)(?=.*1\.1\.1).*\.xlsx?"
    filtered_links = scraper.extract_download_links(mock_html, base_url=base_url, link_pattern=pattern_111)
    assert len(filtered_links) == 1
    assert filtered_links[0]["filename"] == "1.1.1-densidad.xlsx"
