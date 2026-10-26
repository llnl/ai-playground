"""Authenticate identities asserted by a trusted, access-controlled proxy."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import RemoteUserBackend
from django.contrib.auth.middleware import RemoteUserMiddleware
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

PROXY_GROUP_PREFIX = "proxy:"


class ProxyUserBackend(RemoteUserBackend):
    """Reuse local users and create new proxy users without usable passwords."""

    def configure_user(self, request, user, created=True):
        """Disable password authentication for newly provisioned accounts."""
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user


class ProxyUserMiddleware(RemoteUserMiddleware):
    """Log in forwarded users and synchronize only proxy-managed groups."""

    header = "HTTP_X_FORWARDED_USER"
    async_capable = False

    def get_username(self, request):
        """Treat empty identity headers as missing and validate Django usernames."""
        username = super().get_username(request).strip()
        if not username:
            raise KeyError(self.header)
        user_model = get_user_model()
        try:
            user_model._meta.get_field(user_model.USERNAME_FIELD).run_validators(username)
        except ValidationError as error:
            raise PermissionDenied("Invalid proxy username.") from error
        return username

    def process_request(self, request):
        """Refresh group membership even when the user already has a session."""
        group_names = {
            PROXY_GROUP_PREFIX + name.strip()
            for name in request.headers.get("X-Forwarded-Groups", "").split(",")
            if name.strip()
        }
        max_length = Group._meta.get_field("name").max_length
        if any(len(name) > max_length for name in group_names):
            raise PermissionDenied("Invalid proxy group name.")
        super().process_request(request)
        if request.user.is_authenticated:
            self.sync_groups(request.user, group_names)

    def sync_groups(self, user, group_names):
        """Replace proxy memberships while preserving locally managed groups."""
        current_groups = {group.name: group for group in user.groups.filter(name__startswith=PROXY_GROUP_PREFIX)}
        if current_groups.keys() == group_names:
            return
        with transaction.atomic():
            existing_names = set(Group.objects.filter(name__in=group_names).values_list("name", flat=True))
            Group.objects.bulk_create(
                [Group(name=name) for name in group_names - existing_names], ignore_conflicts=True
            )
            user.groups.remove(*(group for name, group in current_groups.items() if name not in group_names))
            user.groups.add(*Group.objects.filter(name__in=group_names - current_groups.keys()))
        for cache_name in ("_perm_cache", "_group_perm_cache", "_user_perm_cache"):
            user.__dict__.pop(cache_name, None)
