from dataclasses import dataclass


@dataclass
class ProcessorConfig:
    # Rich Spinner settings
    spinner_type: str = "dots12"
    spinner_color: str = "bright_green"

    # Tactical / Matrix Theme Colors
    primary: str = "bold green"  # Classic Terminal Green
    secondary: str = "bold spring_green3"  # Brighter accent
    success: str = "bold green1"  # Success Green
    warning: str = "bold dark_orange"  # Tactical Alert Amber
    status_in_progress: str = "bold yellow"  # In Progress Amber
    error: str = "bold red"  # Combat Red
    info: str = "italic sea_green3"  # Faded data stream
    header: str = "bold green on black"  # Tactical Header

    # UI Elements
    panel_border: str = "green"

    # Pipeline specific
    job_data_file: str = "job_data.json"


# Global instance for easy access
config = ProcessorConfig()
