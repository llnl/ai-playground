"""Serializers for the cards API."""

from typing import Any

from rest_framework import serializers

from .models import Cards


class CardSerializer(serializers.ModelSerializer):
    """Convert card instances to and from API representations.

    Ownership and server-managed fields are included in responses but are
    read-only in requests, ensuring that the API controls those values.
    """

    owner = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        """Define the public card representation and immutable fields."""

        model = Cards
        fields = [
            "id",
            "owner",
            "name",
            "description",
            "maintainers",
            "institution",
            "from_official_team",
            "category",
            "tags",
            "logo_url",
            "documentation_url",
            "internal_url",
            "external_url",
            "tools",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "owner", "from_official_team", "created_at", "updated_at"]

    def validate_maintainers(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate that maintainers are objects with email addresses.

        Args:
            value: The proposed maintainer list.

        Returns:
            list: The validated maintainer list.

        Raises:
            serializers.ValidationError: If an item is not a dictionary with
                a non-empty ``email`` value.
        """
        if not isinstance(value, list) or any(not isinstance(item, dict) or not item.get("email") for item in value):
            raise serializers.ValidationError("Maintainers must be objects containing an email address.")
        return value

    def validate_tags(self, value: list[str]) -> list[str]:
        """Validate that tags are a list of non-empty strings.

        Args:
            value: The proposed tag list.

        Returns:
            list: The validated tag list.

        Raises:
            serializers.ValidationError: If any tag is blank or not a string.
        """
        if not isinstance(value, list) or any(not isinstance(tag, str) or not tag.strip() for tag in value):
            raise serializers.ValidationError("Tags must be a list of non-empty strings.")
        return value

    def validate_tools(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate that tools are objects with names.

        Args:
            value: The proposed tool list.

        Returns:
            list: The validated tool list.

        Raises:
            serializers.ValidationError: If an item is not a dictionary with
                a non-empty ``name`` value.
        """
        if not isinstance(value, list) or any(not isinstance(tool, dict) or not tool.get("name") for tool in value):
            raise serializers.ValidationError("Tools must be objects containing a name.")
        return value
