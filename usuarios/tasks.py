# usuarios/tasks.py — emails de cuenta con django.tasks (cola "emails", módulo 26)
from django.core.mail import send_mail
from django.tasks import task
from django.utils import translation
from django.utils.translation import gettext as _

from .models import Usuario


@task(queue_name="emails", priority=50)  # más prioridad que los recordatorios: el usuario espera
def enviar_email_completar_registro(usuario_id: int, enlace: str) -> None:
    usuario = Usuario.objects.get(pk=usuario_id)
    with translation.override(usuario.idioma):  # en una tarea no hay idioma activo: el del usuario
        send_mail(
            _("Completa tu registro"),
            _(
                "Hola %(nombre)s:\n\nPara completar tu registro, elige tu contraseña en este "
                "enlace:\n%(enlace)s\n\nSi no te has registrado tú, ignora este mensaje: "
                "sin ese paso la cuenta no se activa."
            )
            % {"nombre": usuario.nombre or usuario.email, "enlace": enlace},
            None,
            [usuario.email],
        )


@task(queue_name="emails", priority=50)
def enviar_email_cuenta_existente(usuario_id: int, enlace: str) -> None:
    usuario = Usuario.objects.get(pk=usuario_id)
    with translation.override(usuario.idioma):
        send_mail(
            _("Ya tienes una cuenta"),
            _(
                "Hola %(nombre)s:\n\nAlguien ha intentado registrarse con este email, pero ya "
                "tienes una cuenta. Si no recuerdas la contraseña, elige una nueva aquí:\n"
                "%(enlace)s\n\nSi no has sido tú, ignora este mensaje: tu cuenta no ha cambiado."
            )
            % {"nombre": usuario.nombre or usuario.email, "enlace": enlace},
            None,
            [usuario.email],
        )


@task(queue_name="emails", priority=50)
def enviar_email_recuperacion(usuario_id: int, enlace: str) -> None:
    usuario = Usuario.objects.get(pk=usuario_id)
    with translation.override(usuario.idioma):
        send_mail(
            _("Recupera tu contraseña"),
            _(
                "Para elegir una contraseña nueva entra en:\n%(enlace)s\n\n"
                "Si no lo has pedido tú, ignora este mensaje."
            )
            % {"enlace": enlace},
            None,
            [usuario.email],
        )
