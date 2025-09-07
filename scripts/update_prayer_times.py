"""
Fetch and update daily prayer (salah) times using Aladhan API.
"""
import requests
from datetime import datetime
import json
import os

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
        # Update automation_random.txt with a random value and timestamp
        import random
        random_file = "data/automation_random.txt"
        with open(random_file, "w", encoding="utf-8") as f:
            f.write(f"Random value: {random.randint(100000, 999999)}\nTimestamp: {datetime.now().isoformat()}\n")

        prayer_data = fetch_prayer_times()
        # Ensure data directory exists
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        # Always update the file with today's data (overwrite or append)
        all_data = []
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        except Exception:
            pass
        # Remove any existing entry for today
        all_data = [entry for entry in all_data if entry["date"] != prayer_data["date"]]
        all_data.append(prayer_data)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
        print(f"Prayer times for {prayer_data['date']} updated.")

        # Update last_run.txt
        last_run_file = "data/last_run.txt"
        with open(last_run_file, "w", encoding="utf-8") as f:
            f.write(f"Last run: {datetime.now().isoformat()}\n")

        # Update automation_stats.json
        stats_file = "data/automation_stats.json"
        try:
            with open(stats_file, "r", encoding="utf-8") as f:
                stats = json.load(f)
        except Exception:
            stats = {"runs": []}
        stats["runs"].append({"timestamp": datetime.now().isoformat(), "city": prayer_data["city"], "country": prayer_data["country"]})
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error updating prayer times: {e}")

if __name__ == "__main__":
    update_prayer_times()
