"""Rename the stored skills category value to ``skills``."""

from django.db import migrations, models


def rename_skills_category(apps, schema_editor) -> None:
    """Update existing cards before the category choices are changed."""
    cards = apps.get_model("cards", "Cards")
    cards.objects.filter(category="skills_md").update(category="skills")


def restore_skills_md_category(apps, schema_editor) -> None:
    """Restore the previous value if this migration is rolled back."""
    cards = apps.get_model("cards", "Cards")
    cards.objects.filter(category="skills").update(category="skills_md")


class Migration(migrations.Migration):
    """Rename the database value used for Skills cards."""

    dependencies = [("cards", "0005_alter_cards_internal_url_alter_cards_maintainers_and_more")]

    operations = [
        migrations.RunPython(rename_skills_category, restore_skills_md_category),
        migrations.AlterField(
            model_name="cards",
            name="category",
            field=models.CharField(
                blank=True,
                choices=[("mcp_server", "MCP Server"), ("agent", "Agent"), ("skills", "Skills")],
                max_length=20,
            ),
        ),
    ]
