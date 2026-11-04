"""REST API views for cards."""

from typing import Any

from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from .models import Cards
from .serializers import CardSerializer


class CardPermission(permissions.BasePermission):
    """Enforce authentication and card-level write permissions.

    Authenticated users may read cards and create new cards. Updating or
    deleting an existing card is limited to its owner, a listed ownership contact,
    or a staff/superuser account.
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        """Return whether the requesting user is authenticated.

        Authentication is required before any list, detail, create, update,
        or delete action is dispatched.

        Args:
            request: The incoming DRF request.
            view: The view being accessed.

        Returns:
            bool: Whether the request has an authenticated user.
        """
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view: Any, obj: Cards) -> bool:
        """Determine whether the user may access a specific card.

        Safe methods are available to authenticated users. Mutating methods
        follow the ownership rules used by the existing HTML views.

        Args:
            request: The incoming DRF request.
            view: The view being accessed.
            obj: The card being accessed.

        Returns:
            bool: Whether the user may perform the requested operation.
        """
        if request.method in permissions.SAFE_METHODS:
            return True

        user = request.user
        is_staff = user.is_staff
        is_superuser = user.is_superuser
        is_owner = obj.owner_id == user.id
        is_contact = bool(user.email) and user.email in obj.contact_emails

        return is_staff or is_superuser or is_owner or is_contact


class CardViewSet(viewsets.ModelViewSet):
    """Provide authenticated CRUD and resource-type endpoints for cards.

    The router exposes standard routes for creating, listing, retrieving,
    replacing, partially updating, and deleting cards. Creation assigns
    ownership from the authenticated request. Resource-type actions provide simple
    read-only lists for MCP servers, agents, and skills cards.
    """

    queryset = Cards.objects.all().order_by("name")
    serializer_class = CardSerializer
    permission_classes = [CardPermission]

    def perform_create(self, serializer: CardSerializer) -> None:
        """Save a new card with the requesting user as its owner.

        Args:
            serializer: A validated card serializer ready to save.
        """
        serializer.save(owner=self.request.user)

    @action(detail=False, methods=["get"], url_path="mcp-servers")
    def mcp_servers(self, request: Request) -> Response:
        """Return all cards whose resource type is MCP server.

        Args:
            request: The authenticated request supplied by DRF.

        Returns:
            Response: A JSON array of serialized MCP server cards.
        """
        return self._resource_type_response(Cards.ResourceType.MCP_SERVER)

    @action(detail=False, methods=["get"], url_path="agents")
    def agents(self, request: Request) -> Response:
        """Return all cards whose resource type is agent.

        Args:
            request: The authenticated request supplied by DRF.

        Returns:
            Response: A JSON array of serialized agent cards.
        """
        return self._resource_type_response(Cards.ResourceType.AGENT)

    @action(detail=False, methods=["get"], url_path="skills")
    def skills(self, request: Request) -> Response:
        """Return all cards whose resource type is skill.

        Args:
            request: The authenticated request supplied by DRF.

        Returns:
            Response: A JSON array of serialized skill cards.
        """
        return self._resource_type_response(Cards.ResourceType.SKILL)

    def _resource_type_response(self, resource_type: str) -> Response:
        """Build a response containing cards of one resource type.

        Args:
            resource_type: The stored ``Cards.resource_type`` value to match.

        Returns:
            Response: A name-ordered JSON array of matching cards. Pagination
                is intentionally not applied in this initial API version.
        """
        serializer = self.get_serializer(self.get_queryset().filter(resource_type=resource_type), many=True)
        return Response(serializer.data)
