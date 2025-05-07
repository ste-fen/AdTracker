from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from config import GOOGLE_SHEET_ID, GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

creds = Credentials.from_service_account_file(GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)

def read_search_terms():
    """Read search terms and associated metadata from the Google Sheet."""
    # Open the sheet named "Search_Terms"
    sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet("Search terms")

    # Fetch all rows from the sheet
    rows = sheet.get_all_values()

    # Skip the header row and process the data
    search_terms = []
    for row in rows[1:]:  # Skip the header row
        term = row[0]  # Column A: Search term
        date_from = row[1] if len(row) > 1 else None  # Column B: Date from (yyyy-mm-dd)
        date_to = row[2] if len(row) > 2 else None  # Column C: Date to (yyyy-mm-dd)
        fetch_meta = row[3].strip().lower() == "x" if len(row) > 3 else False  # Column D: Meta flag
        fetch_tiktok = row[4].strip().lower() == "x" if len(row) > 4 else False  # Column E: TikTok flag
        fetch_google = row[5].strip().lower() == "x" if len(row) > 5 else False  # Column F: Google flag

        # Append the processed data as a dictionary
        search_terms.append({
            "term": term,
            "date_from": date_from,
            "date_to": date_to,
            "fetch_meta": fetch_meta,
            "fetch_tiktok": fetch_tiktok,
            "fetch_google": fetch_google
        })

    return search_terms

def update_sheet(results):
    sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1
    for i, result in enumerate(results, start=2):
        sheet.update_cell(i, 2, str(result))  # Write results in column B

def write_tiktok_results_to_sheet(results, search_term):
    # Check if results is None or empty
    if not results:
        print(f"No results to write for search term '{search_term}'.")
        return

    """Write TikTok ad results to a Google Sheet."""
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

    # Check if the "Results_TikTok" sheet exists, create it if not
    try:
        sheet = spreadsheet.worksheet("Results_TikTok")
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title="Results_TikTok", rows="1000", cols="26")
        # Write headers only if the sheet is newly created
        headers = [
            "Timestamp", "Search Term", "Ad ID", "Business Name", "Paid For By", "First Shown Date", "Last Shown Date",
            "Status", "Status Statement", "Reach (Unique Users)", "Reach by Country",
            "Targeted Countries", "Targeted Interests", "Targeted Gender", "Targeted Age",
            "Number of Users Targeted", "Video URL", "Video Cover Image URL", "Image URL"
        ]
        sheet.append_row(headers)

    # Write each result to the sheet
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for result in results:
        data = result.get("data", {})
        advertiser = data.get("advertiser", {})
        ad = data.get("ad", {})
        ad_group = data.get("ad_group", {})
        targeting_info = ad_group.get("targeting_info", {})
        reach = ad.get("reach", {})

        # Extract targeting details
        targeted_gender = ", ".join(
            [gender for gender, targeted in targeting_info.get("gender", {}).items() if targeted]
        )
        targeted_age = ", ".join(
            [age for age, targeted in targeting_info.get("age", {}).items() if targeted]
        )

        # Convert "Reach by Country" dictionary to a string
        reach_by_country = ", ".join(
            [f"{country}: {count}" for country, count in reach.get("unique_users_seen_by_country", {}).items()]
        )

        row = [
            timestamp,  # Timestamp
            search_term,  # Search Term
            ad.get("id", ""),
            advertiser.get("business_name", ""),
            advertiser.get("paid_for_by", ""),
            ad.get("first_shown_date", ""),
            ad.get("last_shown_date", ""),
            ad.get("status", ""),
            ad.get("status_statement", ""),
            reach.get("unique_users_seen", ""),
            reach_by_country,  # Converted dictionary to string
            ", ".join(targeting_info.get("country", [])),
            targeting_info.get("interest", ""),
            targeted_gender,
            targeted_age,
            targeting_info.get("number_of_users_targeted", ""),
            ad.get("videos", [{}])[0].get("url", "") if ad.get("videos") else "",
            ad.get("videos", [{}])[0].get("cover_image_url", "") if ad.get("videos") else "",
            ad.get("image_urls", [])[0] if ad.get("image_urls") else "",
        ]
        sheet.append_row(row)

def write_meta_results_to_sheet(results, search_term):
    # Check if results is None or empty
    if not results:
        print(f"No results to write for search term '{search_term}'.")
        return
    
    """Write Meta ad results to a Google Sheet with batching to avoid quota limits."""
    # Open the sheet named "Results_Meta"
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

    # Check if the "Results_Meta" sheet exists, create it if not
    try:
        sheet = spreadsheet.worksheet("Results_Meta")
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title="Results_Meta", rows="1000", cols="50")
        # Write headers only if the sheet is newly created
        headers = [
            "Timestamp", "Search Term", "Ad ID", "Ad Creation Time", "Ad Creative Bodies",
            "Ad Creative Link Captions", "Ad Creative Link Descriptions", "Ad Creative Link Titles",
            "Ad Delivery Start Time", "Ad Delivery Stop Time", "Ad Snapshot URL", "Currency",
            "Delivery by Region", "Demographic Distribution", "Estimated Audience Size",
            "EU Total Reach", "Impressions", "Page ID", "Page Name", "Publisher Platforms",
            "Spend", "Target Ages", "Target Gender", "Target Locations"
        ]
        sheet.append_row(headers)

    # Prepare rows for batch writing
    rows = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Collect all unique age_range and gender combinations for dynamic columns
    dynamic_columns = set()
    for result in results:
        for breakdown in result.get("age_country_gender_reach_breakdown", []):
            country = breakdown.get("country", "")
            if country == "AT": # Remove or adapt to see non-AT countries
                for age_gender in breakdown.get("age_gender_breakdowns", []):
                    age_range = age_gender.get("age_range", "")
                    dynamic_columns.add(f"{country} - {age_range} - Male")
                    dynamic_columns.add(f"{country} - {age_range} - Female")
                    dynamic_columns.add(f"{country} - {age_range} - Unknown")

    # Sort dynamic columns for consistent order
    dynamic_columns = sorted(dynamic_columns)

    # Add dynamic columns to the sheet headers if they don't already exist
    existing_headers = sheet.row_values(1)
    new_headers = existing_headers + [col for col in dynamic_columns if col not in existing_headers]
    if len(new_headers) > len(existing_headers):
        sheet.delete_rows(1)  # Remove the old header row
        sheet.insert_row(new_headers, index=1)  # Insert the updated header row

    for result in results:
        # Extract fields from the result
        ad_id = result.get("id", "")
        ad_creation_time = result.get("ad_creation_time", "")

        # Usually Meta returns lists for these fields, but we only need the first entry
        ad_creative_bodies = result.get("ad_creative_bodies", [None])[0]  # Use the first entry or None if the list is empty
        ad_creative_link_captions = result.get("ad_creative_link_captions", [None])[0]  # Use the first entry or None
        ad_creative_link_descriptions = result.get("ad_creative_link_descriptions", [None])[0]  # Use the first entry or None
        ad_creative_link_titles = result.get("ad_creative_link_titles", [None])[0]  # Use the first entry or None
        # If you want to join all entries, uncomment the following lines:
        # ad_creative_bodies = "\n".join(result.get("ad_creative_bodies", []))
        # ad_creative_link_captions = "\n".join(result.get("ad_creative_link_captions", []))
        # ad_creative_link_descriptions = "\n".join(result.get("ad_creative_link_descriptions", []))
        # ad_creative_link_titles = "\n".join(result.get("ad_creative_link_titles", []))

        ad_delivery_start_time = result.get("ad_delivery_start_time", "")
        ad_delivery_stop_time = result.get("ad_delivery_stop_time", "")
        ad_snapshot_url = result.get("ad_snapshot_url", "")
        currency = result.get("currency", "")
        delivery_by_region = "\n".join(
            [f"{region.get('region', '')}: {region.get('percentage', '')}" for region in result.get("delivery_by_region", [])]
        )
        demographic_distribution = "\n".join(
            [f"Age: {demo.get('age', '')}, Gender: {demo.get('gender', '')}, Percentage: {demo.get('percentage', '')}" for demo in result.get("demographic_distribution", [])]
        )
        estimated_audience_size = result.get("estimated_audience_size", {})
        estimated_audience_size_str = f"{estimated_audience_size.get('lower_bound', '')} - {estimated_audience_size.get('upper_bound', '')}"
        impressions = result.get("impressions", {})
        impressions_str = f"{impressions.get('lower_bound', '')} - {impressions.get('upper_bound', '')}"
        eu_total_reach = result.get("eu_total_reach", "")
        page_id = result.get("page_id", "")
        page_name = result.get("page_name", "")
        publisher_platforms = ", ".join(result.get("publisher_platforms", []))
        spend = result.get("spend", {})
        spend_str = f"{spend.get('lower_bound', '')} - {spend.get('upper_bound', '')}"
        target_ages = "-".join(result.get("target_ages", []))
        target_gender = result.get("target_gender", "")
        target_locations = "\n".join(
            [f"{loc.get('name', '')} (Excluded: {loc.get('excluded', False)})" for loc in result.get("target_locations", [])]
        )

        # Prepare the base row
        row = [
            timestamp, search_term, ad_id, ad_creation_time, ad_creative_bodies,
            ad_creative_link_captions, ad_creative_link_descriptions, ad_creative_link_titles,
            ad_delivery_start_time, ad_delivery_stop_time, ad_snapshot_url, currency,
            delivery_by_region, demographic_distribution, estimated_audience_size_str,
            eu_total_reach, impressions_str, page_id, page_name, publisher_platforms,
            spend_str, target_ages, target_gender, target_locations
        ]

        # Add dynamic columns for age_range and gender combinations
        dynamic_values = {col: 0 for col in dynamic_columns}
        for breakdown in result.get("age_country_gender_reach_breakdown", []):
            country = breakdown.get("country", "")
            if country == "AT": # Remove or adapt to see non-AT countries
                for age_gender in breakdown.get("age_gender_breakdowns", []):
                    age_range = age_gender.get("age_range", "")
                    male = age_gender.get("male", 0)
                    female = age_gender.get("female", 0)
                    unknown = age_gender.get("unknown", 0)
                    dynamic_values[f"{country} - {age_range} - Male"] += male
                    dynamic_values[f"{country} - {age_range} - Female"] += female
                    dynamic_values[f"{country} - {age_range} - Unknown"] += unknown

        # Append dynamic values to the row
        row.extend([dynamic_values[col] for col in dynamic_columns])
        rows.append(row)

    # Batch write rows to the sheet
    sheet.append_rows(rows, value_input_option="RAW")

def write_google_results_to_sheet(results, search_term):
    # Check if results is None or empty
    if not results:
        print(f"No results to write for search term '{search_term}'.")
        return
    
    """Write Google Ads Transparency Center results to a Google Sheet."""
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

    # Check if the "Results_Google" sheet exists, create it if not
    try:
        sheet = spreadsheet.worksheet("Results_Google")
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title="Results_Google", rows="1000", cols="26")
        # Write headers only if the sheet is newly created
        headers = [
            "Timestamp", "Search Term", "Advertiser ID", "Creative ID", "Creative Page URL",
            "Ad Format Type", "Advertiser Disclosed Name", "Advertiser Legal Name",
            "Advertiser Location", "Advertiser Verification Status", "Region Code",
            "First Shown", "Last Shown", "Other Fields..."
        ]
        sheet.append_row(headers)

    # Prepare rows for batch writing
    rows = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for result in results:
        # Extract fields using integer indices
        advertiser_id = result[0]
        creative_id = result[1]
        creative_page_url = result[2]
        ad_format_type = result[3]
        advertiser_disclosed_name = result[4]
        advertiser_legal_name = result[5]
        advertiser_location = result[6]
        advertiser_verification_status = result[7]
        region_code = result[8]
        first_shown = result[9]
        last_shown = result[10]
        times_shown_start_date = result[14]
        times_shown_end_date = result[11]
        times_shown_lower_bound = result[12]
        times_shown_upper_bound = result[13]
        demographic_info = result[16]
        geo_location = result[17]
        contextual_signals = result[18]
        customer_lists = result[19]
        topics_of_interest = result[20]

        # Prepare the row
        row = [
            timestamp,  # Timestamp
            search_term,  # Search Term
            advertiser_id,
            creative_id,
            creative_page_url,
            ad_format_type,
            advertiser_disclosed_name,
            advertiser_legal_name,
            advertiser_location,
            advertiser_verification_status,
            region_code,
            first_shown,
            last_shown,
            times_shown_start_date,
            times_shown_end_date,
            times_shown_lower_bound,
            times_shown_upper_bound,
            demographic_info,
            geo_location,
            contextual_signals,
            customer_lists,
            topics_of_interest
        ]
        rows.append(row)

    # Batch write rows to the sheet
    sheet.append_rows(rows, value_input_option="RAW")