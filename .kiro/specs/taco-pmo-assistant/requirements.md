# Requirements Document

## Introduction

TACO（Task & Communication Optimizer）は、プロジェクトマネージャーの日常業務を自動化するSlackベースのアシスタントです。進捗管理、報告、催促などのノンコア業務を自動化し、PMがクリエイティブな意思決定業務に集中できる環境を提供します。BacklogとSlackを連携させ、自然言語でのタスク問い合わせにも対応する包括的なPMOソリューションです。

## Requirements

### Requirement 1

**User Story:** As a project manager, I want to automatically retrieve task progress from Backlog, so that I can stay updated on project status without manual checking.

#### Acceptance Criteria

1. WHEN the system runs scheduled checks THEN it SHALL retrieve all tasks from configured Backlog projects via API
2. WHEN retrieving tasks THEN the system SHALL identify overdue tasks based on due dates
3. WHEN retrieving tasks THEN the system SHALL identify unassigned or incomplete tasks
4. IF API authentication fails THEN the system SHALL log the error and notify via Slack
5. WHEN processing up to 100 tasks THEN the system SHALL complete retrieval within 5 seconds

### Requirement 2

**User Story:** As a project manager, I want automated daily progress reports posted to Slack at 9 AM, so that the team stays informed without manual reporting.

#### Acceptance Criteria

1. WHEN it is 9:00 AM JST THEN the system SHALL automatically post a progress report to the configured Slack channel
2. WHEN generating reports THEN the system SHALL include overdue tasks with assignee information
3. WHEN generating reports THEN the system SHALL include tasks due within the current week
4. WHEN generating reports THEN the system SHALL format the report in a readable Slack message format
5. IF no tasks require attention THEN the system SHALL post a brief "all clear" status message
6. WHEN posting fails THEN the system SHALL retry up to 3 times with exponential backoff

### Requirement 3

**User Story:** As a project manager, I want team members to be automatically mentioned for their overdue or urgent tasks, so that they are promptly notified without manual follow-up.

#### Acceptance Criteria

1. WHEN a task is overdue THEN the system SHALL mention the assigned team member in Slack
2. WHEN a task is due within 24 hours THEN the system SHALL mention the assigned team member as a reminder
3. WHEN mentioning users THEN the system SHALL map Backlog user IDs to Slack user IDs correctly
4. WHEN no assignee exists THEN the system SHALL mention the project lead or configured fallback user
5. WHEN mentioning THEN the system SHALL include task details and due date information
6. IF user mapping fails THEN the system SHALL post the task information without mention and log the mapping issue

### Requirement 4

**User Story:** As a project manager, I want to ask natural language questions about task status in Slack, so that I can quickly get project insights without navigating multiple tools.

#### Acceptance Criteria

1. WHEN a user asks "今週中のタスクは？" in Slack THEN the system SHALL respond with tasks due this week
2. WHEN a user asks about specific assignees THEN the system SHALL filter and return relevant task information
3. WHEN a user asks about project status THEN the system SHALL provide a summary using GPT-powered natural language processing
4. WHEN processing questions THEN the system SHALL respond within 10 seconds
5. IF the question cannot be understood THEN the system SHALL provide helpful examples of supported queries
6. WHEN generating responses THEN the system SHALL format answers in clear, actionable Slack messages

### Requirement 5

**User Story:** As a system administrator, I want to configure project settings through environment variables, so that the system can be deployed across different environments without code changes.

#### Acceptance Criteria

1. WHEN deploying THEN the system SHALL read Backlog project IDs from environment variables
2. WHEN deploying THEN the system SHALL read Slack workspace and channel configuration from environment variables
3. WHEN deploying THEN the system SHALL securely manage API keys through .env files
4. WHEN configuration is missing THEN the system SHALL fail gracefully with clear error messages
5. WHEN configuration changes THEN the system SHALL reload settings without requiring restart
6. IF invalid configuration is provided THEN the system SHALL validate and report specific configuration errors

### Requirement 6

**User Story:** As a development team, I want the system to be containerized and deployable to cloud platforms, so that it can run reliably in production environments.

#### Acceptance Criteria

1. WHEN packaging THEN the system SHALL be containerized using Docker
2. WHEN deploying THEN the system SHALL be compatible with Render, Heroku, or similar PaaS platforms
3. WHEN running THEN the system SHALL handle up to 100 concurrent tasks efficiently
4. WHEN errors occur THEN the system SHALL log detailed information for debugging
5. WHEN deployed THEN the system SHALL provide health check endpoints for monitoring
6. IF the system fails THEN it SHALL send failure notifications to the configured Slack channel

### Requirement 7

**User Story:** As a project manager, I want to automatically collect progress updates from yesterday's Slack conversations, so that I can capture informal progress reports and blockers shared in chat.

#### Acceptance Criteria

1. WHEN generating daily reports THEN the system SHALL scan previous day's Slack messages for progress indicators
2. WHEN scanning messages THEN the system SHALL identify progress keywords like "完了", "進捗", "ブロック", "遅延"
3. WHEN scanning messages THEN the system SHALL extract task-related updates and link them to Backlog tasks when possible
4. WHEN processing Slack history THEN the system SHALL respect channel permissions and only access configured channels
5. WHEN extracting progress THEN the system SHALL use GPT to summarize key progress points and blockers
6. IF no relevant progress is found THEN the system SHALL note this in the daily report
7. WHEN processing messages THEN the system SHALL handle up to 200 messages from the previous day efficiently

### Requirement 8

**User Story:** As a project manager, I want automated weekly reports generated from daily reports, so that I can provide comprehensive project summaries to stakeholders.

#### Acceptance Criteria

1. WHEN it is Monday at 10:00 AM JST THEN the system SHALL generate a weekly summary report
2. WHEN generating weekly reports THEN the system SHALL aggregate the previous week's daily reports
3. WHEN creating summaries THEN the system SHALL identify trends in task completion and delays
4. WHEN creating summaries THEN the system SHALL highlight recurring blockers and issues
5. WHEN generating weekly reports THEN the system SHALL include metrics like completion rate and overdue task trends
6. WHEN posting weekly reports THEN the system SHALL format them for executive consumption with clear action items
7. IF daily reports are missing THEN the system SHALL note gaps and generate partial summaries from available data

### Requirement 9

**User Story:** As a project manager, I want to collect progress updates during daily sync meetings at 9:00 AM JST, so that I can capture real-time team updates and immediate blockers.

#### Acceptance Criteria

1. WHEN it is 9:00 AM JST on weekdays THEN the system SHALL post a daily sync prompt in the configured channel
2. WHEN posting sync prompts THEN the system SHALL ask team members for their daily updates using a structured format
3. WHEN team members respond THEN the system SHALL collect and parse their progress updates
4. WHEN collecting updates THEN the system SHALL identify completed tasks, current work, and blockers
5. WHEN sync time ends (9:30 AM JST) THEN the system SHALL compile responses into a structured daily sync summary
6. WHEN generating sync summaries THEN the system SHALL cross-reference mentioned tasks with Backlog items
7. IF team members don't respond THEN the system SHALL send gentle reminder mentions
8. WHEN sync collection is complete THEN the system SHALL store the summary for weekly report aggregation

### Requirement 10

**User Story:** As a system administrator, I want secure handling of sensitive API credentials, so that project data remains protected.

#### Acceptance Criteria

1. WHEN storing credentials THEN the system SHALL use environment variables exclusively
2. WHEN logging THEN the system SHALL never log API keys or sensitive tokens
3. WHEN communicating with APIs THEN the system SHALL use HTTPS connections only
4. WHEN handling Slack tokens THEN the system SHALL follow Slack's security best practices
5. WHEN handling Backlog tokens THEN the system SHALL follow Backlog's API security guidelines
6. IF credential validation fails THEN the system SHALL provide generic error messages without exposing credential details