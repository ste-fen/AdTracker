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
    """Write Meta ad results to a Google Sheet with batching to avoid quota limits."""
    # Open the sheet named "Results_Meta"
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

    # Check if the "Results_Meta" sheet exists, create it if not
    try:
        sheet = spreadsheet.worksheet("Results_Meta")
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title="Results_Meta", rows="1000", cols="26")
        # Write headers only if the sheet is newly created
        headers = [
            "Timestamp", "Search Term", "Ad ID", "Ad Creation Time", "Ad Creative Bodies", "Ad Creative Link Captions",
            "Ad Creative Link Descriptions", "Ad Creative Link Titles", "Ad Delivery Start Time",
            "Ad Delivery Stop Time", "Ad Snapshot URL", "Age-Country-Gender Reach Breakdown",
            "Beneficiary Payers", "Currency", "Delivery by Region", "Demographic Distribution",
            "Estimated Audience Size", "EU Total Reach", "Impressions", "Page ID", "Page Name",
            "Publisher Platforms", "Spend", "Target Ages", "Target Gender", "Target Locations"
        ]
        sheet.append_row(headers)

    # Prepare rows for batch writing
    rows = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for result in results:
        # Extract fields from the result
        ad_id = result.get("id", "")
        ad_creation_time = result.get("ad_creation_time", "")
        ad_creative_bodies = "\n".join(result.get("ad_creative_bodies", []))
        ad_creative_link_captions = "\n".join(result.get("ad_creative_link_captions", []))
        ad_creative_link_descriptions = "\n".join(result.get("ad_creative_link_descriptions", []))
        ad_creative_link_titles = "\n".join(result.get("ad_creative_link_titles", []))
        ad_delivery_start_time = result.get("ad_delivery_start_time", "")
        ad_delivery_stop_time = result.get("ad_delivery_stop_time", "")
        ad_snapshot_url = result.get("ad_snapshot_url", "")

        # Process age-country-gender reach breakdown
        age_country_gender_reach = []
        for breakdown in result.get("age_country_gender_reach_breakdown", []):
            country = breakdown.get("country", "")
            age_gender_breakdowns = breakdown.get("age_gender_breakdowns", [])
            for age_gender in age_gender_breakdowns:
                age_range = age_gender.get("age_range", "")
                male = age_gender.get("male", 0)
                female = age_gender.get("female", 0)
                unknown = age_gender.get("unknown", 0)
                age_country_gender_reach.append(
                    f"{country} - {age_range}: Male={male}, Female={female}, Unknown={unknown}"
                )
        age_country_gender_reach_str = "\n".join(age_country_gender_reach)

        # Process beneficiary payers
        beneficiary_payers = []
        for payer in result.get("beneficiary_payers", []):
            beneficiary_payers.append(
                f"Payer: {payer.get('payer', '')}, Beneficiary: {payer.get('beneficiary', '')}, Current: {payer.get('current', '')}"
            )
        beneficiary_payers_str = "\n".join(beneficiary_payers)

        # Process delivery by region
        delivery_by_region = []
        for region in result.get("delivery_by_region", []):
            delivery_by_region.append(
                f"{region.get('region', '')}: {region.get('percentage', '')}"
            )
        delivery_by_region_str = "\n".join(delivery_by_region)

        # Process demographic distribution
        demographic_distribution = []
        for demographic in result.get("demographic_distribution", []):
            demographic_distribution.append(
                f"Age: {demographic.get('age', '')}, Gender: {demographic.get('gender', '')}, Percentage: {demographic.get('percentage', '')}"
            )
        demographic_distribution_str = "\n".join(demographic_distribution)

        # Process estimated audience size
        estimated_audience_size = result.get("estimated_audience_size", {})
        estimated_audience_size_str = f"{estimated_audience_size.get('lower_bound', '')} - {estimated_audience_size.get('upper_bound', '')}"

        # Process impressions
        impressions = result.get("impressions", {})
        impressions_str = f"{impressions.get('lower_bound', '')} - {impressions.get('upper_bound', '')}"

        # Process spend
        spend = result.get("spend", {})
        spend_str = f"{spend.get('lower_bound', '')} - {spend.get('upper_bound', '')}"

        eu_total_reach = result.get("eu_total_reach", "")
        page_id = result.get("page_id", "")
        page_name = result.get("page_name", "")
        publisher_platforms = ", ".join(result.get("publisher_platforms", []))
        target_ages = "-".join(result.get("target_ages", []))
        target_gender = result.get("target_gender", "")

        # Process target locations
        target_locations = []
        for location in result.get("target_locations", []):
            target_locations.append(
                f"{location.get('name', '')} (Excluded: {location.get('excluded', False)})"
            )
        target_locations_str = "\n".join(target_locations)

        # Prepare the row
        row = [
            timestamp,  # Timestamp
            search_term,  # Search Term
            ad_id,
            ad_creation_time,
            ad_creative_bodies,
            ad_creative_link_captions,
            ad_creative_link_descriptions,
            ad_creative_link_titles,
            ad_delivery_start_time,
            ad_delivery_stop_time,
            ad_snapshot_url,
            age_country_gender_reach_str,
            beneficiary_payers_str,
            result.get("currency", ""),
            delivery_by_region_str,
            demographic_distribution_str,
            estimated_audience_size_str,
            eu_total_reach,
            impressions_str,
            page_id,
            page_name,
            publisher_platforms,
            spend_str,
            target_ages,
            target_gender,
            target_locations_str,
        ]
        rows.append(row)

    # Batch write rows to the sheet
    sheet.append_rows(rows, value_input_option="RAW")

def write_google_results_to_sheet(results, search_term):
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