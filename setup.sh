#!/bin/bash

# FinGuard Lite Setup Script
# Automated setup for development environment

set -e  # Exit on any error

echo "🚀 FinGuard Lite - Setup Script"
echo "==============================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    echo "Please install Python 3.8 or higher and try again."
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Check if PostgreSQL is available (optional)
if command -v psql &> /dev/null; then
    echo "✅ PostgreSQL found: $(psql --version | head -n1)"
else
    echo "⚠️  PostgreSQL not found. You can use SQLite for development."
fi

# Create virtual environment
echo "📦 Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "📈 Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📚 Installing Python dependencies..."
pip install -r requirements.txt

echo "✅ Dependencies installed successfully"

# Setup environment file
echo "⚙️  Setting up environment configuration..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "✅ Created .env file from template"
    echo "⚠️  Please edit .env file with your actual configuration values"
else
    echo "✅ .env file already exists"
fi

# Initialize Alembic (if not already done)
echo "🗄️  Setting up database migrations..."
if [ ! -d "migrations/versions" ]; then
    mkdir -p migrations/versions
    echo "✅ Created migrations directory"
fi

# Check database connection (optional)
echo "🔍 Checking database configuration..."
python3 -c "
try:
    from app.config import settings
    print('✅ Configuration loaded successfully')
    print(f'   Database URL: {settings.database_url[:30]}...')
    print(f'   Environment: {settings.environment}')
    print(f'   Debug mode: {settings.debug}')
except Exception as e:
    print(f'⚠️  Configuration issue: {e}')
    print('Please check your .env file')
" || true

# Create initial migration (if needed)
echo "🔄 Creating initial database migration..."
python3 -c "
try:
    import subprocess
    result = subprocess.run(['alembic', 'revision', '--autogenerate', '-m', 'Initial migration'], 
                          capture_output=True, text=True)
    if result.returncode == 0:
        print('✅ Initial migration created')
    else:
        print('⚠️  Migration creation skipped (may already exist)')
        print(result.stderr if result.stderr else result.stdout)
except Exception as e:
    print(f'⚠️  Could not create migration: {e}')
" || echo "⚠️  Alembic migration skipped - run manually if needed"

# Run database setup (if database is available)
echo "🏗️  Setting up database..."
python3 -c "
try:
    from app.db import create_tables
    create_tables()
    print('✅ Database tables created')
except Exception as e:
    print(f'⚠️  Database setup skipped: {e}')
    print('Please ensure your database is running and accessible')
" || echo "⚠️  Database setup skipped - configure database and run migrations manually"

echo ""
echo "🎉 Setup completed!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your actual configuration:"
echo "   - Database connection details"
echo "   - JWT secret key (generate a secure one!)"
echo "   - Daraja API credentials from Safaricom Developer Portal"
echo ""
echo "2. Start the development server:"
echo "   source venv/bin/activate"
echo "   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "3. Open your browser to:"
echo "   http://localhost:8000/docs (API documentation)"
echo "   http://localhost:8000/health (health check)"
echo ""
echo "4. Test M-Pesa webhook with:"
echo "   python test_webhook.py"
echo ""
echo "5. Run tests with:"
echo "   pytest"
echo ""
echo "📖 For more information, see README.md"
echo ""
echo "Happy coding! 🚀"