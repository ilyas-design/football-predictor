# ⚽ Football Match Predictor Pro

A professional terminal-based football prediction tool that analyzes matches and provides betting recommendations similar to R-TECH DEV SCRIPTS.

## Features

- **1X2 Match Outcome Predictions** - Win/Draw/Loss probabilities
- **Over/Under 2.5 Goals** - Total goals analysis
- **Both Teams to Score (BTTS)** - Scoring probability for both teams
- **Exact Score Predictions** - Top 5 most likely scorelines with confidence
- **Best Bet Recommendations** - AI-powered betting suggestions
- **Expected Goals (xG)** - Statistical goal expectancy

## Installation

```bash
# Clone or download the script
cd football_predictor

# No external dependencies required for basic usage!
# Python 3.6+ is all you need

# For API integration, install requests:
pip install requests
```

## Usage

### Interactive Mode
```bash
python predictor.py
```

### Demo Mode (Espanyol vs Real Oviedo)
```bash
python predictor.py --demo
```

### Single Match Prediction
```bash
python predictor.py --match "Barcelona vs Real Madrid"
python predictor.py -m "Atletico Madrid vs Sevilla"
```

### List Available Teams
```bash
python predictor.py --list
```

## Sample Output

```
══════════════════════════════════════════════════════════════════════
  Prediction Results: Espanyol vs. Real Oviedo
══════════════════════════════════════════════════════════════════════

⭐ Best Bet Recommendation ⭐
   Market: Total Goals
   Prediction: Under 2.5
   Confidence: 55.16%

📊 1x2 Match Outcome Predictions:
   - Espanyol Win    | Confidence: 37.24%
   - Draw            | Confidence: 27.19%
   - Real Oviedo Win | Confidence: 35.57%

📊 Over/Under 2.5 Goals:
   - Over 2.5:  44.84%
   - Under 2.5: 55.16%

📊 Both Teams to Score (BTTS):
   - Yes: 50.27%
   - No:  49.73%

📊 Exact Score Predictions (Espanyol - Real Oviedo):
   - Score 1-1   | Confidence: 12.90%
   - Score 1-0   | Confidence: 10.60%
   - Score 0-1   | Confidence: 10.30%
   - Score 0-0   | Confidence: 9.85%
   - Score 2-1   | Confidence: 8.42%

══════════════════════════════════════════════════════════════════════
```

## Available Teams (La Liga 2025-26)

- Alaves
- Athletic Bilbao
- Atletico Madrid
- Barcelona
- Celta Vigo
- Elche
- Espanyol
- Getafe
- Girona
- Levante
- Mallorca
- Osasuna
- Rayo Vallecano
- Real Betis
- Real Madrid
- Real Oviedo
- Real Sociedad
- Sevilla
- Valencia
- Villarreal

## Adding More Teams/Leagues

Edit the `TEAM_DATABASE` dictionary in `predictor.py`:

```python
TEAM_DATABASE = {
    "Team Name": TeamStats(
        name="Team Name",
        attack_strength=1.0,      # Goals scored vs league avg (1.0 = average)
        defense_strength=1.0,     # Goals conceded vs league avg (lower = better)
        home_advantage=1.1,       # Home performance multiplier
        form_rating=0.5,          # Current form (0-1)
        avg_goals_scored=1.5,     # Average goals per game
        avg_goals_conceded=1.2,   # Average goals conceded
        clean_sheet_pct=0.3,      # Clean sheet percentage
        btts_pct=0.55             # Both teams score percentage
    ),
}
```

## API Integration (Real-Time Data)

For real match data, use `api_integration.py` with these free APIs:

### 1. API-Football (RapidAPI)
- **Free tier**: 100 requests/day
- **Sign up**: https://rapidapi.com/api-sports/api/api-football

```bash
export API_FOOTBALL_KEY='02d0d8ca689d028681a1e97e30efba4f'
```

### 2. Football-Data.org
- **Free tier**: 10 requests/minute
- **Sign up**: https://www.football-data.org/

```bash
export FOOTBALL_DATA_KEY='5e8104054fd440239836f997c6b7780f'
```

### 3. The Odds API
- **Free tier**: 500 requests/month
- **Sign up**: https://the-odds-api.com/

```bash
export ODDS_API_KEY='3a63ea318ae84ac28c12758719d6c166'
```

## How the Prediction Model Works

The script uses a **Poisson Distribution Model**:

1. **Expected Goals (xG)** calculated from:
   - Team attack strength
   - Opponent defense strength
   - Home advantage factor
   - Current form rating

2. **Score Probability Matrix**: Calculates probability for every possible scoreline (0-0 to 6-6)

3. **Market Probabilities** derived from score matrix:
   - Sum probabilities where home > away = Home Win %
   - Sum probabilities where home = away = Draw %
   - Sum probabilities where home + away > 2.5 = Over 2.5 %

4. **Best Bet Selection**: Identifies highest confidence market above threshold

## Disclaimer

⚠️ **This tool is for educational and entertainment purposes only.**

- Past performance does not guarantee future results
- Betting involves financial risk
- Always gamble responsibly
- This is not financial advice

## License

MIT License - Free to use, modify, and distribute.

## Contributing

Feel free to submit issues and pull requests to improve the prediction model!

---

Created with ❤️ for football analytics enthusiasts
