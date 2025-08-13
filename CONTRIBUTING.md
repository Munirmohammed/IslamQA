# Contributing to Islamic Q&A Chatbot Backend

First off, thank you for considering contributing to the Islamic Q&A project! 🕌 This project aims to make Islamic knowledge more accessible through modern technology while maintaining authenticity and scholarly verification.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Contribution Guidelines](#contribution-guidelines)
- [Islamic Content Guidelines](#islamic-content-guidelines)
- [Technical Standards](#technical-standards)
- [Pull Request Process](#pull-request-process)
- [Recognition](#recognition)

## 🤝 Code of Conduct

This project adheres to Islamic principles of respect, kindness, and constructive collaboration. By participating, you are expected to uphold these values:

- **Respect**: Treat all community members with respect and kindness
- **Constructive**: Provide constructive feedback and criticism
- **Inclusive**: Welcome contributors from all backgrounds and skill levels
- **Educational**: Focus on learning and teaching in a supportive environment
- **Authentic**: Maintain accuracy and authenticity in Islamic content

## 🌟 How Can I Contribute?

### 🐛 Reporting Bugs

Before creating bug reports, please check the issue list to avoid duplicates. When creating a bug report, include:

- **Clear title** and description
- **Steps to reproduce** the issue
- **Expected vs actual behavior**
- **Environment details** (OS, Python version, etc.)
- **Screenshots** if applicable

### 💡 Suggesting Enhancements

Enhancement suggestions are welcome! Please include:

- **Clear description** of the enhancement
- **Use case** and benefits
- **Possible implementation** approach
- **Alternative solutions** considered

### 📝 Improving Documentation

Documentation improvements are always appreciated:

- Fix typos or unclear explanations
- Add examples and tutorials
- Improve API documentation
- Translate documentation to other languages

### 💻 Code Contributions

Areas where code contributions are especially valuable:

- **Islamic Source Integration**: Adding new verified Islamic Q&A sources
- **Arabic NLP**: Improving Arabic language processing
- **ML Models**: Enhancing question matching accuracy
- **Performance**: Optimizing search and response times
- **Security**: Strengthening authentication and data protection
- **Testing**: Adding comprehensive test coverage
- **Documentation**: API docs and developer guides

## 🛠️ Development Setup

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Git
- PostgreSQL 15+
- Redis 7+

### Setup Steps

1. **Fork and Clone**
   ```bash
   git clone https://github.com/YOUR_USERNAME/IslamQA.git
   cd IslamQA
   ```

2. **Environment Setup**
   ```bash
   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # venv\Scripts\activate  # Windows
   
   # Install dependencies
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

3. **Configuration**
   ```bash
   cp config.env .env
   # Edit .env with your settings
   ```

4. **Database Setup**
   ```bash
   docker-compose up -d db redis
   alembic upgrade head
   ```

5. **Run Tests**
   ```bash
   pytest
   ```

6. **Start Development Server**
   ```bash
   uvicorn app.main:app --reload
   ```

## 📐 Contribution Guidelines

### Branching Strategy

- `main`: Production-ready code
- `develop`: Integration branch for new features
- `feature/your-feature`: Feature development
- `bugfix/issue-description`: Bug fixes
- `docs/improvement-description`: Documentation updates

### Commit Messages

Use conventional commit format:

```
type(scope): brief description

Detailed explanation if needed

- Additional points
- Related issues: #123
```

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

**Examples**:
- `feat(search): add Arabic fuzzy matching`
- `fix(auth): resolve JWT token expiration issue`
- `docs(api): update search endpoint documentation`

### Code Style

- **Python**: Follow PEP 8 standards
- **Line Length**: Maximum 88 characters (Black formatter)
- **Imports**: Use isort for import organization
- **Type Hints**: Add type hints for all functions
- **Docstrings**: Use Google-style docstrings

```python
def search_questions(
    query: str, 
    language: str = "en", 
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Search for questions in the knowledge base.
    
    Args:
        query: The search query string
        language: Language code (en, ar)
        limit: Maximum number of results
        
    Returns:
        List of matching questions with metadata
        
    Raises:
        ValueError: If query is too short
    """
    pass
```

## 🕌 Islamic Content Guidelines

### Source Verification

All Islamic content must be from verified sources:

- **Approved Sources**: IslamQA.info, Dar al-Ifta, recognized scholars
- **Attribution**: Always maintain proper source attribution
- **Accuracy**: Verify content accuracy before inclusion
- **Language**: Support both Arabic and English content

### Scholar Information

When adding scholar information:

- Include full name and credentials
- Add biographical information if available
- Maintain respectful language
- Verify authenticity of attributions

### Content Quality

- **Authenticity**: Ensure content is from reliable Islamic sources
- **Clarity**: Make content accessible to different knowledge levels
- **Completeness**: Include relevant Quranic verses and Hadith references
- **Balance**: Present different scholarly opinions when appropriate

## 🔧 Technical Standards

### Testing Requirements

- **Unit Tests**: All new functions must have unit tests
- **Integration Tests**: API endpoints require integration tests
- **Coverage**: Maintain 80%+ test coverage
- **Performance Tests**: Critical paths need performance tests

### API Design

- **RESTful**: Follow REST principles
- **Versioning**: Use API versioning (/api/v1/)
- **Documentation**: OpenAPI/Swagger documentation
- **Error Handling**: Consistent error response format

### Database Guidelines

- **Migrations**: Use Alembic for database changes
- **Indexing**: Add appropriate indexes for performance
- **Relationships**: Define clear foreign key relationships
- **Data Integrity**: Include appropriate constraints

### Security Requirements

- **Input Validation**: Validate all user inputs
- **SQL Injection**: Use parameterized queries
- **XSS Protection**: Sanitize output data
- **Authentication**: Secure JWT implementation
- **Rate Limiting**: Implement appropriate rate limits

## 🔄 Pull Request Process

### Before Submitting

1. **Rebase** your branch on the latest develop branch
2. **Run tests** and ensure they pass
3. **Check code style** with linting tools
4. **Update documentation** if needed
5. **Test manually** in development environment

### PR Requirements

- **Title**: Clear, descriptive title
- **Description**: Detailed description of changes
- **Issue Reference**: Link to related issues
- **Testing**: Describe testing performed
- **Screenshots**: Include UI changes if applicable

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Performance improvement
- [ ] Code refactoring

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Tests added/updated
```

### Review Process

1. **Automated Checks**: CI/CD pipeline must pass
2. **Code Review**: At least one maintainer review
3. **Islamic Content Review**: Religious content requires scholar review
4. **Testing**: Reviewer tests changes locally
5. **Approval**: Final approval from maintainer

## 🏆 Recognition

Contributors will be recognized in:

- **README**: Contributors section
- **Release Notes**: Major contribution mentions
- **Documentation**: Author attribution
- **Community**: Social media recognition

### Contributor Levels

- **Contributor**: Made accepted contributions
- **Regular Contributor**: Multiple merged PRs
- **Core Contributor**: Significant ongoing contributions
- **Maintainer**: Repository maintenance access

## 🤔 Questions?

- **GitHub Issues**: Technical questions and bugs
- **GitHub Discussions**: General questions and ideas
- **Email**: contact@islamqa.dev for private matters

## 🙏 Islamic Etiquette

As this is an Islamic project, we encourage:

- Begin work with "Bismillah" (In the name of Allah)
- Make du'a for the success and benefit of the project
- Maintain good intention (niyyah) to serve the Muslim community
- Practice patience and kindness in all interactions
- End contributions with "Alhamdulillah" (Praise be to Allah)

---

**JazakAllahu Khairan** (May Allah reward you with good) for your interest in contributing! Your efforts help make Islamic knowledge more accessible to Muslims worldwide. 🌍

**Barakallahu feeki/feeka** (May Allah bless you) 🤲
