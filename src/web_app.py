import io
import hmac
import os
import traceback
from contextlib import redirect_stdout

import streamlit as st

from main import main
from meta_ads import MetaTokenExpiredError, refresh_meta_access_token


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
    # st.write("Runs the same workflow as src/main.py.")

    if st.button("Crawler starten", type="primary"):
        log_buffer = io.StringIO()
        try:
            with st.spinner("Crawler läuft..."):
                with redirect_stdout(log_buffer):
                    main()
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
