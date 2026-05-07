from pipeline.scrapers.mango import MangoScraper
from pipeline.scrapers.kappa import KappaScraper
from pipeline.scrapers.lecoqsportif import LeCoqSportifScraper
from pipeline.scrapers.lotto import LottoScraper
from pipeline.scrapers.tacchini import TacchiniScraper
from pipeline.scrapers.apc import ApcScraper
from pipeline.scrapers.balzac import BalzacScraper
from pipeline.scrapers.maisonlabiche import MaisonLabicheScraper
from pipeline.scrapers.rouje import RoujeScraper
from pipeline.scrapers.cabaia import CabaiaScraper
from pipeline.scrapers.bonnegueule import BonneGueuleScraper
from pipeline.scrapers.merci import MerciScraper
from pipeline.scrapers.isabelmarant import IsabelMarantScraper
from pipeline.scrapers.amiparis import AmiParisScraper

# Scrapers Playwright — optionnels (nécessitent : pip install playwright && playwright install chromium)
try:
    from pipeline.scrapers.jules import JulesScraper
    from pipeline.scrapers.nike import NikeScraper
    from pipeline.scrapers.gymshark import GymsharkScraper
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    JulesScraper    = None  # type: ignore
    NikeScraper     = None  # type: ignore
    GymsharkScraper = None  # type: ignore

__all__ = [
    "MangoScraper", "KappaScraper", "LeCoqSportifScraper",
    "LottoScraper", "TacchiniScraper",
    "ApcScraper", "BalzacScraper", "MaisonLabicheScraper",
    "RoujeScraper", "CabaiaScraper",
    "BonneGueuleScraper", "MerciScraper", "IsabelMarantScraper", "AmiParisScraper",
    "JulesScraper", "NikeScraper", "GymsharkScraper",
]
