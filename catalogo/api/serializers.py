# catalogo/api/serializers.py
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers

from catalogo.busqueda import actualizar_busqueda
from catalogo.fields import ISBNField
from catalogo.models import Autor, Autoria, Genero, Libro

from .fields import ISBNSerializerField


class BaseSerializer(serializers.ModelSerializer):
    """Normaliza el ISBN ANTES de validar longitud y unicidad (ver §6)."""

    serializer_field_mapping = {
        **serializers.ModelSerializer.serializer_field_mapping,
        ISBNField: ISBNSerializerField,
    }


class AutorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Autor
        fields = ["id", "nombre", "apellidos", "slug", "nacimiento"]
        read_only_fields = ["slug"]


class GeneroSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genero
        fields = ["id", "nombre", "padre"]


class LibroListaSerializer(BaseSerializer):
    """Pocos campos para listados. Espera Libro.objects.para_listado().con_disponibles()."""

    autores = serializers.StringRelatedField(many=True)
    generos = serializers.SlugRelatedField(many=True, read_only=True, slug_field="nombre")
    ejemplares_disponibles = serializers.IntegerField(read_only=True)  # de un annotate()

    class Meta:
        model = Libro
        fields = [
            "id",
            "titulo",
            "isbn",
            "publicado",
            "autores",
            "generos",
            "ejemplares_disponibles",
        ]


class LibroSerializer(BaseSerializer):
    """Objeto para leer (autores), ids para escribir (autores_ids)."""

    autores = AutorSerializer(many=True, read_only=True)
    autores_ids = serializers.PrimaryKeyRelatedField(
        source="autores", queryset=Autor.objects.all(), many=True, write_only=True
    )
    generos = serializers.PrimaryKeyRelatedField(
        queryset=Genero.objects.all(), many=True, required=False
    )

    class Meta:
        model = Libro
        fields = [
            "id",
            "titulo",
            "isbn",
            "publicado",
            "paginas",
            "sinopsis",
            "autores",
            "autores_ids",
            "generos",
        ]

    def validate_publicado(self, valor):
        if valor and valor > timezone.localdate():
            raise serializers.ValidationError(_("La fecha de publicación no puede ser futura."))
        return valor

    def validate_autores_ids(self, autores):
        if not autores:
            raise serializers.ValidationError(_("Indica al menos un autor."))
        if len(set(autores)) != len(autores):
            raise serializers.ValidationError(_("Hay autores repetidos."))
        return autores

    @transaction.atomic
    def create(self, validated_data):
        autores = validated_data.pop("autores", [])
        generos = validated_data.pop("generos", [])
        libro = Libro.objects.create(**validated_data)
        Autoria.objects.bulk_create(
            Autoria(libro=libro, autor=autor, orden=orden) for orden, autor in enumerate(autores)
        )
        libro.generos.set(generos)
        # bulk_create no emite m2m_changed: el vector de búsqueda (módulo 15) no se enteraría
        actualizar_busqueda(libro.pk)
        return libro

    @transaction.atomic
    def update(self, libro, validated_data):
        autores = validated_data.pop("autores", None)
        generos = validated_data.pop("generos", None)
        for campo, valor in validated_data.items():
            setattr(libro, campo, valor)
        libro.save()
        if autores is not None:  # PATCH sin autores: no tocarlos
            libro.autoria_set.all().delete()
            Autoria.objects.bulk_create(
                Autoria(libro=libro, autor=a, orden=i) for i, a in enumerate(autores)
            )
            actualizar_busqueda(libro.pk)
        if generos is not None:
            libro.generos.set(generos)
        return libro
