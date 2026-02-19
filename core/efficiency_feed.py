"""
core/efficiency_feed.py — Titanium-Agentic
===========================================
Team efficiency data layer. No live scraping. Static snapshot calibrated to
~2024-25 season. Used to populate the EFFICIENCY component of Sharp Score.

The efficiency component contributes 0-20 points to Sharp Score:
    eff_pts = max(0.0, min(20.0, efficiency_gap))

Gap output is already pre-scaled 0-20 — pass directly to calculate_sharp_score().

Scaling formula (same across all sports):
    differential = home_adj_em - away_adj_em
    gap = (differential + 30) / 60 * 20
    Gap 10.0 = evenly matched. >10 = home structural advantage. <10 = away.
    Clamped to [0.0, 20.0].

Data sources (static snapshots, not live):
    NBA:   Net Rating * 2.2 → adj_em scale. ~2024-25 season.
    NCAAB: KenPom/Barttorvik AdjEM. ~2024-25 season.
    NFL:   EPA/play * 80.0 → adj_em scale. ~2024 season.
    MLB:   (4.30 - ERA) * 8.0 → adj_em scale. ~2024 season.
    MLS:   xGD/90 * 15.0 → adj_em scale. ~2024 season.
    Soccer (EPL/Bund/Ligue1/SerieA/LaLiga): xG-based adj_em. ~2024-25 season.

Unknown teams fall back to gap=8.0 (neutral — slightly below even, per architecture note
in CLAUDE.md: "efficiency_gap defaults to 8.0 in rank_bets() for unknown teams").

Architecture rule: NO imports from other core modules.
"""

from typing import Optional


# ---------------------------------------------------------------------------
# Unknown team fallback
# ---------------------------------------------------------------------------
_UNKNOWN_GAP: float = 8.0


# ---------------------------------------------------------------------------
# Team efficiency data — adj_em is the single number that matters.
# adj_o/adj_d are stored for reference but not used in gap computation.
# ---------------------------------------------------------------------------

_TEAM_DATA: dict[str, dict] = {

    # =========================================================================
    # NBA — Net Rating * 2.2 → adj_em scale (~2024-25)
    # Elite: adj_em 18-30 | Strong: 8-18 | Mid: -2 to 8 | Lower: < -5
    # =========================================================================

    # Elite
    "Oklahoma City Thunder": {"adj_em": 28.0,  "league": "NBA"},
    "Boston Celtics":        {"adj_em": 27.5,  "league": "NBA"},
    "Cleveland Cavaliers":   {"adj_em": 24.6,  "league": "NBA"},
    "Minnesota Timberwolves":{"adj_em": 21.6,  "league": "NBA"},
    "Denver Nuggets":        {"adj_em": 19.0,  "league": "NBA"},

    # Strong
    "Houston Rockets":       {"adj_em": 14.3,  "league": "NBA"},
    "Golden State Warriors": {"adj_em": 14.1,  "league": "NBA"},
    "Los Angeles Lakers":    {"adj_em": 12.5,  "league": "NBA"},
    "Dallas Mavericks":      {"adj_em": 12.5,  "league": "NBA"},
    "Memphis Grizzlies":     {"adj_em": 11.4,  "league": "NBA"},
    "Indiana Pacers":        {"adj_em": 10.6,  "league": "NBA"},
    "Milwaukee Bucks":       {"adj_em":  9.0,  "league": "NBA"},
    "New York Knicks":       {"adj_em":  7.9,  "league": "NBA"},
    "Los Angeles Clippers":  {"adj_em":  7.3,  "league": "NBA"},
    "Sacramento Kings":      {"adj_em":  6.6,  "league": "NBA"},
    "San Antonio Spurs":     {"adj_em":  5.5,  "league": "NBA"},

    # Mid
    "Miami Heat":            {"adj_em":  4.2,  "league": "NBA"},
    "Philadelphia 76ers":    {"adj_em":  3.5,  "league": "NBA"},
    "Phoenix Suns":          {"adj_em":  2.6,  "league": "NBA"},
    "New Orleans Pelicans":  {"adj_em":  1.5,  "league": "NBA"},
    "Orlando Magic":         {"adj_em":  1.1,  "league": "NBA"},
    "Chicago Bulls":         {"adj_em": -0.4,  "league": "NBA"},
    "Atlanta Hawks":         {"adj_em": -2.0,  "league": "NBA"},
    "Toronto Raptors":       {"adj_em": -5.1,  "league": "NBA"},

    # Lower
    "Brooklyn Nets":         {"adj_em": -14.3, "league": "NBA"},
    "Detroit Pistons":       {"adj_em": -13.6, "league": "NBA"},
    "Utah Jazz":             {"adj_em": -13.0, "league": "NBA"},
    "Portland Trail Blazers":{"adj_em": -14.3, "league": "NBA"},
    "Charlotte Hornets":     {"adj_em": -14.9, "league": "NBA"},
    "Washington Wizards":    {"adj_em": -21.6, "league": "NBA"},

    # =========================================================================
    # NCAAB — KenPom/Barttorvik AdjEM (~2024-25)
    # ACC / Big 12 / Big Ten / SEC / Big East / Mid-majors / Low-major
    # =========================================================================

    # ACC
    "Duke":            {"adj_em": 32.8, "league": "NCAAB"},
    "UConn":           {"adj_em": 26.7, "league": "NCAAB"},
    "Marquette":       {"adj_em": 19.4, "league": "NCAAB"},
    "Creighton":       {"adj_em": 15.9, "league": "NCAAB"},
    "NC State":        {"adj_em": 12.3, "league": "NCAAB"},
    "Pitt":            {"adj_em": 10.8, "league": "NCAAB"},
    "Notre Dame":      {"adj_em":  8.5, "league": "NCAAB"},
    "Virginia":        {"adj_em":  6.3, "league": "NCAAB"},
    "Miami FL":        {"adj_em":  5.1, "league": "NCAAB"},
    "Syracuse":        {"adj_em":  5.6, "league": "NCAAB"},
    "Wake Forest":     {"adj_em":  4.5, "league": "NCAAB"},
    "Georgia Tech":    {"adj_em":  2.5, "league": "NCAAB"},
    "Louisville":      {"adj_em":  1.4, "league": "NCAAB"},
    "Clemson":         {"adj_em":  0.9, "league": "NCAAB"},
    "Stanford":        {"adj_em": -2.6, "league": "NCAAB"},
    "Boston College":  {"adj_em": -3.6, "league": "NCAAB"},
    "California":      {"adj_em": -6.6, "league": "NCAAB"},

    # Big 12
    "Kansas":          {"adj_em": 29.7, "league": "NCAAB"},
    "Houston":         {"adj_em": 26.4, "league": "NCAAB"},
    "Texas":           {"adj_em": 17.7, "league": "NCAAB"},
    "Baylor":          {"adj_em": 11.1, "league": "NCAAB"},
    "Texas Tech":      {"adj_em": 14.3, "league": "NCAAB"},
    "Iowa St":         {"adj_em": 13.7, "league": "NCAAB"},
    "Kansas St":       {"adj_em": 10.3, "league": "NCAAB"},
    "BYU":             {"adj_em":  9.7, "league": "NCAAB"},
    "Oklahoma St":     {"adj_em":  7.5, "league": "NCAAB"},
    "TCU":             {"adj_em":  6.1, "league": "NCAAB"},
    "UCF":             {"adj_em":  4.7, "league": "NCAAB"},
    "West Virginia":   {"adj_em":  3.2, "league": "NCAAB"},
    "Cincinnati":      {"adj_em":  1.7, "league": "NCAAB"},

    # Big Ten
    "Michigan St":     {"adj_em": 20.2, "league": "NCAAB"},
    "Purdue":          {"adj_em": 18.9, "league": "NCAAB"},
    "Illinois":        {"adj_em": 12.2, "league": "NCAAB"},
    "Wisconsin":       {"adj_em": 10.5, "league": "NCAAB"},
    "Michigan":        {"adj_em":  7.9, "league": "NCAAB"},
    "Ohio St":         {"adj_em":  7.6, "league": "NCAAB"},
    "Indiana":         {"adj_em":  8.5, "league": "NCAAB"},
    "Maryland":        {"adj_em":  6.9, "league": "NCAAB"},
    "Iowa":            {"adj_em":  6.1, "league": "NCAAB"},
    "Minnesota":       {"adj_em":  2.1, "league": "NCAAB"},
    "Penn St":         {"adj_em":  0.9, "league": "NCAAB"},
    "Nebraska":        {"adj_em":  1.3, "league": "NCAAB"},
    "Northwestern":    {"adj_em": -1.5, "league": "NCAAB"},
    "Rutgers":         {"adj_em": -2.5, "league": "NCAAB"},

    # SEC
    "Kentucky":        {"adj_em": 27.2, "league": "NCAAB"},
    "Auburn":          {"adj_em": 25.7, "league": "NCAAB"},
    "Alabama":         {"adj_em": 18.9, "league": "NCAAB"},
    "Tennessee":       {"adj_em": 18.4, "league": "NCAAB"},
    "Florida":         {"adj_em": 13.2, "league": "NCAAB"},
    "Arkansas":        {"adj_em": 11.1, "league": "NCAAB"},
    "Missouri":        {"adj_em":  9.5, "league": "NCAAB"},
    "Texas A&M":       {"adj_em":  7.7, "league": "NCAAB"},
    "LSU":             {"adj_em":  6.9, "league": "NCAAB"},
    "Ole Miss":        {"adj_em":  6.9, "league": "NCAAB"},
    "Mississippi St":  {"adj_em":  3.8, "league": "NCAAB"},
    "Georgia":         {"adj_em":  2.3, "league": "NCAAB"},
    "South Carolina":  {"adj_em":  0.8, "league": "NCAAB"},
    "Vanderbilt":      {"adj_em": -3.4, "league": "NCAAB"},

    # Big East
    "St. John's":      {"adj_em": 15.6, "league": "NCAAB"},
    "Providence":      {"adj_em":  7.3, "league": "NCAAB"},
    "Xavier":          {"adj_em":  5.7, "league": "NCAAB"},
    "Villanova":       {"adj_em":  4.4, "league": "NCAAB"},
    "Seton Hall":      {"adj_em":  1.2, "league": "NCAAB"},
    "DePaul":          {"adj_em": -2.8, "league": "NCAAB"},
    "Butler":          {"adj_em": -2.2, "league": "NCAAB"},
    "Georgetown":      {"adj_em": -7.7, "league": "NCAAB"},

    # WCC / Mountain West / A-10 (top mid-majors)
    "Gonzaga":         {"adj_em": 17.2, "league": "NCAAB"},
    "Saint Mary's":    {"adj_em": 10.7, "league": "NCAAB"},
    "San Diego St":    {"adj_em":  8.6, "league": "NCAAB"},
    "Utah St":         {"adj_em":  8.5, "league": "NCAAB"},
    "Dayton":          {"adj_em":  8.4, "league": "NCAAB"},
    "VCU":             {"adj_em":  6.8, "league": "NCAAB"},
    "UNLV":            {"adj_em":  5.7, "league": "NCAAB"},
    "New Mexico":      {"adj_em":  4.8, "league": "NCAAB"},
    "Drake":           {"adj_em":  4.2, "league": "NCAAB"},
    "Richmond":        {"adj_em":  1.9, "league": "NCAAB"},
    "Davidson":        {"adj_em":  1.7, "league": "NCAAB"},

    # Low-major
    "Bryant":          {"adj_em": -9.2,  "league": "NCAAB"},
    "Alabama St":      {"adj_em": -14.4, "league": "NCAAB"},
    "Texas Southern":  {"adj_em": -17.5, "league": "NCAAB"},

    # =========================================================================
    # NFL — EPA/play * 80.0 → adj_em scale (~2024 season)
    # Elite: adj_em 8-14 | Average: -2 to 8 | Poor: < -4
    # =========================================================================

    # Elite
    "Kansas City Chiefs":      {"adj_em": 12.8,  "league": "NFL"},
    "Detroit Lions":           {"adj_em": 11.2,  "league": "NFL"},
    "Philadelphia Eagles":     {"adj_em": 10.4,  "league": "NFL"},
    "Baltimore Ravens":        {"adj_em":  9.6,  "league": "NFL"},
    "Buffalo Bills":           {"adj_em":  9.2,  "league": "NFL"},
    "Minnesota Vikings":       {"adj_em":  8.8,  "league": "NFL"},
    "Houston Texans":          {"adj_em":  8.0,  "league": "NFL"},

    # Strong
    "Washington Commanders":   {"adj_em":  7.2,  "league": "NFL"},
    "Los Angeles Rams":        {"adj_em":  6.4,  "league": "NFL"},
    "Los Angeles Chargers":    {"adj_em":  6.4,  "league": "NFL"},
    "Tampa Bay Buccaneers":    {"adj_em":  5.6,  "league": "NFL"},
    "Atlanta Falcons":         {"adj_em":  4.8,  "league": "NFL"},
    "San Francisco 49ers":     {"adj_em":  4.0,  "league": "NFL"},
    "Pittsburgh Steelers":     {"adj_em":  3.2,  "league": "NFL"},
    "Denver Broncos":          {"adj_em":  3.2,  "league": "NFL"},
    "New York Giants":         {"adj_em":  2.4,  "league": "NFL"},
    "Green Bay Packers":       {"adj_em":  1.6,  "league": "NFL"},
    "Indianapolis Colts":      {"adj_em":  1.6,  "league": "NFL"},
    "Miami Dolphins":          {"adj_em":  0.8,  "league": "NFL"},

    # Mid / Below average
    "Seattle Seahawks":        {"adj_em":  0.0,  "league": "NFL"},
    "Arizona Cardinals":       {"adj_em": -0.8,  "league": "NFL"},
    "Chicago Bears":           {"adj_em": -1.6,  "league": "NFL"},
    "New England Patriots":    {"adj_em": -2.4,  "league": "NFL"},
    "Jacksonville Jaguars":    {"adj_em": -3.2,  "league": "NFL"},
    "New York Jets":           {"adj_em": -4.0,  "league": "NFL"},
    "Dallas Cowboys":          {"adj_em": -4.0,  "league": "NFL"},
    "Las Vegas Raiders":       {"adj_em": -5.6,  "league": "NFL"},
    "Cincinnati Bengals":      {"adj_em": -5.6,  "league": "NFL"},
    "New Orleans Saints":      {"adj_em": -6.4,  "league": "NFL"},
    "Carolina Panthers":       {"adj_em": -7.2,  "league": "NFL"},
    "Tennessee Titans":        {"adj_em": -8.0,  "league": "NFL"},
    "Cleveland Browns":        {"adj_em": -8.8,  "league": "NFL"},
    "Oakland Raiders":         {"adj_em": -5.6,  "league": "NFL"},  # alias

    # =========================================================================
    # MLB — (4.30 - ERA) * 8.0 → adj_em scale (~2024 season)
    # Season deferred to Apr 1 but data ready for wire-in
    # =========================================================================

    # Elite rotation (ERA < 4.00)
    "Seattle Mariners":         {"adj_em": (4.30 - 3.52) * 8.0, "league": "MLB"},
    "Cleveland Guardians":      {"adj_em": (4.30 - 3.54) * 8.0, "league": "MLB"},
    "Los Angeles Dodgers":      {"adj_em": (4.30 - 3.63) * 8.0, "league": "MLB"},
    "Milwaukee Brewers":        {"adj_em": (4.30 - 3.69) * 8.0, "league": "MLB"},
    "Philadelphia Phillies":    {"adj_em": (4.30 - 3.80) * 8.0, "league": "MLB"},
    "Baltimore Orioles":        {"adj_em": (4.30 - 3.86) * 8.0, "league": "MLB"},
    "Kansas City Royals":       {"adj_em": (4.30 - 3.89) * 8.0, "league": "MLB"},
    "New York Mets":            {"adj_em": (4.30 - 3.93) * 8.0, "league": "MLB"},
    "San Diego Padres":         {"adj_em": (4.30 - 3.97) * 8.0, "league": "MLB"},
    "New York Yankees":         {"adj_em": (4.30 - 3.99) * 8.0, "league": "MLB"},

    # Above-average rotation (ERA 4.00–4.29)
    "Atlanta Braves":           {"adj_em": (4.30 - 4.01) * 8.0, "league": "MLB"},
    "Pittsburgh Pirates":       {"adj_em": (4.30 - 4.04) * 8.0, "league": "MLB"},
    "Houston Astros":           {"adj_em": (4.30 - 4.12) * 8.0, "league": "MLB"},
    "Minnesota Twins":          {"adj_em": (4.30 - 4.18) * 8.0, "league": "MLB"},
    "Detroit Tigers":           {"adj_em": (4.30 - 4.23) * 8.0, "league": "MLB"},

    # Near-average rotation (ERA 4.28–4.44)
    "San Francisco Giants":     {"adj_em": (4.30 - 4.28) * 8.0, "league": "MLB"},
    "Arizona Diamondbacks":     {"adj_em": (4.30 - 4.31) * 8.0, "league": "MLB"},
    "Tampa Bay Rays":           {"adj_em": (4.30 - 4.35) * 8.0, "league": "MLB"},
    "Cincinnati Reds":          {"adj_em": (4.30 - 4.38) * 8.0, "league": "MLB"},
    "Boston Red Sox":           {"adj_em": (4.30 - 4.44) * 8.0, "league": "MLB"},

    # Below-average rotation (ERA 4.45–4.70)
    "Chicago Cubs":             {"adj_em": (4.30 - 4.48) * 8.0, "league": "MLB"},
    "St. Louis Cardinals":      {"adj_em": (4.30 - 4.51) * 8.0, "league": "MLB"},
    "Texas Rangers":            {"adj_em": (4.30 - 4.55) * 8.0, "league": "MLB"},
    "Miami Marlins":            {"adj_em": (4.30 - 4.58) * 8.0, "league": "MLB"},
    "Los Angeles Angels":       {"adj_em": (4.30 - 4.62) * 8.0, "league": "MLB"},
    "Toronto Blue Jays":        {"adj_em": (4.30 - 4.65) * 8.0, "league": "MLB"},

    # Poor rotation (ERA > 4.70)
    "Chicago White Sox":        {"adj_em": (4.30 - 5.14) * 8.0, "league": "MLB"},
    "Oakland Athletics":        {"adj_em": (4.30 - 5.02) * 8.0, "league": "MLB"},
    "Washington Nationals":     {"adj_em": (4.30 - 4.88) * 8.0, "league": "MLB"},
    "Colorado Rockies":         {"adj_em": (4.30 - 5.22) * 8.0, "league": "MLB"},

    # =========================================================================
    # MLS — xGD/90 * 15.0 → adj_em scale (~2024 season)
    # =========================================================================

    # Elite
    "Inter Miami CF":           {"adj_em": 1.72 * 15.0,  "league": "MLS"},
    "LA Galaxy":                {"adj_em": 1.31 * 15.0,  "league": "MLS"},
    "Columbus Crew":            {"adj_em": 1.08 * 15.0,  "league": "MLS"},
    "Seattle Sounders":         {"adj_em": 0.95 * 15.0,  "league": "MLS"},
    "Cincinnati FC":            {"adj_em": 0.88 * 15.0,  "league": "MLS"},
    "LAFC":                     {"adj_em": 0.82 * 15.0,  "league": "MLS"},
    "New York City FC":         {"adj_em": 0.74 * 15.0,  "league": "MLS"},

    # Strong
    "Philadelphia Union":       {"adj_em": 0.64 * 15.0,  "league": "MLS"},
    "Atlanta United":           {"adj_em": 0.58 * 15.0,  "league": "MLS"},
    "St. Louis City SC":        {"adj_em": 0.51 * 15.0,  "league": "MLS"},
    "New England Revolution":   {"adj_em": 0.44 * 15.0,  "league": "MLS"},
    "Portland Timbers":         {"adj_em": 0.38 * 15.0,  "league": "MLS"},
    "Real Salt Lake":           {"adj_em": 0.32 * 15.0,  "league": "MLS"},

    # Mid
    "New York Red Bulls":       {"adj_em": 0.24 * 15.0,  "league": "MLS"},
    "Vancouver Whitecaps":      {"adj_em": 0.18 * 15.0,  "league": "MLS"},
    "Houston Dynamo":           {"adj_em": 0.12 * 15.0,  "league": "MLS"},
    "Orlando City":             {"adj_em": 0.08 * 15.0,  "league": "MLS"},
    "Nashville SC":             {"adj_em": 0.06 * 15.0,  "league": "MLS"},
    "Minnesota United":         {"adj_em": 0.02 * 15.0,  "league": "MLS"},
    "Colorado Rapids":          {"adj_em":-0.04 * 15.0,  "league": "MLS"},
    "CF Montreal":              {"adj_em":-0.08 * 15.0,  "league": "MLS"},
    "Sporting KC":              {"adj_em":-0.12 * 15.0,  "league": "MLS"},
    "FC Dallas":                {"adj_em":-0.18 * 15.0,  "league": "MLS"},

    # Lower
    "Toronto FC":               {"adj_em":-0.28 * 15.0,  "league": "MLS"},
    "Chicago Fire":             {"adj_em":-0.38 * 15.0,  "league": "MLS"},
    "D.C. United":              {"adj_em":-0.44 * 15.0,  "league": "MLS"},
    "Austin FC":                {"adj_em":-0.52 * 15.0,  "league": "MLS"},
    "San Jose Earthquakes":     {"adj_em":-0.64 * 15.0,  "league": "MLS"},
    "Charlotte FC":             {"adj_em":-0.72 * 15.0,  "league": "MLS"},
    "San Diego FC":             {"adj_em":  0.0,          "league": "MLS"},  # expansion

    # =========================================================================
    # EPL — xG-differential based adj_em (~2024-25)
    # Top teams: adj_em 15-25. Mid-table: 0-8. Relegation: -8 to -20.
    # =========================================================================
    "Manchester City":          {"adj_em": 22.0, "league": "EPL"},
    "Arsenal":                  {"adj_em": 20.5, "league": "EPL"},
    "Liverpool":                {"adj_em": 24.0, "league": "EPL"},
    "Chelsea":                  {"adj_em": 14.0, "league": "EPL"},
    "Aston Villa":              {"adj_em": 16.0, "league": "EPL"},
    "Tottenham Hotspur":        {"adj_em": 12.0, "league": "EPL"},
    "Manchester United":        {"adj_em":  8.0, "league": "EPL"},
    "Newcastle United":         {"adj_em": 13.5, "league": "EPL"},
    "Brighton":                 {"adj_em": 11.0, "league": "EPL"},
    "West Ham United":          {"adj_em":  6.0, "league": "EPL"},
    "Fulham":                   {"adj_em":  5.0, "league": "EPL"},
    "Crystal Palace":           {"adj_em":  3.5, "league": "EPL"},
    "Brentford":                {"adj_em":  4.0, "league": "EPL"},
    "Wolverhampton":            {"adj_em":  2.0, "league": "EPL"},
    "Everton":                  {"adj_em": -2.0, "league": "EPL"},
    "Nottingham Forest":        {"adj_em":  9.0, "league": "EPL"},
    "Bournemouth":              {"adj_em":  6.5, "league": "EPL"},
    "Leicester City":           {"adj_em": -4.0, "league": "EPL"},
    "Ipswich Town":             {"adj_em": -8.0, "league": "EPL"},
    "Southampton":              {"adj_em":-14.0, "league": "EPL"},

    # =========================================================================
    # Bundesliga (~2024-25)
    # =========================================================================
    "Bayer Leverkusen":         {"adj_em": 22.5, "league": "BUNDESLIGA"},
    "Bayern Munich":            {"adj_em": 24.0, "league": "BUNDESLIGA"},
    "Borussia Dortmund":        {"adj_em": 15.0, "league": "BUNDESLIGA"},
    "RB Leipzig":               {"adj_em": 14.5, "league": "BUNDESLIGA"},
    "Eintracht Frankfurt":      {"adj_em":  9.0, "league": "BUNDESLIGA"},
    "VfB Stuttgart":            {"adj_em": 11.0, "league": "BUNDESLIGA"},
    "Borussia Mönchengladbach": {"adj_em":  5.0, "league": "BUNDESLIGA"},
    "Freiburg":                 {"adj_em":  6.0, "league": "BUNDESLIGA"},
    "Werder Bremen":            {"adj_em":  3.0, "league": "BUNDESLIGA"},
    "Augsburg":                 {"adj_em": -1.0, "league": "BUNDESLIGA"},
    "Wolfsburg":                {"adj_em":  2.0, "league": "BUNDESLIGA"},
    "Hoffenheim":               {"adj_em":  1.0, "league": "BUNDESLIGA"},
    "Mainz":                    {"adj_em": -3.0, "league": "BUNDESLIGA"},
    "Union Berlin":             {"adj_em": -4.0, "league": "BUNDESLIGA"},
    "Heidenheim":               {"adj_em": -6.0, "league": "BUNDESLIGA"},
    "Bochum":                   {"adj_em":-10.0, "league": "BUNDESLIGA"},
    "Holstein Kiel":            {"adj_em":-12.0, "league": "BUNDESLIGA"},
    "St. Pauli":                {"adj_em": -8.0, "league": "BUNDESLIGA"},

    # =========================================================================
    # Ligue 1 (~2024-25)
    # =========================================================================
    "Paris Saint-Germain":      {"adj_em": 28.0, "league": "LIGUE1"},
    "Monaco":                   {"adj_em": 18.0, "league": "LIGUE1"},
    "Lyon":                     {"adj_em": 12.0, "league": "LIGUE1"},
    "Marseille":                {"adj_em": 14.0, "league": "LIGUE1"},
    "Nice":                     {"adj_em": 10.0, "league": "LIGUE1"},
    "Lille":                    {"adj_em": 13.5, "league": "LIGUE1"},
    "Rennes":                   {"adj_em":  7.0, "league": "LIGUE1"},
    "Lens":                     {"adj_em":  8.0, "league": "LIGUE1"},
    "Stade de Reims":           {"adj_em":  4.0, "league": "LIGUE1"},
    "Nantes":                   {"adj_em":  1.0, "league": "LIGUE1"},
    "Brest":                    {"adj_em":  9.0, "league": "LIGUE1"},
    "Le Havre":                 {"adj_em": -4.0, "league": "LIGUE1"},
    "Strasbourg":               {"adj_em": -2.0, "league": "LIGUE1"},
    "Toulouse":                 {"adj_em":  3.0, "league": "LIGUE1"},
    "Montpellier":              {"adj_em": -8.0, "league": "LIGUE1"},
    "Angers":                   {"adj_em": -6.0, "league": "LIGUE1"},
    "Auxerre":                  {"adj_em": -5.0, "league": "LIGUE1"},
    "Saint-Etienne":            {"adj_em":-12.0, "league": "LIGUE1"},

    # =========================================================================
    # Serie A (~2024-25)
    # =========================================================================
    "Inter Milan":              {"adj_em": 22.0, "league": "SERIE_A"},
    "Napoli":                   {"adj_em": 20.0, "league": "SERIE_A"},
    "Juventus":                 {"adj_em": 15.0, "league": "SERIE_A"},
    "AC Milan":                 {"adj_em": 14.0, "league": "SERIE_A"},
    "Atalanta":                 {"adj_em": 18.0, "league": "SERIE_A"},
    "Lazio":                    {"adj_em": 10.0, "league": "SERIE_A"},
    "Roma":                     {"adj_em":  8.0, "league": "SERIE_A"},
    "Fiorentina":               {"adj_em":  9.0, "league": "SERIE_A"},
    "Bologna":                  {"adj_em": 11.0, "league": "SERIE_A"},
    "Torino":                   {"adj_em":  4.0, "league": "SERIE_A"},
    "Udinese":                  {"adj_em":  2.0, "league": "SERIE_A"},
    "Genoa":                    {"adj_em": -1.0, "league": "SERIE_A"},
    "Cagliari":                 {"adj_em": -3.0, "league": "SERIE_A"},
    "Lecce":                    {"adj_em": -5.0, "league": "SERIE_A"},
    "Verona":                   {"adj_em": -4.0, "league": "SERIE_A"},
    "Parma":                    {"adj_em": -6.0, "league": "SERIE_A"},
    "Empoli":                   {"adj_em": -2.0, "league": "SERIE_A"},
    "Como":                     {"adj_em": -8.0, "league": "SERIE_A"},
    "Venezia":                  {"adj_em":-10.0, "league": "SERIE_A"},
    "Monza":                    {"adj_em": -7.0, "league": "SERIE_A"},

    # =========================================================================
    # La Liga (~2024-25)
    # =========================================================================
    "Real Madrid":              {"adj_em": 26.0, "league": "LA_LIGA"},
    "FC Barcelona":             {"adj_em": 24.0, "league": "LA_LIGA"},
    "Atletico Madrid":          {"adj_em": 18.0, "league": "LA_LIGA"},
    "Athletic Club":            {"adj_em": 14.0, "league": "LA_LIGA"},
    "Villarreal":               {"adj_em": 12.0, "league": "LA_LIGA"},
    "Real Betis":               {"adj_em": 10.0, "league": "LA_LIGA"},
    "Real Sociedad":            {"adj_em": 11.0, "league": "LA_LIGA"},
    "Osasuna":                  {"adj_em":  6.0, "league": "LA_LIGA"},
    "Girona":                   {"adj_em": 15.0, "league": "LA_LIGA"},
    "Mallorca":                 {"adj_em":  4.0, "league": "LA_LIGA"},
    "Sevilla":                  {"adj_em":  8.0, "league": "LA_LIGA"},
    "Getafe":                   {"adj_em":  2.0, "league": "LA_LIGA"},
    "Celta Vigo":               {"adj_em":  3.0, "league": "LA_LIGA"},
    "Alaves":                   {"adj_em": -2.0, "league": "LA_LIGA"},
    "Rayo Vallecano":           {"adj_em":  1.0, "league": "LA_LIGA"},
    "Valencia":                 {"adj_em": -4.0, "league": "LA_LIGA"},
    "Leganes":                  {"adj_em": -6.0, "league": "LA_LIGA"},
    "Espanyol":                 {"adj_em": -7.0, "league": "LA_LIGA"},
    "Las Palmas":               {"adj_em": -5.0, "league": "LA_LIGA"},
    "Real Valladolid":          {"adj_em":-10.0, "league": "LA_LIGA"},
}

# ---------------------------------------------------------------------------
# Aliases — common short names / alternative spellings
# Maps variant → canonical key in _TEAM_DATA
# ---------------------------------------------------------------------------
_ALIASES: dict[str, str] = {
    # NBA
    "Warriors":              "Golden State Warriors",
    "Mavs":                  "Dallas Mavericks",
    "Thunder":               "Oklahoma City Thunder",
    "Celtics":               "Boston Celtics",
    "Cavs":                  "Cleveland Cavaliers",
    "Wolves":                "Minnesota Timberwolves",
    "Nuggets":               "Denver Nuggets",
    "Rockets":               "Houston Rockets",
    "Lakers":                "Los Angeles Lakers",
    "Mavericks":             "Dallas Mavericks",
    "Grizzlies":             "Memphis Grizzlies",
    "Pacers":                "Indiana Pacers",
    "Bucks":                 "Milwaukee Bucks",
    "Knicks":                "New York Knicks",
    "Clippers":              "Los Angeles Clippers",
    "Kings":                 "Sacramento Kings",
    "Spurs":                 "San Antonio Spurs",
    "Heat":                  "Miami Heat",
    "76ers":                 "Philadelphia 76ers",
    "Sixers":                "Philadelphia 76ers",
    "Suns":                  "Phoenix Suns",
    "Pelicans":              "New Orleans Pelicans",
    "Magic":                 "Orlando Magic",
    "Bulls":                 "Chicago Bulls",
    "Hawks":                 "Atlanta Hawks",
    "Raptors":               "Toronto Raptors",
    "Nets":                  "Brooklyn Nets",
    "Pistons":               "Detroit Pistons",
    "Jazz":                  "Utah Jazz",
    "Blazers":               "Portland Trail Blazers",
    "Trail Blazers":         "Portland Trail Blazers",
    "Hornets":               "Charlotte Hornets",
    "Wizards":               "Washington Wizards",
    "Timberwolves":          "Minnesota Timberwolves",
    # NFL
    "Chiefs":                "Kansas City Chiefs",
    "Lions":                 "Detroit Lions",
    "Eagles":                "Philadelphia Eagles",
    "Ravens":                "Baltimore Ravens",
    "Bills":                 "Buffalo Bills",
    "Vikings":               "Minnesota Vikings",
    "Texans":                "Houston Texans",
    "Commanders":            "Washington Commanders",
    "Rams":                  "Los Angeles Rams",
    "Chargers":              "Los Angeles Chargers",
    "Buccaneers":            "Tampa Bay Buccaneers",
    "Falcons":               "Atlanta Falcons",
    "49ers":                 "San Francisco 49ers",
    "Steelers":              "Pittsburgh Steelers",
    "Broncos":               "Denver Broncos",
    "Giants":                "New York Giants",
    "Packers":               "Green Bay Packers",
    "Colts":                 "Indianapolis Colts",
    "Dolphins":              "Miami Dolphins",
    "Seahawks":              "Seattle Seahawks",
    "Cardinals":             "Arizona Cardinals",
    "Bears":                 "Chicago Bears",
    "Patriots":              "New England Patriots",
    "Jaguars":               "Jacksonville Jaguars",
    "Jets":                  "New York Jets",
    "Cowboys":               "Dallas Cowboys",
    "Raiders":               "Las Vegas Raiders",
    "Bengals":               "Cincinnati Bengals",
    "Saints":                "New Orleans Saints",
    "Panthers":              "Carolina Panthers",
    "Titans":                "Tennessee Titans",
    "Browns":                "Cleveland Browns",
    # MLS aliases
    "Inter Miami":           "Inter Miami CF",
    "NYCFC":                 "New York City FC",
    "NYRB":                  "New York Red Bulls",
    "Galaxy":                "LA Galaxy",
    # Soccer
    "PSG":                   "Paris Saint-Germain",
    "Man City":              "Manchester City",
    "Man Utd":               "Manchester United",
    "Man United":            "Manchester United",
    "Spurs":                 "Tottenham Hotspur",
    "Wolves":                "Wolverhampton",  # note: also NBA alias but resolved by lookup order
    "BVB":                   "Borussia Dortmund",
    "Dortmund":              "Borussia Dortmund",
    "Leverkusen":            "Bayer Leverkusen",
    "Leipzig":               "RB Leipzig",
    "Bayern":                "Bayern Munich",
    "Frankfurt":             "Eintracht Frankfurt",
    "Stuttgart":             "VfB Stuttgart",
    "Gladbach":              "Borussia Mönchengladbach",
    "Barca":                 "FC Barcelona",
    "Barcelona":             "FC Barcelona",
    "Real":                  "Real Madrid",
    "Atletico":              "Atletico Madrid",
    "Betis":                 "Real Betis",
    "Sociedad":              "Real Sociedad",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_team_data(team_name: str) -> Optional[dict]:
    """
    Return raw efficiency dict for a team, or None if not in database.

    Checks canonical name first, then alias lookup.

    >>> get_team_data("Boston Celtics") is not None
    True
    >>> get_team_data("Celtics") is not None
    True
    >>> get_team_data("Unknown FC") is None
    True
    """
    name = team_name.strip()

    # Direct match
    if name in _TEAM_DATA:
        return _TEAM_DATA[name]

    # Alias lookup
    canonical = _ALIASES.get(name)
    if canonical and canonical in _TEAM_DATA:
        return _TEAM_DATA[canonical]

    # Case-insensitive fallback
    lower = name.lower()
    for k in _TEAM_DATA:
        if k.lower() == lower:
            return _TEAM_DATA[k]

    return None


def get_efficiency_gap(home_team: str, away_team: str) -> float:
    """
    Return a 0-20 scaled efficiency gap for a matchup.

    Gap = (home_adj_em - away_adj_em + 30) / 60 * 20
    Clamped to [0.0, 20.0].

    Gap 10.0 = evenly matched.
    Gap > 10.0 = home team has structural edge.
    Gap < 10.0 = away team has structural edge.

    Returns _UNKNOWN_GAP (8.0) if either team is not in the database.
    8.0 is below neutral (10.0) — unknown teams don't inflate scores.

    >>> gap = get_efficiency_gap("Boston Celtics", "Washington Wizards")
    >>> 18.0 < gap <= 20.0  # elite vs worst — should pin at max
    True
    >>> gap = get_efficiency_gap("Unknown A", "Unknown B")
    >>> gap == 8.0
    True
    """
    home_data = get_team_data(home_team)
    away_data = get_team_data(away_team)

    if home_data is None or away_data is None:
        return _UNKNOWN_GAP

    home_em = home_data["adj_em"]
    away_em = away_data["adj_em"]

    differential = home_em - away_em
    gap = (differential + 30.0) / 60.0 * 20.0
    return max(0.0, min(20.0, gap))


def list_teams(league: Optional[str] = None) -> list[str]:
    """
    Return list of canonical team names in the database.

    Args:
        league: Optional filter (e.g. "NBA", "NCAAB", "NFL", "MLB", "MLS",
                "EPL", "BUNDESLIGA", "LIGUE1", "SERIE_A", "LA_LIGA").

    >>> len(list_teams()) > 100
    True
    >>> all("NBA" == t for t in list_teams("NBA"))  # league filter works
    False  # (returns team names, not league names)
    >>> len(list_teams("NBA")) == 30
    True
    """
    if league is None:
        return list(_TEAM_DATA.keys())

    upper = league.upper()
    return [name for name, data in _TEAM_DATA.items() if data.get("league") == upper]
