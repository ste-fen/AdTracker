import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Google Sheets API
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE")

# Meta API
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
META_APP_ID = os.getenv("META_APP_ID")
META_APP_SECRET = os.getenv("META_APP_SECRET")

# TikTok API
TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN")
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")

# Google Ad Library API
GOOGLE_BIGQUERY_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_BIGQUERY_SERVICE_ACCOUNT_FILE")

def update_env_file(key, value):
    """ Update .env file with a new key-value pair """
    env_file = ".env"
    lines = []
    
    with open(env_file, "r") as file:
        lines = file.readlines()
    
    with open(env_file, "w") as file:
        for line in lines:
            if line.startswith(f"{key}="):
                file.write(f"{key}={value}\n")
            else:
                file.write(line)
        
        # If key was not found, append it
        if not any(line.startswith(f"{key}=") for line in lines):
            file.write(f"{key}={value}\n")
