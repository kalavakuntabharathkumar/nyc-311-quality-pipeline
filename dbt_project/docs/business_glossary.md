# NYC 311 Business Glossary

This glossary defines key business terms used in the NYC 311 data pipeline and dashboard.
Each term has an assigned data steward responsible for definition accuracy and usage governance.

---

## 1. Service Request
- **Definition**: A citizen-initiated request for non-emergency government service submitted via 311 (phone, web, mobile app)
- **Domain**: Core Operations
- **Steward**: 311 Operations Manager
- **Source System**: NYC 311 CRM (Salesforce/CRM)
- **Key Attributes**: unique_key, created_date, agency, complaint_type, status

## 2. Unique Key
- **Definition**: System-generated immutable identifier for each service request (format: ##########)
- **Domain**: Technical
- **Steward**: Data Engineering Lead
- **Source System**: 311 CRM
- **Constraints**: Primary key, not null, unique

## 3. Agency
- **Definition**: City agency responsible for fulfilling the service request
- **Domain**: Organizational
- **Steward**: Agency Liaison Officer
- **Source System**: 311 CRM → Agency Assignment Rules
- **Valid Values**: NYPD, DOB, DOHMH, DSNY, DOT, DPR, DEP, HPD, DOF, DCA, DOITT, FDNY, LAW, OATH, TLC, NYCHA

## 4. Complaint Type
- **Definition**: Standardized classification of the service request reason (e.g., "Noise - Residential", "Heat/Hot Water")
- **Domain**: Taxonomy
- **Steward**: 311 Taxonomy Manager
- **Source System**: 311 CRM Complaint Type Hierarchy
- **Hierarchy**: Category → Complaint Type → Descriptor

## 5. Descriptor
- **Definition**: Granular sub-classification providing additional detail within a complaint type
- **Domain**: Taxonomy
- **Steward**: 311 Taxonomy Manager
- **Source System**: 311 CRM
- **Example**: Complaint Type: "Noise - Residential" → Descriptor: "Loud Music/Party"

## 6. SLA (Service Level Agreement)
- **Definition**: Maximum allowable time (in calendar days) for an agency to resolve a specific complaint type
- **Domain**: Performance Metrics
- **Steward**: Agency Performance Analyst
- **Source System**: Agency SLA Policy Documents
- **Note**: Varies by agency, complaint type, and sometimes descriptor

## 7. SLA Compliance
- **Definition**: Binary indicator (Yes/No) whether a closed request was resolved within its SLA days
- **Domain**: Performance Metrics
- **Steward**: Agency Performance Analyst
- **Calculation**: `resolution_days <= sla_days` where `resolution_days = closed_date - created_date`
- **Null Handling**: Open requests and requests without closed_date are excluded

## 8. Borough
- **Definition**: NYC borough where the service request incident occurred
- **Domain**: Geography
- **Steward**: GIS Team Lead
- **Source System**: 311 CRM (geocoded from address)
- **Valid Values**: MANHATTAN, BRONX, BROOKLYN, QUEENS, STATEN ISLAND, UNSPECIFIED

## 9. Incident ZIP
- **Definition**: 5-digit ZIP code of the incident location
- **Domain**: Geography
- **Steward**: GIS Team Lead
- **Source System**: 311 CRM (geocoded from address)
- **Format**: 5 digits (10001-11697 for NYC)
- **Quality**: ~85% completeness

## 10. Status
- **Definition**: Current lifecycle state of the service request
- **Domain**: Workflow
- **Steward**: 311 Operations Manager
- **Valid Values**: Open, Closed, In Progress, Pending
- **Transitions**: Open → In Progress → Closed (Pending is temporary hold)

## 11. Resolution Days
- **Definition**: Calendar days elapsed between request creation and closure
- **Domain**: Performance Metrics
- **Steward**: Data Engineering Lead
- **Calculation**: `EXTRACT(EPOCH FROM (closed_at - created_at)) / 86400`
- **Note**: Calendar days, not business days

## 12. Open Request Age
- **Definition**: Calendar days a request has been open without resolution
- **Domain**: Performance Metrics
- **Steward**: Agency Performance Analyst
- **Calculation**: `CURRENT_DATE - created_date` (for status = 'Open')
- **Usage**: Identifies backlog and aging requests

---

## Governance Notes

- **Review Cycle**: Quarterly (aligned with agency performance reviews)
- **Change Process**: Steward proposes → Data Governance Council approves → Engineering implements
- **Versioning**: All definitions versioned in dbt docs with `dbt_updated_at` timestamp
- **Access**: Published in dbt Docs Catalog and Power BI Data Dictionary