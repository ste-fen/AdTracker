import requests
import time
from datetime import datetime
from config import (
    TIKTOK_CLIENT_KEY,
    TIKTOK_CLIENT_SECRET,
    TIKTOK_ACCESS_TOKEN,
)

TOKEN_EXPIRATION_TIME = 7200  # Token validity in seconds (2 hours)
TOKEN_LAST_REFRESHED = time.time()

def get_client_access_token():
    """Obtain a new client access token from TikTok."""
    url = "https://open.tiktokapis.com/v2/oauth/token/"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "grant_type": "client_credentials",
    }
    response = requests.post(url, headers=headers, data=data)
    response_data = response.json()
    if response.status_code == 200:
        access_token = response_data.get("access_token")
        expires_in = response_data.get("expires_in")
        if access_token and expires_in:
            global TIKTOK_ACCESS_TOKEN, TOKEN_EXPIRATION_TIME, TOKEN_LAST_REFRESHED
            TIKTOK_ACCESS_TOKEN = access_token
            TOKEN_EXPIRATION_TIME = expires_in
            TOKEN_LAST_REFRESHED = time.time()
            return access_token
    else:
        print("Failed to obtain access token:", response_data)
    return None

def is_token_expired():
    """Check if the current access token has expired."""
    return time.time() - TOKEN_LAST_REFRESHED >= TOKEN_EXPIRATION_TIME

def query_tiktok_ads(search_term, min_date, max_date):
    """Query TikTok Ads using the Commercial Content API."""
    global TIKTOK_ACCESS_TOKEN
    if is_token_expired():
        print("Access token expired. Refreshing token...")
        TIKTOK_ACCESS_TOKEN = get_client_access_token()
        if not TIKTOK_ACCESS_TOKEN:
            print("Failed to refresh access token.")
            return None
        
    url = "https://open.tiktokapis.com/v2/research/adlib/ad/query/"
    headers = {
        "Authorization": f"Bearer {TIKTOK_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    params = {
        "fields": "ad.id,ad.first_shown_date,ad.last_shown_date,ad.status,ad.videos",
    }
    body = {
        "search_term": search_term,
        "filters": {
            "ad_published_date_range": {
                "min": min_date,  # Dynamically set min date
                "max": max_date   # Dynamically set max date
            },
            "country_code": "AT"
        },
    }

    response = requests.post(url, headers=headers, params=params, json=body)
    if response.status_code == 401:
        print("Access token expired or invalid. Refreshing token...")
        TIKTOK_ACCESS_TOKEN = get_client_access_token()
        if TIKTOK_ACCESS_TOKEN:
            return query_tiktok_ads(search_term, min_date, max_date)
        else:
            print("Failed to refresh access token.")
            return None
    elif response.status_code == 200:
        try:
            data = response.json()
            return data
        except requests.exceptions.JSONDecodeError as e:
            print("Failed to parse JSON response:", e)
            return None
    else:
        print(f"Failed to query TikTok ads. Status code: {response.status_code}, Response: {response.text}")
        return None

def get_ad_details(ad_id):
    """Fetch details for a list of ad IDs using the TikTok API."""
    global TIKTOK_ACCESS_TOKEN
    url = "https://open.tiktokapis.com/v2/research/adlib/ad/detail/"
    headers = {
        "Authorization": f"Bearer {TIKTOK_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    params = {
        "fields": "ad.id,ad.first_shown_date,ad.last_shown_date,ad.status,ad.status_statement,ad.videos,ad.image_urls,ad.reach,advertiser.business_id,advertiser.business_name,advertiser.paid_for_by,advertiser.follower_count,advertiser.avatar_url,advertiser.profile_url,ad_group.targeting_info",
    }
    body = {
        "ad_id": ad_id,
    }

    response = requests.post(url, headers=headers, params=params, json=body)
    if response.status_code == 200:
        try:
            return response.json()
        except requests.exceptions.JSONDecodeError as e:
            print("Failed to parse JSON response:", e)
            return None
    else:
        print(f"Failed to fetch ad details. Status code: {response.status_code}, Response: {response.text}")
        return None

def query_tiktok_ads_with_details(search_term, min_date, max_date):
    """Query TikTok Ads and fetch details for all returned ads."""
    ads_data = query_tiktok_ads(search_term, min_date, max_date)

    # Check if "data" and "ads" keys exist and if "ads" is a list
    if not ads_data or "data" not in ads_data or "ads" not in ads_data["data"] or not isinstance(ads_data["data"]["ads"], list):
        print("No ads found or failed to query ads.")
        return None

    # Extract ad IDs from the nested structure
    ad_ids = [ad["ad"]["id"] for ad in ads_data["data"]["ads"] if "ad" in ad and "id" in ad["ad"]]
    if not ad_ids:
        print("No ad IDs found in the response.")
        return None

    #print(f"Fetching details for {len(ad_ids)} ads...")
    ad_details_list = []
    for ad_id in ad_ids:
        ad_details = get_ad_details(ad_id)
        if ad_details:
            ad_details_list.append(ad_details)
        else:
            print(f"Failed to fetch details for ad ID: {ad_id}")

    return ad_details_list
