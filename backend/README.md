# PapersWithCode FastAPI Backend

A modern FastAPI-based backend that re-implements the deprecated PapersWithCode API with enhanced features for version tracking, full-text search, and comprehensive paper management.

## Features

### Core API Compatibility
- **Paper Endpoints**: Full compatibility with the original PapersWithCode Paper API
- **Pagination**: Efficient pagination with configurable page sizes
- **Search**: Full-text search across paper titles and abstracts
- **Filtering**: Advanced filtering by date, conference, and version status

### Enhanced Features
- **ArXiv Version Tracking**: Complete support for ArXiv paper versions (v1, v2, v3, etc.)
- **URL Construction**: Automatic ArXiv URL generation for abstracts and PDFs
- **Version Comparison**: Compare different versions of the same paper
- **Database Integration**: PostgreSQL with SQLAlchemy ORM
- **Modern Architecture**: FastAPI with async support and automatic API documentation

## Quick Start

### Prerequisites

1. **PostgreSQL Database**: Ensure you have a PostgreSQL database running
2. **Python Dependencies**: Install dependencies using uv

```bash
# Install dependencies
uv sync

# Initialize database tables (if not already done)
uv run python -m backend.database.connection init
```

### Environment Configuration

Create an env file (this repository uses `backend/keys.env`, loaded with
`uv run --env-file backend/keys.env …`):

> **Note**: For optimal performance, configure API tokens:
> - **Hugging Face** (`PWC_HF_TOKEN`): Increases rate limits from 1,000 to 2,500+ requests per 5-minute window. Get your token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).
> - **GitHub** (`PWC_GITHUB_TOKEN`): Increases rate limits from 60 to 5,000+ requests per hour. Get your token at [github.com/settings/tokens](https://github.com/settings/tokens).

```env
# Database Configuration
PWC_DB_HOST=localhost
PWC_DB_PORT=5432
PWC_DB_NAME=paperswithcode
PWC_DB_USER=postgres
PWC_DB_PASSWORD=your_password

# Server Configuration
PWC_HOST=0.0.0.0
PWC_PORT=8000
PWC_ENVIRONMENT=development

# API Configuration
PWC_DEFAULT_PAGE_SIZE=50
PWC_MAX_PAGE_SIZE=500

# API Tokens (Optional - for higher rate limits)
PWC_HF_TOKEN=your_hf_token_here
PWC_GITHUB_TOKEN=your_github_token_here
```

### Running the Server

#### Development Mode
```bash
# Using the provided runner script
uv run backend/run_server.py

# Or directly with uvicorn
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

#### Production Mode
```bash
# Set environment to production
export PWC_ENVIRONMENT=production

# Run with production settings
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Testing the API

Once the server is running, you can:

1. **View API Documentation**: Visit `http://localhost:8000/docs`
2. **Health Check**: Visit `http://localhost:8000/health`
3. **Test Endpoints**: Use the interactive docs or curl

```bash
# Get recent papers
curl "http://localhost:8000/api/v1/papers/recent?limit=5"

# Get a specific paper by ArXiv ID
curl "http://localhost:8000/api/v1/papers/arxiv/1805.10616"

# Search papers
curl "http://localhost:8000/api/v1/papers/search?q=transformer&page=1&page_size=10"

# Get papers with pagination
curl "http://localhost:8000/api/v1/papers/?page=1&page_size=10"
```

## API Endpoints

### Paper Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/papers/` | GET | Get paginated list of papers with filtering |
| `/api/v1/papers/{paper_id}` | GET | Get paper by database ID |
| `/api/v1/papers/arxiv/{arxiv_id}` | GET | Get paper by ArXiv ID (latest version) |
| `/api/v1/papers/arxiv/{arxiv_id}?version=v2` | GET | Get specific version of a paper |
| `/api/v1/papers/arxiv/{arxiv_id}/versions` | GET | Get all versions of a paper |
| `/api/v1/papers/arxiv/{arxiv_id}/versions/{v1}/compare/{v2}` | GET | Compare two versions |
| `/api/v1/papers/search` | GET | Full-text search papers |
| `/api/v1/papers/recent` | GET | Get recently published papers |
| `/api/v1/papers/stats` | GET | Get database statistics |

### Dataset Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/datasets/` | GET | List datasets with pagination and filtering |
| `/api/v1/datasets/{dataset_id}` | GET | Get specific dataset details |
| `/api/v1/datasets/{dataset_id}/evaluations` | GET | Get evaluations for dataset |
| `/api/v1/datasets/` | POST | Create new dataset with task associations |

### Evaluation Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/evaluations/` | GET | List evaluations with filtering |
| `/api/v1/evaluations/{evaluation_id}` | GET | Get specific evaluation |
| `/api/v1/evaluations/` | POST | Create new evaluation result |
| `/api/v1/evaluations/{evaluation_id}` | PUT | Update evaluation result |
| `/api/v1/evaluations/{evaluation_id}` | DELETE | Delete evaluation result |
| `/api/v1/evaluations/recalculate-ranks` | POST | Recalculate leaderboard ranks |

### Query Parameters

#### `/api/v1/papers/` - Advanced Filtering
- `page`: Page number (default: 1)
- `page_size`: Papers per page (default: 50, max: 500)
- `search`: Search term for title/abstract
- `start_date`: Inclusive earliest publication date (YYYY-MM-DD)
- `end_date`: Inclusive latest publication date (YYYY-MM-DD)
- `conference`: Filter by conference name
- `latest_only`: Only include latest versions (default: true)
- `order_by`: Sort field (`trending`, `date_published`, `citation_count`; default: trending)
- `order_dir`: Sort direction (asc/desc, default: desc)

## API Response Format

### Paper Object
```json
{
  "id": "12345",
  "arxiv_id": "1805.10616",
  "url_abs": "https://arxiv.org/abs/1805.10616",
  "url_pdf": "https://arxiv.org/pdf/1805.10616.pdf",
  "title": "Attention Is All You Need",
  "abstract": "The dominant sequence transduction models...",
  "authors": ["Ashish Vaswani", "Noam Shazeer", "..."],
  "published": "2017-06-12",
  "conference": "NIPS 2017",
  "conference_url_abs": null,
  "conference_url_pdf": null,
  "proceeding": null,
  "version": "v1",
  "is_latest_version": true
}
```

### Paginated Response
```json
{
  "count": 1250,
  "next_page": 2,
  "previous_page": null,
  "results": [
    // ... array of Paper objects
  ]
}
```

## Database Integration

The backend uses SQLAlchemy with PostgreSQL and builds upon the existing database schema:

- **Papers Table**: Core paper information with version tracking
- **Authors Table**: Author information with Hugging Face integration
- **Junction Tables**: Many-to-many relationships (papers ↔ authors, tasks, methods, etc.)
- **Full-text Indexes**: PostgreSQL GIN indexes for efficient searching

## Development

### Project Structure
```
backend/
├── main.py                # FastAPI application entry point
├── config.py              # Configuration management (PWC_* env vars)
├── run_server.py          # Development server runner
├── cli.py                 # `pwc` maintenance CLI (plus cli_*.py subcommands)
├── models/
│   ├── api.py             # Pydantic models for API responses
│   └── database.py        # SQLAlchemy models
├── routers/               # FastAPI route handlers (papers, tasks, datasets, …)
├── services/              # Business logic (one module per domain)
├── database/
│   ├── connection.py      # Database connection management
│   └── migrations/        # Idempotent schema migrations
├── scripts/               # Operational and cron-invoked scripts
├── tests/                 # Pytest suite
└── utils/                 # Shared helpers (URLs, slugs, exceptions, …)
```

### Adding New Endpoints

1. **Define API Models**: Add Pydantic models in `models/api.py`
2. **Extend Database Models**: Update SQLAlchemy models in `models/database.py`
3. **Create Service Methods**: Add business logic in appropriate service classes
4. **Add Router Endpoints**: Define FastAPI routes in the relevant router
5. **Update Main App**: Include new routers in `main.py`

### Testing Database Connection

```bash
# Test database connection
python -c "from backend.database.connection import get_engine; print('✅ Database connected!' if get_engine().connect() else '❌ Connection failed!')"

# Initialize database tables
python -m backend.database.connection init

# Reset database (development only)
python -m backend.database.connection reset
```

## Configuration Options

All configuration is handled through environment variables with the `PWC_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `PWC_DB_HOST` | localhost | Database host |
| `PWC_DB_PORT` | 5432 | Database port |
| `PWC_DB_NAME` | paperswithcode | Database name |
| `PWC_DB_USER` | postgres | Database user |
| `PWC_DB_PASSWORD` | | Database password |
| `PWC_HOST` | 0.0.0.0 | Server host |
| `PWC_PORT` | 8000 | Server port |
| `PWC_ENVIRONMENT` | development | Environment (development/production) |
| `PWC_DEFAULT_PAGE_SIZE` | 50 | Default pagination size |
| `PWC_MAX_PAGE_SIZE` | 500 | Maximum pagination size |
| `PWC_APP_DOMAIN` | paperswithcode.ai | Domain for URL generation |
| `PWC_HF_TOKEN` | | Hugging Face API token (increases rate limits) |
| `PWC_CHAT_ENABLED` | false | Enable the authenticated SSE research-chat endpoint |
| `PWC_CHAT_PAPER_MENTIONS_ENABLED` | false | Enable inline paper mention creation, prewarming, and mention-bearing sends |
| `PWC_CHAT_DEEPSEEK_V4_FLASH_PROVIDER` | huggingface | Active DeepSeek provider (`huggingface` or `openrouter`); both routes remain valid during rolling switches |
| `PWC_CHAT_DEEPSEEK_V4_FLASH_ROUTE` | deepseek-ai/DeepSeek-V4-Flash-0731:baseten | Qualified user-funded Hugging Face Inference Providers route |
| `PWC_CHAT_DEEPSEEK_V4_FLASH_OPENROUTER_ROUTE` | deepseek/deepseek-v4-flash-0731 | Qualified server-funded OpenRouter route |
| `PWC_CHAT_TITLE_HF_TOKEN` | | Environment-specific server credential used only for automatic titles |
| `PWC_CHAT_TITLE_BILL_TO` | | Explicit Hugging Face organization billed for automatic titles |
| `PWC_CHAT_TITLE_MONTHLY_CAP_MICROUSD` | 25000000 | Persistent per-environment title-generation application cap |
| `PWC_CHAT_MAX_TURNS` | 8 | Agent SDK model-turn ceiling; execution reserves two turns for synthesis |
| `PWC_CHAT_MAX_SEARCH_CALLS` | 2 | Maximum paper searches per chat request |
| `PWC_CHAT_TIMEOUT_SECONDS` | 180 | Legacy local-MCP request timeout |
| `PWC_CHAT_MAX_CONCURRENCY` | 1 | PostgreSQL-enforced global active-turn ceiling (deployed policy: 2) |
| `PWC_CHAT_USER_MAX_CONCURRENCY` | 2 | PostgreSQL-enforced active-turn ceiling per user |
| `PWC_CHAT_GATEWAY_URL` | | Dedicated capability-authenticated sandbox gateway |
| `PWC_CHAT_MAX_TOOL_CALLS` | 12 | Maximum individual research tool calls; parallel calls each count |
| `PWC_CHAT_MAX_DIRECT_SEARCH_CALLS` | 4 | Maximum direct `pwc search` calls per Modal turn |
| `PWC_CHAT_SANDBOX_READY_TIMEOUT_SECONDS` | 30 | Modal sandbox readiness deadline |
| `PWC_CHAT_SANDBOX_SPEND_ENFORCEMENT_ENABLED` | false | Enable durable full-lifecycle sandbox spend enforcement (required for deployed Modal chat) |
| `PWC_CHAT_SANDBOX_WARNING_MICROUSD` | 75000000 | Internal operator-warning threshold, in integer microdollars |
| `PWC_CHAT_SANDBOX_APPLICATION_CAP_MICROUSD` | 100000000 | Durable application trip threshold, in integer microdollars |
| `PWC_CHAT_SANDBOX_ENVIRONMENT_CAP_MICROUSD` | 0 | Provider Environment cap in integer microdollars; zero for Starter Workspace-only enforcement |
| `PWC_CHAT_SANDBOX_WORKSPACE_CAP_MICROUSD` | 250000000 | Attested provider Workspace cap, in integer microdollars |
| `PWC_CHAT_SANDBOX_PROVIDER_MODE` | starter_workspace | Personal Workspace token plus Workspace cap, or `team_environments` for scoped service users and the reviewed Environment cap |
| `PWC_CHAT_SANDBOX_BUDGET_ATTESTATION` | | Reviewed provider-policy attestation required by deployed Modal chat |
| `PWC_CHAT_SANDBOX_MODAL_ENVIRONMENT` | pwc-chat-staging | Dedicated Modal Environment expected by runtime validation |
| `PWC_CHAT_SANDBOX_MODAL_WORKSPACE` | | Modal Workspace name expected by runtime validation |
| `PWC_CHAT_SANDBOX_MODAL_OWNER_USERNAME` | | Sole personal-token owner expected in Starter mode |
| `PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL` | | Secret-backed operations alert webhook |
| `PWC_CHAT_SANDBOX_ALERT_FALLBACK_WEBHOOK_URL` | | Independent incident webhook for primary alert-delivery failure |
| `PWC_CHAT_SANDBOX_OPERATOR_USERNAMES` | | Protected allowlist for audited circuit-control CLI invocations |
| `PWC_CHAT_AGENT_TIMEOUT_SECONDS` | 180 | Complete Agent SDK turn deadline |
| `PWC_CHAT_BASH_TIMEOUT_SECONDS` | 30 | Per-Bash-call deadline |
| `PWC_CHAT_HF_BILL_TO` | | Optional HF organization slug billed for chat inference |
| `PWC_THUMBNAIL_STORAGE_BACKEND` | local | Thumbnail storage backend: `local` or `hf_bucket` |
| `PWC_THUMBNAIL_HF_BUCKET_ID` | | Private Hugging Face bucket ID for thumbnail storage |
| `PWC_THUMBNAIL_HF_BUCKET_PREFIX` | thumbnails | Prefix inside the thumbnail bucket |
| `PWC_THUMBNAIL_TEMP_CACHE_DIR` | ./thumbnail_cache | Small local cache for bucket-backed thumbnail responses |
| `PWC_PAPER_MARKDOWN_HF_BUCKET_ID` | huggingface/pwc-papers-content | Private paper Markdown bucket |
| `PWC_GITHUB_TOKEN` | | GitHub API token (increases rate limits) |

## Production Deployment

### Docker (Recommended)

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen

COPY backend/ ./backend/
EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Systemd Service

```ini
[Unit]
Description=PapersWithCode FastAPI Backend
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/paperswithcode
Environment=PWC_ENVIRONMENT=production
ExecStart=/path/to/uv/run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
```

### Nginx Configuration

```nginx
server {
    listen 80;
    server_name paperswithcode.co;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Monitoring and Logging

The application provides structured logging and can be integrated with monitoring tools:

- **Health Check**: `/health` endpoint for load balancer health checks
- **Metrics**: Built-in FastAPI metrics and database connection pooling stats
- **Logging**: Structured logging with configurable levels
- **Database Monitoring**: Connection pool metrics and query performance tracking

## Documentation

- **[Data workflows](../docs/data-workflows.md)** - Adding datasets and evaluations
- **Interactive API docs** - Run the server and open `http://localhost:8000/docs`

## Contributing

1. **Code Style**: Follow PEP 8 and use type hints
2. **Testing**: Add tests for new endpoints and services
3. **Documentation**: Update API documentation and README
4. **Database Changes**: Include migration scripts for schema changes

## License

This project follows the same license as the main PapersWithCode project.
