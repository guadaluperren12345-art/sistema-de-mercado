"""Panel de Django (/admin/): permite a los dueños crear usuarios
mientras se desarrolla la pantalla de gestión de usuarios."""

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth.password_validation import validate_password

from .models import CambioUsuario, RegistroAcceso, Rol, Usuario


class UsuarioCrearForm(forms.ModelForm):
    password1 = forms.CharField(label="Contraseña inicial", widget=forms.PasswordInput)

    class Meta:
        model = Usuario
        fields = ["nombre_usuario", "nombre", "apellido", "dni", "email", "rol"]

    def clean_password1(self):
        password = self.cleaned_data["password1"]
        validate_password(password)
        return password

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.set_password(self.cleaned_data["password1"])
        usuario.debe_cambiar_password = True  # RF-14: la cambia en su primer ingreso
        if commit:
            usuario.save()
        return usuario


class UsuarioEditarForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(label="Contraseña")

    class Meta:
        model = Usuario
        fields = "__all__"


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    add_form = UsuarioCrearForm
    form = UsuarioEditarForm
    ordering = ["nombre_usuario"]
    list_display = ["nombre_usuario", "nombre", "apellido", "rol", "activo", "esta_bloqueado", "last_login"]
    list_filter = ["rol", "activo"]
    search_fields = ["nombre_usuario", "nombre", "apellido", "dni"]
    readonly_fields = ["last_login", "fecha_creacion", "creado_por"]
    filter_horizontal = []
    actions = ["desbloquear"]
    fieldsets = [
        (None, {"fields": ["nombre_usuario", "password"]}),
        ("Datos personales", {"fields": ["nombre", "apellido", "dni", "email"]}),
        ("Acceso", {"fields": ["rol", "activo", "debe_cambiar_password", "intentos_fallidos", "bloqueado_hasta"]}),
        ("Registro", {"fields": ["last_login", "fecha_creacion", "creado_por"]}),
    ]
    add_fieldsets = [
        (None, {"fields": ["nombre_usuario", "password1", "nombre", "apellido", "dni", "email", "rol"]}),
    ]

    @admin.display(boolean=True, description="Bloqueado")
    def esta_bloqueado(self, obj):
        return obj.esta_bloqueado

    @admin.action(description="Desbloquear usuarios seleccionados")
    def desbloquear(self, request, queryset):
        for usuario in queryset:
            usuario.desbloquear()

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ["nombre", "descripcion"]


@admin.register(CambioUsuario)
class CambioUsuarioAdmin(admin.ModelAdmin):
    """RF-19 / RNF-07: historial de altas y bajas, de solo lectura."""

    list_display = ["fecha_hora", "accion", "usuario", "realizado_por", "detalle"]
    list_filter = ["accion"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RegistroAcceso)
class RegistroAccesoAdmin(admin.ModelAdmin):
    """RNF-07: el historial de accesos es de solo lectura."""

    list_display = ["fecha_hora", "tipo", "nombre_usuario_ingresado", "exitoso", "ip"]
    list_filter = ["tipo", "exitoso"]
    search_fields = ["nombre_usuario_ingresado"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
