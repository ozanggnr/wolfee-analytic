// Wolfee Analytics Configuration
// When served from FastAPI, API is at same origin
const API_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://127.0.0.1:8000'
    : '';  // Same origin in production
