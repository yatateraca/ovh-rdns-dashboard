from flask import Flask, request, jsonify, render_template_string
from ovh import Client
import os
import re
from functools import wraps
from datetime import datetime
import json

app = Flask(__name__)

# Configuration from environment variables
OVH_ENDPOINT = os.environ.get('OVH_ENDPOINT', 'ovh-eu')
OVH_APP_KEY = os.environ.get('OVH_APP_KEY')
OVH_APP_SECRET = os.environ.get('OVH_APP_SECRET')
OVH_CONSUMER_KEY = os.environ.get('OVH_CONSUMER_KEY')

# User to IPs mapping (format: email:ip1,ip2,ip3)
USER_IPS = {}
for key, value in os.environ.items():
    if key.startswith('USER_'):
        email = key.replace('USER_', '').replace('_', '@')
        ips = value.split(',')
        USER_IPS[email] = [ip.strip() for ip in ips]

# Simple in-memory rate limiting (per IP)
rate_limit_store = {}

def rate_limit(limit=100, window=3600):  # 100 requests per hour
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = request.remote_addr
            now = datetime.now().timestamp()
            
            if client_ip not in rate_limit_store:
                rate_limit_store[client_ip] = []
            
            # Clean old requests
            rate_limit_store[client_ip] = [t for t in rate_limit_store[client_ip] if now - t < window]
            
            if len(rate_limit_store[client_ip]) >= limit:
                return jsonify({'error': 'Rate limit exceeded. Try again later.'}), 429
            
            rate_limit_store[client_ip].append(now)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_ovh_client():
    """Initialize OVH API client"""
    if not all([OVH_APP_KEY, OVH_APP_SECRET, OVH_CONSUMER_KEY]):
        return None
    return Client(
        endpoint=OVH_ENDPOINT,
        application_key=OVH_APP_KEY,
        application_secret=OVH_APP_SECRET,
        consumer_key=OVH_CONSUMER_KEY,
    )

def validate_hostname(hostname):
    """Validate hostname format for PTR record"""
    if not hostname or len(hostname) > 255:
        return False
    # Allow alphanumeric, hyphens, dots (basic validation)
    pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
    return re.match(pattern, hostname) is not None

def authenticate():
    """Authenticate user via API key or email header"""
    # Method 1: API Key
    api_key = request.headers.get('X-API-Key')
    if api_key:
        for email, api_keys in API_KEYS.items():
            if api_key in api_keys:
                return email
    
    # Method 2: Email header (simpler for testing)
    email = request.headers.get('X-User-Email')
    if email and email in USER_IPS:
        return email
    
    return None

# API Keys mapping (optional, more secure)
API_KEYS = {}
for key, value in os.environ.items():
    if key.startswith('API_KEY_'):
        email = key.replace('API_KEY_', '').replace('_', '@')
        API_KEYS[email] = value.split(',')

# HTML template for web interface
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>OVH rDNS Manager</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .header {
            background: linear-gradient(135deg, #0066cc, #004499);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .ip-card {
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }
        .ip-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        }
        .ip-address {
            font-family: monospace;
            font-size: 1.2em;
            font-weight: bold;
            color: #0066cc;
            margin-bottom: 10px;
        }
        .current-ptr {
            background: #f0f0f0;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
            font-family: monospace;
            word-break: break-all;
        }
        .current-ptr label {
            font-weight: bold;
            color: #666;
        }
        input {
            width: 100%;
            padding: 10px;
            border: 2px solid #ddd;
            border-radius: 5px;
            font-size: 14px;
            margin: 10px 0;
        }
        input:focus {
            outline: none;
            border-color: #0066cc;
        }
        button {
            background: #0066cc;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            transition: background 0.2s;
        }
        button:hover {
            background: #0052a3;
        }
        button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .success {
            color: #28a745;
            margin-top: 10px;
            padding: 8px;
            background: #d4edda;
            border-radius: 5px;
        }
        .error {
            color: #dc3545;
            margin-top: 10px;
            padding: 8px;
            background: #f8d7da;
            border-radius: 5px;
        }
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid #f3f3f3;
            border-top: 3px solid #0066cc;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .footer {
            text-align: center;
            margin-top: 30px;
            color: #666;
            font-size: 12px;
        }
        .logout-btn {
            background: #dc3545;
            margin-left: 10px;
        }
        .logout-btn:hover {
            background: #c82333;
        }
        .auth-section {
            background: white;
            padding: 30px;
            border-radius: 10px;
            text-align: center;
        }
        .auth-section input {
            max-width: 300px;
            margin: 10px auto;
        }
    </style>
</head>
<body>
    <div id="app">
        <div class="header">
            <h1>🔧 Reverse DNS Manager</h1>
            <p>Manage your IP reverse DNS (PTR) records</p>
        </div>
        
        <div id="content"></div>
        
        <div class="footer">
            <p>Changes take 5-10 minutes to propagate globally</p>
        </div>
    </div>

    <script>
        const API_URL = window.location.origin;
        let currentEmail = localStorage.getItem('user_email');
        let apiKey = localStorage.getItem('api_key');
        
        async function init() {
            if (!currentEmail && !apiKey) {
                showAuth();
            } else {
                await loadIPs();
            }
        }
        
        function showAuth() {
            const content = document.getElementById('content');
            content.innerHTML = `
                <div class="auth-section">
                    <h2>Authentication Required</h2>
                    <p>Enter your email or API key to access your IPs</p>
                    <input type="email" id="email" placeholder="your@email.com">
                    <button onclick="login()">Continue with Email</button>
                    <hr style="margin: 20px 0">
                    <p>Or use API Key:</p>
                    <input type="text" id="apikey" placeholder="Your API Key">
                    <button onclick="loginWithApiKey()">Continue with API Key</button>
                </div>
            `;
        }
        
        window.login = function() {
            const email = document.getElementById('email').value;
            if (email) {
                localStorage.setItem('user_email', email);
                currentEmail = email;
                loadIPs();
            }
        };
        
        window.loginWithApiKey = function() {
            const key = document.getElementById('apikey').value;
            if (key) {
                localStorage.setItem('api_key', key);
                apiKey = key;
                loadIPs();
            }
        };
        
        window.logout = function() {
            localStorage.removeItem('user_email');
            localStorage.removeItem('api_key');
            currentEmail = null;
            apiKey = null;
            showAuth();
        };
        
        async function loadIPs() {
            const content = document.getElementById('content');
            content.innerHTML = '<div style="text-align: center"><div class="loading"></div><p>Loading your IPs...</p></div>';
            
            try {
                const headers = {};
                if (apiKey) {
                    headers['X-API-Key'] = apiKey;
                } else if (currentEmail) {
                    headers['X-User-Email'] = currentEmail;
                }
                
                const response = await fetch(`${API_URL}/api/my-ips`, { headers });
                const data = await response.json();
                
                if (response.status === 401) {
                    showAuth();
                    return;
                }
                
                if (data.ips && data.ips.length > 0) {
                    await displayIPs(data.ips);
                } else {
                    content.innerHTML = '<div class="error">No IPs found for your account. Contact administrator.</div>';
                }
            } catch (error) {
                content.innerHTML = '<div class="error">Error loading IPs. Please try again.</div>';
            }
        }
        
        async function displayIPs(ips) {
            const content = document.getElementById('content');
            content.innerHTML = '<button onclick="logout()" class="logout-btn" style="margin-bottom: 20px">🚪 Logout</button><div id="ips-list"></div>';
            const ipsList = document.getElementById('ips-list');
            
            for (const ip of ips) {
                await loadIPDetails(ip, ipsList);
            }
        }
        
        async function loadIPDetails(ip, container) {
            const ipDiv = document.createElement('div');
            ipDiv.className = 'ip-card';
            ipDiv.innerHTML = `
                <div class="ip-address">🌐 ${ip}</div>
                <div class="current-ptr">
                    <label>Current PTR Record:</label>
                    <div id="ptr-${ip.replace(/\./g, '-')}">Loading...</div>
                </div>
                <input type="text" id="input-${ip.replace(/\./g, '-')}" placeholder="hostname.example.com">
                <button onclick="updateRDNS('${ip}')" id="btn-${ip.replace(/\./g, '-')}">Update rDNS</button>
                <div id="msg-${ip.replace(/\./g, '-')}"></div>
            `;
            container.appendChild(ipDiv);
            
            // Load current rDNS
            await refreshRDNS(ip);
        }
        
        async function refreshRDNS(ip) {
            const ptrSpan = document.getElementById(`ptr-${ip.replace(/\./g, '-')}`);
            try {
                const headers = {};
                if (apiKey) {
                    headers['X-API-Key'] = apiKey;
                } else if (currentEmail) {
                    headers['X-User-Email'] = currentEmail;
                }
                
                const response = await fetch(`${API_URL}/api/rdns/${ip}`, { headers });
                const data = await response.json();
                
                if (data.ptr) {
                    ptrSpan.innerHTML = `<code>${data.ptr}</code>`;
                } else {
                    ptrSpan.innerHTML = '<em>No PTR record set</em>';
                }
            } catch (error) {
                ptrSpan.innerHTML = '<span class="error">Failed to load</span>';
            }
        }
        
        window.updateRDNS = async function(ip) {
            const inputId = `input-${ip.replace(/\./g, '-')}`;
            const msgId = `msg-${ip.replace(/\./g, '-')}`;
            const btnId = `btn-${ip.replace(/\./g, '-')}`;
            
            const ptr = document.getElementById(inputId).value;
            const msgDiv = document.getElementById(msgId);
            const button = document.getElementById(btnId);
            
            if (!ptr) {
                msgDiv.innerHTML = '<div class="error">Please enter a hostname</div>';
                return;
            }
            
            button.disabled = true;
            button.textContent = 'Updating...';
            msgDiv.innerHTML = '<div class="loading"></div> Updating...';
            
            try {
                const headers = {
                    'Content-Type': 'application/json'
                };
                if (apiKey) {
                    headers['X-API-Key'] = apiKey;
                } else if (currentEmail) {
                    headers['X-User-Email'] = currentEmail;
                }
                
                const response = await fetch(`${API_URL}/api/rdns/${ip}`, {
                    method: 'PUT',
                    headers: headers,
                    body: JSON.stringify({ ptr_record: ptr })
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    msgDiv.innerHTML = '<div class="success">✓ Updated successfully! Changes will take effect in 5-10 minutes.</div>';
                    await refreshRDNS(ip);
                    document.getElementById(inputId).value = '';
                } else {
                    msgDiv.innerHTML = `<div class="error">Error: ${data.error || 'Update failed'}</div>`;
                }
            } catch (error) {
                msgDiv.innerHTML = '<div class="error">Network error. Please try again.</div>';
            } finally {
                button.disabled = false;
                button.textContent = 'Update rDNS';
            }
        };
        
        init();
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    """Serve the web interface"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/my-ips', methods=['GET'])
@rate_limit(limit=50, window=3600)
def get_my_ips():
    """Get list of IPs for authenticated user"""
    email = authenticate()
    if not email:
        return jsonify({'error': 'Unauthorized'}), 401
    
    ips = USER_IPS.get(email, [])
    return jsonify({'ips': ips, 'email': email})

@app.route('/api/rdns/<ip>', methods=['GET'])
@rate_limit(limit=100, window=3600)
def get_rdns(ip):
    """Get current rDNS for an IP"""
    email = authenticate()
    if not email:
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Verify user owns this IP
    if ip not in USER_IPS.get(email, []):
        return jsonify({'error': 'You do not own this IP'}), 403
    
    client = get_ovh_client()
    if not client:
        return jsonify({'error': 'API configuration error'}), 500
    
    try:
        # Try to get reverse DNS
        result = client.get(f'/ip/{ip}/reverse')
        ptr = result.get('reverse', '')
        return jsonify({'ip': ip, 'ptr': ptr})
    except Exception as e:
        # IP might not have reverse DNS set yet
        if '404' in str(e):
            return jsonify({'ip': ip, 'ptr': None})
        return jsonify({'error': str(e)}), 500

@app.route('/api/rdns/<ip>', methods=['PUT'])
@rate_limit(limit=20, window=3600)  # Stricter limit for updates
def update_rdns(ip):
    """Update rDNS for an IP"""
    email = authenticate()
    if not email:
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Verify user owns this IP
    if ip not in USER_IPS.get(email, []):
        return jsonify({'error': 'You do not own this IP'}), 403
    
    data = request.json
    ptr_record = data.get('ptr_record', '').strip()
    
    # Validate hostname
    if not validate_hostname(ptr_record):
        return jsonify({'error': 'Invalid hostname format. Use: example.com or mail.example.com'}), 400
    
    # Ensure trailing dot (OVH sometimes requires it)
    if not ptr_record.endswith('.'):
        ptr_record += '.'
    
    client = get_ovh_client()
    if not client:
        return jsonify({'error': 'API configuration error'}), 500
    
    try:
        # Update reverse DNS
        client.put(f'/ip/{ip}/reverse', 
                  ipReverse=ptr_record,
                  ip=ip)
        
        # Log the change (optional: save to database)
        print(f"[AUDIT] {email} changed rDNS for {ip} to {ptr_record}")
        
        return jsonify({'success': True, 'ip': ip, 'ptr': ptr_record})
    except Exception as e:
        return jsonify({'error': f'OVH API error: {str(e)}'}), 500

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)