{{ config(
    materialized='table',
    tags=['marts', 'dimension'],
    meta={
        'lineage': {
            'source': 'staging.stg_nyc_311_requests',
            'transformations': ['distinct_agencies', 'attribute_enrichment']
        }
    }
) }}

with agencies as (
    select distinct
        agency_code,
        agency_name
    from {{ ref('stg_nyc_311_requests') }}
    where agency_code is not null
),

enriched as (
    select
        agency_code as agency_key,
        agency_name,
        case 
            when agency_code = 'NYPD' then 'Public Safety'
            when agency_code = 'FDNY' then 'Public Safety'
            when agency_code in ('DOB', 'HPD') then 'Housing & Buildings'
            when agency_code in ('DSNY', 'DEP') then 'Environmental Services'
            when agency_code in ('DOT', 'TLC') then 'Transportation'
            when agency_code = 'DPR' then 'Parks & Recreation'
            when agency_code in ('DOHMH', 'NYCHA') then 'Health & Housing'
            when agency_code in ('DOF', 'DCA', 'LAW', 'OATH', 'DOITT') then 'Administrative'
            else 'Other'
        end as agency_domain,
        current_timestamp as dbt_updated_at
    from agencies
)
select * from enriched