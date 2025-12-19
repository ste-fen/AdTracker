# AdTracker

AdTracker is a Python-based tool that reads search terms from a Google Sheet, queries them via the Meta, TikTok, and Google Ad Library APIs, and writes the results back to the same Google Sheet.

## Prerequisites

Before running the script, ensure you have the following:
- Python 3.8+
- A Google Cloud service account with access to Google Sheets API
- API access tokens for Meta Ads, TikTok Ads, and Google Ad Library
- Meta App ID and Secret (for token refresh functionality)

## Installation

1. Clone the repository:
   ```sh
   git clone https://github.com/ste-fen/adtracker.git
   cd adtracker
   ```

2. Create and activate a virtual environment:
   ```sh
   python -m venv venv
   (optional if access problems: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass)
   venv\Scripts\activate 
   ```

3. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```

4. Set up the `.env` file with your credentials:
   ```sh
   cp .env.example .env
   ```
   Edit `.env` and replace placeholders with actual API keys.

## Usage

Run the main script:
```sh
python src/main.py
```

This will:
1. Read search terms from the first column of the Google Sheet.
2. Query the Meta, TikTok, and Google Ad Library APIs.
3. Write results back into the second column of the same Google Sheet.

## Project Structure
```
adtracker/
│── src/
│   │── main.py              # Main script
│   │── config.py            # Configuration settings
│   │── google_sheets.py     # Google Sheets API integration
│   │── meta_ads.py          # Meta Ads API queries (with auto token refresh)
│   │── tiktok_ads.py        # TikTok Ads API queries
│   │── google_ads.py        # Google Ad Library queries
│   │── utils.py             # Utility functions
│── requirements.txt         # Dependencies
│── .env                     # Environment variables (API keys, etc.)
│── README.md                # Documentation
│── setup.py                 # Package setup (if needed)
```

## Notes
- Ensure your service account has the right permissions to access the Google Sheet.
- API rate limits may apply. If needed, implement a delay in API requests to avoid exceeding limits.
- **Meta Ads API Token Auto-Refresh**: If the access token expires, it will be automatically refreshed using the App ID and Secret.
- https://www.facebook.com/ads/library/api/
- https://developers.facebook.com/docs/facebook-login/guides/access-tokens
- https://developers.tiktok.com/doc/commercial-content-api-query-ads
- https://developers.tiktok.com/doc/commercial-content-api-get-ad-details
- https://console.cloud.google.com/marketplace/details/bigquery-public-data/google-ads-transparency-center
- https://storage.googleapis.com/ads-transparency-center/api-data/README.txt
- Google Big Query User Service Account (https://console.cloud.google.com/iam-admin/serviceaccounts) is necessary to run Google Ads Transparency Center queries
- Google Sheets Service Account (https://console.cloud.google.com/iam-admin/serviceaccounts) is necessary to run access Google Sheets

## License
This project is licensed under the MIT License.

