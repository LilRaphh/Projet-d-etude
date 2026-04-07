from pipeline.scrapers.mango import MangoScraper
from pipeline.scrapers.kappa import KappaScraper
from pipeline.scrapers.lecoqsportif import LeCoqSportifScraper
from pipeline.scrapers.lotto import LottoScraper
from pipeline.scrapers.tacchini import TacchiniScraper

# Scrapers Playwright — optionnels (nécessitent : pip install playwright && playwright install chromium)
try:
    from pipeline.scrapers.jules import JulesScraper
    from pipeline.scrapers.nike import NikeScraper
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    JulesScraper = None  # type: ignore
    NikeScraper = None   # type: ignore

__all__ = [
    "MangoScraper", "KappaScraper", "LeCoqSportifScraper",
    "LottoScraper", "TacchiniScraper", "JulesScraper", "NikeScraper",
]
