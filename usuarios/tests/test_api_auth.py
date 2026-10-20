"""Ejercicio del módulo 35: JWT con refresh en cookie HttpOnly, registro y contraseñas."""

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import jwt
import pytest
from django.core import mail
from django.db import connection
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from usuarios.models import Usuario
from usuarios.tests.factories import UsuarioFactory

pytestmark = pytest.mark.django_db
CLAVE = "clave-segura-123"


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def ana():
    return UsuarioFactory(email="ana@example.com")  # contraseña de la factory: CLAVE


def login(api, email="ana@example.com", password=CLAVE):
    return api.post("/api/v1/auth/login/", {"email": email, "password": password})


# ── Login ──
def test_login_correcto_da_access_y_cookie_httponly(api, ana):
    r = login(api)
    assert r.status_code == 200 and set(r.json()) == {"access"}  # el refresh NO va en el cuerpo
    cookie = r.cookies["refresh"]
    assert cookie["httponly"] and cookie["samesite"] == "Strict"
    assert cookie["path"] == "/api/v1/auth/"

    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    assert api.get("/api/v1/auth/me/").json()["email"] == "ana@example.com"


@pytest.mark.parametrize(
    ("email", "password"), [("ana@example.com", "mala"), ("nadie@example.com", CLAVE)]
)
def test_login_incorrecto_es_401_y_mismo_mensaje(api, ana, email, password):
    r = login(api, email, password)
    assert r.status_code == 401  # no 403: ver la nota de VistaPublicaAuth
    assert "refresh" not in r.cookies


def test_login_ignora_un_access_caducado_en_la_cabecera(api, ana):
    api.credentials(HTTP_AUTHORIZATION="Bearer basura")
    assert login(api).status_code == 200  # authentication_classes = []


# ── Refresh, rotación y logout ──
def test_refresh_sin_cookie_es_401(api):
    assert api.post("/api/v1/auth/refresh/").status_code == 401


def test_refresh_rota_y_el_antiguo_deja_de_valer(api, ana):
    login(api)
    antiguo = api.cookies["refresh"].value
    r = api.post("/api/v1/auth/refresh/")  # APIClient reenvía las cookies, como el navegador
    assert r.status_code == 200 and "access" in r.json()
    nuevo = api.cookies["refresh"].value
    assert nuevo != antiguo

    ladron = APIClient()
    ladron.cookies["refresh"] = antiguo
    assert ladron.post("/api/v1/auth/refresh/").status_code == 401  # en la lista negra


def test_refresh_con_una_cookie_forjada_sin_jti_es_401(api):
    # sin jti y firmado con otra clave: no hay nada que bloquear, y el serializer lo rechaza
    clave_ajena = "una-clave-que-no-es-la-del-servidor"
    falso = jwt.encode({"token_type": "refresh", "exp": int(time.time()) + 60}, clave_ajena)
    api.cookies["refresh"] = falso
    assert api.post("/api/v1/auth/refresh/").status_code == 401


# transaction=True: cada hilo usa su propia conexión y solo ve lo confirmado (como dos requests reales)
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_dos_refresh_a_la_vez_con_la_misma_cookie_solo_uno_rota(ana, monkeypatch):
    api = APIClient()
    login(api)
    cookie = api.cookies["refresh"].value

    # Ensancha la carrera: cada request espera (hasta 1 s) a que la otra también haya comprobado
    # que la cookie no está en la lista negra. Sin el bloqueo, las dos pasan y las dos rotan.
    original, barrera = RefreshToken.check_blacklist, threading.Barrier(2, timeout=1)

    def comprobar_y_esperar(token):
        original(token)
        try:
            barrera.wait()
        except threading.BrokenBarrierError:
            pass  # la otra request está esperando el bloqueo: no llegará

    monkeypatch.setattr(RefreshToken, "check_blacklist", comprobar_y_esperar)

    def refrescar(_):
        cliente = APIClient()
        cliente.cookies["refresh"] = cookie
        try:
            return cliente.post("/api/v1/auth/refresh/").status_code
        finally:
            connection.close()  # la conexión de este hilo

    with ThreadPoolExecutor(max_workers=2) as hilos:
        assert sorted(hilos.map(refrescar, range(2))) == [200, 401]


def test_logout_invalida_el_refresh(api, ana):
    login(api)
    refresh = api.cookies["refresh"].value
    assert api.post("/api/v1/auth/logout/").status_code == 204
    assert api.cookies["refresh"].value == ""  # cookie borrada
    otro = APIClient()
    otro.cookies["refresh"] = refresh
    assert otro.post("/api/v1/auth/refresh/").status_code == 401


def test_throttle_de_login(api, ana):
    for _ in range(5):
        login(api, password="mala")
    assert login(api).status_code == 429  # ni siquiera con la buena: espera un minuto


# ── Registro: solo el email; la contraseña se elige desde el enlace del correo ──
def enlace_del_email(indice=-1) -> tuple[str, str]:
    cuerpo = mail.outbox[indice].body
    uid, token = re.search(r"uid=([^&\s]+)&token=([^\s]+)", cuerpo).groups()
    return uid, token


@pytest.fixture
def registrar(api, django_capture_on_commit_callbacks):
    def registrar(email, **datos):
        with django_capture_on_commit_callbacks(execute=True):
            return api.post("/api/v1/auth/registro/", {"email": email, **datos})

    return registrar


def completar(api, uid, token, password):
    return api.post(
        "/api/v1/auth/completar-registro/", {"uid": uid, "token": token, "password": password}
    )


def test_registro_sin_contrasena_y_completar_con_el_enlace(api, registrar):
    r = registrar("Luis@Example.com", nombre="Luis", password="la-ignora-123")
    assert r.status_code == 202
    usuario = Usuario.objects.get(email="luis@example.com")  # normalizado
    assert not usuario.is_active and not usuario.has_usable_password()  # el password, ignorado
    assert login(api, "luis@example.com", "la-ignora-123").status_code == 401

    assert mail.outbox[-1].subject == "Completa tu registro"
    assert "http://localhost:4200/completar-registro?uid=" in mail.outbox[-1].body
    uid, token = enlace_del_email()
    assert completar(api, uid, "x", "otra-clave-larga-9").status_code == 400
    assert completar(api, uid, token, "otra-clave-larga-9").status_code == 204
    assert login(api, "luis@example.com", "otra-clave-larga-9").status_code == 200
    assert completar(api, uid, token, "y-otra-clave-8").status_code == 400  # de un solo uso


def test_registro_misma_respuesta_para_email_nuevo_pendiente_o_con_cuenta(api, ana, registrar):
    nuevo = registrar("nuevo@example.com")
    pendiente = registrar("nuevo@example.com")
    con_cuenta = registrar("ANA@example.com")
    assert nuevo.status_code == pendiente.status_code == con_cuenta.status_code == 202
    assert nuevo.json() == pendiente.json() == con_cuenta.json()

    asuntos = [(m.to, m.subject) for m in mail.outbox]
    assert asuntos == [
        (["nuevo@example.com"], "Completa tu registro"),
        (["nuevo@example.com"], "Completa tu registro"),  # el mismo enlace, otra vez
        (["ana@example.com"], "Ya tienes una cuenta"),
    ]
    assert "http://localhost:4200/nueva-password?uid=" in mail.outbox[-1].body
    assert Usuario.objects.filter(email__iexact="ana@example.com").count() == 1
    assert login(api).status_code == 200  # la cuenta de Ana no ha cambiado


@pytest.mark.parametrize(
    ("password", "fragmento"),
    [("1234", "demasiado corta"), ("password123", "demasiado común"), ("luisgarcia", "similar")],
)
def test_completar_valida_la_password_sin_gastar_el_enlace(api, registrar, password, fragmento):
    registrar("luisgarcia@example.com", nombre="Luis")
    uid, token = enlace_del_email()
    r = completar(api, uid, token, password)
    assert r.status_code == 400 and fragmento in " ".join(r.json()["errors"]["password"])
    assert completar(api, uid, token, "otra-clave-larga-9").status_code == 204  # sigue valiendo


def test_el_enlace_de_otro_usuario_no_vale(api, registrar):
    registrar("luis@example.com")
    uid_luis, _ = enlace_del_email()
    registrar("eva@example.com")
    _, token_eva = enlace_del_email()
    assert completar(api, uid_luis, token_eva, "otra-clave-larga-9").status_code == 400


def test_registrar_un_email_ajeno_no_da_acceso(api, registrar):
    # Alguien registra el email de Eva antes que ella, con una contraseña que conoce.
    registrar("eva@example.com", password="clave-del-otro-123")
    assert login(api, "eva@example.com", "clave-del-otro-123").status_code == 401
    # Solo quien lee el buzón de Eva puede elegir la contraseña; y será la de Eva.
    uid, token = enlace_del_email()
    assert completar(api, uid, token, "clave-de-eva-456").status_code == 204
    assert login(api, "eva@example.com", "clave-de-eva-456").status_code == 200
    assert login(APIClient(), "eva@example.com", "clave-del-otro-123").status_code == 401


def test_recuperar_con_el_registro_pendiente_envia_el_de_completar(
    api, registrar, django_capture_on_commit_callbacks
):
    registrar("luis@example.com")
    with django_capture_on_commit_callbacks(execute=True):
        api.post("/api/v1/auth/recuperar-password/", {"email": "luis@example.com"})
    assert mail.outbox[-1].subject == "Completa tu registro"
    uid, token = enlace_del_email()
    assert completar(api, uid, token, "otra-clave-larga-9").status_code == 204


def test_completar_no_vale_para_una_cuenta_activa(api, ana, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        api.post("/api/v1/auth/recuperar-password/", {"email": "ana@example.com"})
    uid, token = enlace_del_email()  # un enlace válido… de recuperar contraseña
    assert completar(api, uid, token, "otra-clave-larga-9").status_code == 400


def test_cuenta_desactivada_no_recibe_enlaces(
    api, ana, registrar, django_capture_on_commit_callbacks
):
    ana.is_active = False  # la desactivó el personal: ni registro ni recuperación la reactivan
    ana.save()
    assert registrar("ana@example.com").status_code == 202
    with django_capture_on_commit_callbacks(execute=True):
        api.post("/api/v1/auth/recuperar-password/", {"email": "ana@example.com"})
    assert mail.outbox == []


# ── Cambiar y recuperar contraseña ──
def test_cambiar_password_cierra_las_sesiones(api, ana):
    access = login(api).json()["access"]
    refresh = api.cookies["refresh"].value
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    r = api.post("/api/v1/auth/cambiar-password/", {"actual": "mala", "nueva": "nueva-clave-456"})
    assert r.status_code == 400 and "actual" in r.json()["errors"]
    r = api.post("/api/v1/auth/cambiar-password/", {"actual": CLAVE, "nueva": "nueva-clave-456"})
    assert r.status_code == 204
    assert api.get("/api/v1/auth/me/").status_code == 401  # el access de antes ya no vale
    otro = APIClient()
    otro.cookies["refresh"] = refresh
    assert otro.post("/api/v1/auth/refresh/").status_code == 401  # sesión cerrada
    assert login(APIClient(), password="nueva-clave-456").status_code == 200


def test_recuperar_misma_respuesta_exista_o_no(api, ana, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        existe = api.post("/api/v1/auth/recuperar-password/", {"email": "ana@example.com"})
        no_existe = api.post("/api/v1/auth/recuperar-password/", {"email": "x@example.com"})
    assert (existe.status_code, existe.json()) == (no_existe.status_code, no_existe.json())
    assert len(mail.outbox) == 1  # solo al que existe


def test_recuperar_y_el_enlace_es_de_un_solo_uso(api, ana, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        api.post("/api/v1/auth/recuperar-password/", {"email": "ana@example.com"})
    uid, token = enlace_del_email()
    url = "/api/v1/auth/recuperar-password/confirmar/"
    r = api.post(url, {"uid": uid, "token": token, "password": "123"})
    assert r.status_code == 400 and "password" in r.json()["errors"]  # Django → 400, no 500
    assert (
        api.post(url, {"uid": uid, "token": token, "password": "otra-mas-segura-7"}).status_code
        == 204
    )
    assert (
        api.post(url, {"uid": uid, "token": token, "password": "y-otra-mas-8"}).status_code == 400
    )
    assert login(api, password="otra-mas-segura-7").status_code == 200


# ── Módulo 51: /me/ dice al frontend qué puede hacer el usuario ──
def test_me_incluye_permisos_y_si_es_personal(api, ana):
    from django.contrib.auth.models import Group, Permission

    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login(api).json()['access']}")
    datos = api.get("/api/v1/auth/me/").json()
    assert datos["es_personal"] is False and datos["permisos"] == []

    grupo, _ = Group.objects.get_or_create(name="bibliotecarios")
    grupo.permissions.add(Permission.objects.get(codename="add_libro"))
    ana.groups.add(grupo)
    datos = api.get("/api/v1/auth/me/").json()
    assert datos["es_personal"] is True
    assert "catalogo.add_libro" in datos["permisos"]


def test_me_no_deja_cambiar_permisos_con_patch(api, ana):
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login(api).json()['access']}")
    r = api.patch(
        "/api/v1/auth/me/", {"es_personal": True, "permisos": ["catalogo.add_libro"]}, format="json"
    )
    assert r.status_code == 200
    assert r.json()["es_personal"] is False and r.json()["permisos"] == []
