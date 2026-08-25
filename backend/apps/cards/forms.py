from django import forms

from .models import Cards


class CardForm(forms.ModelForm):
    class Meta:
        model = Cards
        exclude = ["created_at", "updated_at"]
