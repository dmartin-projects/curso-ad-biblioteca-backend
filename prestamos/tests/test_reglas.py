"""Ejercicio 5 del módulo 14: las mismas reglas con django-rules."""

import pytest

from prestamos.reglas import reglas
from prestamos.tests.test_permisos import escena  # noqa: F401  (reutiliza el fixture)

pytestmark = pytest.mark.django_db


def test_mismas_decisiones_que_el_backend(escena):  # noqa: F811
    ana, biblio = escena["ana"], escena["biblio"]
    de_ana, de_luis = escena["de_ana"], escena["de_luis"]
    for usuario, prestamo in [(ana, de_ana), (ana, de_luis), (biblio, de_luis)]:
        con_backend = usuario.has_perm("prestamos.renovar_prestamo") or usuario.has_perm(
            "prestamos.renovar_prestamo", prestamo
        )
        assert reglas.test_rule("renovar_prestamo", usuario, prestamo) == con_backend
    de_ana.estado = "devuelto"
    assert not reglas.test_rule("renovar_prestamo", ana, de_ana)
    assert reglas.test_rule("ver_prestamo", ana, de_ana)
