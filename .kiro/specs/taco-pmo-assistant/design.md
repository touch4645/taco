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
        VCS[Version Control APIs]
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
            CS[Commit Service]
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
        WEBHOOKS[VCS Webhooks]
    end

    CRON --> SCH
    SLACK_EVENTS --> BOT
    API_CALLS --> API
    WEBHOOKS --> CS

    SCH --> TS
    SCH --> RS
    SCH --> NS
    SCH --> CS

    BOT --> QS
    BOT --> TS

    TS --> BL
    NS --> SL
    QS --> AI
    RS --> CACHE
    CS --> VCS
    CS --> BL

    API --> CONFIG
    SCH --> CONFIG
    BOT --> CONFIG
    CS --> CONFIG
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

@dataclass
class ProjectWikiEntry:
    key: str
    title: str
    content: str
    category: str
    tags: List[str]
    created_by: str
    created_at: datetime
    updated_at: datetime
    source_reference: Optional[str] = None
    
@dataclass
class TeamMember:
    name: str
    role: str
    backlog_user_id: Optional[str]
    slack_user_id: Optional[str]
    email: Optional[str]
    responsibilities: List[str]
    expertise: List[str]
    
@dataclass
class ProjectInfo:
    name: str
    description: str
    start_date: date
    end_date: Optional[date]
    goals: List[str]
    success_criteria: List[str]
    stakeholders: List[str]
    team_members: List[TeamMember]
    key_milestones: List[Dict[str, Any]]
    terminology: Dict[str, str]
    standards: List[str]
    guidelines: List[str]
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
    cached_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    description TEXT,
    project_name TEXT
);

-- Daily reports for weekly aggregation
CREATE TABLE daily_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date DATE NOT NULL UNIQUE,
    report_data JSON NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Weekly reports for monthly aggregation
CREATE TABLE weekly_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    report_data JSON NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(week_start, week_end)
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

-- Project Wiki entries
CREATE TABLE project_wiki (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    category TEXT NOT NULL,
    tags TEXT NOT NULL, -- JSON array
    created_by TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    source_reference TEXT,
    project_id TEXT NOT NULL,
    UNIQUE(key, project_id)
);

-- Team members
CREATE TABLE team_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    backlog_user_id TEXT,
    slack_user_id TEXT,
    email TEXT,
    responsibilities TEXT, -- JSON array
    expertise TEXT, -- JSON array
    project_id TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(backlog_user_id, project_id),
    UNIQUE(slack_user_id, project_id)
);

-- Project information
CREATE TABLE project_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    goals TEXT NOT NULL, -- JSON array
    success_criteria TEXT NOT NULL, -- JSON array
    stakeholders TEXT NOT NULL, -- JSON array
    key_milestones TEXT NOT NULL, -- JSON object
    terminology TEXT NOT NULL, -- JSON object
    standards TEXT NOT NULL, -- JSON array
    guidelines TEXT NOT NULL, -- JSON array
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Slack progress updates
CREATE TABLE slack_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    task_reference TEXT,
    content TEXT NOT NULL,
    sentiment TEXT NOT NULL,
    extracted_at DATETIME NOT NULL,
    message_ts TEXT,
    channel_id TEXT,
    user_name TEXT
);

-- Daily sync updates
CREATE TABLE sync_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    completed_yesterday TEXT NOT NULL, -- JSON array
    planned_today TEXT NOT NULL, -- JSON array
    blockers TEXT NOT NULL, -- JSON array
    submitted_at DATETIME NOT NULL,
    user_name TEXT
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
### 8. Commit Service (`services/commit_service.py`)

**Responsibilities:**
- Version control system API統合（BitBucket, GitHub, GitLab）
- コミット履歴の取得と解析
- チケット参照の抽出と検証
- コミット統計の生成

**Key Methods:**
```python
def fetch_repository_commits(repo_url: str, since: datetime) -> List[Commit]
def extract_ticket_references(commit_message: str) -> List[str]
def verify_ticket_references(ticket_ids: List[str]) -> Dict[str, TicketStatus]
def analyze_commit_patterns(commits: List[Commit]) -> CommitAnalysis
def generate_commit_report(analysis: CommitAnalysis) -> CommitReport
```

**Data Models:**
```python
@dataclass
class Commit:
    id: str
    author: str
    message: str
    timestamp: datetime
    repository: str
    branch: str
    files_changed: List[str]
    ticket_references: List[str] = field(default_factory=list)
    
@dataclass
class CommitAnalysis:
    total_commits: int
    commits_with_tickets: int
    commits_without_tickets: int
    tickets_referenced: List[str]
    authors_stats: Dict[str, AuthorStats]
    significant_files_without_tickets: List[str]
    
@dataclass
class AuthorStats:
    total_commits: int
    commits_with_tickets: int
    commits_without_tickets: int
    
@dataclass
class CommitReport:
    date: date
    analysis: CommitAnalysis
    recommendations: List[str]
    alerts: List[str]
```

## Additional Database Schema

```sql
-- Repository configuration
CREATE TABLE repositories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    type TEXT NOT NULL, -- github, bitbucket, gitlab
    branch TEXT NOT NULL DEFAULT 'main',
    api_token TEXT,
    project_id TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(url, project_id)
);

-- Commit history
CREATE TABLE commits (
    id TEXT PRIMARY KEY,
    repository_id INTEGER NOT NULL,
    author TEXT NOT NULL,
    message TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    branch TEXT NOT NULL,
    files_changed TEXT NOT NULL, -- JSON array
    ticket_references TEXT, -- JSON array
    has_valid_ticket BOOLEAN NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (repository_id) REFERENCES repositories(id)
);

-- Commit analysis reports
CREATE TABLE commit_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date DATE NOT NULL,
    repository_id INTEGER NOT NULL,
    report_data JSON NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(report_date, repository_id),
    FOREIGN KEY (repository_id) REFERENCES repositories(id)
);

-- Ticket reference patterns
CREATE TABLE ticket_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    pattern TEXT NOT NULL,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, pattern)
);
```

## Version Control Integration

### BitBucket API Integration

```python
class BitBucketClient:
    def __init__(self, workspace: str, repo_slug: str, api_token: str):
        self.base_url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo_slug}"
        self.auth_header = {"Authorization": f"Bearer {api_token}"}
        
    def get_commits(self, since: datetime, branch: str = "main") -> List[Dict]:
        # ISO 8601形式で日付をフォーマット
        since_str = since.isoformat()
        url = f"{self.base_url}/commits/{branch}"
        params = {"since": since_str}
        
        # ページネーション処理を含む実装
        # ...
        
    def get_commit_details(self, commit_hash: str) -> Dict:
        url = f"{self.base_url}/commit/{commit_hash}"
        # ...
        
    def get_diff(self, commit_hash: str) -> Dict:
        url = f"{self.base_url}/diff/{commit_hash}"
        # ...
```

### GitHub API Integration

```python
class GitHubClient:
    def __init__(self, owner: str, repo: str, api_token: str):
        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"
        self.auth_header = {"Authorization": f"token {api_token}"}
        
    def get_commits(self, since: datetime, branch: str = "main") -> List[Dict]:
        # ISO 8601形式で日付をフォーマット
        since_str = since.isoformat()
        url = f"{self.base_url}/commits"
        params = {"since": since_str, "sha": branch}
        
        # ページネーション処理を含む実装
        # ...
        
    def get_commit_details(self, commit_hash: str) -> Dict:
        url = f"{self.base_url}/commits/{commit_hash}"
        # ...
        
    def get_pull_requests(self, state: str = "all") -> List[Dict]:
        url = f"{self.base_url}/pulls"
        params = {"state": state}
        # ...
```

### Ticket Reference Extraction

```python
class TicketReferenceExtractor:
    def __init__(self, patterns: List[str]):
        self.patterns = [re.compile(pattern) for pattern in patterns]
        
    def extract_references(self, text: str) -> List[str]:
        references = []
        for pattern in self.patterns:
            matches = pattern.findall(text)
            references.extend(matches)
        return list(set(references))  # 重複を除去
        
    @classmethod
    def from_project(cls, project_id: str) -> "TicketReferenceExtractor":
        # プロジェクトに設定されたパターンを取得
        patterns = get_ticket_patterns(project_id)
        return cls(patterns)
```

### Commit Analysis

```python
class CommitAnalyzer:
    def __init__(self, task_service: TaskService):
        self.task_service = task_service
        
    def analyze_commits(self, commits: List[Commit]) -> CommitAnalysis:
        # コミット分析ロジック
        # ...
        
    def verify_ticket_references(self, references: List[str]) -> Dict[str, bool]:
        # チケット参照の検証
        # ...
        
    def detect_significant_changes(self, files_changed: List[str]) -> bool:
        # 重要なファイル変更の検出
        # ...
        
    def generate_recommendations(self, analysis: CommitAnalysis) -> List[str]:
        # 推奨事項の生成
        # ...
```