import io
import hmac
import os
import traceback
from contextlib import redirect_stdout

import streamlit as st

from main import main
from meta_ads import MetaTokenExpiredError, refresh_meta_access_token
from screenshot_helper import generate_meta_screenshot_archive


def require_login():
    """Protect the app with a shared password when APP_PASSWORD is configured."""
    expected_password = os.getenv("APP_PASSWORD", "")
    normalized_expected_password = expected_password.strip()

    if not normalized_expected_password:
        if os.getenv("K_SERVICE"):
            st.error("APP_PASSWORD is not configured. Add the secret before exposing the app publicly.")
            st.stop()
        return

    if st.session_state.get("authenticated"):
        return

    st.title("AdTracker Login")
    st.caption("Enter the shared app password to continue.")

    submitted_password = st.text_input("Password", type="password")
    if st.button("Sign in", type="primary"):
        normalized_submitted_password = submitted_password.strip()
        if hmac.compare_digest(normalized_submitted_password, normalized_expected_password):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Invalid password.")

    st.stop()


st.set_page_config(page_title="AdTracker", layout="wide")
require_login()
st.title("AdTracker Web")
st.caption("Run the crawler and refresh Meta tokens directly in the browser.")

if st.button("Logout"):
    st.session_state["authenticated"] = False
    st.rerun()

run_tab, token_tab = st.tabs(["Crawler", "Meta Token"])

with run_tab:
    st.subheader("Crawler")
    country_options = {"Österreich (AT)": "AT", "Deutschland (DE)": "DE"}
    selected_country_label = st.selectbox(
        "Land",
        options=list(country_options.keys()),
        index=0,
        help="Wird für Meta, TikTok und Google als Länderfilter verwendet.",
    )
    selected_country_code = country_options[selected_country_label]
    max_results_all_platforms = st.number_input(
        "Maximale Ergebnisse je Plattform (Meta, TikTok, Google)",
        min_value=1,
        max_value=5000,
        value=200,
        step=1,
        help="Eine gemeinsame Obergrenze pro Suchbegriff fuer alle drei Plattformen.",
    )
    st.caption(
        f"Aktuelles Limit pro Plattform und Suchbegriff: {int(max_results_all_platforms)}"
    )
    enable_meta_screenshots = st.checkbox(
        "Meta screenshots erstellen (manuell aktivieren)",
        value=False,
        help="Erstellt serverseitig Screenshots aus ad_snapshot_url und bietet sie als ZIP zum Download an.",
    )
    screenshot_limit = st.number_input(
        "Maximale Anzahl Meta Screenshots (N)",
        min_value=1,
        max_value=500,
        value=25,
        step=1,
        disabled=not enable_meta_screenshots,
        help="Nur wenn die Screenshot-Option aktiv ist. Es werden die ersten N Meta Ads verarbeitet.",
    )

    if st.button("Crawler starten", type="primary"):
        log_buffer = io.StringIO()
        try:
            with st.spinner("Crawler läuft..."):
                with redirect_stdout(log_buffer):
                    run_result = main(
                        collect_meta_ads=enable_meta_screenshots,
                        max_results_per_platform=int(max_results_all_platforms),
                        country_code=selected_country_code,
                    )

            st.session_state.pop("meta_screenshots_zip", None)
            st.session_state.pop("meta_screenshots_name", None)

            if enable_meta_screenshots:
                meta_ads = (run_result or {}).get("meta_ads", [])
                token = os.getenv("META_ACCESS_TOKEN", "").strip()

                if not meta_ads:
                    st.info("Keine Meta Ads gefunden. Es wurden keine Screenshots erstellt.")
                elif not token:
                    st.warning("META_ACCESS_TOKEN fehlt. Screenshots konnten nicht erstellt werden.")
                else:
                    limited_meta_ads = meta_ads[: int(screenshot_limit)]
                    with st.spinner("Meta Screenshots werden erstellt..."):
                        zip_bytes, created_count, attempted_count = generate_meta_screenshot_archive(
                            limited_meta_ads,
                            token,
                        )
                    if zip_bytes and created_count > 0:
                        st.session_state["meta_screenshots_zip"] = zip_bytes
                        st.session_state["meta_screenshots_name"] = "meta_ad_screenshots.zip"
                        st.success(
                            f"{created_count} Screenshots erstellt (versucht: {attempted_count}, Limit N={int(screenshot_limit)})."
                        )
                    else:
                        st.warning(
                            f"Keine Screenshots erstellt (Limit N={int(screenshot_limit)}). Bitte pruefe Token/Erreichbarkeit der Snapshot-URLs."
                        )

            st.success("Crawl erfolgreich abgeschlossen.")
        except MetaTokenExpiredError as exc:
            st.error(str(exc))
            st.info(
                "Gehe zum Tab 'Meta Token', aktualisiere den Token und starte den Crawler erneut."
            )
        except Exception as exc:
            traceback_text = traceback.format_exc()
            print(traceback_text)
            st.error(f"Unerwarteter Fehler: {exc!r}")
            st.exception(exc)
            st.text_area("Traceback", traceback_text, height=260)
        finally:
            logs = log_buffer.getvalue().strip()
            if logs:
                st.text_area("Logs", logs, height=380)

    if st.session_state.get("meta_screenshots_zip"):
        st.download_button(
            "Meta Screenshot ZIP herunterladen",
            data=st.session_state["meta_screenshots_zip"],
            file_name=st.session_state.get("meta_screenshots_name", "meta_ad_screenshots.zip"),
            mime="application/zip",
        )

with token_tab:
    st.subheader("Meta Token Refresh")
    st.write(
        "Fuege hier einen kurzlebigen Meta User Token ein. "
        "Die App tauscht ihn gegen einen long-lived Token. Lokal wird er in .env gespeichert; "
        "auf Cloud Run gilt er nur fuer den laufenden Container."
    )
    # st.markdown(
    #     "Token holen: "
    #     "[Meta Graph API Explorer](https://developers.facebook.com/tools/explorer/)"
    # )

    short_lived_token = st.text_area(
        "Short-lived user token",
        height=140,
        placeholder="EAAB...",
    )

    if st.button("Meta Token aktualisieren"):
        try:
            refresh_meta_access_token(short_lived_token)
            if os.getenv("K_SERVICE"):
                st.success("META_ACCESS_TOKEN wurde fuer den laufenden Container aktualisiert.")
            else:
                st.success("META_ACCESS_TOKEN wurde aktualisiert und in .env gespeichert.")
        except Exception as exc:
            st.error(f"Token konnte nicht aktualisiert werden: {exc}")
