from django.db import connection
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def estado(request):
    """GET /api/estado/ — verifica que la API funciona y que llega a SQL Server."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT @@VERSION, DB_NAME()")
            version, base = cursor.fetchone()
        db = {"conectada": True, "base": base, "version": version.splitlines()[0]}
    except Exception as error:  # noqa: BLE001 - se informa cualquier fallo de conexión
        db = {"conectada": False, "error": str(error)}

    return Response({"api": "ok", "sistema": "Sistema de Mercado", "base_de_datos": db})
