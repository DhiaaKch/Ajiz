const express = require('express');
const axios = require('axios');
const WebSocket = require('ws');
const cors = require('cors');
const bodyParser = require('body-parser');
const FormData = require('form-data');

const app = express();
const PORT = 3000;

app.use(cors());
app.use(bodyParser.json());
app.use(express.static('public'));

// CSP Middleware to allow CodeMirror and local scripts
app.use((req, res, next) => {
    res.setHeader(
        'Content-Security-Policy',
        "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; font-src 'self' data:;"
    );
    next();
});

// --- Configuration from API.txt ---
const COOKIES = 'G_ENABLED_IDPS=google; csrftoken=mAoxC3u6BS40wqcASSV4Ioseyx3SzWIn; crossSessionId=iikptg1eco6d3gsvlkapf6e8f01plnmy';
const CSRF_TOKEN = 'mAoxC3u6BS40wqcASSV4Ioseyx3SzWIn';
const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36';

const BASE_HEADERS = {
    'accept': '*/*',
    'accept-language': 'en-US,en;q=0.9,fr;q=0.8',
    'cookie': COOKIES,
    'origin': 'https://csacademy.com',
    'referer': 'https://csacademy.com/contest/archive/task/addition/',
    'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': USER_AGENT,
    'x-csrftoken': CSRF_TOKEN,
    'x-requested-with': 'XMLHttpRequest'
};

const WS_URL = 'wss://ws3.csacademy.com/';

// --- WebSocket Setup ---
let ws;
const pendingRequests = new Map(); // Map<objectId, resolveFunction>

function connectWebSocket() {
    ws = new WebSocket(WS_URL, {
        headers: {
            'User-Agent': USER_AGENT,
            'Origin': 'https://csacademy.com',
            'Cookie': COOKIES
        }
    });

    ws.on('open', () => {
        console.log('Connected to CS Academy WebSocket');

        // Subscription Logic
        // Protocol: s {channel} {length_of_channel_string + 2}

        // 1. Subscribe to Global Events
        const globalChannel = 'global-events';
        ws.send(`s ${globalChannel} ${globalChannel.length + 2}`);

        // 2. Subscribe to Workspace Session (Critical for run results)
        // Check if we have the session ID from the API content or user input.
        // For now, hardcoding based on API.txt user (221818) and updated sessionId.
        // Ideally this should be dynamic, but for this task we use what we have.
        const userId = '221818';
        const sessionId = '0906684182904498'; // Updated from user cURL
        const workspaceChannel = `workspacesession-${userId}-${sessionId}`;

        ws.send(`s ${workspaceChannel} ${workspaceChannel.length + 2}`);
        console.log(`Subscribed to: ${workspaceChannel}`);
    });

    ws.on('message', (data) => {
        const message = data.toString();
        // Debugging: Log the first 200 chars of any message
        console.log('WS Received:', message.substring(0, 200));

        if (message.startsWith('m ')) {
            try {
                const jsonStartIndex = message.indexOf('{');
                if (jsonStartIndex !== -1) {
                    const jsonStr = message.substring(jsonStartIndex);
                    const parsed = JSON.parse(jsonStr);

                    if (parsed.objectType === 'customrun' && parsed.objectId) {
                        const resolve = pendingRequests.get(parsed.objectId);

                        if (parsed.type === 'runResults' && resolve) {
                            resolve(parsed.data);
                            pendingRequests.delete(parsed.objectId);
                        } else if (parsed.type === 'compile_status' && parsed.data.compileOK === false && resolve) {
                            // Handle compilation error
                            resolve({ error: parsed.data.compilerMessage });
                            pendingRequests.delete(parsed.objectId);
                        }
                    }
                }
            } catch (e) {
                console.error('Error parsing WebSocket message:', e);
            }
        }
    });

    ws.on('close', () => {
        console.log('WebSocket disconnected. Reconnecting...');
        setTimeout(connectWebSocket, 1000);
    });

    ws.on('error', (err) => {
        console.error('WebSocket error:', err);
    });
}

connectWebSocket();

// --- API Endpoints ---

app.post('/api/run', async (req, res) => {
    const { sourceCode, input } = req.body;

    // Updated sessionId from user's cURL
    const sessionId = '0906684182904498';
    const workspaceId = '2931018';

    const form = new FormData();
    form.append('workspaceId', workspaceId);
    form.append('sessionId', sessionId);
    form.append('sourceCode', sourceCode);
    form.append('programmingLanguageId', '1');
    form.append('customInput', input || '');
    form.append('contestTaskId', '38');

    try {
        const response = await axios.post('https://csacademy.com/eval/submit_custom_run/', form, {
            headers: {
                ...BASE_HEADERS,
                ...form.getHeaders()
            }
        });
        const { customRunId } = response.data;

        console.log(`Custom run submitted: ${customRunId}`);

        // Wait for result via WebSocket
        const resultPromise = new Promise((resolve, reject) => {
            pendingRequests.set(customRunId, resolve);
            setTimeout(() => {
                if (pendingRequests.has(customRunId)) {
                    pendingRequests.delete(customRunId);
                    reject(new Error('Timeout waiting for results'));
                }
            }, 60000);
        });

        const result = await resultPromise;
        res.json(result);

    } catch (error) {
        console.error('Error submitting run:', error.message);
        if (error.response) {
            console.error('Response status:', error.response.status);
            console.error('Response data:', JSON.stringify(error.response.data, null, 2));
        }
        res.status(500).json({ error: 'Failed to submit run', details: error.message });
    }
});

app.post('/api/submit', async (req, res) => {
    const { sourceCode } = req.body;

    const sessionId = '0906684182904498';
    const workspaceId = '2931018';

    const form = new FormData();
    form.append('workspaceId', workspaceId);
    form.append('sessionId', sessionId);
    form.append('contestTaskId', '38');
    form.append('sourceCode', sourceCode);
    form.append('programmingLanguageId', '1');

    try {
        const response = await axios.post('https://csacademy.com/eval/submit_evaljob/', form, {
            headers: {
                ...BASE_HEADERS,
                ...form.getHeaders()
            }
        });
        res.json(response.data);

    } catch (error) {
        console.error('Error submitting solution:', error.message);
        if (error.response) {
            console.error('Response status:', error.response.status);
            console.error('Response data:', JSON.stringify(error.response.data, null, 2));
        }
        res.status(500).json({ error: 'Failed to submit solution', details: error.message });
    }
});

app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
});
