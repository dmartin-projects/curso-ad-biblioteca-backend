"""Ejercicio del módulo 38: archivos, formato único de error y esquema OpenAPI."""

import io
import tracemalloc
from datetime import timedelta

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection, transaction
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from catalogo.models import Libro
from catalogo.tests.factories import EjemplarFactory, LibroFactory
from core.api.exceptions import _aplanar
from core.exceptions import ErrorDeDominio
from prestamos.models import Prestamo
from prestamos.tests.factories import PrestamoFactory
from usuarios.tests.factories import UsuarioFactory

pytestmark = pytest.mark.django_db
CLAVES = {"type", "title", "status", "detail", "errors", "request_id"}


@pytest.fixture
def api(socio):
    cliente = APIClient()
    cliente.force_authenticate(socio)
    return cliente


@pytest.fixture
def personal(bibliotecario):
    cliente = APIClient()
    cliente.force_authenticate(bibliotecario)  # is_staff → personal (módulo 36)
    return cliente


def imagen(formato="PNG", nombre="tapa.png") -> SimpleUploadedFile:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(buffer, formato)
    return SimpleUploadedFile(nombre, buffer.getvalue())


def png() -> SimpleUploadedFile:
    return imagen()


# ── 4. Formato de error único ──
def test_400_con_errores_aplanados(personal):
    r = personal.post("/api/v1/libros/", {"titulo": "", "isbn": "123", "autores_ids": [999]})
    assert r.status_code == 400
    cuerpo = r.json()
    assert set(cuerpo) == CLAVES and cuerpo["type"] == "validacion"
    assert set(cuerpo["errors"]) == {"titulo", "isbn", "autores_ids"}
    assert cuerpo["request_id"] == r["X-Request-ID"]  # se puede buscar en los logs


def test_aplanar_listas_anidadas():
    # lo que devuelve DRF 3.18 con many=True: un dict indexado por posición
    errores = {"lineas": {1: {"precio_unitario": ["Introduzca un número válido."]}}, "total": ["x"]}
    assert _aplanar(errores) == {
        "lineas.1.precio_unitario": ["Introduzca un número válido."],
        "total": ["x"],
    }
    assert _aplanar([{}, {"cantidad": ["Mal"]}], "lineas") == {"lineas.1.cantidad": ["Mal"]}


def test_401_403_404_405():
    anonimo = APIClient()
    r = anonimo.get("/api/v1/prestamos/")
    assert (r.status_code, r.json()["type"]) == (401, "no_autenticado")
    assert r["WWW-Authenticate"].startswith("Bearer")  # la cabecera se conserva

    socio = APIClient()
    socio.force_authenticate(UsuarioFactory())
    r = socio.get("/api/v1/prestamos/vencidos/")
    assert (r.status_code, r.json()["type"]) == (403, "sin_permiso")
    r = socio.get("/api/v1/prestamos/999999/")
    assert (r.status_code, r.json()["type"]) == (404, "no_encontrado")
    r = socio.delete("/api/v1/prestamos/1/")
    assert (r.status_code, r.json()["type"]) == (405, "metodo_no_permitido")


def test_404_fuera_de_drf_tambien_en_json():
    r = APIClient().get("/api/v1/no-existe/")
    assert r.status_code == 404 and r.json()["type"] == "no_encontrado"
    assert r["Content-Type"] == "application/json"


def test_409_de_dominio_sin_try_except_en_la_vista(api, socio):
    prestamo = PrestamoFactory(socio=socio)
    api.post(f"/api/v1/prestamos/{prestamo.pk}/devolver/")
    r = api.post(f"/api/v1/prestamos/{prestamo.pk}/devolver/")
    assert r.status_code == 409
    cuerpo = r.json()
    assert cuerpo["type"] == "prestamo_ya_devuelto"
    assert cuerpo["title"] == "El préstamo ya estaba devuelto."
    assert cuerpo["detail"] == {"prestamo_id": prestamo.pk}  # el contexto de la excepción

    ocupado = EjemplarFactory(estado="prestado")
    r = api.post("/api/v1/prestamos/", {"ejemplar_id": ocupado.pk})
    assert (r.status_code, r.json()["type"]) == (409, "ejemplar_no_disponible")


def test_un_error_respondido_deshace_lo_escrito_con_atomic_requests(socio, monkeypatch):
    class EscribeYFalla(APIView):
        def post(self, request):
            Libro.objects.create(titulo="A medias", isbn="9788497593793")
            raise ErrorDeDominio("falla después de escribir")

    monkeypatch.setitem(connection.settings_dict, "ATOMIC_REQUESTS", True)
    request = APIRequestFactory().post("/")
    force_authenticate(request, user=socio)
    with transaction.atomic():  # lo que hace Django con cada vista si ATOMIC_REQUESTS = True
        assert EscribeYFalla.as_view()(request).status_code == 409
    assert not Libro.objects.filter(titulo="A medias").exists()  # set_rollback(): no se confirma


def test_422_al_superar_el_maximo_de_prestamos(api, socio):
    socio.socio.max_prestamos = 1
    socio.socio.save(update_fields=["max_prestamos"])
    assert api.post("/api/v1/prestamos/", {"ejemplar_id": EjemplarFactory().pk}).status_code == 201
    r = api.post("/api/v1/prestamos/", {"ejemplar_id": EjemplarFactory().pk})
    assert (r.status_code, r.json()["type"]) == (422, "limite_prestamos")


def test_409_al_borrar_algo_protegido(personal):
    prestamo = PrestamoFactory()
    r = personal.delete(f"/api/v1/libros/{prestamo.ejemplar.libro_id}/")
    assert (r.status_code, r.json()["type"]) == (409, "en_uso")


def test_429_con_retry_after():
    UsuarioFactory(email="ana@example.com")
    api = APIClient()
    for _ in range(6):
        r = api.post("/api/v1/auth/login/", {"email": "ana@example.com", "password": "mala"})
    assert (r.status_code, r.json()["type"]) == (429, "limite_peticiones")
    assert int(r["Retry-After"]) > 0


def test_500_sin_detalles_internos(api, mocker, caplog):
    mocker.patch(
        "prestamos.api.views.prestamos_visibles", side_effect=RuntimeError("clave=secreta")
    )
    r = api.get("/api/v1/prestamos/")
    assert r.status_code == 500
    assert r.json()["type"] == "error_interno" and "secreta" not in r.text
    assert "Error no controlado en PrestamoViewSet" in caplog.text  # → logs y Sentry


# ── 1. Portada ──
def test_subir_y_descargar_portada(personal, api):
    libro = LibroFactory()
    url = f"/api/v1/libros/{libro.pk}/portada/"
    assert api.get(url).status_code == 404  # aún no tiene

    r = personal.put(url, {"portada": png()}, format="multipart")
    assert r.status_code == 200, r.json()
    assert r.json()["portada"].startswith("http://testserver/")
    libro.refresh_from_db()
    assert default_storage.exists(libro.portada.name)

    r = api.get(url)  # cualquier autenticado la descarga
    assert r.status_code == 200 and b"".join(r.streaming_content).startswith(b"\x89PNG")
    assert api.put(url, {"portada": png()}, format="multipart").status_code == 403  # socio


@pytest.mark.parametrize(
    ("archivo", "fragmento"),
    [
        (SimpleUploadedFile("tapa.png", b"%PDF-1.4 falso", content_type="image/png"), "imagen"),
        (imagen("GIF", "tapa.gif"), "extensión"),  # imagen de verdad, formato no admitido
    ],
)
def test_portada_rechaza_lo_que_no_es_imagen(personal, archivo, fragmento):
    libro = LibroFactory()
    r = personal.put(
        f"/api/v1/libros/{libro.pk}/portada/", {"portada": archivo}, format="multipart"
    )
    assert r.status_code == 400
    assert fragmento in " ".join(r.json()["errors"]["portada"]).lower()


def test_portada_valida_el_tipo_real_aunque_pillow_la_acepte(personal):
    """Un SVG con extensión .png: Pillow no lo abre, pero aquí lo para libmagic antes."""
    from core.validators import TipoRealValidator

    svg = SimpleUploadedFile("x.png", b"<svg xmlns='http://www.w3.org/2000/svg'/>")
    with pytest.raises(Exception, match="no admitido"):
        TipoRealValidator(["image/png"])(svg)


# ── 2. Exportar en streaming, respetando filtros ──
def test_exportar_respeta_filtros_y_permisos(personal, api, socio):
    PrestamoFactory.create_batch(3, socio=socio)
    devuelto = PrestamoFactory(socio=socio)
    Prestamo.objects.filter(pk=devuelto.pk).update(estado="devuelto")
    PrestamoFactory()  # de otro

    r = api.get("/api/v1/prestamos/exportar/", {"estado": "activo"})
    assert r["Content-Disposition"] == 'attachment; filename="prestamos.csv"'
    lineas = b"".join(r.streaming_content).decode().splitlines()
    assert lineas[0] == "id;libro;socio;inicio;estado"
    assert len(lineas) == 1 + 3  # solo los suyos y activos
    todas = b"".join(personal.get("/api/v1/prestamos/exportar/").streaming_content)
    assert len(todas.decode().splitlines()) == 1 + 5  # el personal, todos


def test_exportar_con_memoria_constante(personal):
    socio = UsuarioFactory()
    libro = LibroFactory()
    from catalogo.models import Ejemplar

    ejemplares = Ejemplar.objects.bulk_create(
        Ejemplar(libro=libro, codigo=f"M{i}") for i in range(6000)
    )
    limite = timezone.now() + timedelta(days=5)
    Prestamo.objects.bulk_create(
        Prestamo(ejemplar=e, socio=socio, fecha_limite=limite) for e in ejemplares
    )
    r = personal.get("/api/v1/prestamos/exportar/")
    tracemalloc.start()
    n = sum(1 for _ in r.streaming_content)
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"\n{n - 1} filas · pico {pico / 1e6:.1f} MB")
    assert n == 6001 and pico < 10e6


# ── 5. Esquema OpenAPI sin avisos ──
def test_esquema_sin_avisos(tmp_path):
    call_command("spectacular", "--file", tmp_path / "schema.yml", "--validate", "--fail-on-warn")
    esquema = (tmp_path / "schema.yml").read_text()
    assert "/api/v1/auth/login/" in esquema and "Problema" in esquema


def test_docs_publicadas(client):
    assert client.get("/api/schema/").status_code == 200
    assert client.get("/api/docs/").status_code == 200
