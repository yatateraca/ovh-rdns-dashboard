from flask import Flask, request, jsonify, render_template_string, session, redirect as flask_redirect
from ovh import Client
import os
import socket
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# OVH credentials from environment
OVH_ENDPOINT = os.environ.get('OVH_ENDPOINT', 'ovh-eu')
OVH_APP_KEY = os.environ.get('OVH_APP_KEY')
OVH_APP_SECRET = os.environ.get('OVH_APP_SECRET')
OVH_CONSUMER_KEY = os.environ.get('OVH_CONSUMER_KEY')

# Load users and passwords from environment
USER_IPS = {}
USER_PASSWORDS = {}

for key, value in os.environ.items():
    if key.startswith('USER_'):
        email = key.replace('USER_', '').replace('_', '@')
        ips = [ip.strip() for ip in value.split(',')]
        USER_IPS[email] = ips
        print(f"Loaded user: {email} with IPs: {ips}")
    elif key.startswith('PASS_'):
        email = key.replace('PASS_', '').replace('_', '@')
        USER_PASSWORDS[email] = value

# IP to Account mapping
IP_TO_ACCOUNT = {}
for key, value in os.environ.items():
    if key.startswith('IP_ACCOUNT_'):
        ip = key.replace('IP_ACCOUNT_', '')
        IP_TO_ACCOUNT[ip] = value

# HTML template (same as before)
HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>rDNS Manager</title>
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
            font-size: 1.3em;
            font-weight: bold;
            color: #0066cc;
            margin-bottom: 15px;
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
        .current-ptr strong {
            color: #666;
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
            font-weight: bold;
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
            padding: 10px;
            background: #d4edda;
            border-radius: 5px;
        }
        .error {
            color: #dc3545;
            margin-top: 10px;
            padding: 10px;
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
            margin-bottom: 20px;
        }
        .logout-btn:hover {
            background: #c82333;
        }
        .user-info {
            background: #e3f2fd;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .badge {
            background: #28a745;
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔧 Reverse DNS Manager</h1>
        <p>Manage your IP reverse DNS (PTR) records</p>
    </div>

    {% if not session.logged_in %}
    <div class="login-box">
        <h2>🔐 Login Required</h2>
        <form method="POST" action="/login">
            <input type="email" name="email" placeholder="Email address" required style="width: 100%; max-width: 320px;">
            <br>
            <input type="password" name="password" placeholder="Password" required style="width: 100%; max-width: 320px;">
            <br>
            <button type="submit">Login</button>
        </form>
        {% if error %}
        <p class="error">{{ error }}</p>
        {% endif %}
    </div>
    {% else %}

    <div>
        <div class="user-info">
            <span>👤 Logged in as: <strong>{{ session.email }}</strong></span>
            <span class="badge">Authenticated</span>
        </div>
        <button class="logout-btn" onclick="logout()">🚪 Logout</button>
        <div id="ips-container">
            <div style="text-align: center; padding: 40px;">
                <div class="loading"></div>
                <p>Loading your IP addresses...</p>
            </div>
        </div>
    </div>

    <div class="footer">
        <p>⏱️ Changes take 5-10 minutes to propagate globally</p>
    </div>

    <script>
        async function loadIPs() {
            try {
                const response = await fetch('/api/my-ips');
                const data = await response.json();
                
                if (data.ips && data.ips.length > 0) {
                    const container = document.getElementById('ips-container');
                    container.innerHTML = '';
                    
                    for (let i = 0; i < data.ips.length; i++) {
                        const ip = data.ips[i];
                        await displayIP(ip, container);
                    }
                } else {
                    document.getElementById('ips-container').innerHTML = '<div class="error">No IPs found for your account. Contact administrator.</div>';
                }
            } catch (error) {
                document.getElementById('ips-container').innerHTML = '<div class="error">Error loading IPs. Please refresh the page.</div>';
            }
        }
        
        async function displayIP(ip, container) {
            const ipId = ip.replace(/\./g, '-');
            const ipDiv = document.createElement('div');
            ipDiv.className = 'ip-card';
            ipDiv.innerHTML = `
                <div class="ip-address">🌐 ${ip}</div>
                <div class="current-ptr">
                    <strong>📝 Current PTR Record:</strong><br>
                    <span id="ptr-${ipId}">Loading...</span>
                </div>
                <input type="text" id="input-${ipId}" placeholder="Enter hostname (e.g., mail.yourdomain.com)">
                <button onclick="updateRDNS('${ip}')" id="btn-${ipId}">🔄 Update rDNS</button>
                <div id="msg-${ipId}"></div>
            `;
            container.appendChild(ipDiv);
            await refreshRDNS(ip);
        }
        
        async function refreshRDNS(ip) {
            const ipId = ip.replace(/\./g, '-');
            const ptrSpan = document.getElementById(`ptr-${ipId}`);
            try {
                const response = await fetch(`/api/rdns/${ip}`);
                const data = await response.json();
                if (data.ptr && data.ptr !== 'None') {
                    ptrSpan.innerHTML = `<code style="background: #e9ecef; padding: 4px 8px; border-radius: 4px;">${data.ptr}</code>`;
                } else {
                    ptrSpan.innerHTML = '<em style="color: #999;">No PTR record set</em>';
                }
            } catch (error) {
                ptrSpan.innerHTML = '<span class="error">Failed to load</span>';
            }
        }
        
        async function updateRDNS(ip) {
            const ipId = ip.replace(/\./g, '-');
            const inputId = `input-${ipId}`;
            const msgId = `msg-${ipId}`;
            const btnId = `btn-${ipId}`;
            
            const ptr = document.getElementById(inputId).value;
            const msgDiv = document.getElementById(msgId);
            const button = document.getElementById(btnId);
            
            if (!ptr) {
                msgDiv.innerHTML = '<div class="error">❌ Please enter a hostname</div>';
                return;
            }
            
            button.disabled = true;
            button.textContent = 'Updating...';
            msgDiv.innerHTML = '<div class="loading"></div> Updating rDNS...';
            
            try {
                const response = await fetch(`/api/rdns/${ip}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ptr_record: ptr })
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    msgDiv.innerHTML = '<div class="success">✅ Updated successfully! Changes will take 5-10 minutes to propagate.</div>';
                    await refreshRDNS(ip);
                    document.getElementById(inputId).value = '';
                    setTimeout(() => {
                        msgDiv.innerHTML = '';
                    }, 5000);
                } else {
                    msgDiv.innerHTML = `<div class="error">❌ Error: ${data.error || 'Update failed'}</div>`;
                }
            } catch (error) {
                msgDiv.innerHTML = '<div class="error">❌ Network error. Please try again.</div>';
            } finally {
                button.disabled = false;
                button.textContent = '🔄 Update rDNS';
            }
        }
        
        function logout() {
            window.location.href = '/logout';
        }
        
        loadIPs();
    </script>
    {% endif %}
</body>
</html>
'''

@app.route('/')
def index():
    error = request.args.get('error')
    return render_template_string(HTML, session=session, error=error)

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')
    
    expected_password = USER_PASSWORDS.get(email)
    
    if expected_password and password == expected_password:
        session['logged_in'] = True
        session['email'] = email
        return flask_redirect('/')
    else:
        return flask_redirect('/?error=Invalid email or password')

@app.route('/logout')
def logout():
    session.clear()
    return flask_redirect('/')

@app.route('/api/my-ips')
def get_ips():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    email = session.get('email')
    if email in USER_IPS:
        return jsonify({'ips': USER_IPS[email]})
    return jsonify({'ips': []})

@app.route('/api/rdns/<ip>')
def get_rdns(ip):
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    email = session.get('email')
    if email not in USER_IPS:
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
    
    email = session.get('email')
    if email not in USER_IPS:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    new_ptr = data.get('ptr_record', '').strip()
    
    if not new_ptr:
        return jsonify({'error': 'No hostname provided'}), 400
    
    if new_ptr.endswith('.'):
        new_ptr = new_ptr[:-1]
    
    # Check which account this IP belongs to
    account_number = IP_TO_ACCOUNT.get(ip, '1')  # Default to Account 1
    
    if account_number == '1':
        # Use Account 1 credentials
        client = Client(
            endpoint=OVH_ENDPOINT,
            application_key=OVH_APP_KEY,
            application_secret=OVH_APP_SECRET,
            consumer_key=OVH_CONSUMER_KEY,
        )
    elif account_number == '2':
        # Use Account 2 credentials
        endpoint = os.environ.get('OVH_ACCOUNT_2_ENDPOINT', OVH_ENDPOINT)
        client = Client(
            endpoint=endpoint,
            application_key=os.environ.get('OVH_ACCOUNT_2_APP_KEY'),
            application_secret=os.environ.get('OVH_ACCOUNT_2_APP_SECRET'),
            consumer_key=os.environ.get('OVH_ACCOUNT_2_CONSUMER_KEY'),
        )
    elif account_number == '3':
        # Use Account 3 credentials
        endpoint = os.environ.get('OVH_ACCOUNT_3_ENDPOINT', OVH_ENDPOINT)
        client = Client(
            endpoint=endpoint,
            application_key=os.environ.get('OVH_ACCOUNT_3_APP_KEY'),
            application_secret=os.environ.get('OVH_ACCOUNT_3_APP_SECRET'),
            consumer_key=os.environ.get('OVH_ACCOUNT_3_CONSUMER_KEY'),
        )
    elif account_number == '4':
        # Use Account 4 credentials
        endpoint = os.environ.get('OVH_ACCOUNT_4_ENDPOINT', OVH_ENDPOINT)
        client = Client(
            endpoint=endpoint,
            application_key=os.environ.get('OVH_ACCOUNT_4_APP_KEY'),
            application_secret=os.environ.get('OVH_ACCOUNT_4_APP_SECRET'),
            consumer_key=os.environ.get('OVH_ACCOUNT_4_CONSUMER_KEY'),
        )
    else:
        return jsonify({'error': f'Unknown account number: {account_number}'}), 500
    
    try:
        client.post(f'/ip/{ip}/reverse', ipReverse=ip, reverse=new_ptr)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
