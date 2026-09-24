"""Register card-related models with the Django admin site."""

from django.contrib import admin

from .models import CardMetrics, Cards

admin.site.register(CardMetrics)
admin.site.register(Cards)
