{{ config(
    materialized='table',
    tags=['marts', 'dimension'],
    meta={
        'lineage': {
            'source': 'dbt_utils.date_spine',
            'transformations': ['date_spine_generation', 'attribute_enrichment']
        }
    }
) }}

{% set start_date = '2020-01-01' %}
{% set end_date = '2030-12-31' %}

with date_spine as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('" ~ start_date ~ "' as date)",
        end_date="cast('" ~ end_date ~ "' as date)"
    ) }}
),

enriched as (
    select
        date_day as date_key,
        extract(year from date_day)::int as year,
        extract(quarter from date_day)::int as quarter,
        extract(month from date_day)::int as month,
        to_char(date_day, 'Month') as month_name,
        extract(week from date_day)::int as week_of_year,
        extract(day from date_day)::int as day_of_month,
        extract(dow from date_day)::int as day_of_week,  -- 0=Sunday
        to_char(date_day, 'Day') as day_name,
        case when extract(dow from date_day) in (0, 6) then true else false end as is_weekend,
        -- US Federal holidays (simplified)
        case 
            when (extract(month from date_day) = 1 and extract(day from date_day) = 1) then true  -- New Year's Day
            when (extract(month from date_day) = 7 and extract(day from date_day) = 4) then true  -- Independence Day
            when (extract(month from date_day) = 12 and extract(day from date_day) = 25) then true  -- Christmas
            else false
        end as is_federal_holiday,
        current_timestamp as dbt_updated_at
    from date_spine
)
select * from enriched