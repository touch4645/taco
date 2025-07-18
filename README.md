# TACO - Task & Communication Optimizer

TACO (Task & Communication Optimizer) is a Slack-based PMO assistant that automates project management workflows by integrating Backlog task management with Slack communication.

## Features

- Automatic task progress retrieval from Backlog
- Daily progress reports posted to Slack at 9 AM JST
- Automatic mentions for team members with overdue or urgent tasks
- Natural language queries about task status in Slack
- Weekly report generation from daily reports
- Progress extraction from Slack conversations
- Daily sync meeting facilitation

## Getting Started

### Prerequisites

- Python 3.11+
- Slack workspace with admin privileges
- Backlog account with API access
- Gemini API key or AWS Bedrock access

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/taco.git
cd taco
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

3. Copy the example environment file and fill in your values:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Run the application:
```bash
python main.py
```

## Configuration

TACO is configured using environment variables, which can be set in a `.env` file:

- `BACKLOG_SPACE_KEY`: Your Backlog space key
- `BACKLOG_API_KEY`: Your Backlog API key
- `BACKLOG_PROJECT_IDS`: Comma-separated list of Backlog project IDs

- `SLACK_BOT_TOKEN`: Your Slack bot token (xoxb-*)
- `SLACK_APP_TOKEN`: Your Slack app token (xapp-*)
- `SLACK_CHANNEL_ID`: The Slack channel ID for reports
- `SLACK_ADMIN_USER_ID`: The Slack user ID of the admin

- `AI_PROVIDER`: AI provider to use (gemini or bedrock)
- `AI_API_KEY`: API key for the AI provider
- `AI_MODEL`: Model name to use

- `TIMEZONE`: Timezone for scheduling (default: Asia/Tokyo)
- `LOG_LEVEL`: Logging level (default: INFO)
- `DATABASE_URL`: Database URL (default: sqlite:///taco.db)
- `CACHE_TTL_MINUTES`: Cache TTL in minutes (default: 30)

## Project Structure

```
taco/
├── api/            # FastAPI endpoints
├── bot/            # Slack bot handlers
├── config/         # Configuration settings
├── models/         # Data models
├── services/       # Business logic services
└── utils/          # Utility functions
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.