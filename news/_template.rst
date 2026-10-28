{% for section in sections %}
{% if section %}
{{section}}

{% endif %}
{% if sections[section] %}
{% for category, val in definitions.items() if category in sections[section] and category != 'trivial' %}

### {{ definitions[category]['name'] }}

{% if definitions[category]['showcontent'] %}
{% for text, values in sections[section][category]|dictsort(by='value') %}
- {{ text }}{% if values and category != 'plugin' and category != 'process' %} ({{ values|sort|join(', ') }}){% endif %}

{% endfor %}
{% else %}
- {{ sections[section][category]['']|sort|join(', ') }}


{% endif %}
{% if sections[section][category]|length == 0 %}

No significant changes.


{% else %}
{% endif %}
{% endfor %}
{% else %}

No significant changes.


{% endif %}
{% endfor %}
