{{ config(
    materialized='view',
    tags=['staging'],
    meta={
        'lineage': {
            'source': 'raw.nyc_311_requests',
            'transformations': ['type_casting', 'date_parsing', 'standardization']
        }
    }
) }}

with raw as (
    select
        unique_key,
        -- Parse timestamps
        created_date::timestamptz as created_at,
        case 
            when closed_date is not null and closed_date != '' 
            then closed_date::timestamptz 
            else null 
        end as closed_at,
        resolution_action_updated_date::timestamptz as resolution_updated_at,
        
        -- Standardize categorical fields
        upper(trim(agency)) as agency_code,
        trim(agency_name) as agency_name,
        trim(complaint_type) as complaint_type,
        trim(descriptor) as descriptor,
        upper(trim(location_type)) as location_type,
        
        -- Clean ZIP code
        regexp_replace(incident_zip, '\\D', '', 'g') as incident_zip,
        
        -- Address fields
        trim(incident_address) as incident_address,
        trim(street_name) as street_name,
        trim(cross_street_1) as cross_street_1,
        trim(cross_street_2) as cross_street_2,
        upper(trim(city)) as city,
        
        -- Standardize borough
        case 
            when upper(trim(borough)) in ('MANHATTAN', 'NEW YORK', 'MN') then 'MANHATTAN'
            when upper(trim(borough)) in ('BRONX', 'BX') then 'BRONX'
            when upper(trim(borough)) in ('BROOKLYN', 'BK', 'KINGS') then 'BROOKLYN'
            when upper(trim(borough)) in ('QUEENS', 'QN') then 'QUEENS'
            when upper(trim(borough)) in ('STATEN ISLAND', 'SI', 'RICHMOND') then 'STATEN ISLAND'
            else 'UNSPECIFIED'
        end as borough,
        
        -- Coordinates
        latitude::double precision as latitude,
        longitude::double precision as longitude,
        
        -- Location JSON parsing
        location::jsonb as location_json,
        
        -- Status
        trim(status) as status,
        trim(resolution_description) as resolution_description,
        
        -- Geographic/administrative
        trim(community_board) as community_board,
        trim(council_district) as council_district,
        trim(census_tract) as census_tract,
        trim(bin) as bin,
        trim(bbl) as bbl,
        trim(nta) as nta,
        
        -- Metadata
        ingested_at,
        batch_id,
        raw_payload
    from {{ source('raw', 'nyc_311_requests') }}
    where unique_key is not null
)
select * from raw