from django.contrib import admin

from .models import Gasto, Ticket

admin.site.register(Ticket)
admin.site.register(Gasto)
