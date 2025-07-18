# TACO Design Document

## Overview

TACO (Task & Communication Optimizer) is a Slack-based PMO assistant that automates project management workflows by integrating Backlog task management with Slack communication. The system operates as a FastAPI-based microservice with scheduled jobs, real-time Slack interactions, and AI-powered natural language processing.

The architecture follows a modular design with clear separation between external integrations (Backlog, Slack, Gemini/Bedrock), core business logic, and data persistence. The system is designed to be stateless where possible, with minimal local storage for caching and configuration.

## Architecture

### High-Level Architecture

```mermaid
graph TB
    subgraph "External Services"
        BL[Backlog API]
        SL[Slack API]
        AI[Gemini/Bedrock API]
    end
    
    subgraph "TACO System"
        API[FastAPI Server]
        SCH[Scheduler Service]
        BOT[Slack Bot Handler]
        
        subgraph "Core Services"
            TS[Task Service]
            RS[Report Service]
            NS[Notification Service]
            QS[Query Service]
        end
        
        subgraph "Data Layer"
            CACHE[(SQLite Cache)]
            CONFIG[Environment Config]
        end
    end
    
    subgraph "Triggers"
        CRON[Cron Jobs]
        SLACK_EVENTS[Slack Events]
        API_CALLS[API Requests]
    end
    
    CRON --> SCH
    SLACK_EVENTS --> BOT
    API_CALLS --> API
    
    SCH --> TS
    SCH --> RS
    SCH --> NS
    
    BOT --> QS
    BOT --> TS
    
    TS --> BL
    NS --> SL
    QS --> AI
    RS --> CACHE
    
    API --> CONFIG
    SCH --> CONFIG
    BOT --> CONFIG
```

### Component Interaction Flow

```mermaid
sequenceDiagram
    participant C as Cron Scheduler
    participant TS as Task Service
    participant BL as Backlog API
    participant RS as Report Service
    participant NS as Notification Service
    participant SL as Slack API
    
    Note over C: Daily 9:00 AM JST
    C->>TS: Fetch latest tasks
    TS->>BL: GET /api/v2/projects/{id}/issues
    BL-->>TS: Task data
    TS->>RS: Generate daily report
    RS->>NS: Send report to Slack
    NS->>SL: POST message with mentions
    
    Note over C: Weekly Monday 10:00 AM JST  
    C->>RS: Generate weekly summary
    RS->>RS: Aggregate daily reports
    RS->>NS: Send weekly report
    NS->>SL: POST weekly summary
```

## Components and Interfaces

### 1. FastAPI Server (`main.py`)

**Responsibilities:**
- HTTP API endpoints for health checks and manual triggers
- Application lifecycle management
- Dependency injection setup

**Key Endpoints:**
```python
GET /health - System health check
POST /trigger/daily-report - Manual daily report trigger
POST /trigger/weekly-report - Manual weekly report trigger
GET /config/status - Configuration validation status
```

### 2. Scheduler Service (`services/scheduler.py`)

**Responsibilities:**
- Cron job management using APScheduler
- Timezone handling (JST)
- Job failure handling and retry logic

**Key Methods:**
```python
def schedule_daily_sync() -> None
def schedule_daily_report() -> None  
def schedule_weekly_report() -> None
def handle_job_failure(job_id: str, exception: Exception) -> None
```

### 3. Task Service (`services/task_service.py`)

**Responsibilities:**
- Backlog API integration
- Task data processing and filtering
- Cache management for task data

**Key Methods:**
```python
def fetch_project_tasks(project_id: str) -> List[Task]
def get_overdue_tasks() -> List[Task]
def get_tasks_due_this_week() -> List[Task]
def map_backlog_user_to_slack(backlog_user_id: str) -> Optional[str]
```

**Data Models:**
```python
@dataclass
class Task:
    id: str
    summary: str
    assignee_id: Optional[str]
    due_date: Optional[datetime]
    status: TaskStatus
    priority: Priority
    created: datetime
    updated: datetime
```

### 4. Report Service (`services/report_service.py`)

**Responsibilities:**
- Daily and weekly report generation
- Slack message formatting
- Progress trend analysis

**Key Methods:**
```python
def generate_daily_report(tasks: List[Task], slack_progress: List[SlackMessage]) -> DailyReport
def generate_weekly_report(daily_reports: List[DailyReport]) -> WeeklyReport
def format_slack_message(report: Union[DailyReport, WeeklyReport]) -> SlackMessage
```

### 5. Notification Service (`services/notification_service.py`)

**Responsibilities:**
- Slack message posting
- User mention handling
- Message formatting and retry logic

**Key Methods:**
```python
def post_daily_report(report: DailyReport) -> bool
def post_weekly_report(report: WeeklyReport) -> bool
def mention_user_for_task(user_id: str, task: Task) -> bool
def send_sync_prompt() -> bool
```

### 6. Query Service (`services/query_service.py`)

**Responsibilities:**
- Natural language query processing
- GPT integration for intelligent responses
- Context-aware task filtering

**Key Methods:**
```python
def process_natural_language_query(query: str, context: QueryContext) -> str
def extract_query_intent(query: str) -> QueryIntent
def format_task_response(tasks: List[Task], intent: QueryIntent) -> str
```

### 7. Slack Bot Handler (`bot/slack_handler.py`)

**Responsibilities:**
- Slack event handling
- Message parsing and routing
- Interactive component handling

**Key Methods:**
```python
def handle_message_event(event: SlackMessageEvent) -> None
def handle_sync_response(user_id: str, response: str) -> None
def collect_daily_sync_updates() -> List[SyncUpdate]
```

## Data Models

### Core Data Structures

```python
@dataclass
class SlackMessage:
    channel_id: str
    user_id: str
    text: str
    timestamp: datetime
    thread_ts: Optional[str] = None

@dataclass
class DailyReport:
    date: date
    overdue_tasks: List[Task]
    due_today: List[Task]
    due_this_week: List[Task]
    slack_progress: List[ProgressUpdate]
    sync_updates: List[SyncUpdate]
    completion_rate: float

@dataclass
class WeeklyReport:
    week_start: date
    week_end: date
    daily_reports: List[DailyReport]
    trends: TrendAnalysis
    key_achievements: List[str]
    blockers: List[str]
    recommendations: List[str]

@dataclass
class ProgressUpdate:
    user_id: str
    task_reference: Optional[str]
    content: str
    sentiment: str  # positive, neutral, negative
    extracted_at: datetime

@dataclass
class SyncUpdate:
    user_id: str
    completed_yesterday: List[str]
    planned_today: List[str]
    blockers: List[str]
    submitted_at: datetime
```

### Database Schema (SQLite)

```sql
-- Task cache for performance
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    assignee_id TEXT,
    due_date DATETIME,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    cached_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Daily reports for weekly aggregation
CREATE TABLE daily_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date DATE NOT NULL UNIQUE,
    report_data JSON NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- User mapping between Backlog and Slack
CREATE TABLE user_mappings (
    backlog_user_id TEXT PRIMARY KEY,
    slack_user_id TEXT NOT NULL,
    display_name TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Configuration cache
CREATE TABLE config_cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## Error Handling

### Error Categories and Strategies

1. **API Integration Errors**
   - Backlog API failures: Retry with exponential backoff, fallback to cached data
   - Slack API failures: Queue messages for retry, notify via alternative channel
   - OpenAI API failures: Provide fallback responses, log for manual review

2. **Data Processing Errors**
   - Invalid task data: Log and skip, continue processing remaining tasks
   - User mapping failures: Use fallback mention strategy, log for manual mapping
   - Report generation failures: Generate partial reports, notify administrators

3. **Scheduling Errors**
   - Job execution failures: Retry with backoff, alert via Slack if critical
   - Timezone issues: Validate and log, use UTC as fallback
   - Resource constraints: Implement circuit breaker pattern

### Error Response Format

```python
@dataclass
class ErrorResponse:
    error_code: str
    message: str
    details: Optional[Dict[str, Any]]
    timestamp: datetime
    correlation_id: str

class ErrorHandler:
    def handle_api_error(self, error: Exception, context: str) -> ErrorResponse
    def handle_processing_error(self, error: Exception, data: Any) -> ErrorResponse
    def notify_critical_error(self, error: ErrorResponse) -> None
```

## Testing Strategy

### Unit Testing
- **Service Layer**: Mock external APIs, test business logic isolation
- **Data Models**: Validate serialization, edge cases, constraints
- **Utilities**: Date/time handling, text processing, configuration parsing

### Integration Testing
- **API Endpoints**: Test full request/response cycles
- **External Services**: Test with sandbox/staging environments
- **Database Operations**: Test CRUD operations, migrations, constraints

### End-to-End Testing
- **Scheduled Jobs**: Test complete workflow from trigger to Slack posting
- **Interactive Flows**: Test Slack bot interactions and responses
- **Error Scenarios**: Test failure modes and recovery mechanisms

### Test Data Management
```python
# Test fixtures for consistent testing
@pytest.fixture
def sample_tasks():
    return [
        Task(id="TASK-1", summary="Test task", assignee_id="user1", 
             due_date=datetime.now() + timedelta(days=1), 
             status=TaskStatus.IN_PROGRESS, priority=Priority.HIGH),
        # Additional test tasks...
    ]

@pytest.fixture
def mock_slack_client():
    with patch('slack_sdk.WebClient') as mock:
        yield mock

@pytest.fixture
def mock_backlog_client():
    with patch('requests.Session') as mock:
        yield mock
```

### Performance Testing
- **Load Testing**: Simulate 100+ concurrent tasks processing
- **Memory Testing**: Monitor memory usage during report generation
- **API Rate Limiting**: Test behavior under API rate limits

## Deployment and Configuration

### Environment Variables
```bash
# Backlog Configuration
BACKLOG_SPACE_KEY=your-space
BACKLOG_API_KEY=your-api-key
BACKLOG_PROJECT_IDS=PROJECT1,PROJECT2

# Slack Configuration  
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_CHANNEL_ID=C1234567890
SLACK_ADMIN_USER_ID=U1234567890

# OpenAI Configuration
OPENAI_API_KEY=sk-your-openai-key
OPENAI_MODEL=gpt-3.5-turbo

# System Configuration
TIMEZONE=Asia/Tokyo
LOG_LEVEL=INFO
DATABASE_URL=sqlite:///taco.db
CACHE_TTL_MINUTES=30
```

### Docker Configuration
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Health Monitoring
```python
@dataclass
class HealthStatus:
    status: str  # healthy, degraded, unhealthy
    services: Dict[str, ServiceHealth]
    timestamp: datetime

class HealthChecker:
    def check_backlog_connectivity(self) -> ServiceHealth
    def check_slack_connectivity(self) -> ServiceHealth  
    def check_database_connectivity(self) -> ServiceHealth
    def check_openai_connectivity(self) -> ServiceHealth
```