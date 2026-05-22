import io
import base64
import hashlib
import hmac
import json
import os
import re
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from main import main
from meta_ads import MetaTokenExpiredError, refresh_meta_access_token
from screenshot_helper import generate_meta_screenshot_archive


AUTH_QUERY_PARAM = "auth"
AUTH_TOKEN_TTL_SECONDS = 12 * 60 * 60


def _render_inline_iframe(html_content, height):
    encoded_html = base64.b64encode(html_content.encode("utf-8")).decode("ascii")
    normalized_height = height
    if isinstance(height, int) and height <= 0:
        normalized_height = 1
    st.iframe(f"data:text/html;base64,{encoded_html}", height=normalized_height)


def _next_nonce(key):
    value = st.session_state.get(key, 0) + 1
    st.session_state[key] = value
    return value


def _safe_download_filename(file_name):
    normalized = re.sub(r"[^A-Za-z0-9._-]", "_", str(file_name))
    if not normalized.lower().endswith(".zip"):
        normalized = f"{normalized}.zip"
    return normalized


class LiveUILogStream:
    """File-like logger that renders output in a Streamlit text area immediately."""

    def __init__(self, placeholder, scroll_placeholder, title="Logs", max_chars=120000):
        self.placeholder = placeholder
        self.scroll_placeholder = scroll_placeholder
        self.title = title
        self.max_chars = max_chars
        self._buffer = io.StringIO()
        self._scroll_nonce = 0

    def write(self, text):
        text = "" if text is None else str(text)
        if not text:
            return 0

        self._buffer.write(text)
        self._render()
        return len(text)

    def flush(self):
        self._render()

    def log_line(self, message):
        self.write(f"{message}\n")

    def getvalue(self):
        return self._buffer.getvalue()

    def _render(self):
        text = self._buffer.getvalue()
        if len(text) > self.max_chars:
            text = text[-self.max_chars :]
        with self.placeholder.container():
            st.markdown(f"**{self.title}**")
            st.code(text or "(no logs yet)")

        self._scroll_nonce += 1
        with self.scroll_placeholder.container():
            _render_inline_iframe(
                f"""
                <div id="crawler-log-anchor-{self._scroll_nonce}"></div>
                <script>
                    const anchor = document.getElementById("crawler-log-anchor-{self._scroll_nonce}");
                    if (anchor) {{
                        anchor.scrollIntoView({{ behavior: "smooth", block: "end" }});
                    }}
                </script>
                """,
                height=0,
            )


def _build_auth_token(password, expires_at):
    payload = str(int(expires_at))
    signature = hmac.new(
        password.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{payload}.{signature}"


def _is_valid_auth_token(token, password):
    if not token or "." not in token:
        return False

    payload, signature = token.split(".", 1)
    if not payload.isdigit():
        return False

    if int(payload) < int(time.time()):
        return False

    expected_signature = hmac.new(
        password.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)


def _set_auth_query_param(value):
    try:
        st.query_params[AUTH_QUERY_PARAM] = value
    except Exception:
        st.experimental_set_query_params(**{AUTH_QUERY_PARAM: value})


def _clear_auth_query_param():
    try:
        if AUTH_QUERY_PARAM in st.query_params:
            del st.query_params[AUTH_QUERY_PARAM]
    except Exception:
        st.experimental_set_query_params()


def _get_auth_query_param():
    try:
        raw_value = st.query_params.get(AUTH_QUERY_PARAM, "")
    except Exception:
        raw_value = st.experimental_get_query_params().get(AUTH_QUERY_PARAM, "")

    if isinstance(raw_value, list):
        return raw_value[0] if raw_value else ""
    return raw_value


def _render_zip_download_blob(zip_bytes, file_name, auto_scroll=False):
    zip_b64 = base64.b64encode(zip_bytes).decode("ascii")
    safe_file_name = json.dumps(_safe_download_filename(file_name))
    safe_auto_scroll = "true" if auto_scroll else "false"
    button_id = f"zip-download-btn-{_next_nonce('zip_download_btn_nonce')}"

    _render_inline_iframe(
        f"""
        <div style="margin-top:0.25rem; margin-bottom:0.25rem;">
            <button id="{button_id}" style="
                background:#0e1117;
                color:#fafafa;
                border:1px solid #666;
                border-radius:0.5rem;
                padding:0.5rem 0.9rem;
                cursor:pointer;
                font-size:0.95rem;
            ">Meta Screenshot ZIP herunterladen</button>
        </div>
        <script>
            (function() {{
                const fileName = {safe_file_name};
                const b64 = "{zip_b64}";
                const shouldAutoScroll = {safe_auto_scroll};
                const btn = document.getElementById("{button_id}");
                if (!btn) return;

                if (shouldAutoScroll) {{
                    btn.scrollIntoView({{ behavior: "smooth", block: "center" }});
                }}

                btn.addEventListener("click", function() {{
                    const binary = atob(b64);
                    const len = binary.length;
                    const bytes = new Uint8Array(len);
                    for (let i = 0; i < len; i++) {{
                        bytes[i] = binary.charCodeAt(i);
                    }}

                    const blob = new Blob([bytes], {{ type: "application/zip" }});
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = fileName;
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    URL.revokeObjectURL(url);
                }});
            }})();
        </script>
        """,
        height=58,
    )


def _trigger_ui_scroll(scroll_placeholder):
    nonce = _next_nonce("ui_scroll_nonce")

    with scroll_placeholder.container():
        _render_inline_iframe(
            f"""
            <div id="ui-scroll-anchor-{nonce}"></div>
            <script>
                const anchor = document.getElementById("ui-scroll-anchor-{nonce}");
                if (anchor) {{
                    anchor.scrollIntoView({{ behavior: "smooth", block: "end" }});
                }}
            </script>
            """,
            height=0,
        )


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

    auth_token = _get_auth_query_param()
    if _is_valid_auth_token(auth_token, normalized_expected_password):
        st.session_state["authenticated"] = True
        return

    st.title("AdTracker Login")
    st.caption("Enter the shared app password to continue.")

    submitted_password = st.text_input("Password", type="password")
    if st.button("Sign in", type="primary"):
        normalized_submitted_password = submitted_password.strip()
        if hmac.compare_digest(normalized_submitted_password, normalized_expected_password):
            st.session_state["authenticated"] = True
            expires_at = int(time.time()) + AUTH_TOKEN_TTL_SECONDS
            _set_auth_query_param(
                _build_auth_token(normalized_expected_password, expires_at)
            )
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
    _clear_auth_query_param()
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
        live_logs = None
        try:
            with st.spinner("Crawler läuft..."):
                logs_placeholder = st.empty()
                logs_scroll_placeholder = st.empty()
                live_logs = LiveUILogStream(logs_placeholder, logs_scroll_placeholder)
                with redirect_stdout(live_logs), redirect_stderr(live_logs):
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
                        with redirect_stdout(live_logs), redirect_stderr(live_logs):
                            zip_bytes, created_count, attempted_count = generate_meta_screenshot_archive(
                                limited_meta_ads,
                                token,
                            )
                    if zip_bytes and created_count > 0:
                        st.session_state["meta_screenshots_zip"] = zip_bytes
                        timestamp = datetime.now(ZoneInfo("Europe/Vienna")).strftime(
                            "%Y%m%d_%H%M%S"
                        )
                        st.session_state["meta_screenshots_name"] = (
                            f"meta_ad_screenshots_{timestamp}.zip"
                        )
                        st.session_state["scroll_to_zip_download"] = True
                        # st.success(
                        #     f"{created_count} Screenshots erstellt (versucht: {attempted_count}, Limit N={int(screenshot_limit)})."
                        # )
                        # _trigger_ui_scroll(ui_scroll_placeholder)
                    else:
                        st.warning(
                            f"Keine Screenshots erstellt (Limit N={int(screenshot_limit)}). Bitte pruefe Token/Erreichbarkeit der Snapshot-URLs."
                        )

            st.success("Crawl erfolgreich abgeschlossen.")
            st.session_state["scroll_to_result"] = True
        except MetaTokenExpiredError as exc:
            st.error(str(exc))
            st.info(
                "Gehe zum Tab 'Meta Token', aktualisiere den Token und starte den Crawler erneut."
            )
            if live_logs is not None:
                live_logs.log_line(f"MetaTokenExpiredError: {exc}")
        except Exception as exc:
            traceback_text = traceback.format_exc()
            if live_logs is not None:
                live_logs.log_line(f"Unerwarteter Fehler: {exc!r}")
                live_logs.log_line(traceback_text)
            st.error(f"Unerwarteter Fehler: {exc!r}")
            st.exception(exc)
            st.text_area("Traceback", traceback_text, height=260, key="crawler_traceback")
        finally:
            if live_logs is not None:
                live_logs.flush()

    ui_scroll_placeholder = st.empty()

    if st.session_state.get("meta_screenshots_zip"):
        should_scroll_download_button = bool(st.session_state.get("scroll_to_zip_download"))
        _render_zip_download_blob(
            st.session_state["meta_screenshots_zip"],
            st.session_state.get("meta_screenshots_name", "meta_ad_screenshots.zip"),
            auto_scroll=should_scroll_download_button,
        )

    should_scroll_to_result = bool(
        st.session_state.get("scroll_to_result")
    )
    if should_scroll_to_result:
        _trigger_ui_scroll(ui_scroll_placeholder)
        st.session_state["scroll_to_result"] = False
        st.session_state["scroll_to_zip_download"] = False

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
        key="meta_token_input",
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
