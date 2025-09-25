# FinGuard Lite - Project Structure

This document provides an overview of the complete project structure for Sprint 1.

## 📁 Project Structure

```
finguard/
├── 📄 README.md                    # Main project documentation
├── 📄 requirements.txt             # Python dependencies
├── 📄 .env.example                # Environment variables template
├── 📄 .env                        # Environment configuration (local)
├── 📄 alembic.ini                 # Alembic migration configuration
├── 📄 pytest.ini                  # Pytest configuration
├── 📄 setup.sh                    # Automated setup script
├── 📄 test_webhook.py              # Daraja webhook testing script
├── 📄 .gitignore                  # Git ignore patterns
│
├── 📁 app/                        # Main application package
│   ├── 📄 __init__.py
│   ├── 📄 main.py                 # FastAPI application entry point
│   ├── 📄 config.py               # Configuration management
│   ├── 📄 db.py                   # Database session management
│   │
│   ├── 📁 models/                 # SQLAlchemy ORM models
│   │   ├── 📄 __init__.py
│   │   ├── 📄 user.py            # User and AuditLog models
│   │   ├── 📄 account.py         # Business account model
│   │   └── 📄 transaction.py     # Transaction model
│   │
│   ├── 📁 schemas/                # Pydantic validation schemas
│   │   ├── 📄 __init__.py
│   │   ├── 📄 auth.py            # Authentication schemas
│   │   ├── 📄 user.py            # User data schemas
│   │   ├── 📄 account.py         # Account schemas
│   │   └── 📄 transaction.py     # Transaction schemas
│   │
│   ├── 📁 api/                    # FastAPI route handlers
│   │   ├── 📄 __init__.py
│   │   ├── 📄 auth.py            # Authentication endpoints
│   │   ├── 📄 daraja.py          # M-Pesa webhook endpoints
│   │   └── 📄 transactions.py    # Transaction management
│   │
│   ├── 📁 core/                   # Core business logic
│   │   ├── 📄 __init__.py
│   │   ├── 📄 security.py        # JWT & password security
│   │   └── 📄 daraja.py          # Daraja API client
│   │
│   └── 📁 utils/                  # Utility functions
│       ├── 📄 __init__.py
│       └── 📄 logging.py         # Structured logging
│
├── 📁 migrations/                 # Alembic database migrations
│   ├── 📄 env.py                 # Migration environment
│   ├── 📄 script.py.mako         # Migration template
│   └── 📁 versions/              # Migration files (auto-generated)
│
└── 📁 tests/                     # Test suite
    ├── 📄 __init__.py
    ├── 📄 conftest.py            # Test configuration & fixtures
    ├── 📄 test_auth.py           # Authentication tests
    └── 📄 test_daraja.py         # Daraja webhook tests
```

## 🔧 Key Components

### Application Core (`app/`)

- **`main.py`**: FastAPI application with middleware, error handling, and route registration
- **`config.py`**: Environment-based configuration with validation
- **`db.py`**: SQLAlchemy database session management

### Database Models (`app/models/`)

- **User Model**: Authentication, roles (owner/accountant), audit logging
- **Account Model**: Business accounts with M-Pesa configuration
- **Transaction Model**: M-Pesa transactions with full audit trail

### API Schemas (`app/schemas/`)

- **Pydantic models** for request/response validation
- **Input validation** with custom validators
- **Type safety** throughout the application

### API Routes (`app/api/`)

- **Authentication**: Registration, login, token management
- **Daraja Integration**: M-Pesa webhook handling
- **Transactions**: Listing, filtering, reconciliation

### Core Logic (`app/core/`)

- **Security**: JWT tokens, password hashing, authentication
- **Daraja Client**: M-Pesa API integration (STK Push, C2B, etc.)

### Database Migrations (`migrations/`)

- **Alembic setup** for schema versioning
- **Auto-generation** of migrations from model changes

### Testing (`tests/`)

- **Comprehensive test suite** with pytest
- **Test fixtures** for realistic test data
- **Integration tests** for API endpoints

## 📊 Database Schema

### Users Table
```sql
- id (UUID, Primary Key)
- name (String, 100 chars)
- email (String, 255 chars, Unique)
- phone (String, 20 chars)
- hashed_password (String, 255 chars)
- role (Enum: owner/accountant)
- is_active (Boolean)
- is_verified (Boolean)
- created_at (DateTime)
- last_login (DateTime)
```

### Accounts Table
```sql
- id (UUID, Primary Key)
- user_id (UUID, Foreign Key)
- business_name (String, 200 chars)
- business_type (String, 100 chars)
- currency (Enum: KES/USD/EUR)
- mpesa_shortcode (String, 10 chars)
- mpesa_account_reference (String, 50 chars)
- created_at (DateTime)
- updated_at (DateTime)
```

### Transactions Table
```sql
- id (UUID, Primary Key)
- account_id (UUID, Foreign Key)
- mpesa_transaction_id (String, 50 chars, Unique)
- transaction_type (Enum: C2B/B2C/LipaNaMpesa/etc.)
- amount (Numeric 15,2)
- phone (String, 20 chars)
- party_name (String, 200 chars)
- reference (String, 100 chars)
- transaction_time (DateTime)
- status (Enum: pending/completed/failed/duplicate)
- raw_payload (JSONB)
- business_short_code (String, 10 chars)
- created_at (DateTime)
- processed_at (DateTime)
```

### Audit Logs Table
```sql
- id (UUID, Primary Key)
- user_id (UUID, Optional Foreign Key)
- action (String, 100 chars)
- resource (String, 255 chars)
- ip_address (String, 45 chars)
- user_agent (String, 512 chars)
- success (Boolean)
- details (String, 1000 chars)
- timestamp (DateTime)
```

## 🔐 Security Features

- **JWT Authentication** with access + refresh tokens
- **Password hashing** with bcrypt
- **Role-based access control** (owner/accountant)
- **Audit logging** for all user actions
- **Input validation** with Pydantic
- **CORS configuration** for frontend integration
- **Security headers** middleware

## 🔌 API Endpoints

### Authentication (`/api/auth/`)
- `POST /signup` - User registration
- `POST /login` - User login (returns JWT)
- `POST /refresh` - Refresh access token
- `GET /me` - Get current user info
- `POST /reset-password` - Password reset (stub)
- `POST /logout` - User logout

### Transactions (`/api/transactions/`)
- `GET /` - List transactions (filtered, paginated)
- `GET /{id}` - Get specific transaction
- `POST /reconcile` - Reconcile transactions (stub)
- `GET /stats/summary` - Transaction statistics

### Daraja M-Pesa (`/api/daraja/`)
- `POST /webhook` - M-Pesa callback endpoint
- `GET /transactions/recent` - Recent transactions (debug)
- `GET /health` - Service health check
- `POST /test-webhook` - Test endpoint (development)

### System
- `GET /health` - Application health check
- `GET /` - API information

## 🧪 Testing Strategy

- **Unit tests** for business logic
- **Integration tests** for API endpoints
- **Authentication flow** testing
- **Daraja webhook** simulation
- **Idempotency** validation
- **Error handling** verification

## 🚀 Deployment Considerations

### Railway (Backend)
- Environment variables configuration
- PostgreSQL database addon
- Automatic deployments from Git
- Health check endpoints

### Development
- Hot reload with `uvicorn --reload`
- SQLite fallback for local development
- Comprehensive logging
- Test webhook simulation

## 📝 Configuration

All configuration through environment variables:
- Database connection
- JWT secrets
- Daraja API credentials
- CORS origins
- Logging levels

## 🔄 Development Workflow

1. **Setup**: Run `./setup.sh` for automated environment setup
2. **Database**: Alembic migrations for schema changes
3. **Testing**: `pytest` for comprehensive test suite
4. **API Testing**: Use `/docs` for interactive API documentation
5. **Webhook Testing**: `python test_webhook.py` for M-Pesa simulation

This structure provides a solid foundation for Sprint 1 with room for future enhancements in subsequent sprints.