"""Ejercicio del módulo 20: archivos, descargas protegidas y exportación en streaming."""

import io
import tracemalloc

import boto3
import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from moto import mock_aws
from PIL import Image

from catalogo.archivos import filas_prestamos
from catalogo.models import Ejemplar, Libro
from core.validators import TamanoMaximoValidator, validar_pdf_real
from prestamos.models import Prestamo
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db
PDF = b"%PDF-1.4\n%prueba\n"


def png(nombre="portada.png") -> SimpleUploadedFile:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buffer, "PNG")
    return SimpleUploadedFile(nombre, buffer.getvalue(), content_type="image/png")


@pytest.fixture
def libro():
    return Libro.objects.create(titulo="Dune", isbn="9788497593793")


@pytest.fixture
def staff(client):
    u = Usuario.objects.create_user("staff@example.com", password="x", is_staff=True)
    client.force_login(u)
    return u


# ── 1. Validadores ──
def test_validadores():
    with pytest.raises(ValidationError, match="supera 2 MB"):
        TamanoMaximoValidator(2)(ContentFile(b"x" * (2 * 1024 * 1024 + 1)))
    with pytest.raises(ValidationError, match="no es un PDF"):
        validar_pdf_real(ContentFile(b"<html>no soy un pdf</html>"))
    archivo = ContentFile(PDF)
    validar_pdf_real(archivo)
    assert archivo.read() == PDF  # el validador dejó el puntero al principio


# ── 3. Subida y descarga ──
def test_subir_portada_y_ficha(client, staff, libro):
    r = client.post(reverse("catalogo:subir_portada", args=[libro.pk]), {"portada": png()})
    assert r.status_code == 200, r.json()
    libro.refresh_from_db()
    assert libro.portada.name.startswith(f"portadas/{libro.isbn}/")
    assert not libro.portada.name.endswith("portada.png")  # nunca el nombre original

    r = client.post(
        reverse("catalogo:subir_ficha", args=[libro.pk]),
        {"ficha_pdf": SimpleUploadedFile("ficha.pdf", PDF, content_type="application/pdf")},
    )
    assert r.status_code == 200


def test_subida_rechaza_archivos_falsos(client, staff, libro):
    falso = SimpleUploadedFile("foto.png", b"no soy una imagen", content_type="image/png")
    r = client.post(reverse("catalogo:subir_portada", args=[libro.pk]), {"portada": falso})
    assert r.status_code == 400
    assert "portada" in r.json()["errores"]

    pdf_falso = SimpleUploadedFile("ficha.pdf", b"<html>", content_type="application/pdf")
    r = client.post(reverse("catalogo:subir_ficha", args=[libro.pk]), {"ficha_pdf": pdf_falso})
    assert r.json()["errores"]["ficha_pdf"][0]["code"] == "no_pdf"


def test_descarga_solo_staff(client, libro):
    libro.ficha_pdf.save("ficha.pdf", ContentFile(PDF))
    url = reverse("catalogo:descargar_ficha", args=[libro.pk])

    assert client.get(url).status_code == 302  # anónimo → al login del admin
    socio = Usuario.objects.create_user("ana@example.com")
    client.force_login(socio)
    r = client.get(url)
    assert r.status_code == 302 and "/admin/login/" in r["Location"]

    socio.is_staff = True
    socio.save()
    r = client.get(url)
    assert r.status_code == 200
    assert r["Content-Disposition"] == f'attachment; filename="{libro.isbn}.pdf"'
    assert b"".join(r.streaming_content) == PDF


def test_subida_requiere_staff(client, libro):
    client.force_login(Usuario.objects.create_user("ana@example.com"))
    r = client.post(reverse("catalogo:subir_portada", args=[libro.pk]), {"portada": png()})
    assert r.status_code == 302
    libro.refresh_from_db()
    assert not libro.portada


# ── 2. S3 (MinIO en tu máquina; aquí, S3 simulado con moto) ──
S3 = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": "biblioteca",
            "endpoint_url": None,  # moto intercepta las llamadas a AWS
            "access_key": "test",
            "secret_key": "test",
            "region_name": "us-east-1",
            "signature_version": "s3v4",  # firma v4: la v2 está obsoleta
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": 300,
            "file_overwrite": False,
        },
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@mock_aws
def test_s3_url_firmada_y_redireccion(settings, client, staff, libro):
    settings.STORAGES = S3
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="biblioteca")

    libro = Libro.objects.get(pk=libro.pk)  # recarga: el FieldFile toma el storage nuevo
    assert default_storage.__class__.__name__ == "S3Storage"  # LazyObject: __class__ es el real
    libro.ficha_pdf.save("ficha.pdf", ContentFile(PDF))
    claves = [o["Key"] for o in s3.list_objects_v2(Bucket="biblioteca")["Contents"]]
    assert claves == [libro.ficha_pdf.name]  # está en el bucket

    url = libro.ficha_pdf.url
    assert "X-Amz-Signature=" in url and "X-Amz-Expires=300" in url  # firmada y caduca

    r = client.get(reverse("catalogo:descargar_ficha", args=[libro.pk]))
    assert r.status_code == 302 and "X-Amz-Signature=" in r["Location"]

    settings.CORS_MEDIA_ORIGENES = ["http://localhost:4200"]
    salida = io.StringIO()
    call_command("configurar_bucket", stdout=salida)
    call_command("configurar_bucket", stdout=salida)  # idempotente
    assert "1 regla CORS, 3 reglas de caducidad" in salida.getvalue()


# ── 4. Exportación en streaming ──
@pytest.fixture
def muchos_prestamos(libro):
    n = 3000
    ejemplares = Ejemplar.objects.bulk_create(
        Ejemplar(libro=libro, codigo=f"E{i}") for i in range(n)
    )
    socio = Usuario.objects.create_user("ana@example.com")
    limite = timezone.now() + Prestamo.DURACION
    Prestamo.objects.bulk_create(
        Prestamo(ejemplar=e, socio=socio, fecha_limite=limite) for e in ejemplares
    )
    return n


def test_exportar_prestamos(client, staff, muchos_prestamos):
    r = client.get(reverse("catalogo:exportar_prestamos"))
    assert r.streaming
    lineas = b"".join(r.streaming_content).decode().splitlines()
    assert lineas[0] == "id,libro,socio,inicio,estado"
    assert len(lineas) == muchos_prestamos + 1


def pico_memoria(funcion) -> int:
    tracemalloc.start()
    funcion()
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return pico


def test_streaming_usa_menos_memoria(muchos_prestamos):
    def en_streaming():
        for _ in filas_prestamos():  # cada fila se genera y se descarta
            pass

    def todo_en_lista():
        prestamos = list(Prestamo.objects.select_related("ejemplar__libro", "socio"))
        return [[p.pk, p.ejemplar.libro.titulo, p.socio.email] for p in prestamos]

    streaming, lista = pico_memoria(en_streaming), pico_memoria(todo_en_lista)
    print(f"\nstreaming: {streaming / 1e6:.1f} MB · lista: {lista / 1e6:.1f} MB")
    assert streaming < lista


# ── 5. Signals: no dejar archivos huérfanos ──
def test_reemplazar_y_borrar_limpia_archivos(libro, django_capture_on_commit_callbacks):
    libro.portada.save("a.png", png())
    primera = libro.portada.name
    assert default_storage.exists(primera)

    with django_capture_on_commit_callbacks(execute=True):
        libro.portada.save("b.png", png())
    segunda = libro.portada.name
    assert not default_storage.exists(primera)  # la antigua se borró
    assert default_storage.exists(segunda)

    with django_capture_on_commit_callbacks(execute=True):
        libro.titulo = "Dune (edición revisada)"
        libro.save()  # guardar sin cambiar la portada no borra nada
    assert default_storage.exists(segunda)

    with django_capture_on_commit_callbacks(execute=True):
        libro.delete()
    assert not default_storage.exists(segunda)


def test_si_la_transaccion_falla_no_se_borra(libro, django_capture_on_commit_callbacks):
    libro.portada.save("a.png", png())
    primera = libro.portada.name
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        libro.portada.save("b.png", png())
    assert len(callbacks) == 1  # el borrado espera al commit…
    assert default_storage.exists(primera)  # …y si no llega, el archivo sigue ahí
