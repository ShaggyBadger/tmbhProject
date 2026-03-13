# The Ten Minute Bible Hour Podcast Archive & Prose Engine

A comprehensive Python application for archiving "The Ten Minute Bible Hour Podcast," transcribing episodes, and using a multi-agent AI pipeline to convert spoken transcripts into high-quality, book-ready prose. It features a "Tactical Terminal" interface and a "Trust but Verify" editing workflow.

## Project Overview

This tool automates the entire podcast workflow:
1.  **Collection:** Fetches RSS feed data and stores metadata in a local SQLite database.
2.  **Archival:** Downloads and organizes MP3 audio files.
3.  **Transcription:** Deploys audio to an external Whisper AI server for high-accuracy transcription.
4.  **Prose Conversion:** Transforms raw transcripts into polished manuscripts using a multi-stage AI pipeline.

## Key Features

### Tactical Podcast Editing Pipeline
A sophisticated, multi-agent system designed to produce "book-ready" prose with a 100-point quality guarantee.

*   **Multi-Agent Strategy:**
    *   **Gemini (Google Cloud):** Handles high-accuracy tasks like formatting, extracting primary Bible texts, and the final polish.
    *   **Ollama (llama3.2:3b):** local LLM used for surgical paragraph editing (Discipline Mode) and nuanced evaluation.
*   **"Trust but Verify" Quality Control:**
    *   **3-Attempt Refinement Loop:** Ollama attempts to edit a paragraph up to 3 times. If the quality score is < 7/10, it retries with a critique.
    *   **Manual Intervention:** Automatically pauses for user override if 3 attempts fail, ensuring no bad prose slips through.
    *   **Vibe Code Sanitization:** Strict regex cleaning removes LLM artifacts (like "Here is the refined text:") and enforces structural discipline.
    *   **Pipeline Audit:** Generates a detailed report and a final Process Quality Score for every episode.

### robust Architecture
*   **Idempotency:** Progress is tracked paragraph-by-paragraph in a local JSON state file (`job_data.json`), allowing the pipeline to resume exactly where it left off after an interruption.
*   **Tactical TUI:** A high-contrast, military-themed terminal interface built with `rich`, featuring real-time status labels, progress bars, and combat-style alerts.
*   **Database-Backed:** All metadata and processing states are persisted in SQLite using SQLAlchemy.

## Installation

### Prerequisites
*   Python 3.10+
*   Google Gemini API Key
*   Ollama (running locally with `llama3.2:3b` model pulled)
*   FFmpeg (for audio processing)

### Setup
1.  Clone the repository:
    ```bash
    git clone https://github.com/yourusername/tmbhProject.git
    cd tmbhProject
    ```

2.  Create and activate a virtual environment:
    ```bash
    python3 -m venv venvFiles
    source venvFiles/bin/activate
    ```

3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

4.  Configure Environment Variables:
    Create a `.env` file in the project root with your API keys:
    ```
    GOOGLE_API_KEY=your_gemini_api_key
    # Add other necessary keys
    ```

## Usage

### Quick Start
Run the main application using the provided helper script:
```bash
./start.sh
```
Or manually:
```bash
cd main
python3 main.py
```

### Main Menu Operations
The interactive TUI guides you through the workflow:

1.  **Collect Metadata:** Update the local database with the latest RSS feed entries.
2.  **Download Audio:** Fetch MP3 files for new episodes.
3.  **Deploy for Processing:** Send audio to the transcription server.
4.  **Recover Transcripts:** Retrieve completed transcripts from the server.
5.  **Process Manuscripts:** Launch the **Tactical Podcast Editing Pipeline** to generate prose.

## Directory Structure

*   `main/`: Core application logic.
    *   `main.py`: Entry point and TUI controller.
    *   `processor/`: The heart of the editing pipeline (services, models, config).
        *   `services/controller.py`: Orchestrates the multi-stage editing workflow.
    *   `models.py`: SQLAlchemy database models.
*   `podcast_files/`: Storage for downloaded audio, transcripts, and final manuscripts.
*   `venvFiles/`: Virtual environment directory.

## Contributing

This is a personal project optimized for a specific workflow. Contributions are welcome, especially for adding new LLM providers or improving the "Vibe Code" heuristics.

## License

[MIT License](LICENSE)
