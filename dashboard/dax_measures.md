# Key DAX Measures for NYC 311 Power BI Dashboard

## Base Measures

```dax
-- Total Requests
Total Requests = COUNTROWS(fact_service_requests)

-- Closed Requests
Closed Requests = CALCULATE([Total Requests], fact_service_requests[status] = "Closed")

-- Open Requests
Open Requests = CALCULATE([Total Requests], fact_service_requests[status] = "Open")

-- Average Resolution Days
Avg Resolution Days = 
    AVERAGEX(
        FILTER(fact_service_requests, fact_service_requests[resolution_days] > 0),
        fact_service_requests[resolution_days]
    )

-- Median Resolution Days
Median Resolution Days = 
    MEDIANX(
        FILTER(fact_service_requests, fact_service_requests[resolution_days] > 0),
        fact_service_requests[resolution_days]
    )
```

## SLA Measures

```dax
-- SLA Compliant Count
SLA Compliant Count = 
    CALCULATE(
        COUNTROWS(fact_service_requests),
        fact_service_requests[sla_compliant] = TRUE()
    )

-- SLA Breached Count
SLA Breached Count = 
    CALCULATE(
        COUNTROWS(fact_service_requests),
        fact_service_requests[sla_compliant] = FALSE()
    )

-- SLA Compliance %
SLA Compliance % = 
    DIVIDE(
        [SLA Compliant Count],
        [SLA Compliant Count] + [SLA Breached Count],
        BLANK()
    )

-- SLA Compliance % by Agency
SLA Compliance % by Agency = 
    CALCULATE(
        [SLA Compliance %],
        ALLEXCEPT(fact_service_requests, dim_agency[agency_name])
    )
```

## Time Intelligence Measures

```dax
-- Requests MTD
Requests MTD = 
    CALCULATE(
        [Total Requests],
        DATESMTD(dim_date[date_key])
    )

-- Requests QTD
Requests QTD = 
    CALCULATE(
        [Total Requests],
        DATESQTD(dim_date[date_key])
    )

-- Requests YTD
Requests YTD = 
    CALCULATE(
        [Total Requests],
        DATESYTD(dim_date[date_key])
    )

-- Requests Prior Year Same Period
Requests PY = 
    CALCULATE(
        [Total Requests],
        SAMEPERIODLASTYEAR(dim_date[date_key])
    )

-- YoY Growth %
YoY Growth % = 
    DIVIDE(
        [Total Requests] - [Requests PY],
        [Requests PY],
        BLANK()
    )

-- 7-Day Rolling Average
Rolling 7-Day Avg = 
    CALCULATE(
        AVERAGEX(
            VALUES(dim_date[date_key]),
            CALCULATE([Total Requests])
        ),
        DATESINPERIOD(dim_date[date_key], MAX(dim_date[date_key]), -7, DAY)
    )
```

## Aging Measures

```dax
-- Open Requests Aging Buckets
Open Requests 0-7 Days = 
    CALCULATE(
        [Open Requests],
        fact_service_requests[open_request_age_days] <= 7
    )

Open Requests 8-30 Days = 
    CALCULATE(
        [Open Requests],
        fact_service_requests[open_request_age_days] > 7,
        fact_service_requests[open_request_age_days] <= 30
    )

Open Requests 31-60 Days = 
    CALCULATE(
        [Open Requests],
        fact_service_requests[open_request_age_days] > 30,
        fact_service_requests[open_request_age_days] <= 60
    )

Open Requests 61-90 Days = 
    CALCULATE(
        [Open Requests],
        fact_service_requests[open_request_age_days] > 60,
        fact_service_requests[open_request_age_days] <= 90
    )

Open Requests 90+ Days = 
    CALCULATE(
        [Open Requests],
        fact_service_requests[open_request_age_days] > 90
    )

-- Average Open Request Age
Avg Open Request Age = 
    AVERAGEX(
        FILTER(fact_service_requests, fact_service_requests[status] = "Open"),
        fact_service_requests[open_request_age_days]
    )
```

## Geographic Measures

```dax
-- Requests with Coordinates
Requests with Coords = 
    CALCULATE(
        [Total Requests],
        fact_service_requests[has_coordinates] = TRUE()
    )

-- Coordinate Coverage %
Coordinate Coverage % = 
    DIVIDE(
        [Requests with Coords],
        [Total Requests],
        BLANK()
    )
```

## Advanced: Dynamic SLA Target

```dax
-- Dynamic SLA Target (configurable via What-If parameter)
SLA Target Days = SELECTEDVALUE(SLA_Target[Target Days], 30)

-- Adjusted Compliance with Dynamic Target
Adjusted SLA Compliant = 
    CALCULATE(
        COUNTROWS(fact_service_requests),
        fact_service_requests[resolution_days] <= [SLA Target Days],
        fact_service_requests[status] = "Closed"
    )

Adjusted SLA Compliance % = 
    DIVIDE(
        [Adjusted SLA Compliant],
        [Closed Requests],
        BLANK()
    )
```

## Visual-Level Filters (Recommended)

```dax
-- Last N Days Filter (apply to visual)
Last N Days = 
    VAR MaxDate = MAX(dim_date[date_key])
    VAR N = SELECTEDVALUE(Days_Parameter[Days], 30)
    RETURN
        CALCULATE(
            [Total Requests],
            dim_date[date_key] >= MaxDate - N
        )
```

## Performance Tips

1. **Use Calculation Groups** for time intelligence (MTD, QTD, YTD, PY)
2. **Mark dim_date as Date Table** in Power BI
3. **Set Relationship Cross-Filter Direction** to Single (fact → dim)
4. **Enable Incremental Refresh** on fact_service_requests (daily partition)
5. **Use Aggregations** for borough/month level views
6. **Consider DirectQuery** for real-time needs, Import for performance