"""
Módulo de Carga a Databricks DBFS y Almacenamiento Local (Idempotente).
Permite subir archivos Parquet a Databricks (/FileStore/{ENV}/bronze/...) mediante la API REST,
o a un directorio local en ambiente de desarrollo, garantizando no duplicar archivos existentes.
"""

import base64
import io
import logging
import os
from pathlib import Path
from typing import Optional, Union

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class DatabricksUploader:
    """Cliente para la subida de datos a DBFS (Databricks File System) o almacenamiento local."""

    def __init__(
        self,
        host: Optional[str] = None,
        token: Optional[str] = None,
        env: str = "dev",
        local_fallback_dir: str = "data/bronze",
    ):
        self.host = (host or os.getenv("DATABRICKS_HOST", "")).rstrip("/")
        self.token = token or os.getenv("DATABRICKS_TOKEN", "")
        self.env = env or os.getenv("ENV", "dev")
        self.local_fallback_dir = local_fallback_dir

        self.is_cloud_ready = bool(
            self.host and self.token and not self.token.startswith("dapi_tu_token")
        )

        if self.is_cloud_ready:
            logger.info(f"Databricks DBFS configurado hacia: {self.host} (Ambiente: {self.env})")
        else:
            logger.info(
                f"Databricks no configurado o credenciales de ejemplo. Se usará almacenamiento local en: {self.local_fallback_dir}"
            )

    def file_exists_in_dbfs(self, dbfs_path: str) -> bool:
        """Verifica si un archivo ya existe en DBFS para garantizar idempotencia."""
        if not self.is_cloud_ready:
            return False

        url = f"{self.host}/api/2.0/dbfs/get-status"
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {"path": dbfs_path.replace("dbfs:", "")}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def upload_to_dbfs(
        self,
        file_buffer: Union[io.BytesIO, bytes],
        destination_dbfs_path: str,
        overwrite: bool = True,
    ) -> bool:
        """
        Sube un buffer a DBFS mediante la API REST de Databricks.
        Soporta archivos pequeños (<1MB) con 'put' y grandes con streaming en bloques.
        """
        raw_bytes = file_buffer.getvalue() if isinstance(file_buffer, io.BytesIO) else file_buffer
        clean_path = destination_dbfs_path.replace("dbfs:", "")
        headers = {"Authorization": f"Bearer {self.token}"}

        # Subida simple (< 1 MB)
        if len(raw_bytes) <= 1024 * 1024:
            url = f"{self.host}/api/2.0/dbfs/put"
            payload = {
                "path": clean_path,
                "contents": base64.b64encode(raw_bytes).decode("utf-8"),
                "overwrite": overwrite,
            }
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            logger.info(f"Archivo subido exitosamente a DBFS: {destination_dbfs_path}")
            return True

        # Subida en bloques (>= 1 MB)
        create_url = f"{self.host}/api/2.0/dbfs/create"
        res = requests.post(
            create_url, headers=headers, json={"path": clean_path, "overwrite": overwrite}, timeout=30
        )
        res.raise_for_status()
        handle = res.json().get("handle")

        chunk_size = 1024 * 1024  # 1 MB por bloque
        add_block_url = f"{self.host}/api/2.0/dbfs/add-block"
        for i in range(0, len(raw_bytes), chunk_size):
            chunk = raw_bytes[i : i + chunk_size]
            b_res = requests.post(
                add_block_url,
                headers=headers,
                json={"handle": handle, "data": base64.b64encode(chunk).decode("utf-8")},
                timeout=30,
            )
            b_res.raise_for_status()

        close_url = f"{self.host}/api/2.0/dbfs/close"
        c_res = requests.post(close_url, headers=headers, json={"handle": handle}, timeout=30)
        c_res.raise_for_status()
        logger.info(f"Archivo grande ({len(raw_bytes) / 1024 / 1024:.2f} MB) subido a DBFS: {destination_dbfs_path}")
        return True

    def upload_to_local(
        self, file_buffer: Union[io.BytesIO, bytes], relative_path: str
    ) -> str:
        """Guarda el archivo en el sistema de archivos local para desarrollo y pruebas."""
        raw_bytes = file_buffer.getvalue() if isinstance(file_buffer, io.BytesIO) else file_buffer
        target_path = Path(self.local_fallback_dir) / self.env / relative_path.lstrip("/")
        target_path.parent.mkdir(parents=True, exist_ok=True)

        with open(target_path, "wb") as f:
            f.write(raw_bytes)

        logger.info(f"Archivo guardado localmente: {target_path}")
        return str(target_path)

    def upload(
        self,
        file_buffer: Union[io.BytesIO, bytes],
        destination_path: str,
        domain: str,
        filename: str,
        overwrite: bool = True,
    ) -> str:
        """
        Punto de entrada unificado: sube a DBFS si las credenciales están presentes,
        o a almacenamiento local si se ejecuta en modo desarrollo/offline.
        """
        # Formatear ruta final con el ambiente (dev | qas | prd)
        final_dbfs_path = destination_path.format(env=self.env).rstrip("/") + f"/{filename}"

        if self.is_cloud_ready:
            if not overwrite and self.file_exists_in_dbfs(final_dbfs_path):
                logger.info(f"El archivo ya existe en DBFS. Omitiendo por idempotencia: {final_dbfs_path}")
                return final_dbfs_path

            self.upload_to_dbfs(file_buffer, final_dbfs_path, overwrite=overwrite)
            return final_dbfs_path
        else:
            relative_local = f"{domain}/{filename}"
            return self.upload_to_local(file_buffer, relative_local)
