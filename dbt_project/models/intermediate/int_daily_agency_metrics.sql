{{ config(
    materialized='table',
    tags=['intermediate'],
    meta={
        'lineage': {
            'source': 'intermediate.int_service_requests_enriched',
            'transformations': ['daily_aggregation', 'agency_grouping', 'sla_rate_calculation']
        }
    }
) }}

with requests as (
    select * from {{ ref('int_service_requests_enriched') }}
),

daily_agg as (
    select
        created_date_key as date_key,
        agency_code,
        agency_name,
        borough,
        complaint_category,
        
        count(*) as request_count,
        count(case when status = 'Closed' then 1 end) as closed_count,
        count(case when status = 'Open' then 1 end) as open_count,
        
        avg(resolution_days) as avg_resolution_days,
        percentile_cont(0.5) within group (order by resolution_days) as median_resolution_days,
        
        sum(case when sla_compliant = true then 1 else 0 end) as sla_compliant_count,
        sum(case when sla_compliant = false then 1 else 0 end) as sla_breached_count,
        
        case 
            when count(case when sla_compliant is not null then 1 end) > 0
            then round(100.0 * sum(case when sla_compliant = true then 1 else 0 end) 
                 / count(case when sla_compliant is not null then 1 end), 2)
            else null
        end as sla_compliance_rate,
        
        avg(open_request_age_days) as avg_open_request_age_days,
        
        current_timestamp as dbt_updated_at
    from requests
    group by 1, 2, 3, 4, 5
)
select * from daily_agg