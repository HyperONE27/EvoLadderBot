import json

class CountryLookup:
    def __init__(self, countries_list_path="data/misc/countries.json"):
        with open(countries_list_path, "r", encoding="utf-8") as file:
            self.countries = json.load(file)

        # Build dicts in both directions for fast lookup
        self.code_to_name = {c["code"]: c["name"] for c in self.countries}
        self.name_to_code = {c["name"]: c["code"] for c in self.countries}

    def get_sorted_countries(self):
        return sorted(self.countries, key=lambda x: x["name"])

    def get_country_from_code(self, code: str):
        return self.code_to_name.get(code)

    def get_code_from_country(self, name: str):
        return self.name_to_code.get(name)

if __name__ == "__main__":
    country_lookup = CountryLookup()
    print(country_lookup.get_code_from_country("United States"))
    print(country_lookup.get_country_from_code("US"))