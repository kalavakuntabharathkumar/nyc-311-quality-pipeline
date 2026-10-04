"""Unit tests for transformation module."""

import pytest
from datetime import datetime

from src.transform import (
    parse_datetime,
    standardize_borough,
    standardize_agency,
    clean_zip_code,
    calculate_resolution_days,
    calculate_business_days,
    get_sla_days,
    is_sla_compliant,
    categorize_complaint,
    extract_address_components,
    transform_record,
    SLAPolicy,
)


class TestParseDateTime:
    def test_iso_format_with_microseconds(self):
        result = parse_datetime("2024-01-15T10:30:00.123456")
        assert result == datetime(2024, 1, 15, 10, 30, 0, 123456)
    
    def test_iso_format_without_microseconds(self):
        result = parse_datetime("2024-01-15T10:30:00")
        assert result == datetime(2024, 1, 15, 10, 30, 0)
    
    def test_space_separated(self):
        result = parse_datetime("2024-01-15 10:30:00")
        assert result == datetime(2024, 1, 15, 10, 30, 0)
    
    def test_date_only(self):
        result = parse_datetime("2024-01-15")
        assert result == datetime(2024, 1, 15, 0, 0, 0)
    
    def test_none_input(self):
        assert parse_datetime(None) is None
    
    def test_datetime_object(self):
        dt = datetime(2024, 1, 15, 10, 30)
        assert parse_datetime(dt) == dt
    
    def test_invalid_format(self):
        assert parse_datetime("invalid") is None


class TestStandardizeBorough:
    def test_manhattan_variants(self):
        assert standardize_borough("MANHATTAN") == "MANHATTAN"
        assert standardize_borough("Manhattan") == "MANHATTAN"
        assert standardize_borough("NEW YORK") == "MANHATTAN"
        assert standardize_borough("MN") == "MANHATTAN"
    
    def test_bronx_variants(self):
        assert standardize_borough("BRONX") == "BRONX"
        assert standardize_borough("BX") == "BRONX"
    
    def test_brooklyn_variants(self):
        assert standardize_borough("BROOKLYN") == "BROOKLYN"
        assert standardize_borough("BK") == "BROOKLYN"
        assert standardize_borough("KINGS") == "BROOKLYN"
    
    def test_queens_variants(self):
        assert standardize_borough("QUEENS") == "QUEENS"
        assert standardize_borough("QN") == "QUEENS"
    
    def test_staten_island_variants(self):
        assert standardize_borough("STATEN ISLAND") == "STATEN ISLAND"
        assert standardize_borough("SI") == "STATEN ISLAND"
        assert standardize_borough("RICHMOND") == "STATEN ISLAND"
    
    def test_unknown_defaults_to_unspecified(self):
        assert standardize_borough("UNKNOWN") == "UNSPECIFIED"
        assert standardize_borough("") == "UNSPECIFIED"
        assert standardize_borough(None) == "UNSPECIFIED"


class TestStandardizeAgency:
    def test_known_agencies(self):
        assert standardize_agency("New York Police Department") == "NYPD"
        assert standardize_agency("POLICE DEPARTMENT") == "NYPD"
        assert standardize_agency("Department of Buildings") == "DOB"
        assert standardize_agency("DEPARTMENT OF SANITATION") == "DSNY"
    
    def test_unknown_passthrough(self):
        assert standardize_agency("UNKNOWN AGENCY") == "UNKNOWN AGENCY"
        assert standardize_agency(None) is None


class TestCleanZipCode:
    def test_valid_nyc_zip(self):
        assert clean_zip_code("10001") == "10001"
        assert clean_zip_code("10001-1234") == "10001"
        assert clean_zip_code("  10001  ") == "10001"
    
    def test_invalid_zip(self):
        assert clean_zip_code("123") is None
        assert clean_zip_code("abcde") is None
        assert clean_zip_code("99999") is None  # Outside NYC range
        assert clean_zip_code(None) is None
        assert clean_zip_code("") is None


class TestCalculateResolutionDays:
    def test_normal_case(self):
        created = "2024-01-15T10:00:00"
        closed = "2024-01-18T14:00:00"
        result = calculate_resolution_days(created, closed)
        assert result is not None
        assert 3.0 <= result <= 3.2  # ~3.17 days
    
    def test_same_day(self):
        created = "2024-01-15T10:00:00"
        closed = "2024-01-15T14:00:00"
        result = calculate_resolution_days(created, closed)
        assert result is not None
        assert result < 1.0
    
    def test_closed_before_created(self):
        created = "2024-01-15T10:00:00"
        closed = "2024-01-14T10:00:00"
        result = calculate_resolution_days(created, closed)
        assert result is None
    
    def test_missing_dates(self):
        assert calculate_resolution_days(None, "2024-01-15") is None
        assert calculate_resolution_days("2024-01-15", None) is None
        assert calculate_resolution_days(None, None) is None


class TestCalculateBusinessDays:
    def test_weekdays_only(self):
        # Monday to Friday = 5 business days
        created = datetime(2024, 1, 15, 10, 0)  # Monday
        closed = datetime(2024, 1, 19, 10, 0)   # Friday
        result = calculate_business_days(created, closed)
        assert result == 5
    
    def test_weekend_excluded(self):
        # Friday to Monday = 1 business day
        created = datetime(2024, 1, 19, 10, 0)  # Friday
        closed = datetime(2024, 1, 22, 10, 0)   # Monday
        result = calculate_business_days(created, closed)
        assert result == 1
    
    def test_holidays_excluded(self):
        created = datetime(2024, 1, 15, 10, 0)  # Monday
        closed = datetime(2024, 1, 16, 10, 0)   # Tuesday
        holidays = [datetime(2024, 1, 15)]  # Monday is holiday
        result = calculate_business_days(created, closed, holidays)
        assert result == 1  # Only Tuesday counts


class TestSLA:
    def test_known_policy(self):
        assert get_sla_days("NYPD", "Noise - Residential") == 30
        assert get_sla_days("HPD", "Heat/Hot Water") == 1
        assert get_sla_days("DSNY", "Missed Collection") == 2
    
    def test_case_insensitive(self):
        assert get_sla_days("nypd", "noise - residential") == 30
    
    def test_default_fallback(self):
        assert get_sla_days("UNKNOWN", "UNKNOWN") == 30


class TestIsSLACompliant:
    def test_compliant(self):
        created = "2024-01-15T10:00:00"
        closed = "2024-01-16T10:00:00"  # 1 day
        result = is_sla_compliant(created, closed, "HPD", "Heat/Hot Water")
        assert result is True  # SLA is 1 day
    
    def test_non_compliant(self):
        created = "2024-01-15T10:00:00"
        closed = "2024-01-20T10:00:00"  # 5 days
        result = is_sla_compliant(created, closed, "HPD", "Heat/Hot Water")
        assert result is False  # SLA is 1 day
    
    def test_open_request(self):
        created = "2024-01-15T10:00:00"
        result = is_sla_compliant(created, None, "HPD", "Heat/Hot Water")
        assert result is None


class TestCategorizeComplaint:
    def test_noise(self):
        result = categorize_complaint("Noise - Residential", "Loud Music")
        assert result["category"] == "noise"
    
    def test_heat(self):
        result = categorize_complaint("Heat/Hot Water", "No Heat")
        assert result["category"] == "housing"
    
    def test_rodent(self):
        result = categorize_complaint("Rodent", "Mouse sighting")
        assert result["category"] == "housing"
    
    def test_sanitation(self):
        result = categorize_complaint("Missed Collection", "Garbage not picked up")
        assert result["category"] == "sanitation"
    
    def test_other(self):
        result = categorize_complaint("Unknown Type", "Something else")
        assert result["category"] == "other"


class TestExtractAddressComponents:
    def test_standard_address(self):
        result = extract_address_components("123 MAIN ST")
        assert result["house_number"] == "123"
        assert result["street_name"] == "MAIN"
        assert result["street_type"] == "ST"
    
    def test_address_with_unit(self):
        result = extract_address_components("123 MAIN ST APT 4B")
        assert result["house_number"] == "123"
        assert result["unit"] == "APT 4B"
    
    def test_various_street_types(self):
        for st_type in ["AVE", "BLVD", "RD", "DR", "LN", "CT", "PL", "PKWY", "TER", "CIR"]:
            result = extract_address_components(f"100 TEST {st_type}")
            assert result["street_type"] == st_type
    
    def test_invalid_address(self):
        result = extract_address_components("INVALID")
        assert all(v is None for v in result.values())


class TestTransformRecord:
    def test_full_transformation(self):
        record = {
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
        
        result = transform_record(record)
        
        assert result["borough"] == "MANHATTAN"
        assert result["agency"] == "NYPD"
        assert result["incident_zip"] == "10001"
        assert result["complaint_category"] == "noise"
        assert result["sla_days"] == 30
        assert result["sla_compliant"] is True
        assert result["has_coordinates"] is True
        assert result["created_date_parsed"] is not None
        assert result["closed_date_parsed"] is not None
    
    def test_open_request(self):
        record = {
            "unique_key": "12345",
            "created_date": "2024-01-15T10:30:00",
            "closed_date": None,
            "agency": "DSNY",
            "complaint_type": "Missed Collection",
            "borough": "BROOKLYN",
            "status": "Open",
        }
        
        result = transform_record(record)
        
        assert result["sla_compliant"] is None
        assert result["open_request_age_days"] is not None
        assert result["open_request_age_days"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])