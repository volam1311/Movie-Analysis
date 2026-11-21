{#
    Use custom schema names exactly as written (e.g. `staging`, `marts`)
    instead of dbt's default `<target_schema>_<custom_schema>` (e.g. `main_staging`).
    Models without a custom schema fall back to the profile's schema (`main`).
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
