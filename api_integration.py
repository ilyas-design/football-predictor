#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                       FOOTBALL DATA API INTEGRATION                          ║
║              Connect to real football data sources for predictions           ║
╚══════════════════════════════════════════════════════════════════════════════╝

This module provides integration with various football data APIs.
Configure your API keys below or set them as environment variables.

Supported APIs:
- API-Football (https://www.api-football.com/)
- Football-Data.org (https://www.football-data.org/)
- Odds API (https://the-odds-api.com/)
"""

import requests
import json
import hashlib
import time
import pickle
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import os

# ═══════════════════════════════════════════════════════════════════════════════
# API CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Load .env file if present (for local development)
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")
API_FOOTBALL_HOST = "api-football-v1.p.rapidapi.com"

FOOTBALL_DATA_KEY = os.getenv("FOOTBALL_DATA_KEY", "")

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")

# ═══════════════════════════════════════════════════════════════════════════════
# TEAM NAME NORMALIZATION (API names → English common names)
# ═══════════════════════════════════════════════════════════════════════════════

TEAM_NAME_MAP = {
    # Champions League / European clubs
    "FC Barcelone": "Barcelona",
    "FC Barcelona": "Barcelona",
    "Atalanta Bergame": "Atalanta",
    "Atalanta BC": "Atalanta",
    "Club Atlético de Madrid": "Atletico Madrid",
    "Atlético de Madrid": "Atletico Madrid",
    "Atletico de Madrid": "Atletico Madrid",
    "Tottenham Hotspur FC": "Tottenham",
    "Tottenham Hotspur": "Tottenham",
    "Newcastle United FC": "Newcastle",
    "Newcastle United": "Newcastle",
    "FC Bayern München": "Bayern Munich",
    "Bayern München": "Bayern Munich",
    "FC Bayern Munich": "Bayern Munich",
    "Galatasaray SK": "Galatasaray",
    "Galatasaray A.S.": "Galatasaray",
    "Liverpool FC": "Liverpool",
    "Arsenal FC": "Arsenal",
    "Manchester City FC": "Manchester City",
    "Manchester United FC": "Manchester United",
    "Chelsea FC": "Chelsea",
    "AC Milan": "AC Milan",
    "AC Mailand": "AC Milan",
    "FC Internazionale Milano": "Inter Milan",
    "Inter Mailand": "Inter Milan",
    "Inter Milano": "Inter Milan",
    "Paris Saint-Germain FC": "PSG",
    "Paris Saint-Germain": "PSG",
    "Paris SG": "PSG",
    "Juventus FC": "Juventus",
    "Juventus Turin": "Juventus",
    "Real Madrid CF": "Real Madrid",
    "Borussia Dortmund": "Dortmund",
    "BV Borussia 09 Dortmund": "Dortmund",
    "RB Leipzig": "RB Leipzig",
    "Bayer 04 Leverkusen": "Bayer Leverkusen",
    "Bayer Leverkusen": "Bayer Leverkusen",
    "SL Benfica": "Benfica",
    "Sporting Clube de Portugal": "Sporting CP",
    "Sporting CP": "Sporting CP",
    "FC Porto": "Porto",
    "Club Brugge KV": "Club Brugge",
    "AFC Feyenoord": "Feyenoord",
    "Feyenoord Rotterdam": "Feyenoord",
    "PSV Eindhoven": "PSV",
    "AFC Ajax": "Ajax",
    "Celtic FC": "Celtic",
    "Rangers FC": "Rangers",
    "Stade Brestois 29": "Brest",
    "AS Monaco FC": "Monaco",
    "AS Monaco": "Monaco",
    "Lille OSC": "Lille",
    "VfB Stuttgart": "Stuttgart",
    "FC Girona": "Girona",
    "Bologna FC 1909": "Bologna",
    "FC Salzburg": "Salzburg",
    "FC Red Bull Salzburg": "Salzburg",
    "SK Sturm Graz": "Sturm Graz",
    "BSC Young Boys": "Young Boys",
    "Aston Villa FC": "Aston Villa",
    "GNK Dinamo Zagreb": "Dinamo Zagreb",
    "FK Crvena Zvezda": "Red Star Belgrade",
    "AC Sparta Praha": "Sparta Prague",
    "ŠK Slovan Bratislava": "Slovan Bratislava",
    "FK Shakhtar Donetsk": "Shakhtar Donetsk",
    "Shakhtar Donetsk": "Shakhtar Donetsk",
    # Premier League
    "Wolverhampton Wanderers FC": "Wolves",
    "Wolverhampton Wanderers": "Wolves",
    "West Ham United FC": "West Ham",
    "Brighton & Hove Albion FC": "Brighton",
    "Brighton and Hove Albion": "Brighton",
    "Nottingham Forest FC": "Nottingham Forest",
    "Ipswich Town FC": "Ipswich Town",
    "Leicester City FC": "Leicester City",
    "Crystal Palace FC": "Crystal Palace",
    "Everton FC": "Everton",
    "AFC Bournemouth": "Bournemouth",
    "Fulham FC": "Fulham",
    "Southampton FC": "Southampton",
    "Brentford FC": "Brentford",
    # La Liga
    "Real Betis Balompié": "Real Betis",
    "Real Betis Balompie": "Real Betis",
    "Rayo Vallecano de Madrid": "Rayo Vallecano",
    "Athletic Club": "Athletic Bilbao",
    "CA Osasuna": "Osasuna",
    "RCD Mallorca": "Mallorca",
    "RCD Espanyol de Barcelona": "Espanyol",
    "RCD Espanyol": "Espanyol",
    "RC Celta de Vigo": "Celta Vigo",
    "Getafe CF": "Getafe",
    "Villarreal CF": "Villarreal",
    "Sevilla FC": "Sevilla",
    "Valencia CF": "Valencia",
    "Real Sociedad de Fútbol": "Real Sociedad",
    "Deportivo Alavés": "Alaves",
    "Deportivo Alaves": "Alaves",
    "UD Las Palmas": "Las Palmas",
    "Girona FC": "Girona",
    "Real Valladolid CF": "Real Valladolid",
    "CD Leganés": "Leganes",
    "CD Leganes": "Leganes",
    # Bundesliga
    "TSG 1899 Hoffenheim": "Hoffenheim",
    "1. FC Heidenheim 1846": "Heidenheim",
    "1. FC Union Berlin": "Union Berlin",
    "FC Augsburg": "Augsburg",
    "SV Werder Bremen": "Werder Bremen",
    "1. FSV Mainz 05": "Mainz",
    "SC Freiburg": "Freiburg",
    "Eintracht Frankfurt": "Frankfurt",
    "VfL Wolfsburg": "Wolfsburg",
    "VfL Bochum 1848": "Bochum",
    "FC St. Pauli 1910": "St. Pauli",
    "Holstein Kiel": "Holstein Kiel",
    "Borussia Mönchengladbach": "Monchengladbach",
    # Serie A
    "SSC Napoli": "Napoli",
    "SS Lazio": "Lazio",
    "AS Roma": "Roma",
    "ACF Fiorentina": "Fiorentina",
    "Torino FC": "Torino",
    "US Lecce": "Lecce",
    "Genoa CFC": "Genoa",
    "Cagliari Calcio": "Cagliari",
    "Empoli FC": "Empoli",
    "Udinese Calcio": "Udinese",
    "Hellas Verona FC": "Verona",
    "US Salernitana 1919": "Salernitana",
    "Parma Calcio 1913": "Parma",
    "Venezia FC": "Venezia",
    "Como 1907": "Como",
    "AC Monza": "Monza",
    # Ligue 1
    "Olympique de Marseille": "Marseille",
    "Olympique Lyonnais": "Lyon",
    "OGC Nice": "Nice",
    "RC Lens": "Lens",
    "RC Strasbourg Alsace": "Strasbourg",
    "Stade Rennais FC 1901": "Rennes",
    "Stade de Reims": "Reims",
    "FC Nantes": "Nantes",
    "Montpellier HSC": "Montpellier",
    "Toulouse FC": "Toulouse",
    "AJ Auxerre": "Auxerre",
    "Angers SCO": "Angers",
    "Le Havre AC": "Le Havre",
    "FC Lorient": "Lorient",
    "Clermont Foot 63": "Clermont",
    "AS Saint-Étienne": "Saint-Etienne",
}


def normalize_team_name(name: str) -> str:
    """Normalize a team name to its common English form."""
    return TEAM_NAME_MAP.get(name, name)


# ═══════════════════════════════════════════════════════════════════════════════
# LEAGUE CONFIGURATIONS
# ═══════════════════════════════════════════════════════════════════════════════

LEAGUES = {
    "La Liga": {"api_football_id": 140, "football_data_code": "PD"},
    "Premier League": {"api_football_id": 39, "football_data_code": "PL"},
    "Serie A": {"api_football_id": 135, "football_data_code": "SA"},
    "Bundesliga": {"api_football_id": 78, "football_data_code": "BL1"},
    "Ligue 1": {"api_football_id": 61, "football_data_code": "FL1"},
    "Champions League": {"api_football_id": 2, "football_data_code": "CL"},
    "Europa League": {"api_football_id": 3, "football_data_code": "EL"},
    "Eredivisie": {"api_football_id": 88, "football_data_code": "DED"},
    "Primeira Liga": {"api_football_id": 94, "football_data_code": "PPL"},
    "Super Lig": {"api_football_id": 203, "football_data_code": "TSL"},
    "Scottish Premiership": {"api_football_id": 179, "football_data_code": "SPL"},
    "Championship": {"api_football_id": 40, "football_data_code": "ELC"},
    "MLS": {"api_football_id": 253, "football_data_code": "MLS"},
    "Liga MX": {"api_football_id": 262, "football_data_code": None},
    "Brasileirao": {"api_football_id": 71, "football_data_code": "BSA"},
    "Argentine Primera": {"api_football_id": 128, "football_data_code": None},
    "Belgian Pro League": {"api_football_id": 144, "football_data_code": None},
    "Swiss Super League": {"api_football_id": 207, "football_data_code": None},
    "Austrian Bundesliga": {"api_football_id": 218, "football_data_code": None},
    "Greek Super League": {"api_football_id": 197, "football_data_code": None},
}

def get_available_leagues() -> List[str]:
    return sorted(LEAGUES.keys())

# ═══════════════════════════════════════════════════════════════════════════════
# RESPONSE CACHE
# ═══════════════════════════════════════════════════════════════════════════════

class ResponseCache:
    """Disk-backed response cache to stay within API free-tier limits."""

    CACHE_FILE = Path.home() / ".football_predictor_cache"

    # Default TTLs in seconds
    TTL_STANDINGS = 3600      # 1 hour
    TTL_FIXTURES = 1800       # 30 min
    TTL_ODDS = 900            # 15 min
    TTL_H2H = 86400           # 24 hours
    TTL_RESULTS = 86400       # 24 hours

    def __init__(self):
        self._store: Dict[str, Tuple[float, object]] = {}
        self._load_from_disk()

    # ── public api ──────────────────────────────────────────────────────────

    def get(self, key: str, ttl: int) -> Optional[object]:
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, data = entry
        if time.time() - ts > ttl:
            del self._store[key]
            return None
        return data

    def set(self, key: str, data: object):
        self._store[key] = (time.time(), data)
        self._save_to_disk()

    def clear(self):
        self._store.clear()
        if self.CACHE_FILE.exists():
            self.CACHE_FILE.unlink()

    @staticmethod
    def make_key(endpoint: str, params: dict = None) -> str:
        raw = f"{endpoint}|{json.dumps(params or {}, sort_keys=True)}"
        return hashlib.md5(raw.encode()).hexdigest()

    # ── persistence ─────────────────────────────────────────────────────────

    def _save_to_disk(self):
        try:
            with open(self.CACHE_FILE, "wb") as f:
                pickle.dump(self._store, f)
        except Exception:
            pass

    def _load_from_disk(self):
        try:
            if self.CACHE_FILE.exists():
                with open(self.CACHE_FILE, "rb") as f:
                    self._store = pickle.load(f)
        except Exception:
            self._store = {}

# Shared cache instance
_cache = ResponseCache()

# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TeamData:
    """Real team data fetched from API"""
    id: int
    name: str
    logo: str
    games_played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    home_wins: int
    home_draws: int
    home_losses: int
    home_goals_for: int
    home_goals_against: int
    away_wins: int
    away_draws: int
    away_losses: int
    away_goals_for: int
    away_goals_against: int
    form: str  # e.g., "WWDLW"
    clean_sheets: int
    failed_to_score: int

@dataclass
class TeamExtendedStats:
    """Real team-level statistics from API (corners, cards, shots, etc.)."""
    team_id: int
    team_name: str
    corners_for_avg: float = 0.0     # avg corners won per match
    corners_against_avg: float = 0.0 # avg corners conceded per match
    yellow_cards_avg: float = 0.0    # avg yellows per match
    red_cards_avg: float = 0.0
    shots_on_target_avg: float = 0.0
    shots_total_avg: float = 0.0
    fouls_committed_avg: float = 0.0
    fouls_drawn_avg: float = 0.0
    possession_avg: float = 50.0
    games_played: int = 0

@dataclass
class FixtureData:
    """Match fixture data"""
    id: int
    home_team: str
    away_team: str
    date: datetime
    venue: str
    league: str
    round: str
    status: str
    home_odds: float = 0.0
    draw_odds: float = 0.0
    away_odds: float = 0.0

@dataclass
class MatchResult:
    """Historical match result for backtesting / model fitting."""
    date: str
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int

# ═══════════════════════════════════════════════════════════════════════════════
# API-FOOTBALL INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════

class APIFootball:
    """API-Football integration class"""

    BASE_URL = "https://api-football-v1.p.rapidapi.com/v3"

    def __init__(self, api_key: str = API_FOOTBALL_KEY):
        self.api_key = api_key
        self.headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": API_FOOTBALL_HOST,
        }

    def is_available(self) -> bool:
        return self.api_key not in ("YOUR_API_KEY_HERE", "", None)

    def _make_request(self, endpoint: str, params: dict = None, cache_ttl: int = 0) -> dict:
        """Make API request with optional caching."""
        if cache_ttl > 0:
            key = _cache.make_key(f"apifb/{endpoint}", params)
            cached = _cache.get(key, cache_ttl)
            if cached is not None:
                return cached

        url = f"{self.BASE_URL}/{endpoint}"
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            if cache_ttl > 0:
                _cache.set(key, data)
            return data
        except requests.exceptions.RequestException as e:
            print(f"  [API-Football error] {e}")
            return {}

    # ── standings ───────────────────────────────────────────────────────────

    def get_standings(self, league_id: int, season: int = 2025) -> List[TeamData]:
        data = self._make_request(
            "standings",
            {"league": league_id, "season": season},
            cache_ttl=ResponseCache.TTL_STANDINGS,
        )

        teams = []
        if data.get("response"):
            standings = data["response"][0]["league"]["standings"][0]
            for td in standings:
                team = td["team"]
                a = td["all"]
                h = td["home"]
                w = td["away"]
                teams.append(TeamData(
                    id=team["id"],
                    name=normalize_team_name(team["name"]),
                    logo=team.get("logo", ""),
                    games_played=a["played"],
                    wins=a["win"],
                    draws=a["draw"],
                    losses=a["lose"],
                    goals_for=a["goals"]["for"],
                    goals_against=a["goals"]["against"],
                    home_wins=h["win"],
                    home_draws=h["draw"],
                    home_losses=h["lose"],
                    home_goals_for=h["goals"]["for"],
                    home_goals_against=h["goals"]["against"],
                    away_wins=w["win"],
                    away_draws=w["draw"],
                    away_losses=w["lose"],
                    away_goals_for=w["goals"]["for"],
                    away_goals_against=w["goals"]["against"],
                    form=td.get("form", ""),
                    clean_sheets=0,
                    failed_to_score=0,
                ))
        return teams

    # ── fixtures ────────────────────────────────────────────────────────────

    def get_fixtures(self, league_id: int, next_n: int = 10) -> List[FixtureData]:
        data = self._make_request(
            "fixtures",
            {"league": league_id, "next": next_n},
            cache_ttl=ResponseCache.TTL_FIXTURES,
        )

        fixtures = []
        if data.get("response"):
            for fix in data["response"]:
                fixtures.append(FixtureData(
                    id=fix["fixture"]["id"],
                    home_team=normalize_team_name(fix["teams"]["home"]["name"]),
                    away_team=normalize_team_name(fix["teams"]["away"]["name"]),
                    date=datetime.fromisoformat(fix["fixture"]["date"].replace("Z", "+00:00")),
                    venue=(fix["fixture"]["venue"] or {}).get("name", ""),
                    league=fix["league"]["name"],
                    round=fix["league"]["round"],
                    status=fix["fixture"]["status"]["short"],
                ))
        return fixtures

    # ── head-to-head (bug fixed: compare IDs not names) ────────────────────

    def get_head_to_head(self, team1_id: int, team2_id: int, last_n: int = 10) -> dict:
        data = self._make_request(
            "fixtures/headtohead",
            {"h2h": f"{team1_id}-{team2_id}", "last": last_n},
            cache_ttl=ResponseCache.TTL_H2H,
        )

        if not data.get("response"):
            return {}

        h2h = {"matches": [], "team1_wins": 0, "team2_wins": 0, "draws": 0,
               "team1_goals": 0, "team2_goals": 0, "total_goals": 0}

        for match in data["response"]:
            home_goals = match["goals"]["home"] or 0
            away_goals = match["goals"]["away"] or 0
            home_id = match["teams"]["home"]["id"]
            home_name = match["teams"]["home"]["name"]
            away_name = match["teams"]["away"]["name"]

            h2h["matches"].append({
                "date": match["fixture"]["date"],
                "home": home_name,
                "away": away_name,
                "score": f"{home_goals}-{away_goals}",
            })

            h2h["total_goals"] += home_goals + away_goals

            # Track goals per side (relative to team1 / team2)
            if home_id == team1_id:
                t1_goals, t2_goals = home_goals, away_goals
            else:
                t1_goals, t2_goals = away_goals, home_goals

            h2h["team1_goals"] += t1_goals
            h2h["team2_goals"] += t2_goals

            if t1_goals > t2_goals:
                h2h["team1_wins"] += 1
            elif t2_goals > t1_goals:
                h2h["team2_wins"] += 1
            else:
                h2h["draws"] += 1

        return h2h

    # ── historical results ─────────────────────────────────────────────────

    def get_past_results(self, league_id: int, season: int = 2025) -> List[MatchResult]:
        data = self._make_request(
            "fixtures",
            {"league": league_id, "season": season, "status": "FT"},
            cache_ttl=ResponseCache.TTL_RESULTS,
        )

        results = []
        if data.get("response"):
            for fix in data["response"]:
                results.append(MatchResult(
                    date=fix["fixture"]["date"],
                    home_team=normalize_team_name(fix["teams"]["home"]["name"]),
                    away_team=normalize_team_name(fix["teams"]["away"]["name"]),
                    home_goals=fix["goals"]["home"] or 0,
                    away_goals=fix["goals"]["away"] or 0,
                ))
        return results

    # ── team detailed statistics ────────────────────────────────────────────

    def get_team_statistics(self, team_id: int, league_id: int, season: int = 2025) -> Optional[TeamExtendedStats]:
        """Fetch detailed team statistics (corners, cards, shots, etc.)."""
        data = self._make_request(
            "teams/statistics",
            {"team": team_id, "league": league_id, "season": season},
            cache_ttl=ResponseCache.TTL_STANDINGS,  # 1 hour cache
        )
        if not data.get("response"):
            return None

        r = data["response"]
        fixtures_played = r.get("fixtures", {}).get("played", {})
        gp = (fixtures_played.get("home", 0) or 0) + (fixtures_played.get("away", 0) or 0)
        if gp == 0:
            return None

        team_name = normalize_team_name(r.get("team", {}).get("name", "Unknown"))

        # Cards: { "0-15": {"yellow": {"total": N}, "red": {"total": N}}, ... }
        cards = r.get("cards", {})
        total_yellows = 0
        total_reds = 0
        for _, card_data in cards.items():
            if isinstance(card_data, dict):
                y = card_data.get("yellow", {})
                r_card = card_data.get("red", {})
                total_yellows += (y.get("total", 0) or 0)
                total_reds += (r_card.get("total", 0) or 0)

        return TeamExtendedStats(
            team_id=team_id,
            team_name=team_name,
            yellow_cards_avg=round(total_yellows / gp, 2) if gp > 0 else 0,
            red_cards_avg=round(total_reds / gp, 2) if gp > 0 else 0,
            games_played=gp,
        )

    def get_fixture_statistics(self, fixture_id: int) -> dict:
        """Get per-match statistics (corners, shots, etc.) for a played fixture."""
        data = self._make_request(
            "fixtures/statistics",
            {"fixture": fixture_id},
            cache_ttl=ResponseCache.TTL_RESULTS,
        )
        if not data.get("response"):
            return {}
        # Returns list of team stats [{team: {...}, statistics: [...]}, ...]
        result = {}
        for team_block in data["response"]:
            team_name = normalize_team_name(team_block.get("team", {}).get("name", ""))
            stats = {}
            for s in team_block.get("statistics", []):
                stats[s["type"]] = s["value"]
            result[team_name] = stats
        return result

    def get_team_extended_from_fixtures(self, team_id: int, team_name: str,
                                         league_id: int, season: int = 2025) -> Optional[TeamExtendedStats]:
        """Build extended stats by aggregating past fixture statistics.
        Uses cached past results to avoid extra API calls."""
        # Get finished fixtures for this league/season
        data = self._make_request(
            "fixtures",
            {"league": league_id, "season": season, "status": "FT", "last": 40},
            cache_ttl=ResponseCache.TTL_RESULTS,
        )
        if not data.get("response"):
            return None

        # Filter to fixtures involving this team
        team_fixtures = []
        for fix in data["response"]:
            home_id = fix["teams"]["home"]["id"]
            away_id = fix["teams"]["away"]["id"]
            if team_id in (home_id, away_id):
                team_fixtures.append(fix["fixture"]["id"])

        if not team_fixtures:
            return None

        # Aggregate stats from fixture statistics (limit to save API calls)
        corners_list = []
        yellows_list = []
        shots_ot_list = []
        shots_total_list = []
        fouls_list = []
        possession_list = []

        for fid in team_fixtures[:10]:  # Last 10 matches max
            stats = self.get_fixture_statistics(fid)
            # Find our team's stats
            for tname, tstat in stats.items():
                if tname.lower() == team_name.lower() or team_name.lower() in tname.lower():
                    c = tstat.get("Corner Kicks")
                    if c is not None:
                        corners_list.append(int(c) if c else 0)
                    y = tstat.get("Yellow Cards")
                    if y is not None:
                        yellows_list.append(int(y) if y else 0)
                    sot = tstat.get("Shots on Goal")
                    if sot is not None:
                        shots_ot_list.append(int(sot) if sot else 0)
                    st = tstat.get("Total Shots")
                    if st is not None:
                        shots_total_list.append(int(st) if st else 0)
                    f = tstat.get("Fouls")
                    if f is not None:
                        fouls_list.append(int(f) if f else 0)
                    p = tstat.get("Ball Possession")
                    if p is not None:
                        pval = str(p).replace("%", "")
                        try:
                            possession_list.append(float(pval))
                        except ValueError:
                            pass
                    break

        gp = max(len(corners_list), len(yellows_list), 1)

        return TeamExtendedStats(
            team_id=team_id,
            team_name=team_name,
            corners_for_avg=round(sum(corners_list) / len(corners_list), 2) if corners_list else 0,
            yellow_cards_avg=round(sum(yellows_list) / len(yellows_list), 2) if yellows_list else 0,
            shots_on_target_avg=round(sum(shots_ot_list) / len(shots_ot_list), 2) if shots_ot_list else 0,
            shots_total_avg=round(sum(shots_total_list) / len(shots_total_list), 2) if shots_total_list else 0,
            fouls_committed_avg=round(sum(fouls_list) / len(fouls_list), 2) if fouls_list else 0,
            possession_avg=round(sum(possession_list) / len(possession_list), 1) if possession_list else 50.0,
            games_played=gp,
        )

    # ── team id map ─────────────────────────────────────────────────────────

    def get_team_id_map(self, league_id: int, season: int = 2025) -> Dict[str, int]:
        teams = self.get_standings(league_id, season)
        return {t.name: t.id for t in teams}

# ═══════════════════════════════════════════════════════════════════════════════
# FOOTBALL-DATA.ORG INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════

class FootballDataOrg:
    BASE_URL = "https://api.football-data.org/v4"

    def __init__(self, api_key: str = FOOTBALL_DATA_KEY):
        self.api_key = api_key
        self.headers = {"X-Auth-Token": api_key}

    def is_available(self) -> bool:
        return self.api_key not in ("YOUR_API_KEY_HERE", "", None)

    def _make_request(self, endpoint: str, cache_ttl: int = 0) -> dict:
        if cache_ttl > 0:
            key = _cache.make_key(f"fdo/{endpoint}")
            cached = _cache.get(key, cache_ttl)
            if cached is not None:
                return cached

        url = f"{self.BASE_URL}/{endpoint}"
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            if cache_ttl > 0:
                _cache.set(key, data)
            return data
        except requests.exceptions.RequestException as e:
            print(f"  [Football-Data.org error] {e}")
            return {}

    def get_matches(self, competition: str = "PD", date_from: str = None, date_to: str = None) -> List[dict]:
        endpoint = f"competitions/{competition}/matches"
        if date_from and date_to:
            endpoint += f"?dateFrom={date_from}&dateTo={date_to}"
        data = self._make_request(endpoint, cache_ttl=ResponseCache.TTL_FIXTURES)
        return data.get("matches", [])

    def get_standings(self, competition: str = "PD") -> List[dict]:
        data = self._make_request(
            f"competitions/{competition}/standings",
            cache_ttl=ResponseCache.TTL_STANDINGS,
        )
        if data.get("standings"):
            return data["standings"][0]["table"]
        return []

    def get_standings_as_team_data(self, competition: str = "PD") -> List[TeamData]:
        """Get standings and convert to TeamData objects for the predictor."""
        raw = self.get_standings(competition)
        teams = []
        for entry in raw:
            t = entry.get("team", {})
            gp = entry.get("playedGames", 0)
            w = entry.get("won", 0)
            d = entry.get("draw", 0)
            l = entry.get("lost", 0)
            gf = entry.get("goalsFor", 0)
            ga = entry.get("goalsAgainst", 0)
            form_str = entry.get("form", "") or ""
            # football-data.org form uses commas: "W,W,D,L,W"
            form_str = form_str.replace(",", "")

            # This API doesn't split home/away, so estimate 50/50
            hw = round(w * 0.6)
            hd = round(d * 0.5)
            hl = l - round(l * 0.5)
            aw = w - hw
            ad = d - hd
            al = l - hl
            hgf = round(gf * 0.55)
            hga = round(ga * 0.45)
            agf = gf - hgf
            aga = ga - hga

            teams.append(TeamData(
                id=t.get("id", 0),
                name=normalize_team_name(t.get("name", "Unknown")),
                logo=t.get("crest", ""),
                games_played=gp,
                wins=w, draws=d, losses=l,
                goals_for=gf, goals_against=ga,
                home_wins=hw, home_draws=hd, home_losses=hl,
                home_goals_for=hgf, home_goals_against=hga,
                away_wins=aw, away_draws=ad, away_losses=al,
                away_goals_for=agf, away_goals_against=aga,
                form=form_str,
                clean_sheets=0, failed_to_score=0,
            ))
        return teams

# ═══════════════════════════════════════════════════════════════════════════════
# ODDS API INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════

class OddsAPI:
    BASE_URL = "https://api.the-odds-api.com/v4"

    SPORT_KEYS = {
        "La Liga": "soccer_spain_la_liga",
        "Premier League": "soccer_epl",
        "Serie A": "soccer_italy_serie_a",
        "Bundesliga": "soccer_germany_bundesliga",
        "Ligue 1": "soccer_france_ligue_one",
        "Champions League": "soccer_uefa_champs_league",
        "Europa League": "soccer_uefa_europa_league",
        "Eredivisie": "soccer_netherlands_eredivisie",
        "Primeira Liga": "soccer_portugal_primeira_liga",
        "Championship": "soccer_efl_champ",
        "MLS": "soccer_usa_mls",
        "Brasileirao": "soccer_brazil_campeonato",
    }

    def __init__(self, api_key: str = ODDS_API_KEY):
        self.api_key = api_key

    def is_available(self) -> bool:
        return self.api_key not in ("YOUR_API_KEY_HERE", "", None)

    def get_odds(self, sport: str = "soccer_spain_la_liga", regions: str = "eu", markets: str = "h2h") -> List[dict]:
        key = _cache.make_key(f"odds/{sport}", {"regions": regions, "markets": markets})
        cached = _cache.get(key, ResponseCache.TTL_ODDS)
        if cached is not None:
            return cached

        url = f"{self.BASE_URL}/sports/{sport}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal",
        }
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            _cache.set(key, data)
            return data
        except requests.exceptions.RequestException as e:
            print(f"  [Odds API error] {e}")
            return []

    def get_match_odds(self, home_team: str, away_team: str, sport: str = "soccer_spain_la_liga") -> dict:
        all_odds = self.get_odds(sport)

        for match in all_odds:
            if (home_team.lower() in match["home_team"].lower() and
                    away_team.lower() in match["away_team"].lower()):

                home_odds, draw_odds, away_odds = [], [], []

                for bookmaker in match.get("bookmakers", []):
                    for market in bookmaker.get("markets", []):
                        if market["key"] == "h2h":
                            for outcome in market["outcomes"]:
                                if outcome["name"] == match["home_team"]:
                                    home_odds.append(outcome["price"])
                                elif outcome["name"] == match["away_team"]:
                                    away_odds.append(outcome["price"])
                                else:
                                    draw_odds.append(outcome["price"])

                return {
                    "home_team": match["home_team"],
                    "away_team": match["away_team"],
                    "commence_time": match["commence_time"],
                    "home_odds": sum(home_odds) / len(home_odds) if home_odds else 0,
                    "draw_odds": sum(draw_odds) / len(draw_odds) if draw_odds else 0,
                    "away_odds": sum(away_odds) / len(away_odds) if away_odds else 0,
                }
        return {}

# ═══════════════════════════════════════════════════════════════════════════════
# DATA PROCESSOR
# ═══════════════════════════════════════════════════════════════════════════════

class DataProcessor:
    """Process API data into format suitable for prediction engine."""

    @staticmethod
    def calculate_league_avg_goals(results: List[MatchResult]) -> float:
        if not results:
            return 2.65
        total = sum(r.home_goals + r.away_goals for r in results)
        return total / len(results)

    @staticmethod
    def calculate_form_with_decay(form_string: str, decay_factor: float = 0.85) -> float:
        """Exponentially weighted form rating (most recent match weighted highest)."""
        if not form_string:
            return 0.5
        recent = form_string[-5:]  # last 5 matches
        points = 0.0
        weight_sum = 0.0
        for i, result in enumerate(reversed(recent)):
            w = decay_factor ** i  # i=0 is most recent → weight=1.0
            if result == "W":
                points += 3 * w
            elif result == "D":
                points += 1 * w
            weight_sum += 3 * w  # max possible per match
        return points / weight_sum if weight_sum > 0 else 0.5

    @staticmethod
    def odds_to_implied_probabilities(home_odds: float, draw_odds: float, away_odds: float) -> Tuple[float, float, float]:
        """Convert decimal odds to implied probs, removing the overround."""
        if home_odds <= 0 or draw_odds <= 0 or away_odds <= 0:
            return (0.0, 0.0, 0.0)
        raw_h = 1.0 / home_odds
        raw_d = 1.0 / draw_odds
        raw_a = 1.0 / away_odds
        total = raw_h + raw_d + raw_a
        return (raw_h / total, raw_d / total, raw_a / total)

    @staticmethod
    def _shrink_to_league(raw: float, baseline: float, sample_games: int,
                          min_games: int = 10) -> float:
        """Pull noisy early-season rates toward league average (1.0 for strengths)."""
        if sample_games <= 0:
            return baseline
        w = min(1.0, sample_games / max(min_games, 1))
        return w * raw + (1.0 - w) * baseline

    @staticmethod
    def build_team_stats(team_data: TeamData, league_avg_goals: float, form_decay: float = 0.85) -> dict:
        """Build prediction-engine stats from API TeamData (overall + home/away splits)."""
        gp = team_data.games_played or 1
        hg = team_data.home_wins + team_data.home_draws + team_data.home_losses
        ag = team_data.away_wins + team_data.away_draws + team_data.away_losses
        hg = hg if hg > 0 else 1
        ag = ag if ag > 0 else 1

        half_avg = league_avg_goals / 2 if league_avg_goals > 0 else 1.325

        avg_scored = team_data.goals_for / gp
        avg_conceded = team_data.goals_against / gp
        attack_strength = avg_scored / half_avg
        defense_strength = avg_conceded / half_avg

        # Home / away goal rates vs league half-average (for Dixon–Coles matchups)
        raw_ha = (team_data.home_goals_for / hg) / half_avg
        raw_hd = (team_data.home_goals_against / hg) / half_avg
        raw_aa = (team_data.away_goals_for / ag) / half_avg
        raw_ad = (team_data.away_goals_against / ag) / half_avg

        home_attack = DataProcessor._shrink_to_league(raw_ha, 1.0, hg, min_games=10)
        home_defense = DataProcessor._shrink_to_league(raw_hd, 1.0, hg, min_games=10)
        away_attack = DataProcessor._shrink_to_league(raw_aa, 1.0, ag, min_games=10)
        away_defense = DataProcessor._shrink_to_league(raw_ad, 1.0, ag, min_games=10)

        home_ppg = (team_data.home_wins * 3 + team_data.home_draws) / hg
        away_ppg = (team_data.away_wins * 3 + team_data.away_draws) / ag
        home_advantage = min(max(home_ppg / away_ppg if away_ppg > 0 else 1.15, 1.0), 1.3)

        form_rating = DataProcessor.calculate_form_with_decay(team_data.form, form_decay)

        clean_sheet_pct = team_data.clean_sheets / gp if gp > 0 else 0.25

        # BTTS estimation: proportion of games where both teams scored
        btts_pct = 1.0 - clean_sheet_pct - (team_data.failed_to_score / gp if gp > 0 else 0.15)
        btts_pct = min(max(btts_pct, 0.3), 0.85)

        return {
            "name": team_data.name,
            "id": team_data.id,
            "games_played": gp,
            "attack_strength": round(attack_strength, 3),
            "defense_strength": round(defense_strength, 3),
            "home_advantage": round(home_advantage, 3),
            "form_rating": round(form_rating, 3),
            "avg_goals_scored": round(avg_scored, 3),
            "avg_goals_conceded": round(avg_conceded, 3),
            "clean_sheet_pct": round(clean_sheet_pct, 3),
            "btts_pct": round(btts_pct, 3),
            "home_attack": round(home_attack, 3),
            "away_attack": round(away_attack, 3),
            "home_defense": round(home_defense, 3),
            "away_defense": round(away_defense, 3),
        }

# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY
# ═══════════════════════════════════════════════════════════════════════════════

def check_api_availability() -> Dict[str, bool]:
    return {
        "api_football": APIFootball().is_available(),
        "football_data": FootballDataOrg().is_available(),
        "odds_api": OddsAPI().is_available(),
    }

def clear_cache():
    _cache.clear()
    print("Cache cleared.")


if __name__ == "__main__":
    avail = check_api_availability()
    print("API availability:")
    for name, ok in avail.items():
        status = "configured" if ok else "NOT configured"
        print(f"  {name}: {status}")
