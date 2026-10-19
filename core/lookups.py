# core/lookups.py
from django.db.models import CharField, IntegerField, Lookup, TextField, Transform


class NoEs(Lookup):
    """campo__ne=valor  →  campo <> valor"""

    lookup_name = "ne"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        return f"{lhs} <> {rhs}", (*lhs_params, *rhs_params)  # params como tupla (Django 6.0+)


CharField.register_lookup(NoEs)
TextField.register_lookup(NoEs)


class LongitudTitulo(Transform):
    lookup_name = "longitud"
    function = "LENGTH"
    output_field = IntegerField()


CharField.register_lookup(LongitudTitulo)
