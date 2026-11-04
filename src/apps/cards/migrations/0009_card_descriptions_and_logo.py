import apps.cards.models
from django.core.validators import FileExtensionValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cards", "0008_remove_cards_category_remove_cards_external_url_and_more")]

    operations = [
        migrations.RenameField(
            model_name="cards",
            old_name="description",
            new_name="long_description",
        ),
        migrations.AddField(
            model_name="cards",
            name="short_description",
            field=models.CharField(default="", max_length=200),
            preserve_default=False,
        ),
        migrations.RemoveField(model_name="cards", name="logo_url"),
        migrations.AddField(
            model_name="cards",
            name="logo",
            field=models.ImageField(
                blank=True,
                upload_to="cards/logos/",
                validators=[
                    FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "webp"]),
                    apps.cards.models.validate_logo_size,
                ],
            ),
        ),
    ]
