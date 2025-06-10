from django import template

register = template.Library()

@register.filter
def lookup(dictionary, key):
    """
    Template filter to lookup a value in a dictionary.
    Usage: {{ dict|lookup:key }}
    """
    if dictionary and key in dictionary:
        return dictionary[key]
    return None
