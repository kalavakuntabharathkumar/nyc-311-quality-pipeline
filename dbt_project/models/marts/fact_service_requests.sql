{{ config(
    materialized='table',
    tags=['marts', 'fact'],
    partition_by={
        'field': 'created_date_key',
        'data_type': 'date',
        'granularity': 'month'
    },
    cluster_by=['agency_key', 'borough_key'],
    meta={
        'lineage': {
            'source': 'intermediate.int_service_requests_enriched',
            'transformations': ['fact_construction', 'dimension_key_joins', 'measure_calculation']
        }
    }
) }}

with enriched as (
    select * from {{ ref('int_service_requests_enriched') }}
),

agency_dim as (
    select agency_key, agency_name, agency_domain
    from {{ ref('dim_agency') }}
),

complaint_dim as (
    select complaint_type_key, complaint_type, descriptor, complaint_category
    from {{ ref('dim_complaint_type') }}
),

borough_dim as (
    select borough_key, borough_name, county_name
    from {{ ref('dim_borough') }}
)

select
    -- Primary key
    e.unique_key as request_key,
    
    -- Dimension keys
    e.created_date_key,
    e.closed_date_key,
    a.agency_key,
    c.complaint_type_key,
    b.borough_key,
    
    -- Attributes
    e.agency_code,
    e.agency_name,
    e.complaint_type,
    e.descriptor,
    e.complaint_category,
    e.borough,
    e.incident_zip,
    e.status,
    e.location_type,
    
    -- Measures
    e.resolution_days,
    e.sla_days,
    e.sla_compliant,
    e.open_request_age_days,
    e.is_emergency,
    e.has_coordinates,
    
    -- Coordinates for mapping
    e.latitude,
    e.longitude,
    
    -- Metadata
    e.created_at,
    e.closed_at,
    e.dbt_updated_at

from enriched e
left join agency_dim a on a.agency_code = e.agency_code
left join complaint_dim c 
    on c.complaint_type = e.complaint_type 
    and (c.descriptor = e.descriptor or c.descriptor is null or e.descriptor is null)
left join borough_dim b on b.borough_key = e.borough
where e.unique_key is not null