import markdown as markdown_lib
from django import template
from django.contrib.humanize.templatetags.humanize import apnumber as humanize_apnumber
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def markdown(text):
    """Render the house's own Markdown. Only ever use this on text the author wrote."""
    return mark_safe(markdown_lib.markdown(text, extensions=['smarty']))


register.filter('apnumber', humanize_apnumber)
