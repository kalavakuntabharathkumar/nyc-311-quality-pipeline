"""
Core transformation logic for NYC 311 data.

These functions implement the business logic that dbt models call via Python models
or that can be used directly for complex transformations not easily expressed in SQL.
"""

import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SLAPolicy:
    """SLA policy for a complaint type within an agency."""
    agency: str
    complaint_type: str
    descriptor: Optional[str]
    sla_days: int
    business_hours_only: bool = False


# SLA Policies - In production, this would come from a reference table
SLA_POLICIES: List[SLAPolicy] = [
    SLAPolicy("NYPD", "Noise - Residential", None, 30),
    SLAPolicy("NYPD", "Noise - Commercial", None, 30),
    SLAPolicy("DOB", "General Construction/Plumbing", None, 5),
    SLAPolicy("DOHMH", "Rodent", None, 14),
    SLAPolicy("DSNY", "Missed Collection", None, 2),
    SLAPolicy("DOT", "Street Light Condition", None, 10),
    SLAPolicy("HPD", "Heat/Hot Water", None, 1),  # Emergency - 24 hours
    SLAPolicy("DEP", "Water Leak", None, 3),
    # Default fallback
    SLAPolicy("*", "*", None, 30),
]


def parse_datetime(value: Any) -> Optional[datetime]:
    """Parse various datetime formats from NYC 311 API."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        # Assume milliseconds since epoch
        return datetime.fromtimestamp(value / 1000)
    if isinstance(value, str):
        # Try multiple formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    logger.warning("datetime_parse_failed", value=value)
    return None


def standardize_borough(value: Any) -> Optional[str]:
    """Standardize borough names to consistent format."""
    if not value:
        return "UNSPECIFIED"
    
    value = str(value).strip().upper()
    mapping = {
        "MANHATTAN": "MANHATTAN",
        "NEW YORK": "MANHATTAN",
        "MN": "MANHATTAN",
        "BRONX": "BRONX",
        "BX": "BRONX",
        "BROOKLYN": "BROOKLYN",
        "BK": "BROOKLYN",
        "KINGS": "BROOKLYN",
        "QUEENS": "QUEENS",
        "QN": "QUEENS",
        "STATEN ISLAND": "STATEN ISLAND",
        "SI": "STATEN ISLAND",
        "RICHMOND": "STATEN ISLAND",
    }
    return mapping.get(value, "UNSPECIFIED")


def standardize_agency(value: Any) -> Optional[str]:
    """Standardize agency codes."""
    if not value:
        return None
    value = str(value).strip().upper()
    # Common abbreviations
    mapping = {
        "NEW YORK POLICE DEPARTMENT": "NYPD",
        "POLICE DEPARTMENT": "NYPD",
        "DEPARTMENT OF BUILDINGS": "DOB",
        "DEPARTMENT OF HEALTH": "DOHMH",
        "DEPARTMENT OF SANITATION": "DSNY",
        "DEPARTMENT OF TRANSPORTATION": "DOT",
        "DEPARTMENT OF PARKS": "DPR",
        "DEPARTMENT OF ENVIRONMENTAL PROTECTION": "DEP",
        "HOUSING PRESERVATION": "HPD",
        "DEPARTMENT OF FINANCE": "DOF",
        "DEPARTMENT OF CONSUMER AFFAIRS": "DCA",
        "FIRE DEPARTMENT": "FDNY",
        "LAW DEPARTMENT": "LAW",
        "TAXI AND LIMOUSINE": "TLC",
        "HOUSING AUTHORITY": "NYCHA",
    }
    return mapping.get(value, value)


def clean_zip_code(value: Any) -> Optional[str]:
    """Extract and validate 5-digit ZIP code."""
    if not value:
        return None
    
    value = str(value).strip()
    # Extract first 5 digits
    match = re.match(r"^(\d{5})", value)
    if match:
        zip_code = match.group(1)
        # Validate NYC ZIP range
        if 10001 <= int(zip_code) <= 11697:
            return zip_code
    return None


def calculate_resolution_days(created: Any, closed: Any) -> Optional[float]:
    """Calculate calendar days between created and closed."""
    created_dt = parse_datetime(created)
    closed_dt = parse_datetime(closed)
    
    if not created_dt or not closed_dt:
        return None
    
    if closed_dt < created_dt:
        logger.warning("closed_before_created", created=created_dt, closed=closed_dt)
        return None
    
    delta = closed_dt - created_dt
    return delta.total_seconds() / 86400  # Days as float


def calculate_business_days(created: Any, closed: Any, holidays: List[datetime] = None) -> Optional[int]:
    """Calculate business days between created and closed (simplified)."""
    created_dt = parse_datetime(created)
    closed_dt = parse_datetime(closed)
    
    if not created_dt or not closed_dt:
        return None
    
    if closed_dt < created_dt:
        return None
    
    # Simplified: count weekdays only
    business_days = 0
    current = created_dt.date()
    end = closed_dt.date()
    holidays_set = set(h.date() for h in holidays) if holidays else set()
    
    while current <= end:
        if current.weekday() < 5 and current not in holidays_set:  # Mon-Fri
            business_days += 1
        current += timedelta(days=1)
    
    return business_days


def get_sla_days(agency: str, complaint_type: str, descriptor: str = None) -> int:
    """Look up SLA days for agency/complaint_type combination."""
    agency = standardize_agency(agency)
    
    for policy in SLA_POLICIES:
        if policy.agency == "*" and policy.complaint_type == "*":
            continue  # Skip default for now
        if policy.agency == agency and policy.complaint_type == complaint_type:
            if policy.descriptor is None or policy.descriptor == descriptor:
                return policy.sla_days
    
    # Fallback to default
    for policy in SLA_POLICIES:
        if policy.agency == "*" and policy.complaint_type == "*":
            return policy.sla_days
    
    return 30  # Hard default


def is_sla_compliant(created: Any, closed: Any, agency: str, complaint_type: str, descriptor: str = None) -> Optional[bool]:
    """Determine if request was resolved within SLA."""
    resolution_days = calculate_resolution_days(created, closed)
    if resolution_days is None:
        return None  # Can't determine
    
    sla_days = get_sla_days(agency, complaint_type, descriptor)
    return resolution_days <= sla_days


def parse_location_json(location: Any) -> Dict[str, Any]:
    """Parse location JSONB field into structured components."""
    result = {
        "type": None,
        "coordinates": None,
        "human_address": None
    }
    
    if not location:
        return result
    
    if isinstance(location, str):
        try:
            location = json.loads(location)
        except json.JSONDecodeError:
            return result
    
    if isinstance(location, dict):
        result["type"] = location.get("type")
        result["coordinates"] = location.get("coordinates")
        result["human_address"] = location.get("human_address")
    
    return result


def categorize_complaint(complaint_type: str, descriptor: str) -> Dict[str, str]:
    """Categorize complaint into domain categories."""
    complaint_type = (complaint_type or "").lower()
    descriptor = (descriptor or "").lower()
    
    categories = {
        "noise": ["noise"],
        "sanitation": ["garbage", "trash", "recycling", "missed collection", "sanitation"],
        "housing": ["heat", "hot water", "housing", "maintenance", "plumbing", "vermin", "rodent", "pest"],
        "streets": ["street", "sidewalk", "pothole", "light", "sign", "traffic"],
        "vehicles": ["vehicle", "parking", "abandoned", "towed"],
        "construction": ["construction", "building", "permit", "renovation"],
        "environment": ["water", "air", "odor", "pollution", "sewer"],
        "parks": ["park", "tree", "playground"],
        "animals": ["dog", "cat", "animal", "wildlife"],
    }
    
    for category, keywords in categories.items():
        for kw in keywords:
            if kw in complaint_type or kw in descriptor:
                return {"category": category, "subcategory": complaint_type}
    
    return {"category": "other", "subcategory": complaint_type}


def extract_address_components(address: str) -> Dict[str, Optional[str]]:
    """Parse address string into components."""
    result = {
        "house_number": None,
        "street_name": None,
        "street_type": None,
        "unit": None
    }
    
    if not address:
        return result
    
    # Simple regex for NYC addresses
    # e.g., "123 MAIN ST APT 4B"
    pattern = r"^(\d+)\s+(.+?)\s+(ST|AVE|AVENUE|BLVD|BOULEVARD|RD|ROAD|DR|DRIVE|LN|LANE|CT|COURT|PL|PLACE|PKWY|PARKWAY|TER|TERRACE|CIR|CIRCLE)(?:\s+(APT|UNIT|#)\s*(\w+))?$"
    match = re.match(pattern, address.upper())
    
    if match:
        result["house_number"] = match.group(1)
        result["street_name"] = match.group(2).strip()
        result["street_type"] = match.group(3)
        if match.group(4):
            result["unit"] = f"{match.group(4)} {match.group(5)}"
    
    return result


def transform_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Apply all transformations to a single record."""
    transformed = record.copy()
    
    # Standardize fields
    transformed["borough"] = standardize_borough(record.get("borough"))
    transformed["agency"] = standardize_agency(record.get("agency"))
    transformed["incident_zip"] = clean_zip_code(record.get("incident_zip"))
    
    # Parse dates
    transformed["created_date_parsed"] = parse_datetime(record.get("created_date"))
    transformed["closed_date_parsed"] = parse_datetime(record.get("closed_date"))
    
    # Calculate metrics
    transformed["resolution_days"] = calculate_resolution_days(
        record.get("created_date"), record.get("closed_date")
    )
    transformed["sla_days"] = get_sla_days(
        record.get("agency"), record.get("complaint_type"), record.get("descriptor")
    )
    transformed["sla_compliant"] = is_sla_compliant(
        record.get("created_date"),
        record.get("closed_date"),
        record.get("agency"),
        record.get("complaint_type"),
        record.get("descriptor")
    )
    
    # Categorize
    cat = categorize_complaint(record.get("complaint_type"), record.get("descriptor"))
    transformed["complaint_category"] = cat["category"]
    transformed["complaint_subcategory"] = cat["subcategory"]
    
    # Location parsing
    loc = parse_location_json(record.get("location"))
    transformed["location_type_parsed"] = loc["type"]
    transformed["location_coordinates"] = loc["coordinates"]
    
    return transformed


if __name__ == "__main__":
    # Quick test
    test_record = {
        "unique_key": "12345",
        "created_date": "2024-01-15T10:30:00",
        "closed_date": "2024-01-18T14:00:00",
        "agency": "NYPD",
        "agency_name": "New York Police Department",
        "complaint_type": "Noise - Residential",
        "descriptor": "Loud Music/Party",
        "borough": "MANHATTAN",
        "incident_zip": "10001",
        "status": "Closed",
        "location": '{"type": "Point", "coordinates": [-73.99, 40.75]}',
    }
    
    result = transform_record(test_record)
    print(json.dumps(result, indent=2, default=str))