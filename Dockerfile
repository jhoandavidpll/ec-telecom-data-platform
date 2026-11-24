FROM python:3.12-slim

# Evitar buffering de salida y archivos .pyc
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Instalar herramientas básicas del sistema (git requerido para paquetes dbt)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo
WORKDIR /usr/app/telecom_platform

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copiar el código del proyecto
COPY . /usr/app/telecom_platform

# Variable de entorno por defecto
ENV ENV=dev

# Comando por defecto: resumen de ayuda
CMD ["python", "-m", "pipelines.arcotel.main", "--help"]
