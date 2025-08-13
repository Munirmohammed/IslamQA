# Islamic Q&A Frontend

A modern, responsive web interface for the Islamic Q&A knowledge platform featuring beautiful Islamic design, real-time chat, and AI-powered search capabilities.

## 🌟 Features

### 🎨 **Beautiful Islamic Design**
- Modern Islamic color scheme (greens and golds)
- Arabic typography support with Amiri font
- Responsive design for all devices
- Islamic geometric patterns and motifs

### 🔍 **Smart Search**
- AI-powered semantic search
- Category and language filtering
- Real-time search suggestions
- Confidence scoring for results

### 💬 **Real-time Chat**
- WebSocket-based live chat
- Instant Q&A responses
- Auto-reconnection on disconnect
- Message history and timestamps

### 📚 **Question Management**
- Browse questions by category
- Detailed question views with answers
- Related questions suggestions
- User-friendly question submission

### 👤 **User Authentication**
- Secure JWT-based authentication
- User registration and login
- Profile management
- Role-based access control

### 📱 **Responsive Design**
- Mobile-first approach
- Touch-friendly interface
- Optimized for tablets and desktops
- Progressive Web App features

## 🚀 Quick Start

### Prerequisites
- Python 3.7+ (for development server)
- Islamic Q&A Backend running on port 8000

### Option 1: Using Python Development Server

```bash
# Navigate to frontend directory
cd frontend

# Start the development server
python server.py

# Or specify a custom port
python server.py 3001
```

### Option 2: Using any HTTP Server

```bash
# Using Python's built-in server
cd frontend
python -m http.server 3000

# Using Node.js http-server (if installed)
npx http-server frontend -p 3000 -c-1

# Using PHP (if available)
cd frontend
php -S localhost:3000
```

### Option 3: Direct File Access
Simply open `index.html` in your web browser (some features may be limited due to CORS restrictions).

## 🌐 Access Points

Once the server is running:

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## 📖 Usage Guide

### 🏠 **Home Page**
- View featured questions
- Browse by categories
- See platform statistics
- Quick access to all features

### ❓ **Questions Section**
- Browse all questions with filters
- Click any question for detailed view
- See answers, sources, and verification status
- Pagination for large result sets

### 🔍 **Search**
- Enter your Islamic question
- Toggle AI-powered search
- Select language preference
- View results with confidence scores

### 💬 **Live Chat**
- Real-time Q&A assistance
- Instant responses from the AI system
- Connection status indicator
- Message history

### ➕ **Ask Question**
- Submit new questions (requires login)
- Categorize your questions
- Add relevant tags
- Form validation and feedback

### 🔐 **Authentication**
- Register new accounts
- Login with email/password
- Secure session management
- User profile access

## 🎨 Design System

### Colors
- **Primary**: Islamic Green (#006B3C)
- **Secondary**: Golden (#C9A961)
- **Accent**: Islamic Blue (#1B4F8C)
- **Background**: Light Gray (#F8F9FA)

### Typography
- **Primary**: Inter (sans-serif)
- **Arabic**: Amiri (serif)
- **Icons**: Font Awesome 6

### Components
- Modern card-based layouts
- Smooth transitions and animations
- Islamic geometric patterns
- Accessible design patterns

## 🔧 Technical Details

### Technologies Used
- **HTML5**: Semantic markup
- **CSS3**: Modern styling with CSS Grid and Flexbox
- **Vanilla JavaScript**: No framework dependencies
- **WebSocket**: Real-time communication
- **Fetch API**: HTTP requests
- **LocalStorage**: Client-side data persistence

### Browser Support
- Chrome 70+
- Firefox 65+
- Safari 12+
- Edge 79+
- Mobile browsers (iOS Safari, Chrome Mobile)

### Performance Features
- Lazy loading for images
- Debounced search input
- Efficient DOM manipulation
- Minimal JavaScript bundle
- CSS optimization

## 🛠️ Development

### File Structure
```
frontend/
├── index.html          # Main HTML file
├── styles.css          # Complete stylesheet
├── script.js           # All JavaScript functionality
├── server.py           # Development server
└── README.md           # This file
```

### Key JavaScript Modules
- **Navigation**: Section switching and routing
- **API Service**: Backend communication
- **Search**: Smart search functionality
- **Chat**: WebSocket real-time chat
- **Auth**: User authentication
- **Questions**: Question management
- **UI Utils**: Common utilities and helpers

### CSS Architecture
- CSS Custom Properties for theming
- BEM methodology for class naming
- Mobile-first responsive design
- Accessibility-first approach

## 🔌 API Integration

The frontend integrates with these backend endpoints:

### Authentication
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/register` - User registration
- `GET /api/v1/auth/me` - Get current user

### Questions
- `GET /api/v1/questions` - List questions
- `GET /api/v1/questions/{id}` - Get question details
- `POST /api/v1/questions` - Create question
- `GET /api/v1/questions/{id}/related` - Get related questions

### Search
- `GET /api/v1/search` - Search knowledge base

### WebSocket
- `WS /ws/chat` - Real-time chat

### Analytics
- `GET /api/v1/analytics/stats` - Platform statistics

## 🎯 Features in Detail

### Smart Search
```javascript
// AI-powered search with confidence scoring
const results = await api.search(query, {
    language: 'en',
    use_ml: true,
    limit: 20
});
```

### Real-time Chat
```javascript
// WebSocket connection with auto-reconnect
const socket = new WebSocket('ws://localhost:8000/ws/chat');
socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleMessage(data);
};
```

### Authentication
```javascript
// JWT-based authentication
const response = await api.login(email, password);
localStorage.setItem('authToken', response.access_token);
```

## 🌍 Internationalization

### Current Support
- English (primary)
- Arabic (basic support)
- RTL text support for Arabic

### Adding Languages
1. Add language option to select elements
2. Update API calls with language parameter
3. Add translation strings to JavaScript
4. Update CSS for RTL languages if needed

## 🚀 Deployment

### Production Deployment
1. **Static Hosting**: Deploy to Netlify, Vercel, or GitHub Pages
2. **CDN**: Use CloudFlare or similar for global distribution
3. **Optimization**: Minify CSS/JS and optimize images
4. **HTTPS**: Ensure secure connections

### Environment Configuration
Update the API configuration in `script.js`:

```javascript
const CONFIG = {
    API_BASE_URL: 'https://your-api-domain.com/api/v1',
    WS_BASE_URL: 'wss://your-api-domain.com/ws',
    // ... other config
};
```

## 🔒 Security

### Client-side Security
- XSS prevention with content sanitization
- CSRF protection via JWT tokens
- Secure localStorage usage
- Input validation and sanitization

### Best Practices
- No sensitive data in localStorage
- Proper error handling
- Timeout for API requests
- Content Security Policy ready

## 🐛 Troubleshooting

### Common Issues

**1. Chat not connecting**
- Check if backend WebSocket is enabled
- Verify WebSocket URL configuration
- Check browser console for errors

**2. API calls failing**
- Ensure backend is running on port 8000
- Check CORS configuration
- Verify API endpoint URLs

**3. Authentication issues**
- Clear localStorage and try again
- Check token expiration
- Verify backend auth endpoints

**4. Styling issues**
- Check browser compatibility
- Verify CSS file is loading
- Clear browser cache

### Debug Mode
Open browser developer tools and check:
- Console for JavaScript errors
- Network tab for API call status
- Application tab for localStorage data

## 📞 Support

For technical support or feature requests:
1. Check the main project documentation
2. Review backend API documentation at `/docs`
3. Check browser console for error details
4. Ensure all prerequisites are met

## 🤝 Contributing

### Code Style
- Use 2-space indentation
- Follow existing naming conventions
- Comment complex functions
- Test on multiple browsers

### Pull Request Process
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

---

**Built with ❤️ for the Islamic community**

*بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ*
