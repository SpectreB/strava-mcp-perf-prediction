"""User configuration for sport-science calculations."""

import json
from pathlib import Path

from pydantic import BaseModel, Field


class UserConfig(BaseModel):
    """User settings for training metrics."""

    max_hr: int = Field(default=190, description="Maximum heart rate (bpm)")
    resting_hr: int = Field(default=60, description="Resting heart rate (bpm)")
    threshold_pace_min_per_km: float = Field(
        default=5.0, description="Functional threshold pace (min/km)"
    )
    weight_kg: float = Field(default=70, description="Body weight (kg)")
    lthr: int | None = Field(
        default=None,
        description="Lactate threshold heart rate (bpm); estimated as 90% of max_hr if unset",
    )
    ftp_watts: int | None = Field(
        default=None, description="Functional threshold power (W); enables power-based TSS/zones"
    )
    hr_zone_bounds: list[int] | None = Field(
        default=None,
        description=(
            "Upper bounds (bpm) of HR zones 1-4, e.g. from Strava custom zones; "
            "zones are % of max_hr if unset"
        ),
    )

    @property
    def threshold_hr(self) -> float:
        """LTHR if configured, else the common 90%-of-max-HR estimate."""
        return float(self.lthr) if self.lthr else 0.9 * self.max_hr

    @classmethod
    def config_path(cls) -> Path:
        """Get the path to the config file.

        Returns:
            Path to ~/.config/strava-sport-science-mcp/settings.json
        """
        config_dir = Path.home() / ".config" / "strava-sport-science-mcp"
        return config_dir / "settings.json"

    @classmethod
    def load(cls) -> "UserConfig":
        """Load config from file or create with defaults.

        Returns:
            UserConfig instance with values from file or defaults.
        """
        config_path = cls.config_path()

        if config_path.exists():
            with open(config_path) as f:
                data = json.load(f)
            return cls(**data)

        # Create config with defaults
        config = cls()
        config.save()
        return config

    def save(self) -> None:
        """Save config to file.

        Creates the config directory if it doesn't exist.
        """
        config_path = self.config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w") as f:
            json.dump(self.model_dump(), f, indent=2)
