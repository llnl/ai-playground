"""Cards app forms. It houses the card create form."""

from django import forms

from .models import Cards


class CardForm(forms.ModelForm):
    """Form for creating and updating cards."""

    class Meta:
        """Configure the model and fields used by the form."""

        model = Cards
        exclude = ["owner", "created_at", "updated_at"]
