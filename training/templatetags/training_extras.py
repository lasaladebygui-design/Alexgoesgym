from django import template

register = template.Library()

SET_TYPE_DOT = {
    "warmup": "bg-series-blue",
    "working": "bg-series-green",
    "approach": "bg-series-yellow",
    "top_set": "bg-series-red",
    "backoff": "bg-series-violet",
    "drop_set": "bg-ink-secondary border border-ink-muted",
    "rest_pause": "bg-series-orange",
    "myo_reps": "bg-series-blue",
    "failure": "bg-white",
    "custom": "bg-ink-muted",
}


@register.filter
def set_type_dot(set_type):
    return SET_TYPE_DOT.get(set_type, "bg-ink-muted")


@register.filter
def kg(value_kg, unit="kg"):
    """kg canónico -> valor a mostrar en la unidad pedida."""
    from training.utils import from_kg
    if value_kg is None:
        return None
    return from_kg(value_kg, unit)
