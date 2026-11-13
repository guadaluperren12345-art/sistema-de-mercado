# Sistema de Mercado

Sistema de gestión para un mercado (stock, ventas, cuentas, caja y facturación electrónica), accesible desde computadora y celular.

Documentación completa: [`docs/documentacion.md`](docs/documentacion.md)

## Arquitectura

| Capa | Tecnología | Contenedor | URL |
| --- | --- | --- | --- |
| Frontend | React (Vite) | `mercado-frontend` | http://localhost:5173 |
| Backend (API) | Python + Django REST Framework | `mercado-backend` | http://localhost:8000 |
| Base de datos | SQL Server 2022 | `mercado-db` | `localhost,1433` |

## Requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Git

No hace falta instalar Python, Node ni SQL Server: todo corre dentro de Docker.

## Cómo levantar el sistema

1. Copiar `.env.example` como `.env` y completar las contraseñas (solo la primera vez).
2. En la carpeta del proyecto, ejecutar:

   ```powershell
   docker compose up -d --build
   ```

3. Crear el primer usuario dueño (administrador), solo la primera vez:

   ```powershell
   docker compose exec backend python manage.py createsuperuser
   ```

4. Abrir http://localhost:5173 e iniciar sesión.

Los demás usuarios (otros dueños, encargados y empleados) los da de alta un dueño desde **Inicio → Usuarios → Nuevo usuario**. Desde la misma pantalla se los da de baja o se los reactiva. Cada usuario nuevo debe cambiar su contraseña en el primer ingreso.

## Pruebas

```powershell
docker compose exec backend python manage.py test usuarios
```

## Comandos útiles

```powershell
docker compose ps                    # ver el estado de los contenedores
docker compose logs -f backend       # ver los logs del backend
docker compose stop                  # detener todo (los datos se conservan)
docker compose up -d                 # volver a iniciar
docker compose exec backend python manage.py <comando>   # comandos de Django
docker compose down                  # eliminar contenedores (los datos quedan en el volumen)
```

## Estructura

```text
sistema-mercado/
├── docker-compose.yml   # define los 3 contenedores
├── .env                 # contraseñas (no se sube a git)
├── backend/             # API en Django
├── frontend/            # aplicación React
└── docs/                # documentación
```
