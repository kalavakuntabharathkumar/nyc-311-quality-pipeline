{{ config(
    materialized='table',
    tags=['marts', 'aggregate'],
    meta={
        'lineage': {
            'source': 'marts.fact_service_requests',
            'transformations': ['monthly_aggregation', 'borough_grouping', 'kpi_calculation']
        }
    }
) }}

with facts as (
    select * from {{ ref('fact_service_requests') }}
),

date_dim as (
    select date_key, year, month, quarter
    from {{ ref('dim_date') }}
)

select
    d.year,
    d.month,
    d.quarter,
    f.borough_key,
    f.borough_name,
    f.county_name,
    
    count(*) as total_requests,
    count(case when f.status = 'Closed' then 1 end) as closed_requests,
    count(case when f.status = 'Open' then 1 end) as open_requests,
    
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
    
    round(avg(f.open_request_age_days), 2) as avg_open_request_age_days,
    
    current_timestamp as dbt_updated_at

from facts f
join date_dim d on d.date_key = f.created_date_key
group by 1, 2, 3, 4, 5, 6
order by 1, 2, 4