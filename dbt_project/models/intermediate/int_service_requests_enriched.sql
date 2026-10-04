{{ config(
    materialized='table',
    tags=['intermediate'],
    meta={
        'lineage': {
            'source': 'staging.stg_nyc_311_requests',
            'transformations': ['sla_calculation', 'complaint_categorization', 'age_calculation', 'date_dimension_keys']
        }
    }
) }}

with base as (
    select * from {{ ref('stg_nyc_311_requests') }}
),

sla_policies as (
    select * from {{ ref('seed_agency_sla_policies') }}
),

date_spine as (
    select * from {{ ref('date_spine') }}
),

enriched as (
    select
        b.*,
        
        -- SLA Calculation
        coalesce(
            sp.sla_days,
            {{ var('default_sla_days') }}
        ) as sla_days,
        
        -- Resolution time in days
        case 
            when b.closed_at is not null 
            then extract(epoch from (b.closed_at - b.created_at)) / 86400.0
            else null
        end as resolution_days,
        
        -- SLA Compliance
        case 
            when b.closed_at is not null 
            then case 
                when extract(epoch from (b.closed_at - b.created_at)) / 86400.0 
                     <= coalesce(sp.sla_days, {{ var('default_sla_days') }})
                then true else false end
            else null
        end as sla_compliant,
        
        -- Request age (for open requests)
        case 
            when b.status = 'Open'
            then extract(epoch from (now() - b.created_at)) / 86400.0
            else null
        end as open_request_age_days,
        
        -- Complaint categorization
        case 
            when lower(b.complaint_type) like '%noise%' then 'Noise'
            when lower(b.complaint_type) like '%heat%' or lower(b.complaint_type) like '%hot water%' then 'Heat/Hot Water'
            when lower(b.complaint_type) like '%rodent%' or lower(b.complaint_type) like '%pest%' then 'Rodent/Pest'
            when lower(b.complaint_type) like '%garbage%' or lower(b.complaint_type) like '%trash%' or lower(b.complaint_type) like '%sanitation%' then 'Sanitation'
            when lower(b.complaint_type) like '%street%' or lower(b.complaint_type) like '%sidewalk%' or lower(b.complaint_type) like '%pothole%' then 'Streets/Sidewalks'
            when lower(b.complaint_type) like '%water%' or lower(b.complaint_type) like '%leak%' or lower(b.complaint_type) like '%sewer%' then 'Water/Sewer'
            when lower(b.complaint_type) like '%park%' or lower(b.complaint_type) like '%tree%' then 'Parks/Trees'
            when lower(b.complaint_type) like '%building%' or lower(b.complaint_type) like '%construction%' or lower(b.complaint_type) like '%permit%' then 'Construction/Building'
            when lower(b.complaint_type) like '%vehicle%' or lower(b.complaint_type) like '%parking%' or lower(b.complaint_type) like '%abandoned%' then 'Vehicles/Parking'
            else 'Other'
        end as complaint_category,
        
        -- Date dimension keys for joining
        date_trunc('day', b.created_at)::date as created_date_key,
        case when b.closed_at is not null then date_trunc('day', b.closed_at)::date end as closed_date_key,
        
        -- Time bucketing
        date_trunc('week', b.created_at)::date as created_week_key,
        date_trunc('month', b.created_at)::date as created_month_key,
        
        -- Priority flag (heat/water emergencies)
        case 
            when lower(b.complaint_type) like '%heat%' or lower(b.complaint_type) like '%hot water%'
            then true else false
        end as is_emergency,
        
        -- Geographic flags
        case when b.latitude is not null and b.longitude is not null then true else false end as has_coordinates,
        
        -- Metadata
        current_timestamp as dbt_updated_at
    from base b
    left join sla_policies sp
        on sp.agency = b.agency_code
        and (sp.complaint_type = b.complaint_type or sp.complaint_type = '*')
        and (sp.descriptor is null or sp.descriptor = b.descriptor or sp.descriptor = '*')
    where b.unique_key is not null
)
select * from enriched