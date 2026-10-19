class ISBNConverter:
    regex = r"\d{13}"

    def to_python(self, value: str) -> str:
        return value

    def to_url(self, value: str) -> str:
        return value.replace("-", "")


class AnioConverter:
    regex = r"\d{4}"

    def to_python(self, value: str) -> int:
        anio = int(value)
        if not 1450 <= anio <= 2100:
            raise ValueError  # ValueError = "no encaja" → Django prueba el siguiente patrón
        return anio

    def to_url(self, value: int) -> str:
        return f"{value:04d}"
