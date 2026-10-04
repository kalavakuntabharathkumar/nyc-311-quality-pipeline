{{ config(
    materialized='table',
    tags=['marts', 'dimension'],
    meta={
        'lineage': {
            'source': 'staging.stg_nyc_311_requests',
            'transformations': ['distinct_complaint_types', 'category_assignment']
        }
    }
) }}

with complaints as (
    select distinct
        complaint_type,
        descriptor
    from {{ ref('stg_nyc_311_requests') }}
    where complaint_type is not null
),

enriched as (
    select
        {{ dbt_utils.generate_surrogate_key(['complaint_type', 'descriptor']) }} as complaint_type_key,
        complaint_type,
        descriptor,
        case 
            when lower(complaint_type) like '%noise%' then 'Noise'
            when lower(complaint_type) like '%heat%' or lower(complaint_type) like '%hot water%' then 'Heat/Hot Water'
            when lower(complaint_type) like '%rodent%' or lower(complaint_type) like '%pest%' then 'Rodent/Pest'
            when lower(complaint_type) like '%garbage%' or lower(complaint_type) like '%trash%' or lower(complaint_type) like '%sanitation%' then 'Sanitation'
            when lower(complaint_type) like '%street%' or lower(complaint_type) like '%sidewalk%' or lower(complaint_type) like '%pothole%' then 'Streets/Sidewalks'
            when lower(complaint_type) like '%water%' or lower(complaint_type) like '%leak%' or lower(complaint_type) like '%sewer%' then 'Water/Sewer'
            when lower(complaint_type) like '%park%' or lower(complaint_type) like '%tree%' then 'Parks/Trees'
            when lower(complaint_type) like '%building%' or lower(complaint_type) like '%construction%' or lower(complaint_type) like '%permit%' then 'Construction/Building'
            when lower(complaint_type) like '%vehicle%' or lower(complaint_type) like '%parking%' or lower(complaint_type) like '%abandoned%' then 'Vehicles/Parking'
            else 'Other'
        end as complaint_category,
        current_timestamp as dbt_updated_at
    from complaints
)
select * from enriched