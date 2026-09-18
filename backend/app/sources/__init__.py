from .gdelt import fetch_news
from .worldbank import fetch_indicators

# Backwards-compatible singular name used by older integrations.
fetch_indicator = fetch_indicators

__all__ = ["fetch_news", "fetch_indicators", "fetch_indicator"]
