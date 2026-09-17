// Wolfee Analytics Configuration
// When served from FastAPI (same origin), API_URL is empty string ''
// If running on a separate dev server (e.g. port 5500/3000), use same hostname on port 8000
const API_URL = (window.location.port === '8000' || !window.location.port)
    ? ''
    : `${window.location.protocol}//${window.location.hostname}:8000`;
