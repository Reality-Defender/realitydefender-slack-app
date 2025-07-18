# Reality Defender Slack App

A Slack bot that integrates with Reality Defender's deepfake detection platform to analyze media content for
authenticity directly within your Slack workspace.

## Overview

The Reality Defender Slack App enables teams to quickly verify the authenticity of images, videos, and audio files
shared in Slack channels. Using Reality Defender's advanced AI-powered detection
technology[[1]](https://www.realitydefender.com/), the app identifies potential deepfakes and manipulated content,
helping organizations protect against disinformation and maintain trust in their communications.

## Features

- **Real-time Analysis**: Analyze media files directly from Slack messages using the right-click context menu
- **Multiple File Formats**: Supports JPG, JPEG, PNG, and MP4 files, among others.
- **Asynchronous Processing**: Non-blocking analysis that allows continued Slack usage while processing

## Architecture

The application is built with:

- **Python 3.12+**: Modern async/await patterns for concurrent operations
- **Slack Bolt**: Official Slack SDK for Python with socket mode support
- **Reality Defender SDK**: Integration with Reality Defender's detection API
- **Pydantic**: Configuration management and data validation
- **Docker**: Containerized deployment for easy scaling
- **UV**: Package and project management

## Installation

### Prerequisites

- Python 3.12 or higher
- UV
- A Slack workspace with admin permissions
- Reality Defender API access

### Local Development

1. **Clone the repository**:
   ```bash
   git clone https://github.com/reality-defender/slack-app.git
   cd slack-app
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

3. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your Slack tokens
   ```

4. **Run the application**:
   ```bash
   uv run ./src/reality_defender_slack_app/__init__.py
   ```

### Docker Deployment

1. **Build the container**:
   ```bash
   docker build -t reality-defender-slack-app .
   ```

2. **Run with environment variables**:
   ```bash
   docker run -d \
     -e SLACK_BOT_TOKEN=your-bot-token \
     -e SLACK_APP_TOKEN=your-app-token \
     -e LOG_LEVEL=INFO \
     reality-defender-slack-app
   ```

### Docker Compose

```bash
docker-compose up -d
```

## Basic Slack usage

- Register your Reality Defender API key with the `/setup-rd <your key>` command.
- Click on `More options` in any message containing supported media types in Slack, then click on `Analyze media`.
- Type `/analysis-status` to see the status of any ongoing media analysis.