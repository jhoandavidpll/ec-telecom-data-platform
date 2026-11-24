{% macro clean_null_or_empty(column_name) -%}
    CASE 
        WHEN {{ column_name }} IS NULL THEN NULL
        WHEN TRIM(CAST({{ column_name }} AS STRING)) IN ('', 'N/D', 'S/D', 'null', 'NULL', '-', 'nan', 'NaN') THEN NULL
        ELSE TRIM(CAST({{ column_name }} AS STRING))
    END
{%- endmacro %}
