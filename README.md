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
   - Create a new app with **Authorization Callback Domain** set to `localhost`
   - Note your **Client ID** and **Client Secret**

2. **Add them to a `.env` file** (gitignored):
   ```bash
   cp .env.example .env   # then fill in STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET
   ```

3. **Run the setup command:**
   ```bash
   uv run strava-sport-science-setup
   ```
   It opens Strava's authorization page in your browser, catches the redirect on
   `http://localhost:8722`, stores the refresh token in `.env`, then calibrates your
   settings from your activities (see [Configuration](#configuration)).
   Steps can be run separately: `... setup auth` (add `--manual` to paste the redirect
   URL instead) and `... setup calibrate --dry-run`.

### Install

Not yet published on PyPI; run it from a clone:

```bash
git clone https://github.com/SpectreB/strava-mcp-perf-prediction.git
cd strava-mcp-perf-prediction
uv sync
```

### Configure

The server reads `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET` and `STRAVA_REFRESH_TOKEN`
from the environment. It does not load `.env` by itself; pass it with uv's `--env-file`:

```bash
claude mcp add strava-sport-science -- \
  uv --directory /path/to/strava-sport-science-mcp \
  run --env-file /path/to/strava-sport-science-mcp/.env strava-sport-science-mcp
```

### Use with Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows), using absolute paths (Claude Desktop does not inherit your shell's `PATH`; find uv with `which uv`):

```json
{
  "mcpServers": {
    "strava-sport-science": {
      "command": "/absolute/path/to/uv",
      "args": [
        "--directory", "/absolute/path/to/strava-mcp-perf-prediction",
        "run", "--env-file", "/absolute/path/to/strava-mcp-perf-prediction/.env",
        "strava-sport-science-mcp"
      ]
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
| **get_training_load** | CTL/ATL/TSB analysis | `days` (default 42), `end_date` | "Am I overtraining? Analyze my fatigue." |
| **get_zone_distribution** | Intensity zone breakdown | `days` (default 30), `end_date`, `use_streams` | "Am I training easy enough? Show zones." |
| **get_fitness_trend** | Weekly volume/intensity | `weeks` (default 8), `end_date` | "How has my training progressed?" |
| **get_race_readiness** | Race readiness score | `target_distance_km` (default 10), `end_date` | "Am I ready for a 10K this weekend?" |

All sport-science tools accept `end_date` (`YYYY-MM-DD`) to analyze a past period, e.g. "How was my form on June 7, 2026?"

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

### Data pipeline: best source first, with fallbacks

Each activity is analyzed with the most precise data it offers; coarser data is used only when better data is missing. Outputs report what was used (`tss_methods`, `data_sources`, `data_quality`) so the assistant can say how reliable a result is.

| Metric | 1. Best case | 2. | 3. | Last resort |
|---|---|---|---|---|
| **TSS** | Power: NP / FTP (power meter + `ftp_watts`) | Pace: runs, speed / threshold speed | Heart rate: HR reserve vs LTHR | Duration (50 TSS/h) |
| **Zones** | Power stream (second by second) | Heart-rate stream | Pace stream (runs) | Activity average: power > HR > pace |
| **HR zone bounds** | Your custom Strava zones | % of max HR | | |

### Training Stress Score (TSS)

Every method uses `TSS = hours × IF² × 100`, so one hour at threshold = 100 TSS. Only the intensity factor (IF) changes:

```
Power:       IF = normalized power / FTP
Pace (runs): IF = activity speed / threshold speed   (= threshold pace / activity pace)
Heart rate:  IF = (avg HR − resting HR) / (LTHR − resting HR)   (LTHR defaults to 90% of max HR)
```

Without any intensity data, a moderate effort is assumed: `TSS = hours × 50`.

**References:** Allen, H. & Coggan, A. *Training and Racing with a Power Meter* (TSS, NP, IF); rTSS and hrTSS follow the same model with pace and heart rate.

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

### Intensity Zones and Polarization

All zone models map to the same 5 intensity levels, so activities measured differently can be aggregated:

| Zone | Heart rate (% max HR) | Pace (Friel, % of threshold pace) | Power (Coggan, % FTP) |
|---|---|---|---|
| Z1 Recovery | < 60% | slower than 129% | < 55% |
| Z2 Aerobic | 60–70% | 114–129% | 55–75% |
| Z3 Tempo | 70–80% | 106–114% | 75–90% |
| Z4 Threshold | 80–90% | 99–106% | 90–105% |
| Z5 VO2max | ≥ 90% | faster than 99% | ≥ 105% |

Stream-based zones count each second of moving time; average-based zones put the whole session in one zone, which hides intervals. Streams are cached in `~/.cache/strava-sport-science-mcp/streams` (an activity's streams never change), and at most 50 are downloaded per call to stay within Strava's rate limits.

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
  "max_hr": 190,
  "resting_hr": 60,
  "threshold_pace_min_per_km": 5.0,
  "weight_kg": 70,
  "lthr": null,
  "ftp_watts": null,
  "hr_zone_bounds": null
}
```

These are used to calibrate TSS, HR zones, and race readiness. If the file doesn't exist, defaults are created on first run.

`strava-sport-science-setup calibrate` estimates them from your Strava data:

| Setting | How it is estimated |
|---|---|
| `threshold_pace_min_per_km` | Best 60-minute-equivalent pace (Riegel's formula) over runs of 15+ min from the last year. Training runs make it conservative; set it to a recent all-out 10K–half pace if you know it. |
| `max_hr` | Highest `max_heartrate` recorded in your activities (a lower bound). Kept unchanged if no activity has heart-rate data. |
| `weight_kg` | From your Strava profile (requires the `profile:read_all` scope). |
| `ftp_watts` | From your Strava profile, if set. Enables power-based TSS and zones. |
| `hr_zone_bounds` | Upper bounds (bpm) of Z1–Z4 from your **custom** Strava HR zones. Strava's default zones are age-based, so they are ignored and zones fall back to % of `max_hr`. |
| `resting_hr`, `lthr` | Not available from Strava; edit manually. `lthr` defaults to 90% of `max_hr`. |

## Development

### Clone and Install

```bash
git clone https://github.com/SpectreB/strava-mcp-perf-prediction.git
cd strava-mcp-perf-prediction

uv sync --extra dev
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
├── setup_cli.py             # `strava-sport-science-setup`: OAuth + settings calibration
├── stream_cache.py          # On-disk cache for activity streams
├── models/
│   ├── activity.py          # Pydantic models for Strava data
│   └── metrics.py           # Pydantic models for computed metrics
└── tools/
    ├── raw.py               # 4 raw Strava tools
    ├── intensity.py         # TSS and zone pipeline with data-source fallbacks
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

- [x] Cycling-specific TSS model (IF with power)
- [x] Custom zone thresholds (Strava custom HR zones, LTHR, FTP)
- [ ] Grade-adjusted pace for hilly runs
- [ ] Multi-sport periodization plans
- [ ] Peak detection and form forecasting
- [ ] Integration with nutrition/sleep logs
- [ ] Strava segment analysis

## Limitations

- **Strava API rate limits:** 100 requests per 15 minutes, 1,000 per day. Stream downloads are capped per call and cached; when the limit is hit, zones fall back to activity averages and `data_quality` says so
- **Pace ignores terrain:** run TSS and pace zones use raw speed, so hilly runs are under-rated (no grade adjustment yet)
- **TSS uses activity averages:** stream data refines zones but not yet TSS
- **Low-volume training:** with infrequent sessions, each run moves ATL far more than CTL, so phase labels such as "overreaching" can appear at very low absolute load

## License

[MIT License](LICENSE) — use freely in commercial and personal projects.

## Acknowledgments

- **MCP Spec:** [Model Context Protocol](https://modelcontextprotocol.io/)
- **Banister Model:** Banister, E. W., et al. (1975)
- **TSS Framework:** Coggan, A.; Hunter Allen & Andy Coggan Consulting
- **Strava API:** [api.strava.com](https://developers.strava.com/)

## Support

Found a bug or have a feature idea? Open an [issue](https://github.com/SpectreB/strava-mcp-perf-prediction/issues).

---

**Built for athletes and coaches who love data.** Train smarter, not just harder.