-- Data quality tests for curated layer

-- Test 1: Fact table has no duplicate primary keys
select unique_key, count(*) as cnt
from {{ ref('fact_service_requests') }}
group by unique_key
having count(*) > 1

-- Test 2: All fact records have valid dimension keys
select 'missing_agency' as test, count(*) as failures
from {{ ref('fact_service_requests') }}
where agency_key is null
union all
select 'missing_borough', count(*)
from {{ ref('fact_service_requests') }}
where borough_key is null
union all
select 'missing_complaint_type', count(*)
from {{ ref('fact_service_requests') }}
where complaint_type_key is null
union all
select 'missing_date', count(*)
from {{ ref('fact_service_requests') }}
where created_date_key is null

-- Test 3: Resolution days not negative
select count(*) as failures
from {{ ref('fact_service_requests') }}
where resolution_days < 0

-- Test 4: SLA compliance only for closed requests
select count(*) as failures
from {{ ref('fact_service_requests') }}
where sla_compliant is not null and status != 'Closed'

-- Test 5: Emergency requests have 1-day SLA
select count(*) as failures
from {{ ref('fact_service_requests') }}
where is_emergency = true and sla_days != 1

-- Test 6: Borough values are valid
select count(*) as failures
from {{ ref('fact_service_requests') }}
where borough not in ('MANHATTAN', 'BRONX', 'BROOKLYN', 'QUEENS', 'STATEN ISLAND', 'UNSPECIFIED')

-- Test 7: Status values are valid
select count(*) as failures
from {{ ref('fact_service_requests') }}
where status not in ('Open', 'Closed', 'In Progress', 'Pending')

-- Test 8: Coordinates within NYC bounds
select count(*) as failures
from {{ ref('fact_service_requests') }}
where has_coordinates = true
  and (latitude < 40.47 or latitude > 40.92
       or longitude < -74.26 or longitude > -73.70)
