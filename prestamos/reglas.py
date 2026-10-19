"""Las mismas reglas del backend, con django-rules: predicados que se combinan con & | ~."""

import rules

from .models import Prestamo


@rules.predicate
def es_su_prestamo(user, prestamo):
    return prestamo is not None and prestamo.socio_id == user.pk


@rules.predicate
def esta_activo(user, prestamo):
    return prestamo is not None and prestamo.estado == Prestamo.Estado.ACTIVO


es_bibliotecario = rules.is_group_member("bibliotecarios") | rules.is_group_member("responsables")

reglas = rules.RuleSet()
reglas.add_rule("ver_prestamo", es_bibliotecario | es_su_prestamo)
reglas.add_rule("renovar_prestamo", es_bibliotecario | (es_su_prestamo & esta_activo))
