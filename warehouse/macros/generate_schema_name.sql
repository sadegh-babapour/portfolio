{#- Use the folder's schema name as it is (staging, marts) instead of dbt's default
    "<target schema>_<custom schema>", so the reporting schemas have stable names. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name is not none else target.schema }}
{%- endmacro %}
