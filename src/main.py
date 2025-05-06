from google_sheets import read_search_terms, write_tiktok_results_to_sheet, write_meta_results_to_sheet, write_google_results_to_sheet
from meta_ads import query_meta_ads
from tiktok_ads import query_tiktok_ads_with_details
from google_ads import query_google_ad_library
from datetime import datetime

def parse_date(date_str, output_format=None):
    """Parse a date string in yyyy-mm-dd format and optionally format it."""
    try:
        if date_str:
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
            if output_format:
                return parsed_date.strftime(output_format)
            return parsed_date
        return None
    except ValueError as e:
        print(f"Error parsing date '{date_str}': {e}")
        return None

def main():
    search_terms = read_search_terms()

    for entry in search_terms:
        term = entry["term"]
        date_from = entry["date_from"]
        date_to = entry["date_to"]
        fetch_meta = entry["fetch_meta"]
        fetch_tiktok = entry["fetch_tiktok"]
        fetch_google = entry["fetch_google"]

        # Parse dates consistently
        meta_date_from = parse_date(date_from, "%Y-%m-%d")  # For Meta (yyyy-mm-dd format)
        meta_date_to = parse_date(date_to, "%Y-%m-%d")      # For Meta (yyyy-mm-dd format)
        tiktok_min_date = parse_date(date_from, "%Y%m%d")  # For TikTok (yyyyMMdd format)
        tiktok_max_date = parse_date(date_to, "%Y%m%d")    # For TikTok (yyyyMMdd format)
        google_date_from = parse_date(date_from, "%Y-%m-%d")  # For Google (yyyy-mm-dd format)
        google_date_to = parse_date(date_to, "%Y-%m-%d")      # For Google (yyyy-mm-dd format)

        if fetch_meta:
            print(f"Fetching Meta data for term '{term}' from {meta_date_from} to {meta_date_to}...")
            if not meta_date_from or not meta_date_to:
                print(f"Skipping Meta fetch for term '{term}' due to invalid dates.")
                continue
            meta_results = query_meta_ads(term, delivery_date_min=meta_date_from, delivery_date_max=meta_date_to)
            print(f"Writing Meta results for term '{term}'...")
            write_meta_results_to_sheet(meta_results, term)

        if fetch_tiktok:
            print(f"Fetching TikTok data for term '{term}' from {tiktok_min_date} to {tiktok_max_date}...")
            if not tiktok_min_date or not tiktok_max_date:
                print(f"Skipping TikTok fetch for term '{term}' due to invalid dates.")
                continue
            tiktok_results = query_tiktok_ads_with_details(term, tiktok_min_date, tiktok_max_date)
            print(f"Writing TikTok results for term '{term}'...")
            write_tiktok_results_to_sheet(tiktok_results, term)

        if fetch_google:
            print(f"Fetching Google data for term '{term}' from {google_date_from} to {google_date_to}...")
            if not google_date_from or not google_date_to:
                print(f"Skipping Google fetch for term '{term}' due to invalid dates.")
                continue
            google_results = query_google_ad_library(term, google_date_from, google_date_to)
            print(f"Writing Google results for term '{term}'...")
            write_google_results_to_sheet(google_results, term)

if __name__ == "__main__":
    main()
