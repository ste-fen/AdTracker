from config import GOOGLE_BIGQUERY_SERVICE_ACCOUNT_FILE
from google.cloud import bigquery
import os

def query_google_ad_library(term, min_date, max_date):
    """Query BigQuery and return the results."""
    # Ensure GOOGLE_APPLICATION_CREDENTIALS is set
    credentials_path = GOOGLE_BIGQUERY_SERVICE_ACCOUNT_FILE
    if not credentials_path:
        raise EnvironmentError("SERVICE_ACCOUNT_FILE is not set in the .env file.")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

    # Initialize the BigQuery client
    client = bigquery.Client()

    query = f"""
SELECT 
    -- Fields from creative_stats
    creative_stats.advertiser_id,
    creative_stats.creative_id,
    creative_stats.creative_page_url,
    creative_stats.ad_format_type,
    creative_stats.advertiser_disclosed_name,
    creative_stats.advertiser_legal_name,
    creative_stats.advertiser_location,
    creative_stats.advertiser_verification_status,

    -- Fields from region_stats (unnested)
    region_stats.region_code,
    region_stats.first_shown,
    region_stats.last_shown,
    region_stats.times_shown_end_date,
    region_stats.times_shown_lower_bound,
    region_stats.times_shown_upper_bound,
    region_stats.times_shown_start_date,
    region_stats.times_shown_availability_date,

    -- Fields from audience_selection_approach_info (unnested)
    audience_selection_approach_info.demographic_info,
    audience_selection_approach_info.geo_location,
    audience_selection_approach_info.contextual_signals,
    audience_selection_approach_info.customer_lists,
    audience_selection_approach_info.topics_of_interest
FROM 
    `bigquery-public-data.google_ads_transparency_center.creative_stats` AS creative_stats,
    UNNEST(creative_stats.region_stats) AS region_stats
WHERE 
    (
        LOWER(creative_stats.advertiser_disclosed_name) LIKE "%{term}%" OR
        LOWER(creative_stats.advertiser_legal_name) LIKE "%{term}%"
    )
    AND region_stats.region_code = "AT"
    AND DATE(region_stats.first_shown) >= DATE("{min_date}")
    AND DATE(region_stats.last_shown) <= DATE("{max_date}")
    """

    # Run the query
    query_job = client.query(query)

    # Wait for the query to finish and fetch results
    results = query_job.result()

    # Convert results to a list of dictionaries
    #rows = [dict(row) for row in results]
    return results
