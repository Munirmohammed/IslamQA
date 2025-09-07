"""
Fetch and update daily prayer (salah) times using Aladhan API.
"""
import requests
from datetime import datetime
import json

CITY = "Addis Ababa"
COUNTRY = "Ethiopia"
OUTPUT_FILE = "data/daily_prayer_times.json"


def fetch_prayer_times(city=CITY, country=COUNTRY):
    today = datetime.now().strftime("%Y-%m-%d")
    url = f"https://api.aladhan.com/v1/timingsByCity?city={city}&country={country}&method=2&date={today}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        timings = data.get("data", {}).get("timings", {})
        return {"date": today, "city": city, "country": country, "timings": timings}
    else:
        raise Exception(f"Failed to fetch prayer times: {response.status_code}")

def update_prayer_times():
    try:
        prayer_data = fetch_prayer_times()
        # Load existing data if present
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        except Exception:
            all_data = []
        # Append today's data if not already present
        if not any(entry["date"] == prayer_data["date"] for entry in all_data):
            all_data.append(prayer_data)
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(all_data, f, ensure_ascii=False, indent=2)
            print(f"Added prayer times for {prayer_data['date']}")
        else:
            print(f"Prayer times for {prayer_data['date']} already present.")
    except Exception as e:
        print(f"Error updating prayer times: {e}")

if __name__ == "__main__":
    update_prayer_times()
