import requests

def get_location_from_ip(ip_address):
    try:
        # Example using IPinfo
        response = requests.get(f"https://ipinfo.io/{ip_address}/json?token=5f324ed570d187")
        data = response.json()
        return {
            "country": data.get("country"),
            "region": data.get("region"),
            "city": data.get("city"),
            "zip_code": data.get("postal")
        }
    except Exception:
        # If geolocation fails, return empty data
        return {
            "country": None,
            "region": None,
            "city": None,
            "zip_code": None
        }
