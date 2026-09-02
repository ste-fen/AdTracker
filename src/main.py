from google_sheets import (
    clear_results_sheets,
    read_search_terms,
    write_tiktok_results_to_sheet,
    write_meta_results_to_sheet,
    write_google_results_to_sheet,
)
from meta_ads import query_meta_ads
from tiktok_ads import query_tiktok_ads_with_details
from google_ads import query_google_ad_library
from datetime import datetime
from ftplib import FTP, FTP_TLS, all_errors
import json
import os


def _first_list_value(value):
    if isinstance(value, list) and value:
        return value[0]
    if value is None:
        return ""
    return value


def _ensure_output_dir(path):
    os.makedirs(path, exist_ok=True)


def _save_json_payload(payload, output_dir="outputs"):
    _ensure_output_dir(output_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"adtracker_results_{timestamp}.json"
    file_path = os.path.join(output_dir, file_name)

    with open(file_path, "w", encoding="utf-8") as json_file:
        json.dump(payload, json_file, ensure_ascii=False, indent=2)

    return file_path


def _upload_file_to_ftp(local_file_path):
    ftp_host = os.getenv("FTP_HOST", "").strip()
    ftp_username = os.getenv("FTP_USERNAME", "").strip()
    ftp_password = os.getenv("FTP_PASSWORD", "").strip()
    ftp_remote_dir = os.getenv("FTP_REMOTE_DIR", "").strip()
    ftp_port = int(os.getenv("FTP_PORT", "21") or "21")
    ftp_use_tls = os.getenv("FTP_USE_TLS", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if not ftp_host or not ftp_username or not ftp_password:
        raise ValueError(
            "FTP_HOST, FTP_USERNAME und FTP_PASSWORD müssen gesetzt sein, damit der FTP-Upload funktioniert."
        )

    ftp_client = None
    remote_file_name = os.path.basename(local_file_path)
    try:
        if ftp_use_tls:
            ftp_client = FTP_TLS()
            ftp_client.connect(ftp_host, ftp_port, timeout=30)
            ftp_client.login(ftp_username, ftp_password)
            ftp_client.prot_p()
        else:
            ftp_client = FTP()
            ftp_client.connect(ftp_host, ftp_port, timeout=30)
            ftp_client.login(ftp_username, ftp_password)

        if ftp_remote_dir:
            ftp_client.cwd(ftp_remote_dir)

        with open(local_file_path, "rb") as input_file:
            ftp_client.storbinary(f"STOR {remote_file_name}", input_file)
    except all_errors as ftp_error:
        raise RuntimeError(f"FTP-Upload fehlgeschlagen: {ftp_error}") from ftp_error
    finally:
        if ftp_client is not None:
            try:
                ftp_client.quit()
            except all_errors:
                ftp_client.close()


def _build_meta_json_results(meta_results, search_term):
    rows = []
    for result in meta_results or []:
        rows.append(
            {
                "Search Term": search_term,
                "Ad Creative Bodies": _first_list_value(result.get("ad_creative_bodies")),
                "Ad Creative Link Captions": _first_list_value(
                    result.get("ad_creative_link_captions")
                ),
                "Ad Snapshot URL": result.get("ad_snapshot_url", ""),
            }
        )
    return rows


def _build_tiktok_json_results(tiktok_results, search_term):
    rows = []
    for result in tiktok_results or []:
        ad = (result or {}).get("data", {}).get("ad", {})
        videos = ad.get("videos") or []
        first_video = videos[0] if videos and isinstance(videos[0], dict) else {}

        rows.append(
            {
                "Search Term": search_term,
                "Video URL": first_video.get("url", ""),
            }
        )
    return rows


def _build_google_json_results(google_results, search_term):
    rows = []
    for result in google_results or []:
        row = dict(result) if isinstance(result, dict) else {}
        rows.append(
            {
                "Search Term": search_term,
                "Creative Page URL": row.get("creative_page_url", ""),
            }
        )
    return rows


def result_count(results):
    """Return a robust count for list-like API results."""
    if isinstance(results, list):
        return len(results)
    return 0


def parse_date(date_str, output_format=None):
    """Parse a date string in yyyy-mm-dd format and optionally format it."""
    try:
        if date_str:
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
            if output_format:
                return parsed_date.strftime(output_format)
            return parsed_date
        return None
    except ValueError as e:
        print(f"Error parsing date '{date_str}': {e}")
        return None

def main(
    collect_meta_ads=False,
    max_results_per_platform=500,
    country_code=None,
    save_results_json=True,
    upload_results_json_to_ftp=False,
):
    print("Clearing results sheets before crawler start...")
    clear_results_sheets()
    search_terms = read_search_terms()
    all_meta_ads = []
    json_terms = []
    max_results_per_platform = int(max_results_per_platform) if max_results_per_platform else 500
    country_code = country_code or "AT"

    for entry in search_terms:
        term = entry["term"]
        date_from = entry["date_from"]
        date_to = entry["date_to"]
        fetch_meta = entry["fetch_meta"]
        fetch_tiktok = entry["fetch_tiktok"]
        fetch_google = entry["fetch_google"]
        requested_platforms = []
        if fetch_meta:
            requested_platforms.append("meta")
        if fetch_tiktok:
            requested_platforms.append("tiktok")
        if fetch_google:
            requested_platforms.append("google")

        meta_count = 0
        tiktok_count = 0
        google_count = 0
        meta_results = []
        tiktok_results = []
        google_results = []

        # Parse dates consistently
        meta_date_from = parse_date(date_from, "%Y-%m-%d")  # For Meta (yyyy-mm-dd format)
        meta_date_to = parse_date(date_to, "%Y-%m-%d")      # For Meta (yyyy-mm-dd format)
        tiktok_min_date = parse_date(date_from, "%Y%m%d")  # For TikTok (yyyyMMdd format)
        tiktok_max_date = parse_date(date_to, "%Y%m%d")    # For TikTok (yyyyMMdd format)
        google_date_from = parse_date(date_from, "%Y-%m-%d")  # For Google (yyyy-mm-dd format)
        google_date_to = parse_date(date_to, "%Y-%m-%d")      # For Google (yyyy-mm-dd format)

        if fetch_meta:
            print(f"Fetching Meta data for term '{term}' from {meta_date_from} to {meta_date_to}...")
            if not meta_date_from or not meta_date_to:
                print(f"Skipping Meta fetch for term '{term}' due to invalid dates.")
            else:
                meta_results = query_meta_ads(
                    term,
                    delivery_date_min=meta_date_from,
                    delivery_date_max=meta_date_to,
                    max_ads=max_results_per_platform,
                    country_code=country_code,
                )
            if collect_meta_ads and isinstance(meta_results, list):
                all_meta_ads.extend(meta_results)
            meta_count = result_count(meta_results)
            print(f"{meta_count} Meta results for term '{term}'")
            if meta_count > 0:
                print(f"Writing Meta results for term '{term}'...")
                write_meta_results_to_sheet(meta_results, term, country_code)
            print("-" * 100)

        if fetch_tiktok:
            print(f"Fetching TikTok data for term '{term}' from {tiktok_min_date} to {tiktok_max_date}...")
            if not tiktok_min_date or not tiktok_max_date:
                print(f"Skipping TikTok fetch for term '{term}' due to invalid dates.")
            else:
                tiktok_results = query_tiktok_ads_with_details(
                    term,
                    tiktok_min_date,
                    tiktok_max_date,
                    max_results=max_results_per_platform,
                    country_code=country_code,
                )
            tiktok_count = result_count(tiktok_results)
            print(f"{tiktok_count} TikTok results for term '{term}'")
            if tiktok_count > 0:
                print(f"Writing TikTok results for term '{term}'...")
                write_tiktok_results_to_sheet(tiktok_results, term)
            print("-" * 100)

        if fetch_google:
            print(f"Fetching Google data for term '{term}' from {google_date_from} to {google_date_to}...")
            if not google_date_from or not google_date_to:
                print(f"Skipping Google fetch for term '{term}' due to invalid dates.")
            else:
                google_results = query_google_ad_library(
                    term,
                    google_date_from,
                    google_date_to,
                    max_results=max_results_per_platform,
                    country_code=country_code,
                )
            google_count = result_count(google_results)
            print(f"{google_count} Google results for term '{term}'")
            if google_count > 0:
                print(f"Writing Google results for term '{term}'...")
                write_google_results_to_sheet(google_results, term)
            print("-" * 100)

        json_terms.append(
            {
                "search_term": term,
                "queried_platforms_count": len(requested_platforms),
                "queried_platforms": requested_platforms,
                "ad_count_per_platform": {
                    "meta": meta_count,
                    "tiktok": tiktok_count,
                    "google": google_count,
                },
                "ad_count_total": meta_count + tiktok_count + google_count,
                "meta": _build_meta_json_results(meta_results, term),
                "tiktok": _build_tiktok_json_results(tiktok_results, term),
                "google": _build_google_json_results(google_results, term),
            }
        )

    payload = {
        "generated_at": datetime.now().isoformat(),
        "country_code": country_code,
        "max_results_per_platform": max_results_per_platform,
        "terms": json_terms,
    }

    json_file_path = None
    ftp_upload_performed = False
    if save_results_json:
        json_file_path = _save_json_payload(payload)
        print(f"JSON gespeichert: {json_file_path}")

    if upload_results_json_to_ftp:
        if not json_file_path:
            json_file_path = _save_json_payload(payload)
            print(f"JSON gespeichert: {json_file_path}")
        _upload_file_to_ftp(json_file_path)
        ftp_upload_performed = True
        print("JSON erfolgreich auf FTP-Server hochgeladen.")

    run_result = {
        "meta_ads": all_meta_ads if collect_meta_ads else [],
        "json_payload": payload,
        "json_file_path": json_file_path,
        "ftp_upload_performed": ftp_upload_performed,
    }
    return run_result


if __name__ == "__main__":
    main()
