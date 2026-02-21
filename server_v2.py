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
        logging.FileHandler("debug_v2.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='public_v2')

# --- Configuration ---
COOKIES = 'G_ENABLED_IDPS=google; csrftoken=mAoxC3u6BS40wqcASSV4Ioseyx3SzWIn; crossSessionId=iikptg1eco6d3gsvlkapf6e8f01plnmy'
CSRF_TOKEN = 'mAoxC3u6BS40wqcASSV4Ioseyx3SzWIn'
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36'
SESSION_ID = '559865908212979'  # Updated to match active WebSocket session
USER_ID = '221818'
WORKSPACE_ID = '2931058'  # Updated from API2.txt

# --- Problem Configuration ---
PROBLEMS = {
    'addition': {
        'contestTaskId': 38,
        'name': 'Addition',
        'description': 'Given two integers a and b, output their sum.',
        'referer': 'https://csacademy.com/contest/archive/task/addition/',
        'starterCode': '''#include <iostream>

using namespace std;

int main() {
    int a, b;
    cin >> a >> b;
    cout << a + b;
    return 0;
}''',
        'sampleInput': '1 2',
        'sampleOutput': '3'
    },
    'one_letter': {
        'contestTaskId': 680,
        'name': 'One Letter',
        'description': '''You are given a list of N words. From each word you should keep only one letter and discard all the others. Then you should permute the N chosen letters and build a single word by concatenating them. Find the lexicographically smallest word you can obtain.

Input: The first line contains a single integer value N. Each of the following N lines contains a single string, representing one of the words.

Output: The output should contain one string of length N.

Constraints:
- 1 ≤ N ≤ 10^5
- The sum of lengths of the strings is ≤ 10^5
- The strings will contain only lower case letters of the English alphabet.''',
        'referer': 'https://csacademy.com/contest/interview-archive/task/one_letter/',
        'starterCode': '''#include <iostream>
#include <string>
#include <vector>
#include <algorithm>

using namespace std;

int main() {
    int n;
    cin >> n;
    
    vector<string> words(n);
    for (int i = 0; i < n; i++) {
        cin >> words[i];
    }
    
    // Your solution here
    
    return 0;
}''',
        'sampleInput': '''3
cross
stop
arm''',
        'sampleOutput': 'aco'
    }
}

BASE_HEADERS = {
    'accept': '*/*',
    'accept-language': 'en-US,en;q=0.9,fr;q=0.8',
    'cookie': COOKIES,
    'origin': 'https://csacademy.com',
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
                         logger.info(f"Full result data: {json.dumps(RESULTS_CACHE[obj_id], indent=2)}")
        
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
    return send_from_directory('public_v2', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('public_v2', path)

@app.route('/api/problems', methods=['GET'])
def get_problems():
    """Return list of available problems"""
    problems_list = []
    for problem_id, problem_data in PROBLEMS.items():
        problems_list.append({
            'id': problem_id,
            'name': problem_data['name'],
            'description': problem_data['description'],
            'starterCode': problem_data['starterCode'],
            'sampleInput': problem_data['sampleInput'],
            'sampleOutput': problem_data['sampleOutput']
        })
    return jsonify({'problems': problems_list})

@app.route('/api/run/<problem_id>', methods=['POST'])
def run_code(problem_id):
    if problem_id not in PROBLEMS:
        return jsonify({'error': 'Invalid problem ID'}), 400
    
    problem = PROBLEMS[problem_id]
    data = request.json
    source_code = data.get('sourceCode')
    input_data = data.get('input', '')
    
    # Payload for form-data
    payload = {
        'workspaceId': WORKSPACE_ID,
        'sessionId': SESSION_ID,
        'sourceCode': source_code,
        'programmingLanguageId': '1',
        'customInput': input_data,
        'contestTaskId': str(problem['contestTaskId'])
    }
    
    try:
        # Update referer for this problem
        headers = BASE_HEADERS.copy()
        headers['referer'] = problem['referer']
        if 'content-type' in headers:
            del headers['content-type'] # Let requests set it with boundary

        response = requests.post('https://csacademy.com/eval/submit_custom_run/', data=payload, headers=headers)
        response.raise_for_status()
        
        result_json = response.json()
        custom_run_id = result_json.get('customRunId')
        
        logger.info(f"Run submitted for {problem_id}: {custom_run_id}")
        
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

@app.route('/api/submit/<problem_id>', methods=['POST'])
def submit_solution(problem_id):
    if problem_id not in PROBLEMS:
        return jsonify({'error': 'Invalid problem ID'}), 400
    
    problem = PROBLEMS[problem_id]
    data = request.json
    source_code = data.get('sourceCode')
    
    payload = {
        'workspaceId': WORKSPACE_ID,
        'sessionId': SESSION_ID,
        'contestTaskId': str(problem['contestTaskId']),
        'sourceCode': source_code,
        'programmingLanguageId': '1'
    }
    
    try:
        headers = BASE_HEADERS.copy()
        headers['referer'] = problem['referer']
        if 'content-type' in headers:
             del headers['content-type']

        response = requests.post('https://csacademy.com/eval/submit_evaljob/', data=payload, headers=headers)
        response.raise_for_status()
        
        result_json = response.json()
        eval_job_id = result_json.get('evalJobId')
        logger.info(f"Submission started for {problem_id}: {eval_job_id}")

        # Poll for result from WebSocket cache
        start_time = time.time()
        while time.time() - start_time < 120:
            if eval_job_id in RESULTS_CACHE:
                current_data = RESULTS_CACHE[eval_job_id]
                if current_data.get('status') == 'done' or current_data.get('isDone'):
                    result = RESULTS_CACHE.pop(eval_job_id)
                    
                    # Get score and convert from decimal (0.0-1.0) to percentage (0-100)
                    score = result.get('score', 0)
                    if score is not None:
                        result['score'] = score * 100
                    else:
                        # Calculate score from test results if not directly available
                        tests = result.get('tests', [])
                        if tests:
                            total_score = sum(t.get('checkerScore', 0) for t in tests)
                            result['score'] = (total_score / len(tests)) * 100
                        else:
                            result['score'] = 0
                    
                    logger.info(f"Returning score: {result.get('score')}")
                    return jsonify({'results': result})
            time.sleep(0.5)

        # Return the job ID if timeout
        return jsonify({'message': 'Submission pending (timeout)', 'evalJobId': eval_job_id})

    except requests.exceptions.RequestException as e:
        logger.error(f"Submit Error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Threaded=True is default in newer Flask, but good to be explicit for dev
    app.run(port=3001, threaded=True)
