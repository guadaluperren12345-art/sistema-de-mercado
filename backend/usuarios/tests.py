"""Pruebas del módulo de acceso.

Ejecutar con:  docker compose exec backend python manage.py test usuarios
"""

from django.utils import timezone
from rest_framework.test import APITestCase

from .models import CambioUsuario, RegistroAcceso, Rol, Usuario

PASSWORD = "Mercado2026"


class LoginTests(APITestCase):
    def setUp(self):
        self.empleado = Usuario.objects.create_user(
            "jperez", PASSWORD, nombre="Juan", apellido="Pérez", dni="30111222",
            rol=Rol.objects.get(nombre=Rol.EMPLEADO), debe_cambiar_password=False,
        )

    def login(self, usuario="jperez", password=PASSWORD):
        return self.client.post("/api/auth/login/", {"nombre_usuario": usuario, "password": password})

    def test_login_correcto_devuelve_tokens_y_rol(self):  # RF-01, RF-03
        r = self.login()
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)
        self.assertIn("refresh", r.data)
        self.assertEqual(r.data["usuario"]["rol"], "Empleado")
        self.assertTrue(RegistroAcceso.objects.filter(usuario=self.empleado, tipo="LOGIN", exitoso=True).exists())

    def test_password_incorrecta_mensaje_generico(self):  # RF-02
        r = self.login(password="otra1234")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.data["detail"], "Usuario o contraseña incorrectos.")

    def test_usuario_inexistente_mismo_mensaje(self):  # RF-02
        r = self.login(usuario="noexiste")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.data["detail"], "Usuario o contraseña incorrectos.")
        self.assertTrue(RegistroAcceso.objects.filter(nombre_usuario_ingresado="noexiste", exitoso=False).exists())

    def test_bloqueo_despues_de_5_intentos(self):  # RF-07
        for _ in range(4):
            self.assertEqual(self.login(password="mal12345").status_code, 401)
        r = self.login(password="mal12345")
        self.assertEqual(r.status_code, 403)
        self.assertIn("bloqueada", r.data["detail"])
        # Ni con la contraseña correcta puede entrar mientras está bloqueado
        self.assertEqual(self.login().status_code, 403)
        # Al desbloquear, vuelve a entrar
        self.empleado.refresh_from_db()
        self.empleado.desbloquear()
        self.assertEqual(self.login().status_code, 200)

    def test_bloqueo_vencido_permite_entrar(self):
        self.empleado.bloqueado_hasta = timezone.now() - timezone.timedelta(minutes=1)
        self.empleado.save()
        self.assertEqual(self.login().status_code, 200)

    def test_usuario_desactivado_no_entra(self):  # RN-05
        self.empleado.activo = False
        self.empleado.save()
        self.assertEqual(self.login().status_code, 401)

    def test_yo_requiere_token(self):
        self.assertEqual(self.client.get("/api/auth/yo/").status_code, 401)
        token = self.login().data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        r = self.client.get("/api/auth/yo/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["nombre_usuario"], "jperez")

    def test_refresh_rota_y_no_se_puede_reusar(self):  # RF-06
        datos = self.login().data
        r = self.client.post("/api/auth/refresh/", {"refresh": datos["refresh"]})
        self.assertEqual(r.status_code, 200)
        self.assertIn("refresh", r.data)  # token nuevo
        # El token viejo ya no sirve
        self.assertEqual(self.client.post("/api/auth/refresh/", {"refresh": datos["refresh"]}).status_code, 401)
        # El nuevo sí
        self.assertEqual(self.client.post("/api/auth/refresh/", {"refresh": r.data["refresh"]}).status_code, 200)

    def test_empleado_con_password_pendiente_no_usa_otras_vistas(self):  # RF-14
        self.empleado.debe_cambiar_password = True
        self.empleado.save()
        token = self.login().data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get("/api/auth/yo/").status_code, 200)  # permitido

    def test_logout_invalida_refresh(self):  # RF-05
        datos = self.login().data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {datos['access']}")
        self.assertEqual(self.client.post("/api/auth/logout/", {"refresh": datos["refresh"]}).status_code, 204)
        r = self.client.post("/api/auth/refresh/", {"refresh": datos["refresh"]})
        self.assertEqual(r.status_code, 401)


class CambiarPasswordTests(APITestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            "nuevo", PASSWORD, nombre="Ana", apellido="Gómez", dni="40111222",
        )  # debe_cambiar_password=True por defecto
        datos = self.client.post("/api/auth/login/", {"nombre_usuario": "nuevo", "password": PASSWORD}).data
        self.assertTrue(datos["usuario"]["debe_cambiar_password"])
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {datos['access']}")

    def cambiar(self, actual, nueva):
        return self.client.post("/api/auth/cambiar-password/", {"password_actual": actual, "password_nueva": nueva})

    def test_cambio_correcto(self):  # RF-13, RF-14
        r = self.cambiar(PASSWORD, "Verduras99")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["debe_cambiar_password"])
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password("Verduras99"))

    def test_password_actual_incorrecta(self):
        self.assertEqual(self.cambiar("equivocada1", "Verduras99").status_code, 400)

    def test_password_sin_numero_rechazada(self):  # RN-06
        self.assertEqual(self.cambiar(PASSWORD, "soloLetrasLargas").status_code, 400)

    def test_password_corta_rechazada(self):  # RN-06
        self.assertEqual(self.cambiar(PASSWORD, "ab12").status_code, 400)


class PermisosPorRolTests(APITestCase):
    def test_create_superuser_es_administrador(self):
        dueño = Usuario.objects.create_superuser("dueno", PASSWORD, nombre="Carlos", apellido="Ruiz", dni="20111222")
        self.assertTrue(dueño.es_administrador)
        self.assertTrue(dueño.is_staff)
        self.assertFalse(dueño.debe_cambiar_password)

    def test_empleado_no_es_staff(self):
        empleado = Usuario.objects.create_user("emp", PASSWORD, nombre="E", apellido="E", dni="1")
        self.assertFalse(empleado.is_staff)
        self.assertEqual(empleado.rol.nombre, Rol.EMPLEADO)

    def test_administrador_creado_sin_createsuperuser_tiene_todos_los_permisos(self):
        dueño = Usuario.objects.create_user(
            "dueno2", PASSWORD, nombre="D", apellido="D", dni="2", rol=Rol.objects.get(nombre=Rol.ADMINISTRADOR),
        )
        self.assertTrue(dueño.is_superuser)
        self.assertTrue(dueño.has_perm("usuarios.add_usuario"))


class GestionUsuariosTests(APITestCase):
    """Alta y baja de usuarios (RF-08, RF-10, RF-12, RF-19, RN-01 a RN-04)."""

    def setUp(self):
        self.dueño = Usuario.objects.create_superuser("dueno", PASSWORD, nombre="Carlos", apellido="Ruiz", dni="20111222")
        self.entrar_como(self.dueño)

    def entrar_como(self, usuario):
        token = self.client.post("/api/auth/login/", {"nombre_usuario": usuario.nombre_usuario, "password": PASSWORD}).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def alta(self, **cambios):
        datos = {"nombre_usuario": "jperez", "nombre": "Juan", "apellido": "Pérez", "dni": "30.111.222",
                 "rol": "Empleado", "password": "Inicial2026"}
        datos.update(cambios)
        return self.client.post("/api/usuarios/", datos)

    def test_alta_correcta(self):  # RF-08, RF-14, RF-19
        r = self.alta(nombre_usuario=" JPerez ")
        self.assertEqual(r.status_code, 201, r.data)
        nuevo = Usuario.objects.get(nombre_usuario="jperez")
        self.assertEqual(nuevo.dni, "30111222")
        self.assertEqual(nuevo.rol.nombre, Rol.EMPLEADO)
        self.assertTrue(nuevo.debe_cambiar_password)
        self.assertEqual(nuevo.creado_por, self.dueño)
        self.assertTrue(nuevo.check_password("Inicial2026"))
        self.assertNotIn("password", r.data)
        self.assertTrue(CambioUsuario.objects.filter(usuario=nuevo, realizado_por=self.dueño, accion="ALTA").exists())

    def test_nuevo_usuario_puede_entrar(self):
        self.alta()
        self.client.credentials()
        r = self.client.post("/api/auth/login/", {"nombre_usuario": "jperez", "password": "Inicial2026"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["usuario"]["debe_cambiar_password"])

    def test_usuario_y_dni_repetidos(self):  # RN-01, RN-02
        self.alta()
        r = self.alta(dni="99999999")
        self.assertEqual(r.status_code, 400)
        self.assertIn("nombre_usuario", r.data)
        r = self.alta(nombre_usuario="otro")
        self.assertEqual(r.status_code, 400)
        self.assertIn("dni", r.data)

    def test_datos_invalidos(self):
        self.assertIn("dni", self.alta(dni="12ab").data)
        self.assertIn("nombre_usuario", self.alta(nombre_usuario="juan perez").data)
        self.assertIn("rol", self.alta(rol="Gerente").data)
        self.assertIn("password", self.alta(password="corta1").data)  # RN-06
        self.assertEqual(Usuario.objects.count(), 1)

    def test_solo_el_administrador_gestiona_usuarios(self):  # RF-17, RN-13
        for rol in (Rol.ENCARGADO, Rol.EMPLEADO):
            u = Usuario.objects.create_user(
                f"u{rol}", PASSWORD, nombre="X", apellido="X", dni=f"1{len(rol)}",
                rol=Rol.objects.get(nombre=rol), debe_cambiar_password=False,
            )
            self.entrar_como(u)
            self.assertEqual(self.client.get("/api/usuarios/").status_code, 403)
            self.assertEqual(self.alta().status_code, 403)

    def test_lista_con_filtro(self):  # RF-12
        self.alta()
        r = self.client.get("/api/usuarios/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 2)
        self.assertEqual(len(self.client.get("/api/usuarios/?activo=0").data), 0)

    def test_baja_y_reactivacion(self):  # RF-10, RN-05, RF-19
        nuevo = Usuario.objects.get(pk=self.alta().data["id"])
        r = self.client.post(f"/api/usuarios/{nuevo.pk}/desactivar/", {"motivo": "Dejó de trabajar"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["activo"])
        self.assertTrue(CambioUsuario.objects.filter(usuario=nuevo, accion="BAJA", detalle="Dejó de trabajar").exists())
        # No puede entrar, pero la cuenta no se borra
        login = self.client.post("/api/auth/login/", {"nombre_usuario": "jperez", "password": "Inicial2026"})
        self.assertEqual(login.status_code, 401)
        self.assertTrue(Usuario.objects.filter(pk=nuevo.pk).exists())
        # Reactivación
        r = self.client.post(f"/api/usuarios/{nuevo.pk}/reactivar/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["activo"])
        self.assertTrue(CambioUsuario.objects.filter(usuario=nuevo, accion="REACTIVACION").exists())

    def test_baja_corta_la_sesion_abierta(self):
        self.alta()
        nuevo = Usuario.objects.get(nombre_usuario="jperez")
        nuevo.debe_cambiar_password = False
        nuevo.save()
        self.client.credentials()
        datos = self.client.post("/api/auth/login/", {"nombre_usuario": "jperez", "password": "Inicial2026"}).data
        self.entrar_como(self.dueño)
        self.client.post(f"/api/usuarios/{nuevo.pk}/desactivar/")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {datos['access']}")
        self.assertEqual(self.client.get("/api/auth/yo/").status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post("/api/auth/refresh/", {"refresh": datos["refresh"]}).status_code, 401)

    def test_no_puede_darse_de_baja_a_si_mismo(self):  # RN-04
        r = self.client.post(f"/api/usuarios/{self.dueño.pk}/desactivar/")
        self.assertEqual(r.status_code, 400)
        self.dueño.refresh_from_db()
        self.assertTrue(self.dueño.activo)

    def test_puede_dar_de_baja_a_otro_dueño(self):  # RN-03: queda él como administrador activo
        socio = Usuario.objects.get(pk=self.alta(nombre_usuario="socio", dni="25111222", rol="Administrador").data["id"])
        self.assertEqual(self.client.post(f"/api/usuarios/{socio.pk}/desactivar/").status_code, 200)

    def test_no_repetir_baja_ni_reactivacion(self):
        nuevo_id = self.alta().data["id"]
        self.assertEqual(self.client.post(f"/api/usuarios/{nuevo_id}/reactivar/").status_code, 400)
        self.client.post(f"/api/usuarios/{nuevo_id}/desactivar/")
        self.assertEqual(self.client.post(f"/api/usuarios/{nuevo_id}/desactivar/").status_code, 400)
