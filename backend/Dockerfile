FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ACCEPT_EULA=Y

# Driver ODBC de Microsoft para que Python (pyodbc) pueda conectarse a SQL Server
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg ca-certificates \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb -o /tmp/mspkg.deb \
    && dpkg -i /tmp/mspkg.deb \
    && rm /tmp/mspkg.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends msodbcsql18 unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Al iniciar: espera a SQL Server, aplica las migraciones pendientes y levanta la API
CMD ["sh", "-c", "python esperar_db.py && python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:8000"]
