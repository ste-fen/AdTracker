from datetime import datetime
import os
import gspread
import google.auth
import requests
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError
from config import GOOGLE_SHEET_ID, GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE
from report_classification import (
    DEFAULT_PROMPTS,
    PROMPT_DEFINITIONS,
    classify_google_ad,
    classify_meta_ad,
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

if GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE:
    creds = Credentials.from_service_account_file(GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
else:
    # On Cloud Run, prefer ADC from the attached runtime service account.
    creds, _ = google.auth.default(scopes=SCOPES)
    client = gspread.authorize(creds)
RESULT_SHEET_TITLES = ["Results_Meta", "Results_TikTok", "Results_Google"]

# Static Meta headers. The age/country/gender reach breakdown adds country-prefixed
# columns (e.g. "AT - 25-34 - Male") on top of these at write time; those are reset
# on every run so an AT run followed by a DE run does not leave stale AT columns.
META_BASE_HEADERS = [
    "Timestamp", "Search Term", "Ad ID", "Ad Creation Time", "Ad Creative Bodies",
    "Ad Creative Link Captions", "Ad Creative Link Descriptions", "Ad Creative Link Titles",
    "Ad Delivery Start Time", "Ad Delivery Stop Time", "Ad Snapshot URL", "Currency",
    "Delivery by Region", "Demographic Distribution", "Estimated Audience Size",
    "EU Total Reach", "Impressions", "Page ID", "Page Name", "Publisher Platforms", "Beneficiary Payers",
    "Spend", "Target Ages", "Target Gender", "Target Locations",
    # Columns supporting the DSA reporting process on https://officialrequests.meta.com/xreports/
    "Meldeseite", "Service", "Reporting Reason", "Reporting reasons text", "URL", "Land",
    "DSA Payer", "Legal Order", "Unlawful Content", "Specific laws"
]

META_REPORT_PAGE = "https://officialrequests.meta.com/xreports/"
META_AD_LIBRARY_URL = "https://www.facebook.com/ads/library/?id={ad_id}"

GOOGLE_HEADERS = [
    "Timestamp", "Search Term", "Advertiser ID", "Creative ID", "Creative Page URL",
    "Ad Format Type", "Advertiser Disclosed Name", "Advertiser Legal Name",
    "Advertiser Location", "Advertiser Verification Status", "Region Code",
    "First Shown", "Last Shown", "Times Shown Start Date", "Times Shown End Date",
    "Times Shown Lower Bound", "Times Shown Upper Bound", "Demographic Info",
    "Geo Location", "Contextual Signals", "Customer Lists", "Topics of Interest",
    # Columns supporting the DSA reporting process on the Google legal troubleshooter
    "Meldeseite", "Role", "Service", "Inhalte", "Grund der Meldung", "Wohnsitz",
    "Vollständiger Namen", "Name des Unternehmen", "Kontakt-E-Mail", "Format",
    "Anzeigen-URL", "Begründung", "Sachverhalt", "Unterschrift"
]

# Fixed values for the Google reporting columns "Meldeseite" .. "Format".
GOOGLE_REPORT_DEFAULTS = [
    "https://support.google.com/legal/troubleshooter/13966113",  # Meldeseite
    "Trusted Flagger",  # Role
    "Anzeige auf Online-Plattformen",  # Service
    "Inhalte in Google Ads melden",  # Inhalte
    "Sonstiges",  # Grund der Meldung
    "Österreich",  # Wohnsitz
    "NN",  # Vollständiger Namen
    "Österreichisches Institut für angewandte Telekommunikation",  # Name des Unternehmen
    "dsa@oiat.at",  # Kontakt-E-Mail
    "Sichtbare URL",  # Format
]


def _runtime_principal_hint():
    runtime_service_account = os.getenv("CLOUD_RUN_SERVICE_ACCOUNT")
    if runtime_service_account:
        return runtime_service_account

    if os.getenv("K_SERVICE"):
        try:
            response = requests.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email",
                headers={"Metadata-Flavor": "Google"},
                timeout=2,
            )
            response.raise_for_status()
            return response.text.strip()
        except requests.RequestException:
            pass

    return "the attached Cloud Run runtime service account"


def open_spreadsheet():
    """Open the configured spreadsheet with a clearer permission error."""
    try:
        return client.open_by_key(GOOGLE_SHEET_ID)
    except PermissionError as exc:
        raise PermissionError(
            f"Could not open GOOGLE_SHEET_ID ({GOOGLE_SHEET_ID}) in Google Sheets. "
            f"Verify that {_runtime_principal_hint()} has access to the spreadsheet, "
            "that the Google Sheets and Google Drive APIs are enabled, and that GOOGLE_SHEET_ID is correct."
        ) from exc


MAX_CELL_CHARS = 50000  # Google Sheets hard limit per cell
TRUNCATION_MARKER = " …[truncated]"


def _truncate_cells(sheet, rows):
    """Shorten string cells that exceed the Google Sheets per-cell character limit."""
    limit = MAX_CELL_CHARS - len(TRUNCATION_MARKER)
    truncated = 0
    cleaned = []
    for row in rows:
        new_row = []
        for value in row:
            if isinstance(value, str) and len(value) > MAX_CELL_CHARS:
                value = value[:limit] + TRUNCATION_MARKER
                truncated += 1
            new_row.append(value)
        cleaned.append(new_row)
    if truncated:
        print(f"Truncated {truncated} cell(s) exceeding {MAX_CELL_CHARS} characters in '{sheet.title}'.")
    return cleaned


def _free_space_and_retry_append(sheet, rows):
    """Append rows and recover from the 10M-cell workbook limit by trimming oldest data rows."""
    if not rows:
        return

    rows = _truncate_cells(sheet, rows)

    try:
        sheet.append_rows(rows, value_input_option="RAW")
        return
    except APIError as exc:
        message = str(exc)
        if "above the limit of 10000000 cells" not in message:
            raise

    # Remove enough old rows so re-append does not increase workbook size beyond the limit.
    used_rows = len(sheet.get_all_values())
    deletable_rows = max(0, used_rows - 1)  # keep header row
    rows_to_delete = min(deletable_rows, max(len(rows) * 2, 1000))

    if rows_to_delete <= 0:
        raise RuntimeError(
            "Google Sheet reached the 10M cell limit and no data rows can be removed automatically."
        )

    sheet.delete_rows(2, rows_to_delete + 1)
    print(
        f"Workbook near 10M-cell limit. Removed {rows_to_delete} oldest rows from '{sheet.title}' and retrying."
    )

    # Retry once after cleanup.
    sheet.append_rows(rows, value_input_option="RAW")


def _free_space_and_append_row(sheet, row):
    """Single-row wrapper that reuses the same limit-handling logic as batch appends."""
    _free_space_and_retry_append(sheet, [row])


def _replace_header_row(sheet, headers):
    """Replace row 1 with headers, widening the grid first so no column is cut off."""
    if sheet.col_count < len(headers):
        sheet.add_cols(len(headers) - sheet.col_count)
    # Overwrite in place: deleting row 1 fails when it is the sheet's only row.
    sheet.batch_clear(["1:1"])
    sheet.update(range_name="A1", values=[headers])


DEFAULT_ROW_HEIGHT_PX = 21


def _keep_default_row_height(sheet):
    """Force every row of the sheet to the default 21px height.

    Long text in a few cells otherwise makes Sheets auto-grow those rows. We also
    clip (instead of wrap) so the forced height does not hide text mid-line, but
    the explicit pixelSize is what actually keeps the rows short.
    """
    last_col = gspread.utils.rowcol_to_a1(1, sheet.col_count).rstrip("0123456789")
    try:
        sheet.format(f"A:{last_col}", {"wrapStrategy": "CLIP"})
    except APIError as exc:
        print(f"Could not set wrap strategy on '{sheet.title}': {exc}")

    try:
        sheet.spreadsheet.batch_update({
            "requests": [{
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet.id,
                        "dimension": "ROWS",
                        "startIndex": 0,
                        "endIndex": sheet.row_count,
                    },
                    "properties": {"pixelSize": DEFAULT_ROW_HEIGHT_PX},
                    "fields": "pixelSize",
                }
            }]
        })
    except APIError as exc:
        print(f"Could not set row height on '{sheet.title}': {exc}")


def clear_results_sheets():
    """Clear result worksheets before a run while keeping header rows."""
    spreadsheet = open_spreadsheet()

    for sheet_title in RESULT_SHEET_TITLES:
        try:
            sheet = spreadsheet.worksheet(sheet_title)
        except gspread.exceptions.WorksheetNotFound:
            # print(f"Skipping clear: worksheet '{sheet_title}' does not exist yet.")
            continue

        values = sheet.get_all_values()
        if len(values) > 1:
            sheet.delete_rows(2, len(values))
            # print(f"Cleared {len(values) - 1} rows from worksheet '{sheet_title}'.")

        # Drop dynamic country-prefixed breakdown columns so switching between
        # AT and DE runs does not accumulate stale, empty columns.
        if sheet_title == "Results_Meta":
            _replace_header_row(sheet, META_BASE_HEADERS)
        # Keep existing Google sheets in sync with the current column layout.
        elif sheet_title == "Results_Google":
            _replace_header_row(sheet, GOOGLE_HEADERS)

PROMPTS_SHEET_TITLE = "Prompts"
PROMPTS_HEADERS = ["Key", "Spalte", "Prompt"]


def read_prompts():
    """Read the AIT/LLM prompt templates from the "Prompts" worksheet.

    Prompts missing or empty in the sheet fall back to DEFAULT_PROMPTS.
    """
    prompts = dict(DEFAULT_PROMPTS)
    try:
        sheet = open_spreadsheet().worksheet(PROMPTS_SHEET_TITLE)
    except gspread.exceptions.WorksheetNotFound:
        return prompts

    for row in sheet.get_all_values()[1:]:  # Skip the header row
        if len(row) >= 3 and row[0] in prompts and row[2].strip():
            prompts[row[0]] = row[2]
    return prompts


def save_prompts(prompts):
    """Write the AIT/LLM prompt templates to the "Prompts" worksheet."""
    spreadsheet = open_spreadsheet()
    try:
        sheet = spreadsheet.worksheet(PROMPTS_SHEET_TITLE)
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(
            title=PROMPTS_SHEET_TITLE, rows=str(len(PROMPT_DEFINITIONS) + 1), cols=str(len(PROMPTS_HEADERS))
        )

    rows = [PROMPTS_HEADERS] + [
        [key, column, prompts.get(key, DEFAULT_PROMPTS[key])]
        for key, (_, column) in PROMPT_DEFINITIONS.items()
    ]
    sheet.clear()
    sheet.update(range_name="A1", values=_truncate_cells(sheet, rows))


def read_search_terms():
    """Read search terms and associated metadata from the Google Sheet."""
    # Open the sheet named "Search_Terms"
    sheet = open_spreadsheet().worksheet("Search terms")

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
    sheet = open_spreadsheet().sheet1
    for i, result in enumerate(results, start=2):
        sheet.update_cell(i, 2, str(result))  # Write results in column B

def write_tiktok_results_to_sheet(results, search_term):
    # Check if results is None or empty
    if not results:
        print(f"No results to write for search term '{search_term}'.")
        return

    """Write TikTok ad results to a Google Sheet."""
    spreadsheet = open_spreadsheet()

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
        _free_space_and_append_row(sheet, headers)

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
        _free_space_and_append_row(sheet, row)
    _keep_default_row_height(sheet)

def write_meta_results_to_sheet(results, search_term, country_code=None):
    # Check if results is None or empty
    if not results:
        print(f"No results to write for search term '{search_term}'.")
        return

    # Country selected in the UI (AT or DE); default to AT for backwards compatibility
    country_code = country_code or "AT"

    # Check if results contain an error response from Meta API
    if "Meta API error" in results:
        print(f"Meta API error for search term '{search_term}': {results.get('message')} (Code: {results.get('code')})")
        return
    
    """Write Meta ad results to a Google Sheet with batching to avoid quota limits."""
    # Open the sheet named "Results_Meta"
    spreadsheet = open_spreadsheet()

    # Check if the "Results_Meta" sheet exists, create it if not
    try:
        sheet = spreadsheet.worksheet("Results_Meta")
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title="Results_Meta", rows="1000", cols="50")
        # Write headers only if the sheet is newly created
        _free_space_and_append_row(sheet, list(META_BASE_HEADERS))

    # Prepare rows for batch writing
    rows = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prompts = read_prompts()

    # Collect all unique age_range and gender combinations for dynamic columns
    dynamic_columns = set()
    for result in results:
        for breakdown in result.get("age_country_gender_reach_breakdown", []):
            country = breakdown.get("country", "")
            if country == country_code: # Only the country selected in the UI
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
        _replace_header_row(sheet, new_headers)

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
        beneficiary_payers = ", ".join([f"{payer.get('payer', '')}" for payer in result.get("beneficiary_payers", [])])
        spend = result.get("spend", {})
        spend_str = f"{spend.get('lower_bound', '')} - {spend.get('upper_bound', '')}"
        target_ages = "-".join(result.get("target_ages", []))
        target_gender = result.get("target_gender", "")
        target_locations = "\n".join(
            [f"{loc.get('name', '')} (Excluded: {loc.get('excluded', False)})" for loc in result.get("target_locations", [])]
        )
        classification = classify_meta_ad(result, prompts, search_term, country_code)

        # Prepare the base row
        row = [
            timestamp, search_term, ad_id, ad_creation_time, ad_creative_bodies,
            ad_creative_link_captions, ad_creative_link_descriptions, ad_creative_link_titles,
            ad_delivery_start_time, ad_delivery_stop_time, ad_snapshot_url, currency,
            delivery_by_region, demographic_distribution, estimated_audience_size_str,
            eu_total_reach, impressions_str, page_id, page_name, publisher_platforms, beneficiary_payers,
            spend_str, target_ages, target_gender, target_locations,
            # Reporting columns
            META_REPORT_PAGE,  # Meldeseite
            "Facebook Core",  # Service
            classification["reporting_reason"],  # Reporting Reason (AIT/LLM)
            classification["reporting_reasons_text"],  # Reporting reasons text (AIT/LLM)
            META_AD_LIBRARY_URL.format(ad_id=ad_id),  # URL
            country_code,  # Land
            "Ja",  # DSA Payer
            "Nein",  # Legal Order
            "Ja",  # Unlawful Content
            classification["specific_laws"],  # Specific laws (AIT/LLM)
        ]

        # Add dynamic columns for age_range and gender combinations
        dynamic_values = {col: 0 for col in dynamic_columns}
        for breakdown in result.get("age_country_gender_reach_breakdown", []):
            country = breakdown.get("country", "")
            if country == country_code: # Only the country selected in the UI
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
    _free_space_and_retry_append(sheet, rows)
    _keep_default_row_height(sheet)

def write_google_results_to_sheet(results, search_term):
    # Check if results is None or empty
    if not results:
        print(f"No results to write for search term '{search_term}'.")
        return
    
    """Write Google Ads Transparency Center results to a Google Sheet."""
    spreadsheet = open_spreadsheet()

    # Check if the "Results_Google" sheet exists, create it if not
    try:
        sheet = spreadsheet.worksheet("Results_Google")
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title="Results_Google", rows="1000", cols=str(len(GOOGLE_HEADERS)))
        # Write headers only if the sheet is newly created
        _free_space_and_append_row(sheet, list(GOOGLE_HEADERS))

    # Prepare rows for batch writing
    rows = []
    results_rows = [dict(row) for row in results]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prompts = read_prompts()
    for result in results_rows:
        # Extract fields using integer indices
        advertiser_id = result.get('advertiser_id')
        creative_id = result.get('creative_id')
        creative_page_url = result.get('creative_page_url')
        ad_format_type = result.get('ad_format_type')
        advertiser_disclosed_name = result.get('advertiser_disclosed_name')
        advertiser_legal_name = result.get('advertiser_legal_name')
        advertiser_location = result.get('advertiser_location')
        advertiser_verification_status = result.get('advertiser_verification_status')
        region_code = result.get('region_code')
        first_shown = result.get('first_shown')
        last_shown = result.get('last_shown')
        times_shown_start_date = result.get('times_shown_start_date')
        times_shown_end_date = result.get('times_shown_end_date')
        times_shown_lower_bound = result.get('times_shown_lower_bound')
        times_shown_upper_bound = result.get('times_shown_upper_bound')
        demographic_info = result.get('demographic_info')
        geo_location = result.get('geo_location')
        contextual_signals = result.get('contextual_signals')
        customer_lists = result.get('customer_lists')
        topics_of_interest = result.get('topics_of_interest')
        classification = classify_google_ad(result, prompts, search_term)

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
            topics_of_interest,
            # Reporting columns
            *GOOGLE_REPORT_DEFAULTS,  # Meldeseite .. Format
            creative_page_url,  # Anzeigen-URL
            classification["begruendung"],  # Begründung (AIT/LLM)
            classification["sachverhalt"],  # Sachverhalt (AIT/LLM)
            "",  # Unterschrift
        ]
        rows.append(row)

    # Batch write rows to the sheet
    _free_space_and_retry_append(sheet, rows)
    _keep_default_row_height(sheet)