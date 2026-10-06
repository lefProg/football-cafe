import json

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


@register.filter
def json_ld(data):
    """Dump `data` as JSON for a <script> tag. <, > and & are escaped so text in it cannot close the tag."""
    text = json.dumps(data, ensure_ascii=False)
    return mark_safe(text.replace('<', '\\u003C').replace('>', '\\u003E').replace('&', '\\u0026'))
