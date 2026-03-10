#!/usr/bin/env python3
"""
Flask backend API for Football Predictor Pro.
Run: python app.py
Then open http://localhost:5000
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dataclasses import asdict
import os

from predictor import (
    PredictionEngine, LiveDataProvider, TeamStats, MatchPrediction,
    FALLBACK_LEAGUE_AVG, FALLBACK_TEAMS,
)
from api_integration import get_available_leagues, check_api_availability, LEAGUES

app = Flask(__name__, static_folder="static")
CORS(app)

# ── Cache loaded providers so we don't refetch every request ──────────────
_providers: dict = {}


def get_provider(league_name: str) -> LiveDataProvider:
    """Get or create a LiveDataProvider for the given league."""
    if league_name not in _providers:
        provider = LiveDataProvider(league_name)
        provider.load()
        _providers[league_name] = provider
    return _providers[league_name]


# ── API Routes ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/leagues")
def api_leagues():
    leagues = get_available_leagues()
    return jsonify(leagues)


@app.route("/api/leagues/<league_name>/teams")
def api_teams(league_name):
    provider = get_provider(league_name)
    teams = provider.get_team_names()
    return jsonify({
        "league": league_name,
        "teams": teams,
        "is_live": provider.is_live,
    })


@app.route("/api/predict", methods=["POST"])
def api_predict():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    league = data.get("league", "La Liga")
    home_name = data.get("home_team", "").strip()
    away_name = data.get("away_team", "").strip()

    if not home_name or not away_name:
        return jsonify({"error": "home_team and away_team are required"}), 400

    provider = get_provider(league)
    home = provider.get_team(home_name)
    away = provider.get_team(away_name)

    if not home:
        suggestions = provider.fuzzy_search(home_name)
        return jsonify({
            "error": f"Team '{home_name}' not found",
            "suggestions": suggestions,
            "available_teams": provider.get_team_names(),
        }), 404

    if not away:
        suggestions = provider.fuzzy_search(away_name)
        return jsonify({
            "error": f"Team '{away_name}' not found",
            "suggestions": suggestions,
            "available_teams": provider.get_team_names(),
        }), 404

    engine = PredictionEngine(provider.league_avg_goals)

    # Get H2H and odds if available
    h2h = provider.get_h2h(home.name, away.name)
    odds = provider.get_match_odds(home.name, away.name)

    # Get real extended stats (corners, cards, shots) if API available
    home_ext = provider.get_extended_stats(home.name)
    away_ext = provider.get_extended_stats(away.name)

    prediction = engine.predict_match(home, away, h2h=h2h, odds_probs=odds,
                                       home_ext=home_ext, away_ext=away_ext)

    return jsonify({
        "home_team": prediction.home_team,
        "away_team": prediction.away_team,
        "home_win": round(prediction.home_win_prob, 2),
        "draw": round(prediction.draw_prob, 2),
        "away_win": round(prediction.away_win_prob, 2),
        "over_25": round(prediction.over_25_prob, 2),
        "under_25": round(prediction.under_25_prob, 2),
        "over_15": round(prediction.over_15_prob, 2),
        "under_15": round(prediction.under_15_prob, 2),
        "over_35": round(prediction.over_35_prob, 2),
        "under_35": round(prediction.under_35_prob, 2),
        "btts_yes": round(prediction.btts_yes_prob, 2),
        "btts_no": round(prediction.btts_no_prob, 2),
        "home_over_05": round(prediction.home_over_05_prob, 2),
        "away_over_05": round(prediction.away_over_05_prob, 2),
        "home_over_15": round(prediction.home_over_15_prob, 2),
        "away_over_15": round(prediction.away_over_15_prob, 2),
        "expected_home_goals": round(prediction.expected_home_goals, 2),
        "expected_away_goals": round(prediction.expected_away_goals, 2),
        "exact_scores": [{"score": s, "probability": round(p, 2)} for s, p in prediction.exact_scores],
        "best_bet": prediction.best_bet,
        "data_source": prediction.data_source,
        "is_live": provider.is_live,
        # Extended markets
        "corners": {
            "expected": prediction.expected_corners,
            "home": prediction.home_corners,
            "away": prediction.away_corners,
            "over_85": prediction.over_85_corners_prob,
            "over_95": prediction.over_95_corners_prob,
            "over_105": prediction.over_105_corners_prob,
        },
        "cards": {
            "expected": prediction.expected_cards,
            "home": prediction.home_cards,
            "away": prediction.away_cards,
            "over_35": prediction.over_35_cards_prob,
            "over_45": prediction.over_45_cards_prob,
            "over_55": prediction.over_55_cards_prob,
        },
        "shots_on_target": {
            "expected": prediction.expected_shots_on_target,
            "home": prediction.home_shots_on_target,
            "away": prediction.away_shots_on_target,
        },
        "half_goals": {
            "first_half": prediction.first_half_goals,
            "second_half": prediction.second_half_goals,
        },
        "extended_data_source": "live" if (home_ext and away_ext) else "estimated",
    })


@app.route("/api/fixtures/<league_name>")
def api_fixtures(league_name):
    provider = get_provider(league_name)
    fixtures = provider.get_upcoming_fixtures(15)
    return jsonify([
        {
            "home_team": f.home_team,
            "away_team": f.away_team,
            "date": f.date.isoformat() if f.date else "",
            "venue": f.venue,
            "round": f.round,
        }
        for f in fixtures
    ])


@app.route("/api/status")
def api_status():
    return jsonify(check_api_availability())


# ── Run ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  Football Predictor Pro — Web UI")
    print("  Open http://localhost:5000 in your browser\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
