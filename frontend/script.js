/**
 * Modern Islamic Q&A Platform
 * Beautiful Dark Theme Interface
 */

// Configuration
const CONFIG = {
    API_BASE_URL: 'http://localhost:8000',
    WS_URL: 'ws://localhost:8000/ws/chat',
    ENDPOINTS: {
        LOGIN: '/api/v1/auth/login',
        REGISTER: '/api/v1/auth/register',
        SEARCH: '/api/v1/search',
        ASK_QUESTION: '/api/v1/questions/ask'
    }
};

// Global State
let AppState = {
    user: null,
    isAuthenticated: false,
    currentSection: 'home',
    chatConnected: false,
    theme: 'dark'
};

// API Service
const api = {
    baseURL: CONFIG.API_BASE_URL,
    token: localStorage.getItem('authToken'),

    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const headers = {
                'Content-Type': 'application/json',
                ...options.headers
        };

        if (this.token) {
            headers.Authorization = `Bearer ${this.token}`;
        }

        try {
            const response = await fetch(url, {
                ...options,
                headers
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
            return await response.json();
            }
            return await response.text();
        } catch (error) {
            console.error('API Request failed:', error);
            throw error;
        }
    },

    async login(username, password) {
        const response = await this.request(CONFIG.ENDPOINTS.LOGIN, {
                method: 'POST',
            body: JSON.stringify({ username, password })
            });

            if (response.access_token) {
            this.token = response.access_token;
            localStorage.setItem('authToken', this.token);
            AppState.isAuthenticated = true;
            AppState.user = response.user;
            }

            return response;
    },

    async register(userData) {
        return await this.request(CONFIG.ENDPOINTS.REGISTER, {
                method: 'POST',
            body: JSON.stringify(userData)
        });
    },

    async search(query, filters = {}) {
        const params = new URLSearchParams({
            query,
            language: filters.language || 'auto',
            use_ml: filters.useML || true,
            limit: filters.limit || 10
        });

        return await this.request(`${CONFIG.ENDPOINTS.SEARCH}?${params}`);
    },

    logout() {
        this.token = null;
        localStorage.removeItem('authToken');
        AppState.isAuthenticated = false;
        AppState.user = null;
    }
};

// Chat Service
const chat = {
    socket: null,
    reconnectAttempts: 0,
    maxReconnectAttempts: 5,
    reconnectDelay: 1000,
    isConnecting: false,

    connect() {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            return;
        }

        if (this.isConnecting) {
            return;
        }

        this.isConnecting = true;
        this.updateStatus('connecting');
        console.log('Attempting to connect to:', CONFIG.WS_URL);

        try {
            this.socket = new WebSocket(CONFIG.WS_URL);
            this.setupEventListeners();
            
            // Add timeout for connection attempt
            setTimeout(() => {
                if (this.socket && this.socket.readyState === WebSocket.CONNECTING) {
                    console.warn('WebSocket connection timeout');
                    this.socket.close();
                    this.handleConnectionError();
                }
            }, 10000); // 10 second timeout
            
        } catch (error) {
            console.error('WebSocket connection failed:', error);
            this.handleConnectionError();
        }
    },

    setupEventListeners() {
        this.socket.onopen = () => {
            console.log('WebSocket connected');
            this.isConnecting = false;
            this.reconnectAttempts = 0;
            this.updateStatus('connected');
            AppState.chatConnected = true;
        };

        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            } catch (error) {
                console.error('Failed to parse WebSocket message:', error);
            }
        };

        this.socket.onclose = (event) => {
            console.log('WebSocket disconnected:', event.code);
            this.isConnecting = false;
            AppState.chatConnected = false;
            this.updateStatus('disconnected');
            
            if (event.code !== 1000) {
                this.scheduleReconnect();
            }
        };

        this.socket.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.handleConnectionError();
        };
    },

    handleConnectionError() {
        this.isConnecting = false;
        this.updateStatus('offline');
        
        // Show offline message with fallback option
        const messagesContainer = document.getElementById('chatMessages');
        if (messagesContainer && messagesContainer.children.length <= 1) { // Only welcome message
            const offlineMessage = document.createElement('div');
            offlineMessage.className = 'chat-message system';
            offlineMessage.innerHTML = `
                <div class="message-content">
                    <strong>🔌 Connection Issue</strong><br>
                    Can't connect to the server right now. But don't worry! You can still get Islamic answers using our offline AI system.<br><br>
                    <em>Try asking: "What are the Five Pillars of Islam?"</em>
                </div>
            `;
            messagesContainer.appendChild(offlineMessage);
        }
        
        this.scheduleReconnect();
    },

    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            setTimeout(() => {
                console.log(`Reconnecting... Attempt ${this.reconnectAttempts}`);
                this.connect();
            }, this.reconnectDelay * this.reconnectAttempts);
        }
    },

    sendMessage(message) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({
                type: 'question',
                content: message
            }));
            this.displayMessage(message, 'user');
        } else {
            // Use offline AI when WebSocket is not connected
            this.displayMessage(message, 'user');
            
            // Simulate thinking time and get offline response
            setTimeout(() => {
                const offlineResponse = this.getOfflineAIResponse(message);
                this.displaySystemMessage(offlineResponse, {
                    sources: ['Offline AI System'],
                    is_islamic: true,
                    confidence: 0.8
                });
            }, 1000);
        }
    },

    getOfflineAIResponse(message) {
        const messageLower = message.toLowerCase();
        
        // Enhanced Islamic knowledge responses for offline mode
        const islamicResponses = {
            'five pillars': 'The Five Pillars of Islam are:\n\n1. **Shahada** - Declaration of faith: "La ilaha illa Allah, Muhammad rasul Allah"\n2. **Salah** - Five daily prayers\n3. **Zakat** - Charity (2.5% of wealth annually)\n4. **Sawm** - Fasting during Ramadan\n5. **Hajj** - Pilgrimage to Mecca\n\nThese pillars form the foundation of Muslim practice and faith.',
            
            'prayer': 'Islamic prayer (Salah) is performed 5 times daily:\n\n• **Fajr** - Before sunrise\n• **Dhuhr** - After midday\n• **Asr** - Late afternoon\n• **Maghrib** - Just after sunset\n• **Isha** - Night prayer\n\nEach prayer involves ritual purification (Wudu), facing Mecca (Qibla), and reciting verses from the Quran.',
            
            'shahada': 'The Shahada is the Islamic declaration of faith:\n\n**Arabic:** "Ash-hadu an la ilaha illa Allah, wa ash-hadu anna Muhammadan rasul Allah"\n\n**English:** "I bear witness that there is no god but Allah, and I bear witness that Muhammad is the messenger of Allah"\n\nReciting the Shahada with sincere belief makes one a Muslim.',
            
            'wudu': 'Wudu (ablution) is performed before prayer:\n\n1. Make intention and say "Bismillah"\n2. Wash hands 3 times\n3. Rinse mouth 3 times\n4. Rinse nose 3 times\n5. Wash face 3 times\n6. Wash arms to elbows 3 times\n7. Wipe head once\n8. Wash feet to ankles 3 times\n\nWudu purifies the body and soul before standing before Allah.',
            
            'ramadan': 'Ramadan is the holy month of fasting:\n\n• **Duration:** 9th month of Islamic calendar (29-30 days)\n• **Fasting:** From dawn (Fajr) to sunset (Maghrib)\n• **Purpose:** Spiritual purification, self-control, empathy for the poor\n• **Benefits:** Increased devotion, community unity, charity\n• **Eid:** Celebrated at the end with Eid al-Fitr',
            
            'quran': 'The Quran is Allah\'s final revelation:\n\n• **Revealed to:** Prophet Muhammad (peace be upon him)\n• **Language:** Arabic\n• **Structure:** 114 chapters (Surahs), 6,236 verses (Ayahs)\n• **Purpose:** Guidance for all humanity\n• **Preservation:** Memorized by millions, unchanged since revelation\n\nThe Quran is the primary source of Islamic teachings and law.',
        };
        
        // Check for keywords and return appropriate response
        for (const [keyword, response] of Object.entries(islamicResponses)) {
            if (messageLower.includes(keyword)) {
                return response;
            }
        }
        
        // Handle question patterns
        if (messageLower.includes('how') && messageLower.includes('pray')) {
            return islamicResponses['prayer'];
        }
        
        if (messageLower.includes('what') && messageLower.includes('islam')) {
            return 'Islam is the religion of peace and submission to Allah. It\'s based on five pillars, belief in one God (Allah), Prophet Muhammad as His final messenger, and following the Quran and Sunnah for guidance in all aspects of life.';
        }
        
        // Default response
        return `Thank you for your question: "${message}"\n\nI'm currently running in offline mode. For comprehensive Islamic guidance, I recommend:\n\n• Consulting authentic Islamic sources\n• Speaking with local Islamic scholars\n• Referring to the Quran and authentic Hadith\n\nIs there a specific Islamic topic I can help you with using my offline knowledge?`;
    },

    handleMessage(data) {
        const messageContent = data.content || data.message || '';
        const metadata = data.metadata || {};

        switch (data.message_type || data.type) {
            case 'answer':
                this.displaySystemMessage(messageContent, metadata);
                break;
            case 'suggestions':
                this.displaySuggestions(metadata.suggestions || []);
                break;
            case 'error':
                this.displayMessage(`Error: ${messageContent}`, 'error');
                break;
            default:
                if (messageContent) {
                    this.displaySystemMessage(messageContent);
                }
        }
    },

    displayMessage(content, type = 'user') {
        const messagesContainer = document.getElementById('chatMessages');
        const messageElement = document.createElement('div');
        messageElement.className = `chat-message ${type}`;
        
        messageElement.innerHTML = `
            <div class="message-content">
                ${this.formatMessage(content)}
            </div>
        `;

        messagesContainer.appendChild(messageElement);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    },

    displaySystemMessage(content, metadata = {}) {
        let displayContent = content;
        
        if (metadata.sources && metadata.sources.length > 0) {
            displayContent += `\n\n📚 Sources: ${metadata.sources.join(', ')}`;
            
            if (metadata.is_islamic && metadata.confidence) {
                const confidenceLevel = metadata.confidence > 0.8 ? 'High' : 
                                      metadata.confidence > 0.5 ? 'Medium' : 'Low';
                displayContent += `\n🎯 Islamic Content Confidence: ${confidenceLevel}`;
            }
        }

        this.displayMessage(displayContent, 'system');
    },

    displaySuggestions(suggestions) {
        const messagesContainer = document.getElementById('chatMessages');
        const suggestionsElement = document.createElement('div');
        suggestionsElement.className = 'chat-suggestions';
        
        const suggestionsHtml = suggestions
            .map(suggestion => `
                <button class="suggestion-btn" onclick="chat.sendMessage('${suggestion.replace(/'/g, "\\'")}')">
                    ${suggestion}
                </button>
        `).join('');

        suggestionsElement.innerHTML = `
            <div class="suggestions-container">
                ${suggestionsHtml}
            </div>
        `;
        
        messagesContainer.appendChild(suggestionsElement);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    },

    formatMessage(content) {
        return content
            .replace(/\n/g, '<br>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>');
    },

    updateStatus(status) {
        const statusElement = document.getElementById('chatStatus');
        if (statusElement) {
            statusElement.className = `status-indicator ${status}`;
            statusElement.textContent = status.charAt(0).toUpperCase() + status.slice(1);
        }
    },

    disconnect() {
        if (this.socket) {
            this.socket.close(1000);
            this.socket = null;
        }
    }
};

// Navigation
const navigation = {
    currentSection: 'home',

    init() {
        const navItems = document.querySelectorAll('.nav-item[data-section]');
        
        navItems.forEach(item => {
            item.addEventListener('click', () => {
                const targetSection = item.dataset.section;
                this.navigateToSection(targetSection);
                this.updateActiveNavItem(item);
            });
        });

        this.initSectionHandlers();
    },

    navigateToSection(sectionName) {
        const contentSections = document.querySelectorAll('.content-section');
        
        contentSections.forEach(section => {
            if (section.id === `${sectionName}-section`) {
                section.classList.add('active');
            } else {
                section.classList.remove('active');
            }
        });

        this.currentSection = sectionName;

        // Section-specific actions
        if (sectionName === 'ask' || sectionName === 'chat') {
            // Show chat section for both 'ask' and 'chat' navigation
            document.getElementById('chat-section').classList.add('active');
            
            // Auto-connect to chat
            setTimeout(() => {
                chat.connect();
            }, 500);
        }
    },

    updateActiveNavItem(activeItem) {
        const navItems = document.querySelectorAll('.nav-item[data-section]');
        navItems.forEach(nav => nav.classList.remove('active'));
        activeItem.classList.add('active');
    },

    initSectionHandlers() {
        // Chat input handler
        const chatInput = document.getElementById('chatInput');
        const sendBtn = document.getElementById('sendBtn');

        if (chatInput && sendBtn) {
            const sendMessage = () => {
                const message = chatInput.value.trim();
                if (message) {
                    chat.sendMessage(message);
                    chatInput.value = '';
                }
            };

            sendBtn.addEventListener('click', sendMessage);
            chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    sendMessage();
                }
            });
        }

        // Ask question form handler
        const askForm = document.getElementById('askQuestionForm');
        if (askForm) {
            askForm.addEventListener('submit', async (event) => {
                event.preventDefault();
                
                const formData = new FormData(event.target);
                const questionData = {
                    title: formData.get('questionTitle'),
                    content: formData.get('questionContent'),
                    category: formData.get('questionCategory'),
                    language: formData.get('questionLanguage')
                };

                try {
                    const response = await api.request(CONFIG.ENDPOINTS.ASK_QUESTION, {
                        method: 'POST',
                        body: JSON.stringify(questionData)
                    });
                    showToast('Question submitted successfully!', 'success');
                    event.target.reset();
                } catch (error) {
                    showToast('Failed to submit question. Please try again.', 'error');
                }
            });
        }

        // Search form handler
        const searchSubmit = document.getElementById('searchSubmit');
        const searchInput = document.getElementById('searchInput');
        const globalSearch = document.getElementById('globalSearch');
        
        if (searchSubmit && searchInput) {
            const handleSearch = async () => {
                const query = searchInput.value.trim();
                if (!query) return;

                const filters = {
                    language: document.getElementById('searchLanguage')?.value || 'auto',
                    useML: document.getElementById('useMLSearch')?.checked || true
                };

                try {
                    const results = await api.search(query, filters);
                    this.displaySearchResults(results);
        } catch (error) {
                    showToast('Search failed. Please try again.', 'error');
                }
            };

            searchSubmit.addEventListener('click', handleSearch);
            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    handleSearch();
                }
            });
        }

        // Global search handler
        if (globalSearch) {
            globalSearch.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    const query = globalSearch.value.trim();
                    if (query) {
                        // Navigate to search section and populate
                        this.navigateToSection('search');
                        const searchInput = document.getElementById('searchInput');
                        if (searchInput) {
                            searchInput.value = query;
                        }
                        globalSearch.value = '';
                    }
                }
            });
        }
    },

    displaySearchResults(results) {
        const resultsContainer = document.getElementById('searchResults');
        if (!resultsContainer) return;

        if (!results.results || results.results.length === 0) {
            resultsContainer.innerHTML = `
                <div class="answer-card">
                    <div class="answer-content">
                        <h3 class="answer-title">No results found</h3>
                        <p class="answer-excerpt">Try adjusting your search terms or use different keywords.</p>
            </div>
            </div>
        `;
            return;
        }

        const resultsHtml = results.results.map(result => `
                    <div class="answer-card">
                <div class="answer-content">
                    <h3 class="answer-title">${result.question || 'Islamic Knowledge'}</h3>
                    <p class="answer-excerpt">${result.answer ? result.answer.substring(0, 200) + '...' : 'Click to view full answer'}</p>
                        <div class="answer-meta">
                        <span class="answer-date">${result.source_name || 'Islamic Knowledge Base'}</span>
                        ${result.similarity_score ? `<span class="similarity">Match: ${Math.round(result.similarity_score * 100)}%</span>` : ''}
                            </div>
                            </div>
                <div class="answer-actions">
                    <button class="action-btn" onclick="saveAnswer('${result.id || 'unknown'}')">
                        <i class="fas fa-bookmark"></i>
                        Save
                    </button>
                    <button class="action-btn" onclick="shareAnswer('${result.id || 'unknown'}')">
                        <i class="fas fa-share"></i>
                        Share
                    </button>
                        </div>
                    </div>
        `).join('');

        resultsContainer.innerHTML = resultsHtml;
    }
};

// Theme Management
const theme = {
    currentTheme: localStorage.getItem('theme-preference') || 'dark',

    init() {
        const themeButtons = document.querySelectorAll('.theme-btn');
        
        themeButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                const themeType = btn.dataset.theme;
                this.setTheme(themeType);
                this.updateActiveButton(btn);
            });
        });

        // Apply saved theme
        this.applyTheme(this.currentTheme);
        this.updateActiveButton(document.querySelector(`[data-theme="${this.currentTheme}"]`));
    },

    setTheme(themeType) {
        this.currentTheme = themeType;
        this.applyTheme(themeType);
        localStorage.setItem('theme-preference', themeType);
    },

    applyTheme(themeType) {
        const body = document.body;
        
        body.classList.remove('dark-theme', 'light-theme');
        
        if (themeType === 'dark') {
            body.classList.add('dark-theme');
        } else if (themeType === 'light') {
            body.classList.add('light-theme');
        } else {
            // Auto theme
            if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
                body.classList.add('dark-theme');
            } else {
                body.classList.add('light-theme');
            }
        }
    },

    updateActiveButton(activeBtn) {
        if (!activeBtn) return;
        
        const themeButtons = document.querySelectorAll('.theme-btn');
        themeButtons.forEach(btn => btn.classList.remove('active'));
        activeBtn.classList.add('active');
    }
};

// Authentication
const auth = {
    init() {
        // Modal handlers
        const loginModal = document.getElementById('loginModal');
        const registerModal = document.getElementById('registerModal');
        
        // Form handlers
        const loginForm = document.getElementById('loginForm');
        const registerForm = document.getElementById('registerForm');
        
        if (loginForm) {
            loginForm.addEventListener('submit', async (event) => {
                event.preventDefault();
                
                const formData = new FormData(event.target);
                const username = formData.get('loginUsername');
                const password = formData.get('loginPassword');

                try {
                    const response = await api.login(username, password);
                    showToast('Login successful!', 'success');
                    this.closeModals();
                } catch (error) {
                    showToast('Login failed. Please check your credentials.', 'error');
                }
            });
        }
        
        if (registerForm) {
            registerForm.addEventListener('submit', async (event) => {
                event.preventDefault();
                
                const formData = new FormData(event.target);
                const userData = {
                    username: formData.get('registerUsername'),
                    email: formData.get('registerEmail'),
                    password: formData.get('registerPassword')
                };

                try {
                    const response = await api.register(userData);
                    showToast('Registration successful! Please log in.', 'success');
                    this.closeModals();
                    this.showModal(loginModal);
                } catch (error) {
                    showToast('Registration failed. Please try again.', 'error');
                }
            });
        }

        // Modal close handlers
        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', this.closeModals);
        });

        // Modal switch handlers
        const showRegister = document.getElementById('showRegister');
        const showLogin = document.getElementById('showLogin');
        
        if (showRegister) {
            showRegister.addEventListener('click', (e) => {
                e.preventDefault();
                this.closeModals();
                this.showModal(registerModal);
            });
        }
        
        if (showLogin) {
            showLogin.addEventListener('click', (e) => {
                e.preventDefault();
                this.closeModals();
                this.showModal(loginModal);
            });
        }

        this.checkAuthStatus();
    },

    showModal(modal) {
        if (modal) {
            modal.classList.add('active');
        }
    },

    closeModals() {
        document.querySelectorAll('.modal').forEach(modal => {
            modal.classList.remove('active');
        });
    },

    checkAuthStatus() {
        const token = localStorage.getItem('authToken');
        if (token) {
            AppState.isAuthenticated = true;
        }
    },

    logout() {
        api.logout();
        showToast('Logged out successfully', 'info');
    }
};

// Utility Functions
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <i class="fas fa-${getToastIcon(type)}"></i>
        <span>${message}</span>
    `;

    toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 5000);
}

function getToastIcon(type) {
    const icons = {
        success: 'check-circle',
        error: 'exclamation-triangle',
        warning: 'exclamation-circle',
        info: 'info-circle'
    };
    return icons[type] || 'info-circle';
}

function saveAnswer(answerId) {
    showToast('Answer saved!', 'success');
}

function shareAnswer(answerId) {
    if (navigator.share) {
        navigator.share({
            title: 'Islamic Q&A Answer',
            url: window.location.href
        });
    } else {
        navigator.clipboard.writeText(window.location.href);
        showToast('Link copied to clipboard!', 'success');
    }
}

// Load sample data
function loadSampleAnswers() {
    const answersList = document.getElementById('answersList');
    if (!answersList) return;

    const sampleAnswers = [
        {
            title: "How to perform Wudu (Ablution) correctly before prayer",
            excerpt: "Wudu is the ritual purification required before prayer. The steps include: 1) Make intention (Niyyah), 2) Say Bismillah, 3) Wash hands 3 times, 4) Rinse mouth 3 times, 5) Rinse nose 3 times, 6) Wash face 3 times, 7) Wash arms to elbows 3 times, 8) Wipe head once, 9) Wash feet to ankles 3 times.",
            date: "Today",
            source: "AI + Islamic Knowledge"
        },
        {
            title: "Understanding the Five Pillars of Islam",
            excerpt: "The Five Pillars are the foundation of Muslim practice: 1) Shahada (Declaration of Faith), 2) Salah (Prayer), 3) Zakat (Charity), 4) Sawm (Fasting during Ramadan), 5) Hajj (Pilgrimage to Mecca). Each pillar represents a fundamental aspect of Islamic worship and community.",
            date: "2 hours ago",
            source: "Hybrid AI Response"
        },
        {
            title: "The importance and benefits of reading Quran daily",
            excerpt: "Reading the Quran daily brings numerous spiritual benefits including increased faith, guidance for life decisions, peace of mind, and connection with Allah. The Prophet (peace be upon him) encouraged regular recitation and reflection on the Quran's teachings.",
            date: "6 hours ago",
            source: "Islamic Knowledge Base"
        },
        {
            title: "Prayer times and their significance in Islam",
            excerpt: "Muslims pray five times daily: Fajr (dawn), Dhuhr (midday), Asr (afternoon), Maghrib (sunset), and Isha (night). Each prayer time has spiritual significance and helps maintain constant remembrance of Allah throughout the day.",
            date: "1 day ago",
            source: "AI-Enhanced Answer"
        }
    ];

    const answersHtml = sampleAnswers.map(answer => `
        <div class="answer-card">
            <div class="answer-content">
                <h3 class="answer-title">${answer.title}</h3>
                <p class="answer-excerpt">${answer.excerpt}</p>
                <div class="answer-meta">
                    <span class="answer-date">${answer.date}</span>
                    <span class="answer-source">📚 ${answer.source}</span>
                </div>
            </div>
            <div class="answer-actions">
                <button class="action-btn" onclick="saveAnswer('sample')">
                    <i class="fas fa-bookmark"></i>
                    Save
                </button>
                <button class="action-btn" onclick="shareAnswer('sample')">
                    <i class="fas fa-share"></i>
                    Share
                </button>
                <button class="action-btn" onclick="chat.sendMessage('Tell me more about ${answer.title.replace(/'/g, "\\'")}')">
                    <i class="fas fa-comments"></i>
                    Ask AI
                </button>
            </div>
        </div>
    `).join('');

    answersList.innerHTML = answersHtml;
}

// Load recent answers for the Recent Q&A section
function loadRecentAnswers() {
    const recentAnswersList = document.getElementById('recentAnswersList');
    if (!recentAnswersList) return;

    const recentAnswers = [
        {
            title: "What is the best time to make Dua?",
            excerpt: "The Prophet (peace be upon him) mentioned several blessed times for making Dua: between Maghrib and Isha, during the last third of the night, after obligatory prayers, during rain, while fasting, and between Asr and Maghrib on Fridays.",
            date: "2 minutes ago",
            source: "Hybrid AI + Hadith Collection"
        },
        {
            title: "Can I pray Taraweeh at home?",
            excerpt: "Yes, Taraweeh prayers can be performed at home. While praying in congregation at the mosque has extra reward, individual prayer at home is perfectly acceptable and valid in Islam. The Prophet (peace be upon him) sometimes prayed Taraweeh at home.",
            date: "15 minutes ago",
            source: "Islamic Jurisprudence"
        },
        {
            title: "How to seek forgiveness from Allah?",
            excerpt: "Seeking forgiveness (Istighfar) involves sincere repentance (Tawbah) which includes: recognizing the sin, feeling genuine remorse, asking Allah for forgiveness, and making a firm intention not to repeat the sin. Regular recitation of 'Astaghfirullah' is also recommended.",
            date: "1 hour ago",
            source: "AI + Quran & Sunnah"
        },
        {
            title: "What are the etiquettes of visiting a mosque?",
            excerpt: "Mosque etiquettes include: performing ablution before entering, dressing modestly, removing shoes, entering with the right foot while saying the mosque entry supplication, praying two Rakah Tahiyyat al-Masjid, maintaining cleanliness, and observing silence.",
            date: "3 hours ago",
            source: "Islamic Manners Guide"
        }
    ];

    const recentHtml = recentAnswers.map(answer => `
        <div class="answer-card">
            <div class="answer-content">
                <h3 class="answer-title">${answer.title}</h3>
                <p class="answer-excerpt">${answer.excerpt}</p>
                <div class="answer-meta">
                    <span class="answer-date">${answer.date}</span>
                    <span class="answer-source">📚 ${answer.source}</span>
                </div>
            </div>
            <div class="answer-actions">
                <button class="action-btn" onclick="saveAnswer('recent')">
                    <i class="fas fa-bookmark"></i>
                    Save
                </button>
                <button class="action-btn" onclick="shareAnswer('recent')">
                    <i class="fas fa-share"></i>
                    Share
                </button>
                <button class="action-btn" onclick="chat.sendMessage('Tell me more about ${answer.title.replace(/'/g, "\\'")}')">
                    <i class="fas fa-comments"></i>
                    Ask AI
                </button>
            </div>
        </div>
    `).join('');

    recentAnswersList.innerHTML = recentHtml;
}

// Initialize Application
document.addEventListener('DOMContentLoaded', function() {
    console.log('🕌 Islamic Q&A Platform - Beautiful Interface Loading...');
    
    // Initialize all services
    navigation.init();
    theme.init();
    auth.init();
    
    // Load sample data
    loadSampleAnswers();
    loadRecentAnswers();
    
    // Auto-connect chat if on ask section
    if (navigation.currentSection === 'ask') {
        chat.connect();
    }
    
    console.log('✅ Beautiful Islamic Q&A Platform Ready!');
});

// Handle online/offline status
window.addEventListener('online', function() {
    showToast('Connection restored', 'success');
    if (!AppState.chatConnected) {
        chat.connect();
    }
});

window.addEventListener('offline', function() {
    showToast('Connection lost', 'warning');
});

// Clean up on page unload
window.addEventListener('beforeunload', function() {
    chat.disconnect();
});
