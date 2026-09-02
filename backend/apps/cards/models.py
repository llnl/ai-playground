from django.db import models
from django.urls import reverse
from django.conf import settings

# Create your models here.
class Cards(models.Model):

    # Default user database from Django so we can see who created it later
    owner = models.ForeignKey( # many-to-one relationship. Each card has one owner, while one user can own many cards.
        settings.AUTH_USER_MODEL,  # built in django user database
        on_delete=models.SET_NULL, # in case user gets deleted, card will still be here.
        null=True, # just in case user gets deleted but still gets filled out on creation
        blank=True, # just in case user gets deleted but still gets filled out on creation
        related_name="cards",  # reverse relationship lookup from user database to cards database
    )

    name = models.CharField(max_length=100)
    description = models.TextField()

    maintainers = models.JSONField(
        default=list,
        blank=True,  # makes it optional
        help_text=("Enter one maintainer per line using the format: Name, email address."),
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

    # This gets called after a row in the database is created succesfully
    # We send it to the card_detail url view based on its primary key
    def get_absolute_url(self):
        return reverse(
            "cards:card_detail",
            kwargs={"pk": self.pk}
        )
