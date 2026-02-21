import threading
import json
import time
import requests
import websocket
from flask import Flask, request, jsonify, send_from_directory, Response

import logging

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("debug.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='public')

# --- Configuration ---
COOKIES = 'G_ENABLED_IDPS=google; csrftoken=mAoxC3u6BS40wqcASSV4Ioseyx3SzWIn; crossSessionId=iikptg1eco6d3gsvlkapf6e8f01plnmy'
CSRF_TOKEN = 'mAoxC3u6BS40wqcASSV4Ioseyx3SzWIn'
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36'
SESSION_ID = '0906684182904498' # From user cURL
USER_ID = '221818' # From API.txt
WORKSPACE_ID = '2931018'

BASE_HEADERS = {
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
}

WS_URL = 'wss://ws3.csacademy.com/'

# --- WebSocket & Cache ---
RESULTS_CACHE = {} # {customRunId: result_data}
WS_CONNECTED = False

def on_message(ws, message):
    try:
        if message.startswith('m '):
            json_start = message.find('{')
            if json_start != -1:
                json_str = message[json_start:]
                parsed = json.loads(json_str)
                
                # Check for run results
                if parsed.get('objectType') == 'customrun' and parsed.get('objectId'):
                    obj_id = parsed['objectId']
                    if parsed.get('type') == 'runResults':
                        logger.info(f"Received results for run {obj_id}")
                        RESULTS_CACHE[obj_id] = parsed['data']
                    elif parsed.get('type') == 'compile_status' and not parsed['data'].get('compileOK'):
                         logger.error(f"Compilation failed for run {obj_id}")
                         RESULTS_CACHE[obj_id] = {'error': parsed['data'].get('compilerMessage')}
                
                # Check for submission results (evaljob)
                elif parsed.get('objectType') == 'evaljob' and parsed.get('objectId'):
                    obj_id = parsed['objectId']
                    
                    # Initialize cache entry if not exists
                    if obj_id not in RESULTS_CACHE:
                         RESULTS_CACHE[obj_id] = {'tests': [], 'status': 'pending'}
                    
                    if parsed.get('type') == 'test_results':
                         # Append test results
                         tests = parsed['data'].get('tests', {})
                         for tid, tdata in tests.items():
                              RESULTS_CACHE[obj_id]['tests'].append(tdata)
                              
                    elif parsed.get('type') == 'finished' or parsed.get('type') == 'done':
                         # Mark as done and store final data
                         RESULTS_CACHE[obj_id]['status'] = 'done'
                         if parsed.get('data'):
                             RESULTS_CACHE[obj_id].update(parsed['data'])
                         logger.info(f"Job {obj_id} finished")
        
        # Keepalive / Heartbeat
        if 'heartbeat' in message:
             pass 
             # logger.debug("Heartbeat received")

    except Exception as e:
        logger.error(f"Error processing message: {e}")

def on_error(ws, error):
    logger.error(f"WebSocket Error: {error}")

def on_close(ws, close_status_code, close_msg):
    global WS_CONNECTED
    WS_CONNECTED = False
    logger.info("WebSocket closed")

def on_open(ws):
    global WS_CONNECTED
    WS_CONNECTED = True
    logger.info("WebSocket connection opened")
    
    # Subscribe to channels
    channels = [
        'global-events',
        f'workspacesession-{USER_ID}-{SESSION_ID}'
    ]
    
    for channel in channels:
        msg = f"s {channel} {len(channel) + 2}"
        ws.send(msg)
        logger.info(f"Subscribed to: {channel}")

def start_websocket():
    # WebSocketApp header needs to be a list or dict
    ws_headers = {
        'User-Agent': USER_AGENT,
        'Origin': 'https://csacademy.com',
        'Cookie': COOKIES
    }
    
    while True:
        ws = websocket.WebSocketApp(WS_URL,
                                    header=ws_headers,
                                    on_open=on_open,
                                    on_message=on_message,
                                    on_error=on_error,
                                    on_close=on_close)
        ws.run_forever()
        time.sleep(2) # Reconnect delay

# Start WS in background thread
ws_thread = threading.Thread(target=start_websocket, daemon=True)
ws_thread.start()

# --- Flask Routes ---

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('public', path)

@app.route('/api/run', methods=['POST'])
def run_code():
    data = request.json
    source_code = data.get('sourceCode')
    input_data = data.get('input', '')
    
    # Payload for form-data
    # requests handles boundaries automatically when files/data passed
    payload = {
        'workspaceId': WORKSPACE_ID,
        'sessionId': SESSION_ID,
        'sourceCode': source_code,
        'programmingLanguageId': '1',
        'customInput': input_data,
        'contestTaskId': '38'
    }
    
    try:
        # We need to manually construct headers to NOT override content-type boundary
        # requests does it automatically if we don't set Content-Type
        headers = BASE_HEADERS.copy()
        if 'content-type' in headers:
            del headers['content-type'] # Let requests set it with boundary

        response = requests.post('https://csacademy.com/eval/submit_custom_run/', data=payload, headers=headers)
        response.raise_for_status()
        
        result_json = response.json()
        custom_run_id = result_json.get('customRunId')
        
        print(f"Run submitted: {custom_run_id}")
        logger.info(f"Run submitted: {custom_run_id}")
        
        # Poll for result
        start_time = time.time()
        while time.time() - start_time < 60:
            if custom_run_id in RESULTS_CACHE:
                result = RESULTS_CACHE.pop(custom_run_id)
                return jsonify({'results': result}) if 'error' not in result else jsonify(result)
            time.sleep(0.5)
            
        return jsonify({'error': 'Timeout waiting for results'}), 504

    except requests.exceptions.RequestException as e:
        logger.error(f"API Error: {e}")
        if e.response:
             logger.error(f"Response: {e.response.text}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/submit', methods=['POST'])
def submit_solution():
    data = request.json
    source_code = data.get('sourceCode')
    
    payload = {
        'workspaceId': WORKSPACE_ID,
        'sessionId': SESSION_ID,
        'contestTaskId': '38',
        'sourceCode': source_code,
        'programmingLanguageId': '1'
    }
    
    try:
        headers = BASE_HEADERS.copy()
        if 'content-type' in headers:
             del headers['content-type']

        response = requests.post('https://csacademy.com/eval/submit_evaljob/', data=payload, headers=headers)
        response.raise_for_status()
        
        result_json = response.json()
        eval_job_id = result_json.get('evalJobId')
        logger.info(f"Submission started: {eval_job_id}")

        # Poll for result (longer timeout for submissions)
        start_time = time.time()
        while time.time() - start_time < 120:
            if eval_job_id in RESULTS_CACHE:
                current_data = RESULTS_CACHE[eval_job_id]
                if current_data.get('status') == 'done':
                    result = RESULTS_CACHE.pop(eval_job_id)
                    return jsonify({'results': result})
            time.sleep(0.5)

        # Return the job ID if timeout, so client can at least see it's pending
        return jsonify({'message': 'Submission pending (timeout)', 'evalJobId': eval_job_id})

    except requests.exceptions.RequestException as e:
        logger.error(f"Submit Error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Threaded=True is default in newer Flask, but good to be explicit for dev
    app.run(port=3000, threaded=True)
