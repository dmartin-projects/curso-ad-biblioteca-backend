# prestamos/api/urls.py
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("prestamos", views.PrestamoViewSet, basename="prestamo")

urlpatterns = router.urls
