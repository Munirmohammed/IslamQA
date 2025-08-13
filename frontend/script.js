/**
 * Modern Islamic Q&A Platform
 * Beautiful Dark Theme Interface
 */

// Configuration
const CONFIG = {
    API_BASE_URL: CONFIG_ENV?.API_BASE_URL || 'http://localhost:8000',
    WS_URL: CONFIG_ENV?.WS_URL || 'ws://localhost:8000/ws/chat',
    ENDPOINTS: {
        LOGIN: '/api/v1/auth/login',
        REGISTER: '/api/v1/auth/register',
        SEARCH: '/api/v1/search',
        ASK_QUESTION: '/api/v1/questions/ask'
    },
    // AI API Keys from config
    AI_KEYS: {
        HUGGINGFACE: CONFIG_ENV?.HUGGINGFACE_API_KEY,
        GROQ: CONFIG_ENV?.GROQ_API_KEY,
        OPENAI: CONFIG_ENV?.OPENAI_API_KEY
    },
    AI_MODELS: CONFIG_ENV?.AI_MODELS || {
        HUGGINGFACE: 'facebook/blenderbot-400M-distill',
        GROQ: 'llama3-8b-8192',
        OPENAI: 'gpt-3.5-turbo'
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
        // DISABLED: Always use frontend AI instead of WebSocket
        console.log('🚫 WebSocket disabled - using frontend AI only');
        this.updateStatus('offline');
        this.handleConnectionError();
        return;
        
        // Old WebSocket code (disabled)
        /*
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
        */
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
        this.updateStatus('ai');
        
        // Show AI ready message
        const messagesContainer = document.getElementById('chatMessages');
        if (messagesContainer && messagesContainer.children.length <= 1) { // Only welcome message
            const aiMessage = document.createElement('div');
            aiMessage.className = 'chat-message system';
            aiMessage.innerHTML = `
                <div class="message-content">
                    <strong>🤖 AI Assistant Ready</strong><br>
                    I'm powered by advanced AI technology and ready to help answer your questions! Ask me anything - from Islamic knowledge to general topics.<br><br>
                    <em>Try asking: "How to perform prayer?" or "What is the meaning of life?"</em>
                </div>
            `;
            messagesContainer.appendChild(aiMessage);
        }
        
        // Don't schedule reconnect since we're using AI mode
        // this.scheduleReconnect();
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
            this.showTypingIndicator();
        } else {
            // Use advanced free AI when WebSocket is not connected
            this.displayMessage(message, 'user');
            this.showTypingIndicator();
            
            // Use advanced AI with Islamic context
            this.getAdvancedAIResponse(message).then(response => {
                this.hideTypingIndicator();
                this.displaySystemMessage(response, {
                    sources: ['Advanced AI Assistant'],
                    is_islamic: true,
                    confidence: 0.9
                });
            }).catch(error => {
                this.hideTypingIndicator();
                const fallbackResponse = this.getOfflineAIResponse(message);
                this.displaySystemMessage(fallbackResponse, {
                    sources: ['Offline AI System'],
                    is_islamic: true,
                    confidence: 0.8
                });
            });
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

    async getAdvancedAIResponse(message) {
        try {
            // Try Hugging Face AI first for natural responses
            let response = await this.tryHuggingFaceAPI(message);
            if (response) {
                return response;
            }
            
            // Try other free AI services
            response = await this.tryFreePublicAPI(message);
            if (response) {
                return response;
            }
            
            response = await this.tryGroqAPI(message);
            if (response) {
                return response;
            }
            
            // Fallback to smart simulation
            return this.getSmartFallbackResponse(message);
        } catch (error) {
            console.error('Advanced AI failed:', error);
            return `I apologize, but I'm having technical difficulties right now. Please try asking your question again!`;
        }
    },

    getEnhancedIslamicResponse(message) {
        const messageLower = message.toLowerCase();
        
        // Comprehensive Islamic Q&A Database
        const islamicQA = {
            'how to perform prayer': `**How to Perform Islamic Prayer (Salah):**

**Preparation:**
1. **Wudu (Ablution)**: Perform ritual cleansing
2. **Qibla**: Face towards Mecca
3. **Niyyah**: Make intention in your heart
4. **Clean place**: Pray on clean ground/prayer mat

**Prayer Steps:**
1. **Takbir**: Say "Allahu Akbar" while raising hands
2. **Al-Fatiha**: Recite the opening chapter of Quran
3. **Surah**: Recite another chapter from Quran
4. **Ruku**: Bow down saying "Subhana Rabbiyal Adheem"
5. **Qiyam**: Stand up saying "Sami Allahu liman hamidah"
6. **Sujud**: Prostrate twice saying "Subhana Rabbiyal A'la"
7. **Tashahhud**: Sit and recite the testimony
8. **Tasleem**: End with "Assalamu alaikum" to both sides

**Daily Prayers:**
• **Fajr**: 2 Rakah (before sunrise)
• **Dhuhr**: 4 Rakah (after midday)
• **Asr**: 4 Rakah (late afternoon)
• **Maghrib**: 3 Rakah (after sunset)
• **Isha**: 4 Rakah (night)

May Allah accept your prayers! 🤲`,

            'what are the five pillars': `**The Five Pillars of Islam:**

**1. Shahada (Declaration of Faith) ☪️**
"La ilaha illa Allah, Muhammad rasul Allah"
(There is no god but Allah, and Muhammad is His messenger)

**2. Salah (Prayer) 🤲**
Five daily prayers connecting us with Allah

**3. Zakat (Charity) 💝**
Giving 2.5% of wealth annually to help the poor

**4. Sawm (Fasting) 🌙**
Fasting during the month of Ramadan

**5. Hajj (Pilgrimage) 🕋**
Pilgrimage to Mecca once in a lifetime if able

These pillars form the foundation of Muslim faith and practice, uniting Muslims worldwide in worship and community.`,

            'what is shahada': `**The Shahada - Declaration of Faith:**

**Arabic:** "Ash-hadu an la ilaha illa Allah, wa ash-hadu anna Muhammadan rasul Allah"

**English:** "I bear witness that there is no god but Allah, and I bear witness that Muhammad is the messenger of Allah"

**Significance:**
• **First Pillar** of Islam
• **Entry** into Islam - sincere recitation makes one Muslim
• **Core Belief** - Oneness of Allah (Tawhid)
• **Daily Remembrance** - recited in prayers

**Two Parts:**
1. **La ilaha illa Allah** - No deity worthy of worship except Allah
2. **Muhammad rasul Allah** - Muhammad is Allah's final messenger

The Shahada is the foundation of Islamic belief, affirming monotheism and the prophethood of Muhammad (peace be upon him).`,

            'how to make wudu': `**How to Perform Wudu (Ablution):**

**Steps in Order:**
1. **Intention (Niyyah)** - Make intention in your heart
2. **Bismillah** - Say "In the name of Allah"
3. **Wash hands** 3 times up to wrists
4. **Rinse mouth** 3 times
5. **Rinse nose** 3 times (sniff water and blow out)
6. **Wash face** 3 times from forehead to chin
7. **Wash arms** 3 times up to elbows (right then left)
8. **Wipe head** once with wet hands
9. **Wash feet** 3 times up to ankles (right then left)

**Dua after Wudu:**
"Ash-hadu an la ilaha illa Allah, wa ash-hadu anna Muhammadan rasul Allah"

**When Wudu is Required:**
• Before prayer (Salah)
• Before touching the Quran
• Before entering mosque (recommended)

**What Breaks Wudu:**
• Using the bathroom
• Passing gas
• Deep sleep
• Loss of consciousness

Wudu purifies both body and soul! 💧`,

            'what is ramadan': `**Ramadan - The Holy Month:**

**What is Ramadan?**
The 9th month of the Islamic lunar calendar, when Muslims fast from dawn to sunset.

**Duration:** 29-30 days (varies by moon sighting)

**Fasting Rules:**
• **From**: Fajr (dawn) prayer time
• **Until**: Maghrib (sunset) prayer time
• **Abstain from**: Food, drink, marital relations, smoking

**Who Must Fast:**
• Adult Muslims who are healthy
• **Exemptions**: Sick, traveling, pregnant, elderly, menstruating women

**Special Practices:**
• **Suhoor**: Pre-dawn meal
• **Iftar**: Breaking fast at sunset
• **Taraweeh**: Special night prayers
• **Laylat al-Qadr**: Night of Power (last 10 nights)

**Benefits:**
• Spiritual purification
• Self-discipline and control
• Empathy for the poor
• Increased charity and prayer
• Community unity

**End of Ramadan:**
Celebrated with **Eid al-Fitr** - a joyous festival!

Ramadan Mubarak! 🌙✨`
        };

        // Check for direct matches first
        for (const [key, response] of Object.entries(islamicQA)) {
            if (messageLower.includes(key.replace(/\s+/g, '')) || 
                key.split(' ').every(word => messageLower.includes(word))) {
                return response;
            }
        }

        // Pattern matching for common questions
        if (messageLower.includes('pray') || messageLower.includes('salah')) {
            return islamicQA['how to perform prayer'];
        }
        
        if (messageLower.includes('pillar')) {
            return islamicQA['what are the five pillars'];
        }
        
        if (messageLower.includes('shahada') || messageLower.includes('declaration')) {
            return islamicQA['what is shahada'];
        }
        
        if (messageLower.includes('wudu') || messageLower.includes('ablution')) {
            return islamicQA['how to make wudu'];
        }
        
        if (messageLower.includes('ramadan') || messageLower.includes('fasting')) {
            return islamicQA['what is ramadan'];
        }

        // Greeting responses
        if (messageLower.includes('hello') || messageLower.includes('hi') || messageLower.includes('salaam')) {
            return `**Assalamu Alaikum wa Rahmatullahi wa Barakatuh!** 🕌

Welcome to our Islamic Q&A platform! I'm here to help you learn about Islam.

**Popular Questions:**
• How to perform prayer?
• What are the Five Pillars of Islam?
• How to make Wudu?
• What is Ramadan?
• What is the Shahada?

Feel free to ask any Islamic question! 📚✨`;
        }

        // Default intelligent response
        return `**Thank you for your question about:** "${message}"

I'd be happy to help you learn about Islam! Here are some topics I can assist with:

**🕌 Core Beliefs & Practices:**
• Five Pillars of Islam
• Shahada (Declaration of Faith)
• Prayer (Salah) and Wudu
• Fasting and Ramadan
• Hajj and Umrah

**📖 Islamic Knowledge:**
• Quran and its teachings
• Prophet Muhammad (peace be upon him)
• Islamic history and values
• Daily Islamic practices

**🤲 Worship & Spirituality:**
• How to pray correctly
• Duas and Dhikr
• Islamic manners and ethics

Please feel free to ask a specific Islamic question, and I'll provide detailed, authentic guidance based on Quran and Sunnah! 

*What would you like to learn about Islam today?* 🌟`;
    },

    getSmartFallbackResponse(message) {
        const messageLower = message.toLowerCase();
        
        // Greetings and casual responses
        if (messageLower.includes('hi') || messageLower.includes('hello') || messageLower.includes('hey')) {
            return `Hello! 👋 Nice to meet you! I'm an AI assistant ready to help with your questions. What would you like to talk about today?`;
        }
        
        if (messageLower.includes('how are you')) {
            return `I'm doing great, thank you for asking! 😊 I'm here and ready to help answer your questions. How can I assist you today?`;
        }
        
        if (messageLower.includes('what is your name')) {
            return `I'm an AI assistant created to help answer questions and have conversations. You can think of me as your friendly digital helper! What would you like to know?`;
        }
        
        // Question responses
        if (messageLower.includes('meaning of life')) {
            return `That's a profound question! The meaning of life has been pondered by philosophers, theologians, and thinkers throughout history. Many believe it involves finding purpose, building relationships, contributing to others, personal growth, and spiritual connection. What aspects of life's meaning are you most curious about?`;
        }
        
        if (messageLower.includes('how') && messageLower.includes('work')) {
            return `Great question! Most things work through a combination of principles, processes, and interactions. Could you be more specific about what you'd like to understand? I'd be happy to explain the workings of technology, natural phenomena, social systems, or whatever interests you!`;
        }
        
        if (messageLower.includes('joke') || messageLower.includes('funny')) {
            return `Here's a light one for you: Why don't scientists trust atoms? Because they make up everything! 😄 Got any other questions I can help with?`;
        }
        
        // Islamic questions
        if (messageLower.includes('islam') || messageLower.includes('muslim') || messageLower.includes('allah')) {
            return `I'd be happy to discuss Islamic topics! Islam is a rich tradition with deep spiritual and practical teachings. Whether you're curious about beliefs, practices, history, or contemporary issues, feel free to ask specific questions and I'll do my best to provide helpful information.`;
        }
        
        // General intelligent response
        return `That's an interesting question about "${message}"! 

I'd love to help you explore this topic. While I'm currently having some connection issues with my advanced AI services, I can still provide thoughtful responses based on general knowledge.

Could you tell me a bit more about what specifically interests you about this? That way I can give you a more focused and helpful answer! 🤔💭`;
    },

    async tryHuggingFaceAPI(message) {
        try {
            console.log('🤖 Trying Hugging Face AI for:', message);
            
            // Check if API key is available
            if (!CONFIG.AI_KEYS.HUGGINGFACE) {
                console.log('❌ Hugging Face API key not available');
                return null;
            }
            
            // Use Blenderbot for better conversational AI
            const response = await fetch(`https://api-inference.huggingface.co/models/${CONFIG.AI_MODELS.HUGGINGFACE}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${CONFIG.AI_KEYS.HUGGINGFACE}`
                },
                body: JSON.stringify({
                    inputs: message,
                    parameters: {
                        max_length: 300,
                        temperature: 0.8,
                        do_sample: true,
                        top_p: 0.9
                    }
                })
            });

            if (response.ok) {
                const result = await response.json();
                console.log('🎯 Hugging Face response:', result);
                
                // Handle different response formats
                if (result && result[0]) {
                    let aiResponse = '';
                    
                    // Try generated_text first (most common)
                    if (result[0].generated_text) {
                        aiResponse = result[0].generated_text.trim();
                    }
                    // Try response field (some models use this)
                    else if (result[0].response) {
                        aiResponse = result[0].response.trim();
                    }
                    // Try the result directly if it's a string
                    else if (typeof result[0] === 'string') {
                        aiResponse = result[0].trim();
                    }
                    
                    // Clean up the response
                    if (aiResponse) {
                        // Remove the original input if it's repeated
                        if (aiResponse.includes(message)) {
                            aiResponse = aiResponse.replace(message, '').trim();
                        }
                        
                        // If response is good length, return it
                        if (aiResponse.length >= 10) {
                            return aiResponse;
                        }
                    }
                }
            } else {
                console.log('❌ Hugging Face API error:', response.status, response.statusText);
            }
        } catch (error) {
            console.log('❌ Hugging Face API failed:', error);
        }
        return null;
    },

    async tryFreePublicAPI(message) {
        try {
            console.log('🌐 Trying free public AI for:', message);
            
            // Try a working free AI service
            const response = await fetch('https://api.pawan.krd/v1/chat/completions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer pk-this-is-a-real-free-api-key-pk-for-everyone'
                },
                body: JSON.stringify({
                    model: 'gpt-3.5-turbo',
                    messages: [
                        {
                            role: 'user',
                            content: message
                        }
                    ],
                    temperature: 0.7,
                    max_tokens: 300
                })
            });

            if (response.ok) {
                const result = await response.json();
                console.log('🎯 Free API response:', result);
                
                if (result.choices && result.choices[0] && result.choices[0].message) {
                    return result.choices[0].message.content.trim();
                }
            } else {
                console.log('❌ Free API error:', response.status, await response.text());
            }
        } catch (error) {
            console.log('❌ Free Public API failed:', error);
        }
        return null;
    },

    async tryOpenAIFreeAPI(prompt) {
        // For now, return null - you can add OpenAI API key later
        return null;
    },

    async tryGroqAPI(message) {
        try {
            console.log('🚀 Trying Groq AI for:', message);
            
            // Check if API key is available
            if (!CONFIG.AI_KEYS.GROQ) {
                console.log('❌ Groq API key not available');
                return null;
            }
            
            // Try Groq's free API (very fast)
            const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${CONFIG.AI_KEYS.GROQ}`
                },
                body: JSON.stringify({
                    messages: [
                        {
                            role: 'user',
                            content: message
                        }
                    ],
                    model: CONFIG.AI_MODELS.GROQ,
                    temperature: 0.7,
                    max_tokens: 300
                })
            });

            if (response.ok) {
                const result = await response.json();
                if (result.choices && result.choices[0] && result.choices[0].message) {
                    return result.choices[0].message.content.trim();
                }
            }
        } catch (error) {
            console.log('❌ Groq API failed:', error);
        }
        return null;
    },

    async tryClaudeAPI(prompt) {
        // For now, return null - you can add Claude API key later  
        return null;
    },

    showTypingIndicator() {
        const messagesContainer = document.getElementById('chatMessages');
        
        // Remove existing typing indicator
        this.hideTypingIndicator();
        
        const typingElement = document.createElement('div');
        typingElement.className = 'chat-message system typing-indicator';
        typingElement.id = 'typing-indicator';
        typingElement.innerHTML = `
            <div class="message-content">
                <div class="typing-animation">
                    <span class="typing-dot"></span>
                    <span class="typing-dot"></span>
                    <span class="typing-dot"></span>
                </div>
            </div>
        `;
        
        messagesContainer.appendChild(typingElement);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    },

    hideTypingIndicator() {
        const typingIndicator = document.getElementById('typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    },

    handleMessage(data) {
        const messageContent = data.content || data.message || '';
        const metadata = data.metadata || {};

        // Hide typing indicator when any response comes
        this.hideTypingIndicator();

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
            
            // Custom status text
            switch (status) {
                case 'ai':
                    statusElement.textContent = 'AI Ready';
                    statusElement.className = 'status-indicator connected';
                    break;
                case 'connecting':
                    statusElement.textContent = 'Connecting...';
                    break;
                case 'connected':
                    statusElement.textContent = 'Connected';
                    break;
                case 'offline':
                    statusElement.textContent = 'Offline';
                    break;
                default:
                    statusElement.textContent = status.charAt(0).toUpperCase() + status.slice(1);
            }
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
