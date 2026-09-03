"""Cards app databae tables (models). It houses the Cards and CardMetrics models."""

from django.conf import settings
from django.db import models
from django.urls import reverse


# Create your models here.
class Cards(models.Model):
    """Store an MCP Server, Agent, SKILL.md, etc... card.

    Each row represents a specific card.
    """

    # Default user database from Django so we can see who created it later
    owner = models.ForeignKey(  # many-to-one relationship. Each card has one owner, while one user can own many cards.
        settings.AUTH_USER_MODEL,  # built in django user database
        on_delete=models.SET_NULL,  # in case user gets deleted, card will still be here.
        null=True,  # just in case user gets deleted but still gets filled out on creation
        blank=True,  # just in case user gets deleted but still gets filled out on creation
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
        """Available categories for a card."""

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
        """Return a readable description of a database row."""
        return self.name

    def get_absolute_url(self):
        """Return the URL for this card's detail page after CardCreateView validates form."""
        return reverse("cards:card_detail", kwargs={"pk": self.pk})


class CardMetrics(models.Model):
    """Store daily impression and click metrics for a card.

    Each row represents a specific card with a daily date.
    Impressions and clicks are incremented on that row for that day.
    """

    card = models.ForeignKey(
        Cards,
        on_delete=models.CASCADE,
        related_name="metrics",
    )
    date = models.DateField()
    impressions = models.PositiveIntegerField(default=0)  # Show up during a search result
    clicks = models.PositiveIntegerField(default=0)  # Click on card detail page

    class Meta:
        """Configure uniqueness and default ordering for card metrics."""

        constraints = [
            models.UniqueConstraint(
                fields=["card", "date"],
                name="unique_card_metric_per_day",
            )
        ]
        ordering = ["-date"]

    def __str__(self) -> str:
        """Return a readable description of a database row."""
        return f"{self.card.name} - {self.date}"
