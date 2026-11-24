"""The plugins this server has: the modules in settings.PLUGINS, each with a `plugin`."""

import re
from functools import lru_cache
from importlib import import_module

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .plugin import Plugin

ID = re.compile(r"^[a-z][a-z0-9]{1,39}$")


@lru_cache(maxsize=8)
def load(modules: tuple[str, ...]) -> dict[str, Plugin]:
    found: dict[str, Plugin] = {}
    for path in modules:
        try:
            plugin = import_module(path).plugin
        except (ImportError, AttributeError) as error:
            raise ImproperlyConfigured(f"{path} is not a plugin: {error}") from error
        if not isinstance(plugin, Plugin) or not ID.match(plugin.id) or not plugin.name:
            raise ImproperlyConfigured(f"{path}.plugin must be a Plugin with a name and an id of letters and digits.")
        if plugin.id in found:
            raise ImproperlyConfigured(f"Two plugins have the id {plugin.id}.")
        found[plugin.id] = plugin
    return found


def plugins() -> dict[str, Plugin]:
    """By id, in the order they are listed."""
    return load(tuple(settings.PLUGINS))


def get(plugin_id: str) -> Plugin | None:
    return plugins().get(plugin_id)
