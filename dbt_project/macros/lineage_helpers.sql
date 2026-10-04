{% macro get_column_lineage(model_name, column_name) %}
    {% set model = graph.nodes.get('model.' ~ model_name) %}
    {% if model and model.columns.get(column_name) %}
        {{ return(model.columns[column_name].get('meta', {}).get('lineage', {})) }}
    {% endif %}
    {{ return({}) }}
{% endmacro %}

{% macro document_lineage() %}
    {% set output = [] %}
    {% for node in graph.nodes.values() %}
        {% if node.resource_type == 'model' %}
            {% for col_name, col_info in node.columns.items() %}
                {% set lineage = col_info.get('meta', {}).get('lineage', {}) %}
                {% if lineage %}
                    {% do output.append({
                        'model': node.name,
                        'column': col_name,
                        'source_columns': lineage.get('source_columns', []),
                        'transformations': lineage.get('transformations', [])
                    }) %}
                {% endif %}
            {% endfor %}
        {% endif %}
    {% endfor %}
    {{ return(output) }}
{% endmacro %}

{% macro generate_lineage_report() %}
    {% set lineage_data = document_lineage() %}
    {% if execute %}
        {% do log(lineage_data | tojson, info=true) %}
    {% endif %}
{% endmacro %}