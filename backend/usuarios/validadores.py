import re

from django.core.exceptions import ValidationError


class LetraYNumeroValidator:
    """RN-06: la contraseña debe tener al menos una letra y un número."""

    def validate(self, password, user=None):
        if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            raise ValidationError(
                "La contraseña debe tener al menos una letra y un número.",
                code="password_sin_letra_o_numero",
            )

    def get_help_text(self):
        return "La contraseña debe tener al menos una letra y un número."
