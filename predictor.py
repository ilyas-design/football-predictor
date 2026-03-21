#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                        FOOTBALL MATCH PREDICTOR                              ║
║                    Professional Betting Analysis Tool                        ║
╚══════════════════════════════════════════════════════════════════════════════╝

Uses Dixon-Coles model with live API data, H2H adjustment, odds calibration,
recency-weighted form, and backtesting.

Usage:
    python predictor.py                              # Interactive mode
    python predictor.py --match "Team1 vs Team2"
    python predictor.py --league "Premier League"
    python predictor.py --fixtures
    python predictor.py --backtest "La Liga"
    python predictor.py --demo
"""

import math
import json
import os
import argparse
from collections import defaultdict
from datetime import datetime
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional

try:
    from scipy.optimize import minimize_scalar
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from api_integration import (
    APIFootball, OddsAPI, FootballDataOrg, DataProcessor,
    ResponseCache, LEAGUES, TeamData, TeamExtendedStats, FixtureData, MatchResult,
    CumulativeTeam,
    get_available_leagues, check_api_availability, clear_cache,
    FOOTBALL_DATA_KEY,
)

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

VERSION = "2.2.0"
SCRIPT_NAME = "FOOTBALL PREDICTOR PRO"

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'
    GOLD = '\033[33m'

# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TeamStats:
    name: str
    attack_strength: float
    defense_strength: float
    home_advantage: float
    form_rating: float
    avg_goals_scored: float
    avg_goals_conceded: float
    clean_sheet_pct: float
    btts_pct: float
    team_id: int = 0
    games_played: int = 20
    # Home/away splits (vs league half-average); 0 = use attack_strength/defense_strength
    home_attack: float = 0.0
    away_attack: float = 0.0
    home_defense: float = 0.0
    away_defense: float = 0.0

def _split_team_ratings(t: TeamStats) -> Tuple[float, float, float, float]:
    ha = t.home_attack if t.home_attack > 1e-9 else t.attack_strength
    aa = t.away_attack if t.away_attack > 1e-9 else t.attack_strength
    hd = t.home_defense if t.home_defense > 1e-9 else t.defense_strength
    ad = t.away_defense if t.away_defense > 1e-9 else t.defense_strength
    return ha, aa, hd, ad

def _clip_mean(xs: List[float], lo: float, hi: float) -> float:
    if not xs:
        return 1.0
    m = sum(xs) / len(xs)
    return max(lo, min(hi, m))

def _stats_dict_to_team_stats(info: dict) -> TeamStats:
    return TeamStats(
        name=info["name"],
        attack_strength=info["attack_strength"],
        defense_strength=info["defense_strength"],
        home_advantage=info["home_advantage"],
        form_rating=info["form_rating"],
        avg_goals_scored=info["avg_goals_scored"],
        avg_goals_conceded=info["avg_goals_conceded"],
        clean_sheet_pct=info["clean_sheet_pct"],
        btts_pct=info["btts_pct"],
        team_id=info.get("id", 0),
        games_played=info.get("games_played", 1),
        home_attack=info.get("home_attack", 0.0),
        away_attack=info.get("away_attack", 0.0),
        home_defense=info.get("home_defense", 0.0),
        away_defense=info.get("away_defense", 0.0),
    )

@dataclass
class MatchPrediction:
    home_team: str
    away_team: str
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    over_25_prob: float
    under_25_prob: float
    btts_yes_prob: float
    btts_no_prob: float
    exact_scores: List[Tuple[str, float]]
    expected_home_goals: float
    expected_away_goals: float
    best_bet: dict
    confidence: float
    data_source: str = "live"
    # Extended markets
    over_15_prob: float = 0.0
    under_15_prob: float = 0.0
    over_35_prob: float = 0.0
    under_35_prob: float = 0.0
    home_over_05_prob: float = 0.0
    away_over_05_prob: float = 0.0
    home_over_15_prob: float = 0.0
    away_over_15_prob: float = 0.0
    expected_corners: float = 0.0
    home_corners: float = 0.0
    away_corners: float = 0.0
    over_85_corners_prob: float = 0.0
    over_95_corners_prob: float = 0.0
    over_105_corners_prob: float = 0.0
    expected_cards: float = 0.0
    home_cards: float = 0.0
    away_cards: float = 0.0
    over_35_cards_prob: float = 0.0
    over_45_cards_prob: float = 0.0
    over_55_cards_prob: float = 0.0
    expected_shots_on_target: float = 0.0
    home_shots_on_target: float = 0.0
    away_shots_on_target: float = 0.0
    first_half_goals: float = 0.0
    second_half_goals: float = 0.0

# ═══════════════════════════════════════════════════════════════════════════════
# FALLBACK DATA (used when no API keys are configured)
# ═══════════════════════════════════════════════════════════════════════════════

FALLBACK_LEAGUE_AVG = 2.65

FALLBACK_TEAMS = {
    "Barcelona": TeamStats("Barcelona", 1.45, 0.75, 1.15, 0.85, 2.1, 0.9, 0.42, 0.58),
    "Real Madrid": TeamStats("Real Madrid", 1.40, 0.80, 1.12, 0.82, 2.0, 0.95, 0.38, 0.62),
    "Atletico Madrid": TeamStats("Atletico Madrid", 1.15, 0.70, 1.10, 0.78, 1.6, 0.85, 0.45, 0.52),
    "Athletic Bilbao": TeamStats("Athletic Bilbao", 1.10, 0.85, 1.08, 0.75, 1.5, 1.0, 0.35, 0.60),
    "Villarreal": TeamStats("Villarreal", 1.05, 0.90, 1.05, 0.70, 1.4, 1.05, 0.32, 0.62),
    "Real Sociedad": TeamStats("Real Sociedad", 1.08, 0.88, 1.06, 0.72, 1.45, 1.0, 0.33, 0.65),
    "Real Betis": TeamStats("Real Betis", 1.00, 0.95, 1.05, 0.68, 1.35, 1.1, 0.30, 0.58),
    "Sevilla": TeamStats("Sevilla", 0.95, 0.92, 1.08, 0.65, 1.3, 1.05, 0.28, 0.60),
    "Valencia": TeamStats("Valencia", 0.92, 1.00, 1.05, 0.60, 1.25, 1.15, 0.25, 0.62),
    "Celta Vigo": TeamStats("Celta Vigo", 1.02, 1.05, 1.03, 0.62, 1.4, 1.2, 0.22, 0.70),
    "Girona": TeamStats("Girona", 1.12, 0.95, 1.02, 0.70, 1.5, 1.1, 0.28, 0.65),
    "Osasuna": TeamStats("Osasuna", 0.88, 0.92, 1.08, 0.58, 1.2, 1.05, 0.30, 0.55),
    "Mallorca": TeamStats("Mallorca", 0.85, 0.88, 1.06, 0.55, 1.15, 1.0, 0.32, 0.52),
    "Rayo Vallecano": TeamStats("Rayo Vallecano", 0.90, 0.98, 1.10, 0.52, 1.2, 1.1, 0.25, 0.58),
    "Getafe": TeamStats("Getafe", 0.75, 0.82, 1.12, 0.50, 1.0, 0.95, 0.35, 0.48),
    "Alaves": TeamStats("Alaves", 0.82, 1.02, 1.05, 0.48, 1.1, 1.15, 0.22, 0.55),
    "Espanyol": TeamStats("Espanyol", 0.80, 1.05, 1.08, 0.45, 1.05, 1.2, 0.20, 0.58),
    "Real Oviedo": TeamStats("Real Oviedo", 0.78, 1.08, 1.05, 0.42, 1.0, 1.25, 0.18, 0.55),
    "Levante": TeamStats("Levante", 0.85, 1.00, 1.05, 0.50, 1.15, 1.15, 0.22, 0.60),
    "Elche": TeamStats("Elche", 0.72, 1.12, 1.02, 0.38, 0.95, 1.3, 0.15, 0.52),
}

# ═══════════════════════════════════════════════════════════════════════════════
# LIVE DATA PROVIDER
# ═══════════════════════════════════════════════════════════════════════════════

class LiveDataProvider:
    """Fetches real data from APIs and converts to TeamStats."""

    def __init__(self, league_name: str = "La Liga"):
        self.league_name = league_name
        self.league_cfg = LEAGUES.get(league_name, LEAGUES["La Liga"])
        self.league_id = self.league_cfg["api_football_id"]
        self.fdo_code = self.league_cfg.get("football_data_code")

        self.api = APIFootball()
        self.fdo = FootballDataOrg()
        self.odds = OddsAPI()

        self.team_stats: Dict[str, TeamStats] = {}
        self.team_id_map: Dict[str, int] = {}
        self.extended_stats_cache: Dict[str, TeamExtendedStats] = {}
        self.league_avg_goals: float = FALLBACK_LEAGUE_AVG
        self.is_live = False

    def _ingest_teams(self, teams_raw: List[TeamData], source: str):
        """Convert raw TeamData list into team_stats dict."""
        total_goals = sum(t.goals_for + t.goals_against for t in teams_raw)
        total_games = sum(t.games_played for t in teams_raw)
        if total_games > 0:
            self.league_avg_goals = total_goals / total_games

        for td in teams_raw:
            info = DataProcessor.build_team_stats(td, self.league_avg_goals)
            ts = TeamStats(
                name=info["name"],
                attack_strength=info["attack_strength"],
                defense_strength=info["defense_strength"],
                home_advantage=info["home_advantage"],
                form_rating=info["form_rating"],
                avg_goals_scored=info["avg_goals_scored"],
                avg_goals_conceded=info["avg_goals_conceded"],
                clean_sheet_pct=info["clean_sheet_pct"],
                btts_pct=info["btts_pct"],
                team_id=info["id"],
                games_played=info.get("games_played", td.games_played),
                home_attack=info.get("home_attack", 0.0),
                away_attack=info.get("away_attack", 0.0),
                home_defense=info.get("home_defense", 0.0),
                away_defense=info.get("away_defense", 0.0),
            )
            self.team_stats[td.name] = ts
            self.team_id_map[td.name] = td.id

        self.is_live = True
        print(f"  Loaded {len(self.team_stats)} teams via {source} (avg {self.league_avg_goals:.2f} goals/game)")

    def _apply_opponent_strength_adjustment(self) -> None:
        """SoS-adjust home/away ratings using finished fixtures (reduces schedule bias)."""
        if not self.api.is_available() or not self.team_stats:
            return
        results = self.api.get_past_results(self.league_id)
        if len(results) < 10:
            return
        ha_sos: Dict[str, List[float]] = defaultdict(list)
        aa_sos: Dict[str, List[float]] = defaultdict(list)
        hd_sos: Dict[str, List[float]] = defaultdict(list)
        ad_sos: Dict[str, List[float]] = defaultdict(list)
        clip_lo, clip_hi = 0.72, 1.38
        for r in results:
            ht = self.team_stats.get(r.home_team)
            at = self.team_stats.get(r.away_team)
            if ht is None or at is None:
                continue
            h_ha, _, h_hd, _ = _split_team_ratings(ht)
            _, a_aa, _, a_ad = _split_team_ratings(at)
            ha_sos[r.home_team].append(a_ad)
            hd_sos[r.home_team].append(a_aa)
            aa_sos[r.away_team].append(h_hd)
            ad_sos[r.away_team].append(h_ha)
        teams = list(self.team_stats.values())
        for ts in teams:
            name = ts.name
            ha = ts.home_attack if ts.home_attack > 1e-9 else ts.attack_strength
            aa = ts.away_attack if ts.away_attack > 1e-9 else ts.attack_strength
            hd = ts.home_defense if ts.home_defense > 1e-9 else ts.defense_strength
            ad = ts.away_defense if ts.away_defense > 1e-9 else ts.defense_strength
            if len(ha_sos[name]) >= 2:
                ha *= 1.0 / _clip_mean(ha_sos[name], clip_lo, clip_hi)
            if len(aa_sos[name]) >= 2:
                aa *= 1.0 / _clip_mean(aa_sos[name], clip_lo, clip_hi)
            if len(hd_sos[name]) >= 2:
                hd *= 1.0 / _clip_mean(hd_sos[name], clip_lo, clip_hi)
            if len(ad_sos[name]) >= 2:
                ad *= 1.0 / _clip_mean(ad_sos[name], clip_lo, clip_hi)
            ts.home_attack = ha
            ts.away_attack = aa
            ts.home_defense = hd
            ts.away_defense = ad
        for attr in ("home_attack", "away_attack", "home_defense", "away_defense"):
            fb = "attack_strength" if "attack" in attr else "defense_strength"
            vals = []
            for t in teams:
                v = getattr(t, attr)
                if v <= 1e-9:
                    v = getattr(t, fb)
                vals.append(v)
            m = sum(vals) / len(vals) if vals else 1.0
            if m < 1e-6:
                continue
            for t in teams:
                v = getattr(t, attr)
                if v <= 1e-9:
                    v = getattr(t, fb)
                setattr(t, attr, v / m)

    def load(self) -> bool:
        """Load league data. Tries API-Football first, then Football-Data.org."""
        # Try API-Football first
        if self.api.is_available():
            print(f"  Fetching {self.league_name} data from API-Football...")
            teams_raw = self.api.get_standings(self.league_id)
            if teams_raw:
                self._ingest_teams(teams_raw, "API-Football")
                self._apply_opponent_strength_adjustment()
                return True
            print(f"  API-Football failed, trying Football-Data.org...")

        # Fallback to Football-Data.org
        if self.fdo.is_available() and self.fdo_code:
            print(f"  Fetching {self.league_name} data from Football-Data.org...")
            teams_raw = self.fdo.get_standings_as_team_data(self.fdo_code)
            if teams_raw:
                self._ingest_teams(teams_raw, "Football-Data.org")
                self._apply_opponent_strength_adjustment()
                return True
            print(f"  Football-Data.org also failed.")

        return False

    def get_team(self, name: str) -> Optional[TeamStats]:
        db = self.team_stats if self.is_live else FALLBACK_TEAMS
        # Exact
        if name in db:
            return db[name]
        # Case-insensitive
        for k, v in db.items():
            if k.lower() == name.lower():
                return v
        # Partial
        matches = [k for k in db if name.lower() in k.lower()]
        if len(matches) == 1:
            return db[matches[0]]
        return None

    def fuzzy_search(self, name: str) -> List[str]:
        db = self.team_stats if self.is_live else FALLBACK_TEAMS
        return [k for k in db if name.lower() in k.lower()]

    def get_team_names(self) -> List[str]:
        db = self.team_stats if self.is_live else FALLBACK_TEAMS
        return sorted(db.keys())

    def get_extended_stats(self, team_name: str) -> Optional[TeamExtendedStats]:
        """Fetch real corners/cards/shots stats for a team (cached)."""
        if team_name in self.extended_stats_cache:
            return self.extended_stats_cache[team_name]

        if not self.api.is_available():
            return None

        team_id = self.team_id_map.get(team_name)
        if team_id is None:
            return None

        stats = self.api.get_team_extended_from_fixtures(
            team_id, team_name, self.league_id
        )
        if stats:
            self.extended_stats_cache[team_name] = stats
        return stats

    def get_h2h(self, team1: str, team2: str) -> dict:
        if not self.api.is_available():
            return {}
        id1 = self.team_id_map.get(team1)
        id2 = self.team_id_map.get(team2)
        if id1 is None or id2 is None:
            return {}
        return self.api.get_head_to_head(id1, id2)

    def get_match_odds(self, home: str, away: str) -> Tuple[float, float, float]:
        if not self.odds.is_available():
            return (0, 0, 0)
        sport_key = OddsAPI.SPORT_KEYS.get(self.league_name)
        if not sport_key:
            return (0, 0, 0)
        data = self.odds.get_match_odds(home, away, sport_key)
        if not data:
            return (0, 0, 0)
        return DataProcessor.odds_to_implied_probabilities(
            data["home_odds"], data["draw_odds"], data["away_odds"]
        )

    def get_upcoming_fixtures(self, n: int = 10) -> List[FixtureData]:
        if not self.api.is_available():
            return []
        return self.api.get_fixtures(self.league_id, n)

    def get_past_results(self) -> List[MatchResult]:
        if not self.api.is_available():
            return []
        return self.api.get_past_results(self.league_id)

# ═══════════════════════════════════════════════════════════════════════════════
# DIXON-COLES PREDICTION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class PredictionEngine:
    """Dixon-Coles model with H2H adjustment and odds calibration."""

    def __init__(self, league_avg_goals: float = FALLBACK_LEAGUE_AVG, rho: float = -0.13):
        self.league_avg = league_avg_goals
        self.rho = rho  # Dixon-Coles low-score correction parameter

    @staticmethod
    def _split_ratings(t: TeamStats) -> Tuple[float, float, float, float]:
        """Home/away attack & defense; fall back to overall strengths when unset (demo DB)."""
        return _split_team_ratings(t)

    # ── Poisson base ────────────────────────────────────────────────────────

    @staticmethod
    def poisson_pmf(lam: float, k: int) -> float:
        return (math.exp(-lam) * (lam ** k)) / math.factorial(k)

    # ── Dixon-Coles tau correction ──────────────────────────────────────────

    def dixon_coles_tau(self, hg: int, ag: int, home_xg: float, away_xg: float) -> float:
        """Adjustment factor for low-scoring outcomes."""
        rho = self.rho
        if hg == 0 and ag == 0:
            val = 1.0 - home_xg * away_xg * rho
        elif hg == 0 and ag == 1:
            val = 1.0 + home_xg * rho
        elif hg == 1 and ag == 0:
            val = 1.0 + away_xg * rho
        elif hg == 1 and ag == 1:
            val = 1.0 - rho
        else:
            return 1.0
        return max(val, 1e-10)

    # ── Fit rho from historical data ────────────────────────────────────────

    def fit_rho(self, results: List[MatchResult], team_stats: Dict[str, TeamStats]):
        """Estimate rho via maximum likelihood over past results."""
        if not HAS_SCIPY or len(results) < 30:
            return  # keep default

        def neg_log_likelihood(rho_candidate):
            self.rho = rho_candidate
            ll = 0.0
            count = 0
            for r in results:
                ht = team_stats.get(r.home_team)
                at = team_stats.get(r.away_team)
                if ht is None or at is None:
                    continue
                hxg, axg = self._raw_expected_goals(ht, at)
                p_h = self.poisson_pmf(hxg, r.home_goals) if r.home_goals <= 10 else 1e-10
                p_a = self.poisson_pmf(axg, r.away_goals) if r.away_goals <= 10 else 1e-10
                tau = self.dixon_coles_tau(r.home_goals, r.away_goals, hxg, axg)
                prob = p_h * p_a * tau
                if prob > 0:
                    ll += math.log(prob)
                    count += 1
            return -ll if count > 0 else 0

        result = minimize_scalar(neg_log_likelihood, bounds=(-1, 1), method="bounded")
        self.rho = result.x
        print(f"  Dixon-Coles rho fitted: {self.rho:.4f}")

    # ── Expected goals ──────────────────────────────────────────────────────

    def _raw_expected_goals(self, home: TeamStats, away: TeamStats) -> Tuple[float, float]:
        """Expected goals using home/away splits: home attack vs away defense, etc."""
        half = self.league_avg / 2
        form_mult_h = 0.8 + 0.4 * home.form_rating
        form_mult_a = 0.8 + 0.4 * away.form_rating

        h_ha, h_aa, h_hd, h_ad = self._split_ratings(home)
        a_ha, a_aa, a_hd, a_ad = self._split_ratings(away)

        home_xg = h_ha * a_ad * home.home_advantage * half * form_mult_h
        away_xg = a_aa * h_hd * (1.0 / home.home_advantage) * half * form_mult_a
        return home_xg, away_xg

    def calculate_expected_goals(self, home: TeamStats, away: TeamStats,
                                  h2h: dict = None) -> Tuple[float, float]:
        home_xg, away_xg = self._raw_expected_goals(home, away)

        # H2H adjustment
        if h2h and len(h2h.get("matches", [])) >= 3:
            home_xg, away_xg = self._adjust_xg_with_h2h(home_xg, away_xg, h2h, home.name)

        return round(home_xg, 3), round(away_xg, 3)

    def _adjust_xg_with_h2h(self, home_xg: float, away_xg: float,
                              h2h: dict, home_name: str) -> Tuple[float, float]:
        matches = h2h.get("matches", [])
        if not matches:
            return home_xg, away_xg

        h_goals, a_goals = 0, 0
        for m in matches:
            parts = m["score"].split("-")
            hg, ag = int(parts[0]), int(parts[1])
            if m["home"] == home_name:
                h_goals += hg
                a_goals += ag
            else:
                h_goals += ag
                a_goals += hg

        n = len(matches)
        h2h_home_avg = h_goals / n
        h2h_away_avg = a_goals / n

        # Slightly more H2H weight when more games; cap so we do not overfit tiny samples
        weight = min(0.22, 0.085 + 0.018 * max(0, n - 3)) if n >= 3 else 0.10

        adj_home = (1 - weight) * home_xg + weight * h2h_home_avg
        adj_away = (1 - weight) * away_xg + weight * h2h_away_avg
        return adj_home, adj_away

    # ── Score probability matrix (Dixon-Coles) ─────────────────────────────

    def calculate_score_probabilities(self, home_xg: float, away_xg: float,
                                       max_goals: int = 8) -> Dict[str, float]:
        scores = {}
        total = 0.0
        for hg in range(max_goals + 1):
            for ag in range(max_goals + 1):
                p = (self.poisson_pmf(home_xg, hg) *
                     self.poisson_pmf(away_xg, ag) *
                     self.dixon_coles_tau(hg, ag, home_xg, away_xg))
                scores[f"{hg}-{ag}"] = p
                total += p

        # Renormalize
        if total > 0:
            for k in scores:
                scores[k] /= total
        return scores

    # ── Market probabilities ────────────────────────────────────────────────

    def calculate_1x2(self, score_probs: Dict[str, float]) -> Tuple[float, float, float]:
        hw, d, aw = 0.0, 0.0, 0.0
        for score, prob in score_probs.items():
            h, a = map(int, score.split("-"))
            if h > a:
                hw += prob
            elif h == a:
                d += prob
            else:
                aw += prob
        t = hw + d + aw or 1
        return hw / t, d / t, aw / t

    def calculate_over_under(self, score_probs: Dict[str, float],
                              threshold: float = 2.5) -> Tuple[float, float]:
        over, under = 0.0, 0.0
        for score, prob in score_probs.items():
            h, a = map(int, score.split("-"))
            if h + a > threshold:
                over += prob
            else:
                under += prob
        t = over + under or 1
        return over / t, under / t

    def calculate_btts(self, home: TeamStats, away: TeamStats,
                        score_probs: Dict[str, float]) -> Tuple[float, float]:
        yes, no = 0.0, 0.0
        for score, prob in score_probs.items():
            h, a = map(int, score.split("-"))
            if h > 0 and a > 0:
                yes += prob
            else:
                no += prob
        # Blend with team historical BTTS (slightly more weight on the model grid)
        btts_factor = (home.btts_pct + away.btts_pct) / 2
        yes = yes * 0.72 + btts_factor * 0.28
        no = 1.0 - yes
        return yes, no

    def get_top_scores(self, score_probs: Dict[str, float], top_n: int = 5) -> List[Tuple[str, float]]:
        sorted_scores = sorted(score_probs.items(), key=lambda x: x[1], reverse=True)
        return [(s, p * 100) for s, p in sorted_scores[:top_n]]

    # ── Odds calibration ───────────────────────────────────────────────────

    @staticmethod
    def calibrate_with_odds(model_probs: Tuple[float, float, float],
                             odds_probs: Tuple[float, float, float],
                             base_model_weight: float = 0.58) -> Tuple[float, float, float]:
        """Blend model with de-vigged odds; lean more on odds when the model is very uncertain."""
        if sum(odds_probs) < 0.01:
            return model_probs
        m = model_probs
        p = [x for x in m if x > 1e-12]
        if p:
            ent = -sum(x * math.log(x) for x in p)
            # Uniform 1X2 ~ ln(3) ≈ 1.099; blend more to market when spread is flat
            if ent > 1.04:
                model_weight = 0.44
            elif ent < 0.72:
                model_weight = min(0.68, base_model_weight + 0.08)
            else:
                model_weight = base_model_weight
        else:
            model_weight = base_model_weight
        blended = tuple(model_weight * a + (1 - model_weight) * b
                        for a, b in zip(model_probs, odds_probs))
        t = sum(blended) or 1
        return tuple(b / t for b in blended)

    # ── Additional goal thresholds ───────────────────────────────────────

    def calculate_team_goals_probs(self, score_probs: Dict[str, float]) -> dict:
        """Calculate probability of each team scoring over/under thresholds."""
        home_over_05 = sum(p for s, p in score_probs.items() if int(s.split("-")[0]) >= 1)
        away_over_05 = sum(p for s, p in score_probs.items() if int(s.split("-")[1]) >= 1)
        home_over_15 = sum(p for s, p in score_probs.items() if int(s.split("-")[0]) >= 2)
        away_over_15 = sum(p for s, p in score_probs.items() if int(s.split("-")[1]) >= 2)
        return {
            "home_over_05": home_over_05,
            "away_over_05": away_over_05,
            "home_over_15": home_over_15,
            "away_over_15": away_over_15,
        }

    # ── Corners prediction ───────────────────────────────────────────────

    @staticmethod
    def _poisson_over(lam: float, threshold: float) -> float:
        """P(X > threshold) using Poisson CDF."""
        under = sum((math.exp(-lam) * lam**k) / math.factorial(k) for k in range(int(threshold) + 1))
        return 1.0 - under

    @staticmethod
    def predict_corners(home: TeamStats, away: TeamStats, home_xg: float, away_xg: float,
                        home_ext: Optional[TeamExtendedStats] = None,
                        away_ext: Optional[TeamExtendedStats] = None) -> dict:
        """Predict corners using real per-team averages when available,
        otherwise estimate from attack strength and xG."""

        if home_ext and home_ext.corners_for_avg > 0 and away_ext and away_ext.corners_for_avg > 0:
            # Use real data: each team's avg corners won, adjusted for home advantage
            home_corners = home_ext.corners_for_avg * 1.05  # slight home boost
            away_corners = away_ext.corners_for_avg * 0.95
        else:
            # Fallback: estimate from attack strength and xG
            LEAGUE_AVG_CORNERS = 10.2
            total_xg = home_xg + away_xg
            xg_ratio = total_xg / 2.65 if total_xg > 0 else 1.0
            total_est = LEAGUE_AVG_CORNERS * xg_ratio

            home_attack_factor = (home.attack_strength + (1 / max(away.defense_strength, 0.3))) / 2
            away_attack_factor = (away.attack_strength + (1 / max(home.defense_strength, 0.3))) / 2
            factor_sum = home_attack_factor + away_attack_factor
            home_corners = total_est * (home_attack_factor / factor_sum) * 1.08
            away_corners = total_est - home_corners

        home_corners = max(2.0, min(9.0, home_corners))
        away_corners = max(1.5, min(8.0, away_corners))
        total_corners = home_corners + away_corners

        return {
            "expected": round(total_corners, 1),
            "home": round(home_corners, 1),
            "away": round(away_corners, 1),
            "over_85": round(PredictionEngine._poisson_over(total_corners, 8.5) * 100, 1),
            "over_95": round(PredictionEngine._poisson_over(total_corners, 9.5) * 100, 1),
            "over_105": round(PredictionEngine._poisson_over(total_corners, 10.5) * 100, 1),
        }

    # ── Yellow cards prediction ──────────────────────────────────────────

    @staticmethod
    def predict_cards(home: TeamStats, away: TeamStats, home_xg: float, away_xg: float,
                      home_ext: Optional[TeamExtendedStats] = None,
                      away_ext: Optional[TeamExtendedStats] = None) -> dict:
        """Predict yellow cards using real per-team averages when available."""

        if home_ext and home_ext.yellow_cards_avg > 0 and away_ext and away_ext.yellow_cards_avg > 0:
            # Use real data
            home_cards = home_ext.yellow_cards_avg
            away_cards = away_ext.yellow_cards_avg * 1.05  # away teams get slightly more
        else:
            # Fallback: estimate from defense strength and form
            LEAGUE_AVG_CARDS = 4.2
            home_def_factor = max(home.defense_strength, 0.3)
            away_def_factor = max(away.defense_strength, 0.3)
            home_form_factor = 1.0 + 0.3 * (1.0 - home.form_rating)
            away_form_factor = 1.0 + 0.3 * (1.0 - away.form_rating)
            xg_diff = abs(home_xg - away_xg)
            competitiveness = 1.0 + 0.15 * max(0, 1.0 - xg_diff)

            home_cards = (LEAGUE_AVG_CARDS / 2) * home_def_factor * home_form_factor * competitiveness
            away_cards = (LEAGUE_AVG_CARDS / 2) * away_def_factor * away_form_factor * competitiveness * 1.08

        home_cards = max(1.0, min(5.0, home_cards))
        away_cards = max(1.0, min(5.0, away_cards))
        total_cards = home_cards + away_cards

        return {
            "expected": round(total_cards, 1),
            "home": round(home_cards, 1),
            "away": round(away_cards, 1),
            "over_35": round(PredictionEngine._poisson_over(total_cards, 3.5) * 100, 1),
            "over_45": round(PredictionEngine._poisson_over(total_cards, 4.5) * 100, 1),
            "over_55": round(PredictionEngine._poisson_over(total_cards, 5.5) * 100, 1),
        }

    # ── Shots on target prediction ───────────────────────────────────────

    @staticmethod
    def predict_shots_on_target(home: TeamStats, away: TeamStats, home_xg: float, away_xg: float,
                                 home_ext: Optional[TeamExtendedStats] = None,
                                 away_ext: Optional[TeamExtendedStats] = None) -> dict:
        """Predict shots on target using real data when available."""

        if home_ext and home_ext.shots_on_target_avg > 0 and away_ext and away_ext.shots_on_target_avg > 0:
            home_sot = home_ext.shots_on_target_avg
            away_sot = away_ext.shots_on_target_avg
        else:
            # Fallback: estimate from xG
            home_sot = home_xg / 0.11 * 0.55 * (0.7 + 0.3 * home.attack_strength)
            away_sot = away_xg / 0.11 * 0.55 * (0.7 + 0.3 * away.attack_strength)

        home_sot = max(1.5, min(9.0, home_sot))
        away_sot = max(1.0, min(8.0, away_sot))

        return {
            "expected": round(home_sot + away_sot, 1),
            "home": round(home_sot, 1),
            "away": round(away_sot, 1),
        }

    # ── Half-time goals split ────────────────────────────────────────────

    @staticmethod
    def predict_half_goals(home_xg: float, away_xg: float) -> dict:
        """Split expected goals into halves. ~42% of goals scored in first half."""
        total_xg = home_xg + away_xg
        first_half = total_xg * 0.42
        second_half = total_xg * 0.58
        return {
            "first_half": round(first_half, 2),
            "second_half": round(second_half, 2),
        }

    # ── Best bet ────────────────────────────────────────────────────────────

    def determine_best_bet(self, pred: dict) -> dict:
        bets = []

        if pred["home_win"] > 0.50:
            bets.append(("Home Win", pred["home_win"], "Match Outcome"))
        if pred["away_win"] > 0.50:
            bets.append(("Away Win", pred["away_win"], "Match Outcome"))
        if pred["draw"] > 0.32:
            bets.append(("Draw", pred["draw"], "Match Outcome"))

        if pred["over_25"] > 0.55:
            bets.append(("Over 2.5", pred["over_25"], "Total Goals"))
        if pred["under_25"] > 0.55:
            bets.append(("Under 2.5", pred["under_25"], "Total Goals"))

        if pred["btts_yes"] > 0.55:
            bets.append(("BTTS Yes", pred["btts_yes"], "Both Teams to Score"))
        if pred["btts_no"] > 0.55:
            bets.append(("BTTS No", pred["btts_no"], "Both Teams to Score"))

        hd = pred["home_win"] + pred["draw"]
        ad = pred["away_win"] + pred["draw"]
        if hd > 0.70:
            bets.append(("Home or Draw", hd, "Double Chance"))
        if ad > 0.70:
            bets.append(("Away or Draw", ad, "Double Chance"))

        if bets:
            best = max(bets, key=lambda x: x[1])
            return {"prediction": best[0], "confidence": best[1] * 100, "market": best[2]}
        return {"prediction": "No Strong Edge", "confidence": 0, "market": "N/A"}

    # ── Full prediction ─────────────────────────────────────────────────────

    def predict_match(self, home: TeamStats, away: TeamStats,
                       h2h: dict = None,
                       odds_probs: Tuple[float, float, float] = (0, 0, 0),
                       home_ext: Optional[TeamExtendedStats] = None,
                       away_ext: Optional[TeamExtendedStats] = None) -> MatchPrediction:

        home_xg, away_xg = self.calculate_expected_goals(home, away, h2h)
        score_probs = self.calculate_score_probabilities(home_xg, away_xg)

        hw, d, aw = self.calculate_1x2(score_probs)

        # Calibrate with market odds if available
        if sum(odds_probs) > 0.01:
            hw, d, aw = self.calibrate_with_odds((hw, d, aw), odds_probs)

        o25, u25 = self.calculate_over_under(score_probs)
        o15, u15 = self.calculate_over_under(score_probs, threshold=1.5)
        o35, u35 = self.calculate_over_under(score_probs, threshold=3.5)
        btts_y, btts_n = self.calculate_btts(home, away, score_probs)
        top_scores = self.get_top_scores(score_probs, 5)
        team_goals = self.calculate_team_goals_probs(score_probs)

        # Extended predictions (use real data when available)
        corners = self.predict_corners(home, away, home_xg, away_xg, home_ext, away_ext)
        cards = self.predict_cards(home, away, home_xg, away_xg, home_ext, away_ext)
        shots = self.predict_shots_on_target(home, away, home_xg, away_xg, home_ext, away_ext)
        halves = self.predict_half_goals(home_xg, away_xg)

        pred_dict = {
            "home_win": hw, "draw": d, "away_win": aw,
            "over_25": o25, "under_25": u25,
            "btts_yes": btts_y, "btts_no": btts_n,
        }
        best_bet = self.determine_best_bet(pred_dict)

        data_source = "live+odds" if sum(odds_probs) > 0.01 else "live" if h2h else "model"

        return MatchPrediction(
            home_team=home.name, away_team=away.name,
            home_win_prob=hw * 100, draw_prob=d * 100, away_win_prob=aw * 100,
            over_25_prob=o25 * 100, under_25_prob=u25 * 100,
            btts_yes_prob=btts_y * 100, btts_no_prob=btts_n * 100,
            exact_scores=top_scores,
            expected_home_goals=home_xg, expected_away_goals=away_xg,
            best_bet=best_bet, confidence=best_bet["confidence"],
            data_source=data_source,
            # Extended markets
            over_15_prob=o15 * 100, under_15_prob=u15 * 100,
            over_35_prob=o35 * 100, under_35_prob=u35 * 100,
            home_over_05_prob=team_goals["home_over_05"] * 100,
            away_over_05_prob=team_goals["away_over_05"] * 100,
            home_over_15_prob=team_goals["home_over_15"] * 100,
            away_over_15_prob=team_goals["away_over_15"] * 100,
            expected_corners=corners["expected"],
            home_corners=corners["home"],
            away_corners=corners["away"],
            over_85_corners_prob=corners["over_85"],
            over_95_corners_prob=corners["over_95"],
            over_105_corners_prob=corners["over_105"],
            expected_cards=cards["expected"],
            home_cards=cards["home"],
            away_cards=cards["away"],
            over_35_cards_prob=cards["over_35"],
            over_45_cards_prob=cards["over_45"],
            over_55_cards_prob=cards["over_55"],
            expected_shots_on_target=shots["expected"],
            home_shots_on_target=shots["home"],
            away_shots_on_target=shots["away"],
            first_half_goals=halves["first_half"],
            second_half_goals=halves["second_half"],
        )

# ═══════════════════════════════════════════════════════════════════════════════
# BACKTESTER
# ═══════════════════════════════════════════════════════════════════════════════

class Backtester:
    """Walk-forward backtesting: only uses data available before each match."""

    def __init__(self, engine: PredictionEngine, provider: LiveDataProvider):
        self.engine = engine
        self.provider = provider

    def run(self, min_matchday: int = 8) -> dict:
        """Backtest on completed results. Rebuilds each team's stats from *prior* games only."""
        results = self.provider.get_past_results()
        if not results:
            print(f"{Colors.RED}  No historical results available for backtesting.{Colors.END}")
            return {}

        results.sort(key=lambda r: r.date)

        correct_1x2 = 0
        total_tested = 0
        brier_sum = 0.0
        log_loss_sum = 0.0
        calibration_buckets: Dict[int, List[int]] = {i: [] for i in range(0, 101, 10)}

        states: Dict[str, CumulativeTeam] = {}
        completed = 0
        total_goals = 0
        saved_league_avg = self.engine.league_avg

        for r in results:
            ht_key, at_key = r.home_team, r.away_team
            if ht_key not in states:
                states[ht_key] = CumulativeTeam(
                    name=ht_key,
                    team_id=self.provider.team_id_map.get(ht_key, 0),
                )
            if at_key not in states:
                states[at_key] = CumulativeTeam(
                    name=at_key,
                    team_id=self.provider.team_id_map.get(at_key, 0),
                )

            ht_state = states[ht_key]
            at_state = states[at_key]

            if (ht_state.games_played() >= min_matchday and at_state.games_played() >= min_matchday):
                league_avg = total_goals / max(1, completed)
                league_avg = max(2.0, min(3.4, league_avg))

                info_h = DataProcessor.build_team_stats_from_cumulative(ht_state, league_avg)
                info_a = DataProcessor.build_team_stats_from_cumulative(at_state, league_avg)
                ts_h = _stats_dict_to_team_stats(info_h)
                ts_a = _stats_dict_to_team_stats(info_a)

                self.engine.league_avg = league_avg
                pred = self.engine.predict_match(ts_h, ts_a)
                self.engine.league_avg = saved_league_avg

                total_tested += 1

                if r.home_goals > r.away_goals:
                    actual = "H"
                    actual_vec = (1, 0, 0)
                elif r.home_goals == r.away_goals:
                    actual = "D"
                    actual_vec = (0, 1, 0)
                else:
                    actual = "A"
                    actual_vec = (0, 0, 1)

                probs = (pred.home_win_prob / 100, pred.draw_prob / 100, pred.away_win_prob / 100)

                predicted = max(zip(["H", "D", "A"], probs), key=lambda x: x[1])[0]
                if predicted == actual:
                    correct_1x2 += 1

                brier = sum((p - a) ** 2 for p, a in zip(probs, actual_vec))
                brier_sum += brier

                eps = 1e-10
                ll = -sum(a * math.log(max(p, eps)) for p, a in zip(probs, actual_vec))
                log_loss_sum += ll

                top_prob = max(probs) * 100
                bucket = int(top_prob // 10) * 10
                bucket = min(bucket, 100)
                calibration_buckets[bucket].append(1 if predicted == actual else 0)

            ht_state.add_home_result(r.home_goals, r.away_goals)
            at_state.add_away_result(r.home_goals, r.away_goals)
            total_goals += r.home_goals + r.away_goals
            completed += 1

        if total_tested == 0:
            print(f"{Colors.RED}  Not enough data for backtesting.{Colors.END}")
            return {}

        metrics = {
            "total_matches": total_tested,
            "correct_1x2": correct_1x2,
            "accuracy_pct": correct_1x2 / total_tested * 100,
            "brier_score": brier_sum / total_tested,
            "log_loss": log_loss_sum / total_tested,
            "calibration": {},
        }

        for bucket, outcomes in calibration_buckets.items():
            if outcomes:
                metrics["calibration"][bucket] = {
                    "count": len(outcomes),
                    "actual_pct": sum(outcomes) / len(outcomes) * 100,
                }

        return metrics

    def print_report(self, metrics: dict):
        if not metrics:
            return
        print(f"\n{Colors.CYAN}{'═' * 70}{Colors.END}")
        print(f"{Colors.BOLD}  BACKTEST REPORT — {self.provider.league_name}{Colors.END}")
        print(f"{Colors.CYAN}{'═' * 70}{Colors.END}")

        print(f"\n  Matches tested:  {metrics['total_matches']}")
        print(f"  {Colors.BLUE}(Walk-forward: stats from matches before each game only){Colors.END}")
        print(f"  1X2 Accuracy:    {Colors.GREEN}{metrics['accuracy_pct']:.1f}%{Colors.END} ({metrics['correct_1x2']}/{metrics['total_matches']})")
        print(f"  Brier Score:     {metrics['brier_score']:.4f}  (lower is better, baseline ~0.667)")
        print(f"  Log Loss:        {metrics['log_loss']:.4f}  (lower is better)")

        print(f"\n  {Colors.YELLOW}Calibration:{Colors.END}")
        print(f"  {'Bucket':>8}  {'Matches':>8}  {'Actual Hit%':>12}")
        print(f"  {'─' * 32}")
        for bucket in sorted(metrics["calibration"].keys()):
            info = metrics["calibration"][bucket]
            print(f"  {bucket:>5}-{bucket+9}%  {info['count']:>8}  {info['actual_pct']:>10.1f}%")

        print(f"\n{Colors.CYAN}{'═' * 70}{Colors.END}\n")

# ═══════════════════════════════════════════════════════════════════════════════
# DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

def print_header():
    print(f"\n{Colors.CYAN}{'═' * 70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.GOLD}   ⚽  {SCRIPT_NAME} v{VERSION}  ⚽{Colors.END}")
    print(f"{Colors.CYAN}{'═' * 70}{Colors.END}")
    print(f"{Colors.BLUE}   Dixon-Coles Model • Live Data • Odds Calibration{Colors.END}")
    print(f"{Colors.CYAN}{'═' * 70}{Colors.END}\n")

def print_prediction(prediction: MatchPrediction):
    print(f"\n{Colors.CYAN}{'═' * 70}{Colors.END}")
    print(f"{Colors.BOLD}  {prediction.home_team} vs {prediction.away_team}{Colors.END}")
    print(f"  Data source: {Colors.BLUE}{prediction.data_source}{Colors.END}")
    print(f"{Colors.CYAN}{'═' * 70}{Colors.END}")

    print(f"\n{Colors.GOLD}⭐ Best Bet Recommendation ⭐{Colors.END}")
    print(f"   Market:     {Colors.GREEN}{prediction.best_bet['market']}{Colors.END}")
    print(f"   Prediction: {Colors.GREEN}{prediction.best_bet['prediction']}{Colors.END}")
    print(f"   Confidence: {Colors.YELLOW}{prediction.best_bet['confidence']:.1f}%{Colors.END}")

    print(f"\n{Colors.YELLOW}📊 1X2 Match Outcome:{Colors.END}")
    print(f"   {prediction.home_team:20} Win  │ {prediction.home_win_prob:.1f}%")
    print(f"   {'Draw':20}      │ {prediction.draw_prob:.1f}%")
    print(f"   {prediction.away_team:20} Win  │ {prediction.away_win_prob:.1f}%")

    print(f"\n{Colors.YELLOW}📊 Over/Under 2.5 Goals:{Colors.END}")
    print(f"   Over 2.5:  {prediction.over_25_prob:.1f}%")
    print(f"   Under 2.5: {prediction.under_25_prob:.1f}%")

    print(f"\n{Colors.YELLOW}📊 Both Teams to Score:{Colors.END}")
    print(f"   Yes: {prediction.btts_yes_prob:.1f}%")
    print(f"   No:  {prediction.btts_no_prob:.1f}%")

    print(f"\n{Colors.YELLOW}📊 Expected Goals:{Colors.END}")
    print(f"   {prediction.home_team}: {prediction.expected_home_goals:.2f} xG")
    print(f"   {prediction.away_team}: {prediction.expected_away_goals:.2f} xG")

    print(f"\n{Colors.GREEN}📊 Exact Score Predictions:{Colors.END}")
    for score, conf in prediction.exact_scores:
        bar = '█' * int(conf * 2)
        print(f"   {score:5}  {conf:5.1f}% {Colors.CYAN}{bar}{Colors.END}")

    print(f"\n{Colors.CYAN}{'═' * 70}{Colors.END}")
    print(f"{Colors.GREEN}[Done]{Colors.END}\n")

def print_fixtures(fixtures: List[FixtureData]):
    print(f"\n{Colors.CYAN}{'═' * 70}{Colors.END}")
    print(f"{Colors.BOLD}  Upcoming Fixtures{Colors.END}")
    print(f"{Colors.CYAN}{'═' * 70}{Colors.END}")
    for i, f in enumerate(fixtures, 1):
        dt = f.date.strftime("%Y-%m-%d %H:%M") if f.date else "TBD"
        print(f"  {i:2}. {f.home_team:20} vs {f.away_team:20}  {dt}  ({f.round})")
    print(f"{Colors.CYAN}{'═' * 70}{Colors.END}\n")

def list_teams(provider: LiveDataProvider):
    names = provider.get_team_names()
    print(f"\n{Colors.CYAN}  Available Teams — {provider.league_name} ({len(names)}){Colors.END}")
    print(f"{Colors.CYAN}  {'─' * 40}{Colors.END}")
    for i, name in enumerate(names, 1):
        print(f"  {i:3}. {name}")
    print(f"{Colors.CYAN}  {'─' * 40}{Colors.END}\n")

def select_league() -> str:
    leagues = get_available_leagues()
    print(f"{Colors.CYAN}  Available Leagues:{Colors.END}")
    for i, name in enumerate(leagues, 1):
        print(f"  {i:3}. {name}")
    print()
    while True:
        choice = input(f"{Colors.YELLOW}  Select league (number or name): {Colors.END}").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(leagues):
                return leagues[idx]
        for lg in leagues:
            if choice.lower() == lg.lower() or choice.lower() in lg.lower():
                return lg
        print(f"{Colors.RED}  Invalid choice.{Colors.END}")

# ═══════════════════════════════════════════════════════════════════════════════
# INPUT HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_team_input(prompt: str, provider: LiveDataProvider) -> Optional[TeamStats]:
    while True:
        user_input = input(f"{Colors.YELLOW}{prompt}{Colors.END}").strip()
        if user_input.lower() == "list":
            list_teams(provider)
            continue
        if user_input.lower() in ("quit", "q"):
            return None

        team = provider.get_team(user_input)
        if team:
            print(f"{Colors.GREEN}   → {team.name}{Colors.END}")
            return team

        matches = provider.fuzzy_search(user_input)
        if matches:
            print(f"{Colors.YELLOW}   Did you mean: {', '.join(matches)}?{Colors.END}")
        else:
            print(f"{Colors.RED}   Team not found. Type 'list' to see available teams.{Colors.END}")

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN MODES
# ═══════════════════════════════════════════════════════════════════════════════

def make_provider_and_engine(league_name: str) -> Tuple[LiveDataProvider, PredictionEngine]:
    provider = LiveDataProvider(league_name)
    loaded = provider.load()
    engine = PredictionEngine(provider.league_avg_goals)

    if loaded:
        # Try to fit rho from historical data
        results = provider.get_past_results()
        if results and len(results) >= 30:
            engine.fit_rho(results, provider.team_stats)
    else:
        print(f"{Colors.YELLOW}  No API key configured — using fallback data (La Liga only).{Colors.END}")
        print(f"  Set API_FOOTBALL_KEY env var for live data.\n")

    return provider, engine

def run_prediction(provider: LiveDataProvider, engine: PredictionEngine,
                    home: TeamStats, away: TeamStats):
    """Run a single prediction with all available enrichments."""
    h2h = provider.get_h2h(home.name, away.name)
    odds = provider.get_match_odds(home.name, away.name)

    prediction = engine.predict_match(home, away, h2h=h2h, odds_probs=odds)
    print_prediction(prediction)

def run_demo():
    print_header()
    print(f"{Colors.BLUE}  Demo: Espanyol vs Real Oviedo (La Liga){Colors.END}\n")
    provider, engine = make_provider_and_engine("La Liga")
    home = provider.get_team("Espanyol")
    away = provider.get_team("Real Oviedo")
    if home and away:
        run_prediction(provider, engine, home, away)
    else:
        print(f"{Colors.RED}  Demo teams not found.{Colors.END}")

def run_interactive(league_name: str = None):
    print_header()
    if league_name is None:
        league_name = select_league()

    provider, engine = make_provider_and_engine(league_name)

    print(f"\n{Colors.BLUE}  League: {league_name}{Colors.END}")
    print(f"  Type 'list' for teams, 'fixtures' for upcoming matches, 'quit' to exit.\n")

    while True:
        user_cmd = input(f"{Colors.YELLOW}  > {Colors.END}").strip()

        if user_cmd.lower() in ("quit", "q", "exit"):
            print(f"\n{Colors.YELLOW}  Goodbye!{Colors.END}\n")
            break
        elif user_cmd.lower() == "list":
            list_teams(provider)
            continue
        elif user_cmd.lower() == "fixtures":
            fixtures = provider.get_upcoming_fixtures()
            if fixtures:
                print_fixtures(fixtures)
            else:
                print(f"{Colors.RED}  No fixtures available.{Colors.END}")
            continue
        elif user_cmd.lower() == "league":
            league_name = select_league()
            provider, engine = make_provider_and_engine(league_name)
            print(f"\n{Colors.GREEN}  Switched to {league_name}{Colors.END}\n")
            continue

        # Treat input as home team
        home = provider.get_team(user_cmd)
        if home is None:
            matches = provider.fuzzy_search(user_cmd)
            if matches:
                print(f"{Colors.YELLOW}   Did you mean: {', '.join(matches)}?{Colors.END}")
            else:
                print(f"{Colors.RED}   Not recognized. Type 'list' for teams or 'quit' to exit.{Colors.END}")
            continue

        print(f"{Colors.GREEN}   Home: {home.name}{Colors.END}")
        away = get_team_input("  Enter AWAY team: ", provider)
        if away is None:
            print(f"\n{Colors.YELLOW}  Goodbye!{Colors.END}\n")
            break

        run_prediction(provider, engine, home, away)

def run_single_match(match_string: str, league_name: str = "La Liga"):
    print_header()
    provider, engine = make_provider_and_engine(league_name)

    parts = match_string.lower().replace(" vs ", "|").replace(" vs. ", "|").replace(" v ", "|").replace(" - ", "|").split("|")
    if len(parts) != 2:
        print(f"{Colors.RED}  Invalid format. Use: 'Team1 vs Team2'{Colors.END}")
        return

    home_name, away_name = [p.strip() for p in parts]
    home = provider.get_team(home_name)
    away = provider.get_team(away_name)

    if home is None:
        print(f"{Colors.RED}  Home team '{home_name}' not found.{Colors.END}")
        list_teams(provider)
        return
    if away is None:
        print(f"{Colors.RED}  Away team '{away_name}' not found.{Colors.END}")
        list_teams(provider)
        return

    run_prediction(provider, engine, home, away)

def run_backtest(league_name: str):
    print_header()
    print(f"{Colors.BLUE}  Backtesting: {league_name}{Colors.END}\n")
    provider, engine = make_provider_and_engine(league_name)
    bt = Backtester(engine, provider)
    metrics = bt.run()
    bt.print_report(metrics)

def run_show_fixtures(league_name: str):
    print_header()
    provider = LiveDataProvider(league_name)
    provider.load()
    fixtures = provider.get_upcoming_fixtures(20)
    if fixtures:
        print_fixtures(fixtures)
    else:
        print(f"{Colors.RED}  No upcoming fixtures found.{Colors.END}")

# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Football Match Predictor — Dixon-Coles Model")
    parser.add_argument("--match", "-m", type=str, help='Match to predict (e.g., "Barcelona vs Real Madrid")')
    parser.add_argument("--league", "-lg", type=str, default=None, help="League name (e.g., Premier League)")
    parser.add_argument("--demo", "-d", action="store_true", help="Run demo prediction")
    parser.add_argument("--list", "-l", action="store_true", help="List available teams")
    parser.add_argument("--fixtures", "-f", action="store_true", help="Show upcoming fixtures")
    parser.add_argument("--backtest", "-b", type=str, help='Backtest league (e.g., "La Liga")')
    parser.add_argument("--cache-clear", action="store_true", help="Clear the API response cache")
    parser.add_argument("--check-api", action="store_true", help="Check API key configuration")

    args = parser.parse_args()

    if args.cache_clear:
        clear_cache()
        return

    if args.check_api:
        avail = check_api_availability()
        print("\nAPI Status:")
        for name, ok in avail.items():
            status = f"{Colors.GREEN}configured{Colors.END}" if ok else f"{Colors.RED}NOT configured{Colors.END}"
            print(f"  {name}: {status}")
        print()
        return

    if args.demo:
        run_demo()
    elif args.backtest:
        run_backtest(args.backtest)
    elif args.fixtures:
        league = args.league or "La Liga"
        run_show_fixtures(league)
    elif args.list:
        print_header()
        league = args.league or "La Liga"
        provider, _ = make_provider_and_engine(league)
        list_teams(provider)
    elif args.match:
        league = args.league or "La Liga"
        run_single_match(args.match, league)
    else:
        run_interactive(args.league)

if __name__ == "__main__":
    main()
