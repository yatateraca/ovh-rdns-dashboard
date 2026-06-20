from flask import Flask, request, jsonify, render_template_string, session, redirect as flask_redirect
from ovh import Client
import os
import socket
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Default OVH endpoint
OVH_ENDPOINT = os.environ.get('OVH_ENDPOINT', 'ovh-eu')

# ============ MULTI-ACCOUNT CONFIGURATION ============
# Load Account 1 separately (uses old format)
OVH_ACCOUNTS = {}

# Load Account 1 from old format variables
account_1 = {
    'app_key': os.environ.get('OVH_APP_KEY'),
    'app_secret': os.environ.get('OVH_APP_SECRET'),
    'consumer_key': os.environ.get('OVH_CONSUMER_KEY'),
}

# Only add if all keys exist
if all(account_1.values()):
    OVH_ACCOUNTS['1'] = account_1

# Load Account 2, 3, etc. from new format
for key, value in os.environ.items():
    if key.startswith('OVH_ACCOUNT_'):
        parts = key.split('_')
        if len(parts) >= 4:
            account_name = parts[2]
            key_type = '_'.join(parts[3:])
            
            if account_name not in OVH_ACCOUNTS:
                OVH_ACCOUNTS[account_name] = {}
            
            if key_type == 'APP_KEY':
                OVH_ACCOUNTS[account_name]['app_key'] = value
            elif key_type == 'APP_SECRET':
                OVH_ACCOUNTS[account_name]['app_secret'] = value
            elif key_type == 'CONSUMER_KEY':
                OVH_ACCOUNTS[account_name]['consumer_key'] = value

print(f"Loaded {len(OVH_ACCOUNTS)} OVH account(s): {list(OVH_ACCOUNTS.keys())}")

# ============ IP TO ACCOUNT MAPPING ============
IP_TO_ACCOUNT = {}

for key, value in os.environ.items():
    if key.startswith('IP_ACCOUNT_'):
        ip = key.replace('IP_ACCOUNT_', '')
        IP_TO_ACCOUNT[ip] = value

print(f"Mapped {len(IP_TO_ACCOUNT)} IP(s) to accounts")

# ============ USER MANAGEMENT ============
USER_IPS = {}
USER_PASSWORDS = {}

for key, value in os.environ.items():
    if key.startswith('USER_'):
        email = key.replace('USER_', '').replace('_', '@')
        ips = [ip.strip() for ip in value.split(',')]
        USER_IPS[email] = ips
    elif key.startswith('PASS_'):
        email = key.replace('PASS_', '').replace('_', '@')
        USER_PASSWORDS[email] = value

# ============ HELPER FUNCTION ============
def get_ovh_client_for_ip(ip):
    """Get the correct OVH client for a specific IP"""
    account_name = IP_TO_ACCOUNT.get(ip)
    
    # If no mapping found, try Account 1 (fallback)
    if not account_name:
        print(f"No mapping found for {ip}, using Account 1 fallback")
        account_name = '1'
    
    if account_name not in OVH_ACCOUNTS:
        print(f"Account {account_name} not configured for IP: {ip}")
        return None
    
    account = OVH_ACCOUNTS[account_name]
    
    if not all(k in account for k in ['app_key', 'app_secret', 'consumer_key']):
        print(f"Account {account_name} missing credentials for IP: {ip}")
        return None
    
    # Check for account-specific endpoint
    endpoint_key = f'OVH_ACCOUNT_{account_name}_ENDPOINT'
    endpoint = os.environ.get(endpoint_key, OVH_ENDPOINT)
    
    print(f"Using endpoint: {endpoint} for account {account_name}")
    
    return Client(
        endpoint=endpoint,
        application_key=account['app_key'],
        application_secret=account['app_secret'],
        consumer_key=account['consumer_key'],
    )

# ============ HTML TEMPLATE ============
HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Multi-Account rDNS Manager</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f0f2f5;
        }
        .header {
            background: linear-gradient(135deg, #0066cc, #004499);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .login-box {
            background: white;
            padding: 30px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .ip-card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            border-left: 4px solid #0066cc;
        }
        .ip-address {
            font-family: monospace;
            font-size: 1.2em;
            font-weight: bold;
            color: #0066cc;
            margin-bottom: 10px;
        }
        .account-badge {
            display: inline-block;
            background: #e9ecef;
            color: #495057;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            margin-left: 10px;
            vertical-align: middle;
        }
        .current-ptr {
            background: #f8f9fa;
            padding: 12px;
            border-radius: 6px;
            margin: 15px 0;
            font-family: monospace;
            word-break: break-all;
            border: 1px solid #e0e0e0;
        }
        input {
            width: 100%;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 6px;
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
            padding: 10px 24px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
        }
        button:hover { background: #0052a3; }
        button:disabled { background: #ccc; cursor: not-allowed; }
        .success { color: #28a745; margin-top: 10px; padding: 10px; background: #d4edda; border-radius: 5px; }
        .error { color: #dc3545; margin-top: 10px; padding: 10px; background: #f8d7da; border-radius: 5px; }
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
        .footer { text-align: center; margin-top: 30px; color: #666; font-size: 12px; }
        .logout-btn { background: #dc3545; margin-bottom: 20px; }
        .logout-btn:hover { background: #c82333; }
        .user-info {
            background: #e3f2fd;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .badge { background: #28a745; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔧 Multi-Account Reverse DNS Manager</h1>
        <p>Manage rDNS across multiple OVH accounts</p>
    </div>

    {% if not session.logged_in %}
    <div class="login-box">
        <h2>🔐 Login</h2>
        <form method="POST" action="/login">
            <input type="email" name="email" placeholder="Email" required style="width: 100%; max-width: 320px;">
            <br>
            <input type="password" name="password" placeholder="Password" required style="width: 100%; max-width: 320px;">
            <br>
            <button type="submit">Login</button>
        </form>
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
    </div>
    {% else %}

    <div>
        <div class="user-info">
            <span>👤 Logged in: <strong>{{ session.email }}</strong></span>
            <span class="badge">Multi-Account Mode</span>
        </div>
        <button class="logout-btn" onclick="logout()">🚪 Logout</button>
        <div id="ips-container"><div style="text-align: center; padding: 40px;"><div class="loading"></div><p>Loading your IPs...</p></div></div>
    </div>

    <div class="footer">
        <p>⏱️ Changes take 5-10 minutes to propagate | Supports multiple OVH accounts</p>
    </div>

    <script>
        async function loadIPs() {
            try {
                const response = await fetch('/api/my-ips');
                const data = await response.json();
                
                if (data.ips && data.ips.length > 0) {
                    const container = document.getElementById('ips-container');
                    container.innerHTML = '';
                    
                    for (const ip of data.ips) {
                        await displayIP(ip, container);
                    }
                } else {
                    document.getElementById('ips-container').innerHTML = '<div class="error">No IPs found for your account.</div>';
                }
            } catch (error) {
                document.getElementById('ips-container').innerHTML = '<div class="error">Error loading IPs.</div>';
            }
        }
        
        async function displayIP(ip, container) {
            const ipId = ip.replace(/\./g, '-');
            const ipDiv = document.createElement('div');
            ipDiv.className = 'ip-card';
            ipDiv.innerHTML = `
                <div class="ip-address">
                    🌐 ${ip}
                    <span class="account-badge" id="account-${ipId}">Loading account...</span>
                </div>
                <div class="current-ptr">
                    <strong>📝 Current PTR:</strong><br>
                    <span id="ptr-${ipId}">Loading...</span>
                </div>
                <input type="text" id="input-${ipId}" placeholder="hostname.example.com">
                <button onclick="updateRDNS('${ip}')" id="btn-${ipId}">🔄 Update rDNS</button>
                <div id="msg-${ipId}"></div>
            `;
            container.appendChild(ipDiv);
            
            await Promise.all([
                refreshAccountInfo(ip),
                refreshRDNS(ip)
            ]);
        }
        
        async function refreshAccountInfo(ip) {
            const ipId = ip.replace(/\./g, '-');
            const accountSpan = document.getElementById(`account-${ipId}`);
            try {
                const response = await fetch(`/api/account/${ip}`);
                const data = await response.json();
                accountSpan.innerHTML = `📁 Account: ${data.account || 'Unknown'}`;
            } catch {
                accountSpan.innerHTML = `📁 Account: Unknown`;
            }
        }
        
        async function refreshRDNS(ip) {
            const ipId = ip.replace(/\./g, '-');
            const ptrSpan = document.getElementById(`ptr-${ipId}`);
            try {
                const response = await fetch(`/api/rdns/${ip}`);
                const data = await response.json();
                ptrSpan.innerHTML = data.ptr ? `<code>${data.ptr}</code>` : '<em>No PTR record set</em>';
            } catch {
                ptrSpan.innerHTML = '<span class="error">Failed to load</span>';
            }
        }
        
        async function updateRDNS(ip) {
            const ipId = ip.replace(/\./g, '-');
            const ptr = document.getElementById(`input-${ipId}`).value;
            const msgDiv = document.getElementById(`msg-${ipId}`);
            const button = document.getElementById(`btn-${ipId}`);
            
            if (!ptr) {
                msgDiv.innerHTML = '<div class="error">❌ Enter a hostname</div>';
                return;
            }
            
            button.disabled = true;
            button.textContent = 'Updating...';
            msgDiv.innerHTML = '<div class="loading"></div> Updating...';
            
            try {
                const response = await fetch(`/api/rdns/${ip}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ptr_record: ptr })
                });
                const result = await response.json();
                
                if (response.ok) {
                    msgDiv.innerHTML = '<div class="success">✅ Updated! Takes 5-10 minutes.</div>';
                    await refreshRDNS(ip);
                    document.getElementById(`input-${ipId}`).value = '';
                    setTimeout(() => msgDiv.innerHTML = '', 5000);
                } else {
                    msgDiv.innerHTML = `<div class="error">❌ Error: ${result.error}</div>`;
                }
            } catch {
                msgDiv.innerHTML = '<div class="error">❌ Network error</div>';
            } finally {
                button.disabled = false;
                button.textContent = '🔄 Update rDNS';
            }
        }
        
        function logout() { window.location.href = '/logout'; }
        loadIPs();
    </script>
    {% endif %}
</body>
</html>
'''

# ============ API ROUTES ============
@app.route('/')
def index():
    error = request.args.get('error')
    return render_template_string(HTML, session=session, error=error)

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')
    
    if USER_PASSWORDS.get(email) == password:
        session['logged_in'] = True
        session['email'] = email
        return flask_redirect('/')
    return flask_redirect('/?error=Invalid email or password')

@app.route('/logout')
def logout():
    session.clear()
    return flask_redirect('/')

@app.route('/api/my-ips')
def get_ips():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify({'ips': USER_IPS.get(session['email'], [])})

@app.route('/api/account/<ip>')
def get_account(ip):
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    account = IP_TO_ACCOUNT.get(ip, '1')
    return jsonify({'ip': ip, 'account': account})

@app.route('/api/rdns/<ip>')
def get_rdns(ip):
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    email = session['email']
    if ip not in USER_IPS.get(email, []):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        ptr = socket.gethostbyaddr(ip)[0]
        return jsonify({'ptr': ptr})
    except:
        return jsonify({'ptr': None})

@app.route('/api/rdns/<ip>', methods=['PUT'])
def update_rdns(ip):
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    email = session['email']
    if ip not in USER_IPS.get(email, []):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    new_ptr = data.get('ptr_record', '').strip()
    
    if not new_ptr:
        return jsonify({'error': 'No hostname provided'}), 400
    
    if new_ptr.endswith('.'):
        new_ptr = new_ptr[:-1]
    
    client = get_ovh_client_for_ip(ip)
    if not client:
        return jsonify({'error': f'No OVH account configured for IP {ip}'}), 500
    
    try:
        client.post(f'/ip/{ip}/reverse', ipReverse=ip, reverse=new_ptr)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'accounts': len(OVH_ACCOUNTS)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
