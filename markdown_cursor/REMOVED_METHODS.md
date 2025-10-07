# Removed Unused Methods

This document lists methods that were removed from the codebase because they were unused, along with their functionality for future reference.

## CountriesService Methods

### `get_country_codes() -> List[str]`
- **Functionality**: Returns a list of all country codes from the countries data
- **Implementation**: `[country.get("code", "") for country in self.get_countries() if country.get("code")]`
- **Removed from**: `src/backend/services/countries_service.py`
- **Reason**: Never called anywhere in the codebase
- **Alternative**: Use `get_codes()` from BaseConfigService instead

### `get_common_country_codes() -> List[str]`
- **Functionality**: Returns a list of country codes for common countries only
- **Implementation**: `[country.get("code", "") for country in self.get_common_countries() if country.get("code")]`
- **Removed from**: `src/backend/services/countries_service.py`
- **Reason**: Never called anywhere in the codebase
- **Alternative**: Use `get_common_countries()` and extract codes manually if needed

### `get_country_name(country_code: str) -> str`
- **Functionality**: Gets the display name for a given country code
- **Implementation**: `return self.get_name_by_code(country_code)`
- **Removed from**: `src/backend/services/countries_service.py`
- **Reason**: Never called anywhere in the codebase
- **Alternative**: Use `get_name_by_code()` from BaseConfigService instead

## Notes

- All removed methods were simple wrappers around BaseConfigService methods
- The functionality is still available through the base class methods
- No breaking changes since these methods were never used
- If these methods are needed in the future, they can be easily re-implemented or the base class methods can be used directly
