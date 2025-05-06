import requests
import os
from dotenv import load_dotenv
from config import META_APP_ID, META_APP_SECRET, update_env_file

# Load environment variables from .env file
load_dotenv()

def exchange_user_token_for_long_lived_token(user_token):
    """Exchange a short-lived user token for a long-lived token."""
    url = "https://graph.facebook.com/v22.0/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": META_APP_ID,
        "client_secret": META_APP_SECRET,
        "fb_exchange_token": user_token,
    }

    response = requests.get(url, params=params)
    data = response.json()

    if "access_token" in data:
        long_lived_token = data["access_token"]
        print("Long-lived token fetched successfully.")
        # Optionally save the token to your environment or configuration
        #update_env_file("META_ACCESS_TOKEN", long_lived_token)
        return long_lived_token
    else:
        print("Failed to exchange user token for long-lived token:", data)
        return None

def query_meta_ads(term, delivery_date_min=None, delivery_date_max=None):
    """Query Meta Ads Library with automatic token refresh."""
    # Read the access token from the .env file
    token = os.getenv("META_ACCESS_TOKEN")
    if not token:
        token = 'REFETCH_TOKEN'  # Placeholder for the token if not found
    url = "https://graph.facebook.com/v22.0/ads_archive"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "search_terms": term,
        "search_type": "KEYWORD_EXACT_PHRASE",
        "ad_type": "ALL",
        "ad_active_status": "ALL",
        "ad_reached_countries": ['AT'],  # Replace 'AT' with the desired country code(s)
        "limit": 5000,  # Maximum number of results per page
        "access_token": token,
        "fields": "id,ad_creation_time,ad_creative_bodies,ad_creative_link_captions,ad_creative_link_descriptions,ad_creative_link_titles,ad_delivery_start_time,ad_delivery_stop_time,ad_snapshot_url,age_country_gender_reach_breakdown,beneficiary_payers,bylines,currency,delivery_by_region,demographic_distribution,estimated_audience_size,eu_total_reach,impressions,page_id,page_name,publisher_platforms,spend,target_ages,target_gender,target_locations"
    }

    # Add delivery date filters if provided
    if delivery_date_min:
        params["ad_delivery_date_min"] = delivery_date_min #.strftime("%Y-%m-%d")
    if delivery_date_max:
        params["ad_delivery_date_max"] = delivery_date_max #.strftime("%Y-%m-%d")

    all_ads = []  # List to store all ad details
    while url:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()

        # Check for token errors
        if "error" in data:
            error_code = data["error"].get("code")
            if error_code == 190 or error_code == 10:  # Token expired or invalid
                print("Meta token expired or invalid. Please provide a new user token.")
                short_lived_token = input("Paste your short-lived user token: ").strip()
                long_lived_token = exchange_user_token_for_long_lived_token(short_lived_token)
                if long_lived_token:
                    # Update the .env file with the new token
                    update_env_file("META_ACCESS_TOKEN", long_lived_token)
                    return query_meta_ads(term)  # Retry the query with the new token
                else:
                    print("Failed to refresh token. Cannot proceed.")
                    return {"error": "Failed to refresh token"}
            else:
                print(f"Meta API error: {data['error']}")
                return data

        # Add the current page of ads to the list
        all_ads.extend(data.get("data", []))

        # Get the next page URL from the "paging" field
        paging = data.get("paging", {})
        url = paging.get("next")  # Set the URL to the next page, or None if no more pages

        # Clear params for subsequent requests (next page URL already includes them)
        params = {}

    return all_ads