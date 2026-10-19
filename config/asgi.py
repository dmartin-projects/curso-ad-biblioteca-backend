# config/asgi.py
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
django_asgi_app = get_asgi_application()  # ⚠️ ANTES de importar consumers (carga las apps)

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from notificaciones.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(  # rechaza orígenes no permitidos
            # Sesión (admin, API navegable); el ticket de Angular llega en el módulo 35
            AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
