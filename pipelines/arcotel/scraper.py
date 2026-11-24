"""
Módulo de Web Scraping para ARCOTEL (Ecuador).
Descubre y descarga dinámicamente archivos Excel publicados en el portal web de ARCOTEL,
resolviendo redirecciones, envoltorios de Office Apps y variabilidad de rutas en WordPress.
"""

import io
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class ArcotelScraper:
    """Rastreador web especializado en el portal de estadísticas públicas de ARCOTEL."""

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(self, timeout: int = 30, user_agent: Optional[str] = None):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent or self.DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            }
        )

    def fetch_html(self, url: str) -> str:
        """Descarga el contenido HTML de una página web con reintentos y validación."""
        logger.info(f"Conectando a portal ARCOTEL: {url}")
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or "utf-8"
            return response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al descargar HTML desde {url}: {e}")
            raise

    @staticmethod
    def unwrap_officeapps_url(raw_url: str) -> str:
        """
        Extrae la URL real al archivo .xlsx si el enlace está envuelto por el visor web de Office:
        https://view.officeapps.live.com/op/view.aspx?src=https%3A%2F%2Fwww.arcotel.gob.ec%2F...
        """
        if "officeapps.live.com" in raw_url and "src=" in raw_url:
            parsed = urlparse(raw_url)
            query_params = parse_qs(parsed.query)
            if "src" in query_params and query_params["src"]:
                unwrapped = unquote(query_params["src"][0])
                logger.debug(f"Desenvolviendo enlace OfficeApps: {raw_url} -> {unwrapped}")
                return unwrapped
        return raw_url

    def extract_download_links(
        self, html_content: str, base_url: str, link_pattern: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Parsea el DOM HTML buscando todos los enlaces a archivos Excel (.xlsx / .xls).
        Filtra opcionalmente por una expresión regular y normaliza las URLs a absolutas.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        matched_links: List[Dict[str, str]] = []
        regex = re.compile(link_pattern, re.IGNORECASE) if link_pattern else None

        for anchor in soup.find_all("a", href=True):
            raw_href = anchor["href"].strip()
            anchor_text = anchor.get_text(strip=True)

            # Desenvolver visores de Office si aplica
            clean_url = self.unwrap_officeapps_url(raw_href)

            # Resolver URLs relativas
            absolute_url = urljoin(base_url, clean_url)

            # Verificar si apunta a una hoja de cálculo
            is_excel = any(
                absolute_url.lower().endswith(ext) or ext in absolute_url.lower()
                for ext in [".xlsx", ".xls"]
            )

            if not is_excel:
                continue

            # Validar patrón si se especificó
            search_target = f"{absolute_url} {anchor_text}"
            if regex and not regex.search(search_target):
                continue

            # Extraer nombre del archivo del path
            path = urlparse(absolute_url).path
            filename = path.split("/")[-1] if "/" in path else "archivo.xlsx"

            matched_links.append(
                {
                    "url": absolute_url,
                    "filename": filename,
                    "text": anchor_text,
                }
            )

        logger.info(
            f"Se encontraron {len(matched_links)} enlaces de descarga válidos (filtro: '{link_pattern}')"
        )
        return matched_links

    def download_file(self, file_url: str) -> io.BytesIO:
        """Descarga un archivo directamente a un buffer en memoria (io.BytesIO)."""
        logger.info(f"Descargando archivo en memoria: {file_url}")
        try:
            response = self.session.get(file_url, timeout=self.timeout)
            response.raise_for_status()
            buffer = io.BytesIO(response.content)
            logger.info(f"Descarga exitosa ({len(response.content) / 1024:.2f} KB): {file_url}")
            return buffer
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al descargar archivo desde {file_url}: {e}")
            raise
