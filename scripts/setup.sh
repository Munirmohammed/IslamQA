#!/bin/bash

# Islamic Q&A Setup Script
# Automated setup for development and production environments

set -e

echo "🕌 Setting up Islamic Q&A Chatbot Backend..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   print_error "This script should not be run as root"
   exit 1
fi

# Check system requirements
print_status "Checking system requirements..."

# Check Python version
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    print_status "Python version: $PYTHON_VERSION"
else
    print_error "Python 3 is not installed"
    exit 1
fi

# Check Docker
if command -v docker &> /dev/null; then
    print_status "Docker is installed"
else
    print_warning "Docker is not installed. Please install Docker first."
fi

# Check Docker Compose
if command -v docker-compose &> /dev/null; then
    print_status "Docker Compose is installed"
else
    print_warning "Docker Compose is not installed. Please install Docker Compose first."
fi

# Setup environment
print_status "Setting up environment..."

# Create data directories
mkdir -p data/{backups,logs,cache,models}
mkdir -p backups
mkdir -p logs

print_status "Created data directories"

# Copy environment file if it doesn't exist
if [ ! -f .env ]; then
    if [ -f config.env ]; then
        cp config.env .env
        print_status "Created .env file from config.env"
    else
        print_warning ".env file not found. Please create one based on the template."
    fi
fi

# Setup Python environment for development
if [ "$1" = "dev" ] || [ "$1" = "development" ]; then
    print_status "Setting up development environment..."
    
    # Create virtual environment
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        print_status "Created Python virtual environment"
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install dependencies
    pip install -r requirements.txt
    
    # Install development dependencies
    pip install pytest pytest-cov black isort flake8 mypy pre-commit
    
    print_status "Installed Python dependencies"
    
    # Setup pre-commit hooks
    pre-commit install
    print_status "Installed pre-commit hooks"
    
    print_status "Development environment setup complete!"
    print_status "To activate the environment, run: source venv/bin/activate"
    print_status "To start the development server, run: uvicorn app.main:app --reload"

# Production setup with Docker
elif [ "$1" = "prod" ] || [ "$1" = "production" ]; then
    print_status "Setting up production environment..."
    
    # Check if Docker is running
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker is not running. Please start Docker first."
        exit 1
    fi
    
    # Build and start services
    print_status "Building Docker images..."
    docker-compose build
    
    print_status "Starting services..."
    docker-compose up -d
    
    # Wait for database to be ready
    print_status "Waiting for database to be ready..."
    sleep 30
    
    # Run database migrations
    print_status "Running database migrations..."
    docker-compose exec app alembic upgrade head
    
    # Create admin user (if not exists)
    print_status "Creating admin user..."
    docker-compose exec app python -c "
from app.core.database import SessionLocal
from app.core.security import AuthService
try:
    db = SessionLocal()
    auth = AuthService(db)
    auth.create_user('admin', 'admin@islamqa.dev', 'admin123', is_admin=True)
    print('Admin user created successfully')
except Exception as e:
    print(f'Admin user creation failed (may already exist): {e}')
finally:
    db.close()
"
    
    print_status "Production environment setup complete!"
    print_status "API available at: http://localhost:8000"
    print_status "Documentation: http://localhost:8000/docs"
    print_status "Admin login: admin / admin123"

# Default setup
else
    print_status "Setting up basic environment..."
    
    # Generate secret key
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    
    # Update .env file with generated secret
    if [ -f .env ]; then
        sed -i.bak "s/your-super-secret-key-here-change-this-in-production/$SECRET_KEY/" .env
        print_status "Updated secret key in .env file"
    fi
    
    print_status "Basic setup complete!"
    print_status ""
    print_status "Next steps:"
    print_status "1. For development: ./scripts/setup.sh dev"
    print_status "2. For production: ./scripts/setup.sh prod"
    print_status "3. Or manually configure your environment"
fi

print_status ""
print_status "🎉 Setup completed successfully!"
print_status ""
print_status "Useful commands:"
print_status "  Start services: docker-compose up -d"
print_status "  View logs: docker-compose logs -f"
print_status "  Stop services: docker-compose down"
print_status "  Run tests: docker-compose exec app pytest"
print_status ""
print_status "📚 Documentation: README.md"
print_status "🐛 Issues: https://github.com/yourusername/IslamQA/issues"
