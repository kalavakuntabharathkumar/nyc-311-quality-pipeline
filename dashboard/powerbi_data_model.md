# Power BI Data Model for NYC 311 Dashboard

## Star Schema Diagram

```
                    ┌─────────────────┐
                    │  dim_date       │
                    ├─────────────────┤
                    │ date_key (PK)   │
                    │ year            │
                    │ quarter         │
                    │ month           │
                    │ week_of_year    │
                    │ day_of_week     │
                    │ is_weekend      │
                    │ is_holiday      │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ dim_agency    │  │ dim_borough   │  │dim_complaint  │
├───────────────┤  ├───────────────┤  ├───────────────┤
│ agency_key(PK)│  │ borough_key   │  │complaint_key  │
│ agency_code   │  │ borough_name  │  │ complaint_type│
│ agency_name   │  │ county_name   │  │ descriptor    │
│ agency_domain │  │ sort_order    │  │ category      │
└───────┬───────┘  └───────┬───────┘  └───────┬───────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │ fact_service_requests   │
              ├─────────────────────────┤
              │ request_key (PK)        │
              │ created_date_key (FK)   │
              │ closed_date_key (FK)    │
              │ agency_key (FK)         │
              │ complaint_type_key (FK) │
              │ borough_key (FK)        │
              │ resolution_days         │
              │ sla_days                │
              │ sla_compliant (bool)    │
              │ open_request_age_days   │
              │ is_emergency (bool)     │
              │ has_coordinates (bool)  │
              │ latitude                │
              │ longitude               │
              └─────────────────────────┘
```

## Relationships

| From Table | From Column | To Table | To Column | Cardinality |
|------------|-------------|----------|-----------|-------------|
| fact_service_requests | created_date_key | dim_date | date_key | Many-to-One |
| fact_service_requests | closed_date_key | dim_date | date_key | Many-to-One |
| fact_service_requests | agency_key | dim_agency | agency_key | Many-to-One |
| fact_service_requests | complaint_type_key | dim_complaint_type | complaint_type_key | Many-to-One |
| fact_service_requests | borough_key | dim_borough | borough_key | Many-to-One |

## Recommended Visuals

### 1. Request Volume Trend
- **Visual**: Line chart
- **Axis**: dim_date[date_key] (continuous)
- **Values**: COUNT(fact[request_key])
- **Legend**: dim_agency[agency_domain] or dim_borough[borough_name]
- **Slicer**: Date range, Agency, Borough, Complaint Category

### 2. SLA Compliance Rate
- **Visual**: Gauge / KPI card + Trend line
- **Measure**: `[SLA Compliance %]`
- **Target**: 85% (configurable)
- **Drillthrough**: Agency, Borough, Complaint Category

### 3. Top 10 Complaint Types
- **Visual**: Bar chart (horizontal)
- **Axis**: dim_complaint_type[complaint_type]
- **Values**: COUNT(fact[request_key])
- **Tooltip**: SLA Compliance %, Avg Resolution Days
- **Filter**: Last 30/90/365 days

### 4. Agency Performance Scorecard
- **Visual**: Table / Matrix
- **Rows**: dim_agency[agency_name]
- **Columns**: 
  - Total Requests
  - Avg Resolution Days
  - SLA Compliance %
  - Open Requests > 30 days
  - Emergency Request Rate
- **Conditional Formatting**: Red/Green on SLA Compliance %

### 5. Geographic Heat Map
- **Visual**: Azure Map / Filled Map
- **Location**: fact[latitude], fact[longitude] OR dim_borough[borough_name]
- **Size**: COUNT(fact[request_key])
- **Color**: SLA Compliance % (diverging)
- **Filter**: Has Coordinates = true

### 6. Open Requests Aging
- **Visual**: Stacked bar / Histogram
- **Axis**: Age buckets (0-7, 8-30, 31-60, 61-90, 90+ days)
- **Values**: COUNT(fact[request_key]) where status = 'Open'
- **Legend**: dim_agency[agency_name]

## Key DAX Measures

See `dax_measures.md` for complete measure definitions.