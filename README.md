# AdTracker

AdTracker is a Python-based tool that reads search terms from a Google Sheet, queries them via the Meta, TikTok, and Google Ad Library APIs, and writes the results back to the same Google Sheet.

## Local deployment

### Prerequisites

Before running the script, ensure you have the following:
- Python 3.8+
- A Google Cloud service account with access to Google Sheets API
- API access tokens for Meta Ads, TikTok Ads, and Google Ad Library
- Meta App ID and Secret (for token refresh functionality)

### Installation

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

### Usage

Run the main script:
```sh
python src/main.py
```

Run the web app:
```sh
python -m streamlit run src/web_app.py
```

This will:
1. Read search terms from the first column of the Google Sheet.
2. Query the Meta, TikTok, and Google Ad Library APIs.
3. Write results back into the second column of the same Google Sheet.
4. Clear `Results_Meta`, `Results_TikTok`, and `Results_Google` before each crawler run.

In the web app, open the `Meta Token` tab to refresh `META_ACCESS_TOKEN` in the browser.
You can paste a short-lived user token from the Meta Graph API Explorer and store the new long-lived token in `.env`.

The web app also supports a simple shared password via `APP_PASSWORD`.
Locally, set it in `.env`. On Cloud Run, pass it via Secret Manager.

## Deploy to Google Cloud Run

This repository includes a `Dockerfile` and `.dockerignore` for Cloud Run.

### 0) Create Google Project and install gcloud on your machine

```sh
winget install Google.CloudSDK
Restart terminal or Visual Studio
gcloud --version
gcloud auth login
gcloud init
gcloud projects create <PROJECT-ID> --name="AdTracker" (or via Google Cloud UI)
gcloud config set project <PROJECT-ID>
gcloud config set run/region europe-west3
gcloud projects list (test if project is there)
```

### 1) Enable APIs
```sh
gcloud services enable sheets.googleapis.com drive.googleapis.com bigquery.googleapis.com run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com
```

### 2) Create a runtime service account
```sh
gcloud iam service-accounts create adtracker-run-sa --display-name="AdTracker Cloud Run"
```

Grant least-privilege roles (adjust to your project needs):
```sh
gcloud projects add-iam-policy-binding <PROJECT-ID> --member="serviceAccount:adtracker-run-sa@<PROJECT-ID>.iam.gserviceaccount.com" --role="roles/bigquery.jobUser"

gcloud projects add-iam-policy-binding <PROJECT-ID> --member="serviceAccount:adtracker-run-sa@<PROJECT-ID>.iam.gserviceaccount.com" --role="roles/bigquery.dataViewer"
```

For Google Sheets access, share your spreadsheet with:
`adtracker-run-sa@<PROJECT-ID>.iam.gserviceaccount.com`

### 3) Create secrets
```sh
echo -n "<GOOGLE_SHEET_ID>" | gcloud secrets create GOOGLE_SHEET_ID --data-file=-
echo -n "<APP_PASSWORD>" | gcloud secrets create APP_PASSWORD --data-file=-
echo -n "<META_ACCESS_TOKEN>" | gcloud secrets create META_ACCESS_TOKEN --data-file=-
echo -n "<META_APP_ID>" | gcloud secrets create META_APP_ID --data-file=-
echo -n "<META_APP_SECRET>" | gcloud secrets create META_APP_SECRET --data-file=-
echo -n "<TIKTOK_ACCESS_TOKEN>" | gcloud secrets create TIKTOK_ACCESS_TOKEN --data-file=-
echo -n "<TIKTOK_CLIENT_KEY>" | gcloud secrets create TIKTOK_CLIENT_KEY --data-file=-
echo -n "<TIKTOK_CLIENT_SECRET>" | gcloud secrets create TIKTOK_CLIENT_SECRET --data-file=-
```

If a secret already exists, add a new version:
```sh
echo -n "<NEW_VALUE>" | gcloud secrets versions add <SECRET_NAME> --data-file=-
```

Add permissions to the secrets:
```sh
gcloud projects add-iam-policy-binding <PROJECT-ID> --member="serviceAccount:adtracker-run-sa@<PROJECT-ID>.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
```

### 4) Build and deploy
```sh
gcloud builds submit --tag gcr.io/<PROJECT_ID>/adtracker

gcloud run deploy adtracker \
   --image gcr.io/<PROJECT_ID>/adtracker \
   --region europe-west3 \
   --platform managed \
   --service-account adtracker-run-sa@<PROJECT_ID>.iam.gserviceaccount.com \
   --allow-unauthenticated \
   --set-secrets "GOOGLE_SHEET_ID=GOOGLE_SHEET_ID:latest,APP_PASSWORD=APP_PASSWORD:latest,META_ACCESS_TOKEN=META_ACCESS_TOKEN:latest,META_APP_ID=META_APP_ID:latest,META_APP_SECRET=META_APP_SECRET:latest,TIKTOK_ACCESS_TOKEN=TIKTOK_ACCESS_TOKEN:latest,TIKTOK_CLIENT_KEY=TIKTOK_CLIENT_KEY:latest,TIKTOK_CLIENT_SECRET=TIKTOK_CLIENT_SECRET:latest"
```

PowerShell helper script for this project:
```powershell
.\scripts\deploy-cloud-run.ps1
```

The script always deploys with public browser access (`--allow-unauthenticated`) and is preconfigured for project `adtracker-491310`, region `europe-west3`, service `adtracker`, and all current Secret Manager bindings.

### 5) Access

Access the app via URL and password.

### 6) Grant user access to the app (optional)
```sh
gcloud run services add-iam-policy-binding adtracker \
   --region europe-west3 \
   --member="user:<YOUR_EMAIL>" \
   --role="roles/run.invoker"
```

### Security notes for Cloud Run
- Do not put `.env` or JSON key files into the container image (src directory).
- Prefer Application Default Credentials (runtime service account) over key files.
- Token refresh in the web UI updates the in-memory token for the running container. For persistent rotation in production, update `META_ACCESS_TOKEN` in Secret Manager and deploy a new revision.
- If you use `--allow-unauthenticated`, keep `APP_PASSWORD` configured so the app does not become publicly accessible without any gate.

## Project Structure
```
adtracker/
│── scripts/
│   └── deploy-cloud-run_example.ps1  # PowerShell helper for Cloud Run deployment
│
│── src/
│   │── main.py                       # Main script (batch ad queries)
│   │── web_app.py                    # Streamlit web UI (crawler + Meta token refresh + login)
│   │── config.py                     # Environment variable loading & .env persistence
│   │── google_sheets.py              # Google Sheets API integration (read/write results)
│   │── meta_ads.py                   # Meta Ads API queries (with auto token refresh)
│   │── tiktok_ads.py                 # TikTok Ads API queries
│   │── google_ads.py                 # Google Ad Library / BigQuery queries
│   └── utils.py                      # Utility functions
│
│── .dockerignore                     # Files to exclude from Docker image
│── .env                              # Local environment variables (API keys, passwords)
│── .env.example                      # Template for .env (local + Cloud Run vars)
│── Dockerfile                        # Container image definition for Cloud Run
│── README.md                         # Documentation (this file)
│── requirements.txt                  # Python dependencies
│── service-account.json              # Google Cloud service account (local dev, optional)
└── <PROJECT-ID>-<HASH>.json          # Google Cloud credentials export (optional)
```

## Notes
- Ensure your service account has the right permissions to access the Google Sheet.
- API rate limits may apply. If needed, implement a delay in API requests to avoid exceeding limits.
- **Meta Ads API Token Auto-Refresh**: If the access token expires, it will be automatically refreshed using the App ID and Secret.
- **Google Sheets cell limit (10,000,000 cells)**: If the workbook is near the limit, the writer now removes oldest rows in result tabs and retries automatically.
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

