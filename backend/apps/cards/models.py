from django.db import models

# Create your models here.


class Cards(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()

    maintainers = models.JSONField(
        default=list,
        blank=True,  # makes it optional
        help_text=("Enter one maintainer per line using the format: Name, email address.")
    )

    institution = models.CharField(max_length=200, blank=True)

    class Category(models.TextChoices):
        MCP_SERVER = "mcp_server", "MCP Server"
        AGENT = "agent", "Agent"
        SKILLS_MD = "skills_md", "Skills.md"

    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        blank=True,
    )

    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Example: ['simulation', 'geometry']",
    )

    logo_url = models.URLField(blank=True)

    documentation_url = models.URLField(blank=True)

    internal_url = models.URLField(
        blank=True,
        help_text=('Example: [{"name": "run_simulation", "description": "Runs a simulation"}]'),
    )
    external_url = models.URLField(blank=True)

    tools = models.JSONField(
        default=list,
        blank=True,
        help_text=('Example: [{"name": "run_simulation", "description": "Runs a simulation"}]'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
