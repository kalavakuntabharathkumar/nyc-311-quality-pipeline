{{ config(
    materialized='table',
    tags=['marts', 'dimension'],
    meta={
        'lineage': {
            'source': 'staging.stg_nyc_311_requests',
            'transformations': ['distinct_boroughs', 'geo_enrichment']
        }
    }
) }}

with boroughs as (
    select distinct borough
    from {{ ref('stg_nyc_311_requests') }}
    where borough is not null
),

enriched as (
    select
        borough as borough_key,
        borough as borough_name,
        case borough
            when 'MANHATTAN' then 'New York County'
            when 'BRONX' then 'Bronx County'
            when 'BROOKLYN' then 'Kings County'
            when 'QUEENS' then 'Queens County'
            when 'STATEN ISLAND' then 'Richmond County'
            else 'Unspecified'
        end as county_name,
        case borough
            when 'MANHATTAN' then 1
            when 'BRONX' then 2
            when 'BROOKLYN' then 3
            when 'QUEENS' then 4
            when 'STATEN ISLAND' then 5
            else 0
        end as borough_sort_order,
        current_timestamp as dbt_updated_at
    from boroughs
)
select * from enriched