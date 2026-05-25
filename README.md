# strava-sport-science-mcp

**A sports-science-aware MCP server for Strava with advanced training analytics**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![MCP Spec Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)

## Overview

`strava-sport-science-mcp` is an MCP (Model Context Protocol) server that goes beyond basic Strava API access. It brings **sports-science intelligence** to your training data, providing deep insights into fitness, fatigue, and race readiness using **Banister impulse-response models**, **HR zone polarization analysis**, and **periodized training assessment**.

Use it with Claude Desktop or any MCP-compatible client to analyze your training like a sports scientist—without leaving your AI assistant.

## Key Features

### 🏃 Raw Strava Tools
- **Get Activities** — Fetch recent activities with distance, duration, heart rate, pace
- **Get Activity Detail** — Full activity details including laps, splits, and best efforts
- **Get Athlete Profile** — Authenticated athlete's profile and stats
- **Get Activity Streams** — Second-by-second time-series data (heart rate, altitude, speed, cadence)

### 🧪 Sport-Science Tools
- **Training Load Analysis** — CTL (fitness), ATL (fatigue), TSB (form) using Banister's model; current phase detection (building/tapering/overreaching)
- **Zone Distribution** — HR zone breakdown (Z1-Z5) with 80/20 polarization assessment
- **Fitness Trend** — Weekly volume and intensity tracking; injury-risk detection (>10% weekly increase)
- **Race Readiness** — Holistic 0-100 score based on fitness, freshness, long-run progress, and consistency

## Quick Start

### Prerequisites

- Python 3.11+ ([download](https://www.python.org/downloads/))
- `uv` package manager ([install](https://docs.astral.sh/uv/getting-started/))
- A [Strava account](https://www.strava.com)
- A Strava API app (create one [here](https://www.strava.com/settings/api))

### Get Your Strava Tokens

1. **Create a Strava API app:**
   - Go to https://www.strava.com/settings/api
   - Create a new app, note your **Client ID** and **Client Secret**

2. **Authorize to get a Refresh Token:**
   - Use the authorization URL: `https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri=http://localhost&scope=activity:read_all`
   - Replace `{CLIENT_ID}` with your app's Client ID
   - Click authorize, you'll be redirected with a `code` parameter
   - Exchange the code for tokens:
     ```bash
     curl -X POST https://www.strava.com/oauth/token \
       -d client_id={CLIENT_ID} \
       -d client_secret={CLIENT_SECRET} \
       -d code={CODE} \
       -d grant_type=authorization_code
     ```
   - Save the `refresh_token` from the response

### Install

```bash
# Latest release
uvx strava-sport-science-mcp

# Or install locally for development
uv pip install strava-sport-science-mcp
```

### Configure

Set environment variables (or create a `.env` file):

```bash
export STRAVA_CLIENT_ID="your_client_id"
export STRAVA_CLIENT_SECRET="your_client_secret"
export STRAVA_REFRESH_TOKEN="your_refresh_token"
```

### Use with Claude Desktop

Add to `~/.config/Claude/claude_desktop_config.json` (macOS/Linux) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "strava-sport-science": {
      "command": "uvx",
      "args": ["strava-sport-science-mcp"],
      "env": {
        "STRAVA_CLIENT_ID": "your_client_id",
        "STRAVA_CLIENT_SECRET": "your_client_secret",
        "STRAVA_REFRESH_TOKEN": "your_refresh_token"
      }
    }
  }
}
```

Restart Claude Desktop. The tools will appear in the tool picker.

## Tool Reference

| Tool | Description | Key Inputs | Example Prompt |
|------|-------------|-----------|-----------------|
| **get_activities** | Fetch recent activities | `days_back` (default 30) | "Show me my last 30 days of runs" |
| **get_activity_detail** | Full activity details | `activity_id` | "Get details for activity 12345" |
| **get_athlete_profile** | Your Strava profile | — | "What's my Strava profile?" |
| **get_activity_streams** | Second-by-second data | `activity_id`, `stream_types` | "Get HR data for my last run" |
| **get_training_load** | CTL/ATL/TSB analysis | `days` (default 42) | "Am I overtraining? Analyze my fatigue." |
| **get_zone_distribution** | HR zone breakdown | `days` (default 30) | "Am I training easy enough? Show zones." |
| **get_fitness_trend** | Weekly volume/intensity | `weeks` (default 8) | "How has my training progressed?" |
| **get_race_readiness** | Race readiness score | `target_distance_km` (default 10) | "Am I ready for a 10K this weekend?" |

### Example Conversations

**Assessing Training Balance:**
> "How's my current fitness and form? Show me training load for the last 42 days."
> 
> *Response:* Training Load Summary with CTL, ATL, TSB, and phase (building/tapering/etc.)

**Checking Intensity Distribution:**
> "Am I doing too much zone 3? Analyze my zone distribution for August."
> 
> *Response:* Zone breakdown with assessment: "Well-polarized" or "Too much tempo work"

**Pre-Race Assessment:**
> "Can I run a half marathon next month? Check my race readiness for 21.1 km."
> 
> *Response:* 0-100 score + breakdown of fitness, freshness, long-run progress, consistency

**Injury-Risk Detection:**
> "Show me my weekly training volume. Am I increasing mileage safely?"
> 
> *Response:* Weekly metrics with distance change %; flags >10% increases

## How It Works

### Training Stress Score (TSS)

For **running**, we use **pace-based rTSS** (running Training Stress Score):

```
Intensity Factor (IF) = Threshold Pace / Activity Pace
rTSS = (hours) × IF² × 100
```

By definition: 1 hour at exactly threshold pace = 100 TSS.

For **other sports** without recent pace calibration, we fall back to **hrTSS** (heart rate based):

```
hrTSS = (hours) × (avg_HR / max_HR)² × 100
```

If no HR data is available, we estimate conservatively:

```
TSS = moving_time_hours × 50
```

**Reference:** Coggan, A. (2020). *Training and Racing with Power*; Dr. T. Stegner's research on rTSS.

### CTL, ATL, TSB (Banister Model)

We use **exponential moving averages** to compute training adaptation:

```
CTL_today = CTL_yesterday + (daily_TSS - CTL_yesterday) / 42
ATL_today = ATL_yesterday + (daily_TSS - ATL_yesterday) / 7
TSB_today = CTL_today - ATL_today
```

- **CTL (Chronic Training Load):** 42-day EMA; represents fitness
- **ATL (Acute Training Load):** 7-day EMA; represents fatigue/readiness
- **TSB (Training Stress Balance):** CTL - ATL; negative = fatigued, positive = fresh

**Training Phases:**
- **Building:** CTL ↑ with manageable fatigue
- **Maintaining:** CTL stable
- **Tapering:** CTL ↓ + TSB ↑ (freshening for a race)
- **Detraining:** CTL ↓ + TSB flat (unintended fitness loss)
- **Overreaching:** CTL ↑ but ATL > CTL × 1.1 (unsustainable)

**Reference:** Banister, E. W., et al. (1975). "Modeling the Training Response in Athletes." *Australian Journal of Sports Medicine*.

### HR Zone Polarization

Training is most effective when **80% of volume is easy (Z1-Z2) and 20% is hard (Z4-Z5)**, minimizing "no man's land" (Z3, tempo).

We calculate a **polarization index** and flag training that violates this principle:
- Easy % < 60% → risk of overtraining
- Z3 % > 30% → "no man's land" trap
- Hard % < 10% → insufficient stimulus

### Race Readiness Scoring

A holistic 0-100 score combining four 0-25 components:

1. **Fitness:** Current CTL vs. target CTL for distance (calibrated from benchmarks)
2. **Freshness:** Current TSB (-30 to +15 optimal range)
3. **Long-Run Readiness:** Longest run in last 21 days vs. target for distance
4. **Consistency:** Training days per week (aim 4+)

## Configuration

User settings are stored in `~/.config/strava-sport-science-mcp/settings.json`:

```json
{
  "max_hr": 190,                    // Maximum heart rate (bpm)
  "resting_hr": 60,                 // Resting heart rate (bpm)
  "threshold_pace_min_per_km": 5.0, // Threshold pace (min/km)
  "weight_kg": 70                   // Body weight (kg)
}
```

These are used to calibrate TSS, HR zones, and race readiness. If the file doesn't exist, defaults are created on first run.

## Development

### Clone and Install

```bash
git clone https://github.com/yourusername/strava-sport-science-mcp.git
cd strava-sport-science-mcp

uv sync --dev
```

### Run Tests

```bash
uv run pytest tests/ -v
```

### Linting & Type Checking

```bash
uv run ruff check src/ tests/
uv run mypy src/
```

### Debug the MCP Server

```bash
# Start the server in debug mode
uv run mcp dev src/strava_sport_science_mcp/server.py

# In another terminal, test with the MCP inspector
# (if you have the inspector installed)
```

### Project Structure

```
src/strava_sport_science_mcp/
├── __init__.py
├── server.py                # MCP server entry point + tool registration
├── strava_client.py         # Async Strava API v3 wrapper
├── auth.py                  # OAuth2 token management
├── config.py                # User settings (max HR, threshold pace, etc.)
├── dependencies.py          # Shared dependency initialization
├── models/
│   ├── activity.py          # Pydantic models for Strava data
│   └── metrics.py           # Pydantic models for computed metrics
└── tools/
    ├── raw.py               # 4 raw Strava tools
    └── sport_science.py     # 4 sport-science computed tools
```

## Contributing

Contributions welcome! Please:

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/amazing-thing`)
3. Write tests for new functionality
4. Run linting and type checks (`ruff check`, `mypy`)
5. Commit with clear messages
6. Push and open a Pull Request

## Roadmap

- [ ] Cycling-specific TSS model (IF with power)
- [ ] Multi-sport periodization plans
- [ ] Peak detection and form forecasting
- [ ] Integration with nutrition/sleep logs
- [ ] Strava segment analysis
- [ ] Custom zone thresholds (LTHR, VDOT)

## Limitations

- **Stream data:** Uses activity-level average HR for zone classification (not second-by-second) to minimize API calls
- **Strava API Rate Limits:** 100 requests per 15 minutes, 1000 per day. The server respects these; check error messages if you hit limits
- **Sport detection:** Assumes activities labeled "Run" use pace-based TSS; others fall back to HR-based or duration-based estimation
- **No power data:** Currently focuses on HR and pace, not power meters

## License

[MIT License](LICENSE) — use freely in commercial and personal projects.

## Acknowledgments

- **MCP Spec:** [Model Context Protocol](https://modelcontextprotocol.io/)
- **Banister Model:** Banister, E. W., et al. (1975)
- **TSS Framework:** Coggan, A.; Hunter Allen & Andy Coggan Consulting
- **Strava API:** [api.strava.com](https://developers.strava.com/)

## Support

Found a bug or have a feature idea? Open an [issue](https://github.com/yourusername/strava-sport-science-mcp/issues).

---

**Built for athletes and coaches who love data.** Train smarter, not just harder.