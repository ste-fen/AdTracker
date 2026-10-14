"""Prompts and placeholders for the AIT / LLM calls that fill the reporting columns.

Every AIT/LLM-filled column has its own prompt template. The templates are
editable in the web UI (tab "Prompts") and stored in the "Prompts" worksheet;
DEFAULT_PROMPTS is used for any prompt that is missing there.

Templates use {placeholders} that are filled from the ad data, see
META_PLACEHOLDERS and GOOGLE_PLACEHOLDERS. Unknown placeholders are left as-is.
"""

META_PLACEHOLDERS = {
    "search_term": "Suchbegriff",
    "country": "Land (AT/DE)",
    "page_name": "Name der Facebook-Seite",
    "ad_text": "Anzeigentext (Ad Creative Body)",
    "link_title": "Link-Titel",
    "link_caption": "Link-Caption (meist Domain)",
    "link_description": "Link-Beschreibung",
    "beneficiary_payers": "Begünstigte / Zahler",
    "ad_url": "Ad-Library-URL der Anzeige",
}

GOOGLE_PLACEHOLDERS = {
    "search_term": "Suchbegriff",
    "advertiser_name": "Angezeigter Werbetreibender",
    "advertiser_legal_name": "Rechtlicher Name des Werbetreibenden",
    "advertiser_location": "Standort des Werbetreibenden",
    "verification_status": "Verifizierungsstatus",
    "ad_format": "Anzeigenformat",
    "ad_url": "URL der Anzeige im Transparency Center",
}

# key -> (platform, column label)
PROMPT_DEFINITIONS = {
    "meta_reporting_reason": ("meta", "Reporting Reason"),
    "meta_reporting_reasons_text": ("meta", "Reporting reasons text"),
    "meta_specific_laws": ("meta", "Specific laws"),
    "google_begruendung": ("google", "Begründung"),
    "google_sachverhalt": ("google", "Sachverhalt"),
}

_META_AD_BLOCK = """Anzeige:
- Seite: {page_name}
- Text: {ad_text}
- Link-Titel: {link_title}
- Link-Caption: {link_caption}
- Link-Beschreibung: {link_description}
- Zahler/Begünstigte: {beneficiary_payers}
- URL: {ad_url}
- Suchbegriff: {search_term}
- Land: {country}"""

_GOOGLE_AD_BLOCK = """Anzeige:
- Werbetreibender: {advertiser_name}
- Rechtlicher Name: {advertiser_legal_name}
- Standort: {advertiser_location}
- Verifizierungsstatus: {verification_status}
- Format: {ad_format}
- URL: {ad_url}
- Suchbegriff: {search_term}"""

DEFAULT_PROMPTS = {
    "meta_reporting_reason": f"""Du unterstützt einen Trusted Flagger (ÖIAT) bei DSA-Meldungen an Meta.
Ordne die folgende Anzeige genau einem Meldegrund zu. Antworte ausschließlich mit dem Meldegrund, ohne Erklärung.

Mögliche Meldegründe:
- Fraud or scam
- Impersonation
- Intellectual property infringement
- Consumer protection violation
- Other

{_META_AD_BLOCK}""",
    "meta_reporting_reasons_text": f"""Du unterstützt einen Trusted Flagger (ÖIAT) bei DSA-Meldungen an Meta.
Begründe in 3-5 sachlichen Sätzen, warum die folgende Anzeige rechtswidrig ist. Nenne konkrete Merkmale aus der Anzeige
(z. B. Fake-Testimonials, missbräuchliche Verwendung von Prominenten oder Marken, unrealistische Gewinnversprechen).
Antworte nur mit dem Begründungstext.

{_META_AD_BLOCK}""",
    "meta_specific_laws": f"""Du unterstützt einen Trusted Flagger (ÖIAT) bei DSA-Meldungen an Meta.
Nenne die konkreten Rechtsvorschriften des Landes {{country}}, gegen die die folgende Anzeige verstößt
(z. B. § 146 StGB Betrug, §§ 1, 2 UWG irreführende Geschäftspraktiken, § 43 ABGB Namensrecht, § 78 UrhG Bildnisschutz).
Antworte nur mit einer kommagetrennten Liste der Paragraphen und Gesetze.

{_META_AD_BLOCK}""",
    "google_begruendung": f"""Du unterstützt einen Trusted Flagger (ÖIAT) bei DSA-Meldungen an Google.
Erkläre in 3-5 sachlichen Sätzen, warum die folgende Google-Anzeige rechtswidrig ist, und nenne die verletzten
österreichischen Rechtsvorschriften (z. B. § 146 StGB, §§ 1, 2 UWG). Antworte nur mit dem Begründungstext.

{_GOOGLE_AD_BLOCK}""",
    "google_sachverhalt": f"""Du unterstützt einen Trusted Flagger (ÖIAT) bei DSA-Meldungen an Google.
Beschreibe in 2-4 sachlichen Sätzen den Sachverhalt: Was wird in der Anzeige beworben, wer ist der Werbetreibende
und wohin führt die Anzeige? Keine rechtliche Bewertung. Antworte nur mit dem Sachverhaltstext.

{_GOOGLE_AD_BLOCK}""",
}


class _KeepMissing(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def render_prompt(template, values):
    """Fill {placeholders} in a template; unknown placeholders stay untouched."""
    try:
        return template.format_map(_KeepMissing(values))
    except (ValueError, IndexError):
        # Template contains unbalanced braces; fall back to plain replacement.
        for key, value in values.items():
            template = template.replace("{" + key + "}", str(value))
        return template


def _call_classifier(prompt):
    """Send a rendered prompt to the AIT or LLM API and return the answer text.

    Placeholder: returns an empty string until the real API is wired in.
    """
    # TODO: call AIT or LLM API here with `prompt`.
    return ""


def _first(value):
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


def classify_meta_ad(ad, prompts, search_term="", country_code=""):
    """Return the AIT/LLM-derived reporting fields for a raw Meta Ad Library result.

    Returns a dict with the keys:
      "reporting_reason"       -> column "Reporting Reason"
      "reporting_reasons_text" -> column "Reporting reasons text"
      "specific_laws"          -> column "Specific laws"
    """
    ad_id = ad.get("id", "")
    values = {
        "search_term": search_term,
        "country": country_code,
        "page_name": ad.get("page_name", ""),
        "ad_text": _first(ad.get("ad_creative_bodies")),
        "link_title": _first(ad.get("ad_creative_link_titles")),
        "link_caption": _first(ad.get("ad_creative_link_captions")),
        "link_description": _first(ad.get("ad_creative_link_descriptions")),
        "beneficiary_payers": ", ".join(p.get("payer", "") for p in ad.get("beneficiary_payers", [])),
        "ad_url": f"https://www.facebook.com/ads/library/?id={ad_id}" if ad_id else "",
    }
    return {
        "reporting_reason": _call_classifier(render_prompt(prompts["meta_reporting_reason"], values)),
        "reporting_reasons_text": _call_classifier(render_prompt(prompts["meta_reporting_reasons_text"], values)),
        "specific_laws": _call_classifier(render_prompt(prompts["meta_specific_laws"], values)),
    }


def classify_google_ad(ad, prompts, search_term=""):
    """Return the AIT/LLM-derived reporting fields for a Google Ads Transparency result.

    Returns a dict with the keys:
      "begruendung" -> column "Begründung"
      "sachverhalt" -> column "Sachverhalt"
    """
    values = {
        "search_term": search_term,
        "advertiser_name": ad.get("advertiser_disclosed_name") or "",
        "advertiser_legal_name": ad.get("advertiser_legal_name") or "",
        "advertiser_location": ad.get("advertiser_location") or "",
        "verification_status": ad.get("advertiser_verification_status") or "",
        "ad_format": ad.get("ad_format_type") or "",
        "ad_url": ad.get("creative_page_url") or "",
    }
    return {
        "begruendung": _call_classifier(render_prompt(prompts["google_begruendung"], values)),
        "sachverhalt": _call_classifier(render_prompt(prompts["google_sachverhalt"], values)),
    }
