from datetime import timedelta

from django import template
from django.utils import timezone
from django.utils.timesince import timesince

register = template.Library()


@register.filter
def relative_time(value):
    """"az önce" for < 1 minute, otherwise e.g. "5 dakika önce" / "2 gün önce"."""
    if not value:
        return ""
    if timezone.now() - value < timedelta(minutes=1):
        return "az önce"
    return f"{timesince(value, depth=1)} önce"


@register.filter
def get_item(mapping, key):
    """Dictionary lookup in templates: {{ mydict|get_item:key }}."""
    try:
        return mapping.get(key)
    except AttributeError:
        return None
