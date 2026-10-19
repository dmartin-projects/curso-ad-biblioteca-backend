# config/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from core import views as core_views

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", views.health, name="health"),
    path("csp-report/", core_views.csp_report, name="csp_report"),
    path("catalogo/", include("catalogo.urls")),
    path("prestamos/", include("prestamos.urls")),
    path("notas/<str:app>/<str:modelo>/<int:pk>/", core_views.notas, name="notas"),
    path("cuentas/", include("django.contrib.auth.urls")),
    path("libros/", RedirectView.as_view(pattern_name="catalogo:lista_libros")),
]

if settings.DEBUG:  # solo en desarrollo y con FileSystemStorage
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Biblioteca · Administración"
admin.site.site_title = "Biblioteca"
admin.site.index_title = "Panel de gestión"
