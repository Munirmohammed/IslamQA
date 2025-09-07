// Frontend Configuration (safe, no secrets)
const CONFIG_ENV = {
    HUGGINGFACE_API_KEY: null, 
    GROQ_API_KEY: null,  
    OPENAI_API_KEY: null, 
    // API Endpoints
    API_BASE_URL: 'http://localhost:8000',
    WS_URL: 'ws://localhost:8000/ws/chat',
    // AI Configuration
    AI_MODELS: {
        HUGGINGFACE: 'facebook/blenderbot-400M-distill',
        GROQ: 'llama3-8b-8192',
        OPENAI: 'gpt-3.5-turbo'
    },
    // Features
    ENABLE_AI_CHAT: true,
    ENABLE_WEBSOCKET: false,
    ENABLE_TYPING_INDICATOR: true
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = CONFIG_ENV;
} else {
    window.CONFIG_ENV = CONFIG_ENV;
}
