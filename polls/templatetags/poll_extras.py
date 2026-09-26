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


@register.filter
def time_left(value):
    """"2 saat kaldı" / "az kaldı" for an upcoming datetime."""
    if not value:
        return ""
    if value - timezone.now() < timedelta(minutes=1):
        return "az kaldı"
    from django.utils.timesince import timeuntil

    return f"{timeuntil(value, depth=1)} kaldı"
