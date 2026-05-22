import requests
import os
from dotenv import load_dotenv
from config import META_APP_ID, META_APP_SECRET, update_env_file

# Load environment variables from .env file
load_dotenv()


class MetaTokenExpiredError(Exception):
    """Raised when the Meta access token is missing, invalid, or expired."""

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


def refresh_meta_access_token(short_lived_token):
    """Refresh and persist the Meta access token using a short-lived user token."""
    if not short_lived_token:
        raise ValueError("A short-lived Meta user token is required.")

    long_lived_token = exchange_user_token_for_long_lived_token(short_lived_token.strip())
    if not long_lived_token:
        raise ValueError("Could not exchange token. Please verify app credentials and token scope.")

    # Cloud Run file system is ephemeral; avoid pretending the token is permanently stored there.
    if not os.getenv("K_SERVICE"):
        update_env_file("META_ACCESS_TOKEN", long_lived_token)
    os.environ["META_ACCESS_TOKEN"] = long_lived_token
    return long_lived_token

def query_meta_ads(term, delivery_date_min=None, delivery_date_max=None, max_ads=500, country_code=None):
    """Query Meta Ads Library with automatic token refresh."""
    # Read the access token from the .env file
    token = os.getenv("META_ACCESS_TOKEN").strip()
    if not token:
        raise MetaTokenExpiredError(
            "META_ACCESS_TOKEN is missing. Refresh it in the web UI before querying Meta Ads."
        )
    url = "https://graph.facebook.com/v22.0/ads_archive"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "search_terms": term,
        # "search_type": "KEYWORD_EXACT_PHRASE",
        "ad_type": "ALL",
        "ad_active_status": "ALL",
        "ad_reached_countries": [country_code or 'AT'],  # Country code from UI selection
        "limit": 200,  # Maximum number of results per page
        "access_token": token,
        "fields": "id,ad_creation_time,ad_creative_bodies,ad_creative_link_captions,ad_creative_link_descriptions,ad_creative_link_titles,ad_delivery_start_time,ad_delivery_stop_time,ad_snapshot_url,age_country_gender_reach_breakdown,beneficiary_payers,bylines,currency,delivery_by_region,demographic_distribution,estimated_audience_size,eu_total_reach,impressions,page_id,page_name,publisher_platforms,spend,target_ages,target_gender,target_locations"
    }

    # Add delivery date filters if provided
    if delivery_date_min:
        params["ad_delivery_date_min"] = delivery_date_min #.strftime("%Y-%m-%d")
    if delivery_date_max:
        params["ad_delivery_date_max"] = delivery_date_max #.strftime("%Y-%m-%d")

    all_ads = []  # List to store all ad details
    max_ads = int(max_ads) if max_ads else 500
    while url:
        response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            print(f"Error querying Meta Ads API: {response.status_code} - {response.text}")
            return all_ads

        try:
            data = response.json()
        except ValueError:
            print("Meta API returned an invalid JSON response.")
            return all_ads

        # Check for token errors
        if "error" in data:
            error_code = data["error"].get("code")
            if error_code == 190 or error_code == 10:  # Token expired or invalid
                raise MetaTokenExpiredError(
                    "Meta access token expired or invalid. Refresh it in the browser UI and retry."
                )
            else:
                print(f"Meta API error: {data['error']}")
                return all_ads

        # Add the current page of ads to the list (capped at max_ads)
        page_ads = data.get("data", [])
        remaining_capacity = max_ads - len(all_ads)
        if remaining_capacity <= 0:
            break
        all_ads.extend(page_ads[:remaining_capacity])
        if len(all_ads) >= max_ads:
            print(f"Reached Meta ad cap of {max_ads} entries. Stopping pagination.")
            break

        # Get the next page URL from the "paging" field
        paging = data.get("paging", {})
        url = paging.get("next")  # Set the URL to the next page, or None if no more pages

        # Clear params for subsequent requests (next page URL already includes them)
        params = {}

    return all_ads


def test_query_meta_ads(search_term="nike", max_ads=500):
    """Small local test helper to call query_meta_ads with one term."""
    print(f"[Meta Test] querying term: {search_term}")
    ads = query_meta_ads(search_term, max_ads=max_ads)
    print(f"[Meta Test] ads fetched: {len(ads)}")

    if ads:
        first_ad = ads[0]
        print(f"[Meta Test] first ad id: {first_ad.get('id')}")
        print(f"[Meta Test] first snapshot url: {first_ad.get('ad_snapshot_url')}")

    return ads


if __name__ == "__main__":
    term = os.getenv("META_TEST_TERM", "nike")
    max_ads = int(os.getenv("META_TEST_MAX_ADS", "500"))
    test_query_meta_ads(term, max_ads=max_ads)