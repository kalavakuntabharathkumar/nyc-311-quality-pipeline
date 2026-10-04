{{ config(
    materialized='table',
    tags=['marts', 'aggregate'],
    meta={
        'lineage': {
            'source': 'marts.fact_service_requests',
            'transformations': ['agency_aggregation', 'sla_kpi_calculation', 'scorecard_formatting']
        }
    }
) }}

with facts as (
    select * from {{ ref('fact_service_requests') }}
    where created_at >= (select max(created_at) from {{ ref('fact_service_requests') }}) - interval '90 days'
),

agency_agg as (
    select
        f.agency_key,
        f.agency_name,
        f.agency_domain,
        
        count(*) as total_requests_90d,
        count(case when f.status = 'Closed' then 1 end) as closed_requests_90d,
        count(case when f.status = 'Open' then 1 end) as open_requests_90d,
        
        round(avg(f.resolution_days), 2) as avg_resolution_days,
        round(percentile_cont(0.5) within group (order by f.resolution_days), 2) as median_resolution_days,
        
        sum(case when f.sla_compliant = true then 1 else 0 end) as sla_compliant_count,
        sum(case when f.sla_compliant = false then 1 else 0 end) as sla_breached_count,
        
        case 
            when count(case when f.sla_compliant is not null then 1 end) > 0
            then round(100.0 * sum(case when f.sla_compliant = true then 1 else 0 end) 
                 / count(case when f.sla_compliant is not null then 1 end), 2)
            else null
        end as sla_compliance_rate_pct,
        
        -- Top complaint type
        mode() within group (order by f.complaint_category) as top_complaint_category,
        
        -- Emergency request rate
        round(100.0 * sum(case when f.is_emergency then 1 else 0 end) / count(*), 2) as emergency_request_rate_pct,
        
        current_timestamp as dbt_updated_at
    from facts f
    group by 1, 2, 3
)
select * from agency_agg
order by sla_compliance_rate_pct asc nulls last