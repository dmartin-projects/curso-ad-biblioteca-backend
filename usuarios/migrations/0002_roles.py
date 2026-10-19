# usuarios/migrations/0002_roles.py
from django.db import migrations

ROLES = {
    "socios": ["catalogo.view_libro"],  # sus préstamos los ve por objeto (sección 6), no todos
    "bibliotecarios": [
        "catalogo.add_libro", "catalogo.change_libro", "catalogo.view_libro",
        "catalogo.add_ejemplar", "catalogo.change_ejemplar",
        "prestamos.add_prestamo", "prestamos.change_prestamo", "prestamos.view_prestamo",
        "prestamos.renovar_prestamo",
    ],
    "responsables": ["prestamos.condonar_multa", "prestamos.ver_estadisticas"],
}


def crear_roles(apps, schema_editor):
    from django.contrib.auth.management import create_permissions

    # Los permisos se crean en una signal post_migrate: forzamos su creación aquí
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for nombre, perms in ROLES.items():
        grupo, _ = Group.objects.get_or_create(name=nombre)
        for perm in perms:
            app_label, codename = perm.split(".")
            grupo.permissions.add(
                Permission.objects.get(content_type__app_label=app_label, codename=codename)
            )
    # Los responsables heredan los permisos de bibliotecarios
    Group.objects.get(name="responsables").permissions.add(
        *Group.objects.get(name="bibliotecarios").permissions.all()
    )


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("catalogo", "0008_autor_nombre_trgm"),  # la última de cada app (las tuyas pueden llamarse distinto)
        ("prestamos", "0006_permisos_propios"),
        ("usuarios", "0001_initial"),
    ]
    operations = [migrations.RunPython(crear_roles, migrations.RunPython.noop)]
