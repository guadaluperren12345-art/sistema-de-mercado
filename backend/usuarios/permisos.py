"""Permisos por rol para la API (RF-17).

Se usan en las vistas con `permission_classes = [EsAdministrador]`, etc.
La API verifica el rol en cada petición, aunque el frontend oculte las opciones.
"""

from rest_framework.permissions import BasePermission


class PasswordAlDia(BasePermission):
    """RF-14: quien debe cambiar su contraseña no puede usar el resto de la API.

    Las vistas que sí se permiten (ver mis datos, cambiar contraseña, salir)
    declaran `permitir_password_pendiente = True`.
    """

    message = "Debe cambiar su contraseña antes de continuar."

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated) or getattr(view, "permitir_password_pendiente", False):
            return True
        return not u.debe_cambiar_password


class EsAdministrador(BasePermission):
    message = "Solo los dueños (administradores) pueden hacer esta operación."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.es_administrador)


class GestionaClientes(BasePermission):
    """Alta, corrección y baja de clientes: los dueños y los encargados que un dueño autorizó (RF-96)."""

    message = "Solo los dueños y los encargados autorizados pueden cargar o cambiar clientes."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.gestiona_clientes)


class EsEncargadoOAdministrador(BasePermission):
    message = "Solo encargados y dueños pueden hacer esta operación."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.es_administrador or u.es_encargado))
