import pycountry

for country in pycountry.countries:
    if hasattr(country, "common_name"):
        print(f"{{\"code\": \"{country.alpha_2}\", \"name\": \"{country.common_name}\"}}, ")
    else:
        print(f"{{\"code\": \"{country.alpha_2}\", \"name\": \"{country.name}\"}}, ")

print(len(pycountry.countries))