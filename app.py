from flask import Flask, request, jsonify, render_template_string, session
from ovh import Client
import os
import socket
import hashlib
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Secure session key

# Your OVH credentials from environment
OVH_ENDPOINT = os.environ.get('OVH_ENDPOINT', 'ovh-eu')
OVH_APP_KEY = os.environ.get('OVH_APP_KEY')
OVH_APP_SECRET = os.environ.get('OVH_APP_SECRET')
OVH_CONSUMER_KEY = os.environ.get('OVH_CONSUMER_KEY')

# Your users (email -> list of IPs and password)
USER_IPS = {}
USER_PASSWORDS = {}

for key, value in os.environ.items():
    if key.startswith('USER_'):
        email = key.replace('USER_', '').replace('_', '@')
        USER_IPS[email] = [value]
    elif key.startswith('PASS_'):
        email = key.replace('PASS_', '').replace('_', '@')
        USER_PASSWORDS[email] = value

# Simple HTML page with password
HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>rDNS Manager</title>
    <style>
        body { font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px; }
        input, button { padding: 10px; margin: 5px; width: 100%; max-width: 300px; }
        .success { color: green; }
        .error { color: red; }
        .current-ptr { background: #f0f0f0; padding: 10px; border-radius: 5px; margin: 10px 0; }
        .login-box { background: #f9f9f9; padding: 30px; border-radius: 10px; text-align: center; }
        button { background: #0066cc; color: white; border: none; cursor: pointer; width: auto; padding: 10px 30px; }
        button:hover { background: #0052a3; }
    </style>
</head>
<body>
    <h1>🔧 Reverse DNS Manager</h1>
    
    {% if not session.logged_in %}
    <div class="login-box">
        <h3>Login</h3>
        <form method="POST" action="/login">
            <input type="email" name="email" placeholder="Email" required><br>
            <input type="password" name="password" placeholder="Password" required><br>
            <button type="submit">Login</button>
        </form>
        {% if error %}
        <p class="error">{{ error }}</p>
        {% endif %}
    </div>
    {% else %}
    
    <div id="dashboard">
        <p>Logged in as: <strong>{{ session.email }}</strong></p>
        <div id="ipInfo">
            <div id="ips-list">Loading your IPs...</div>
        </div>
        <button onclick="logout()">Logout</button>
    </div>

    <script>
        async function loadIPs() {
            const response = await fetch('/api/my-ips');
            const data = await response.json();
            
            if (data.ips && data.ips.length > 0) {
                let html = '';
                for (const ip of data.ips) {
                    const rdnsResponse = await fetch(`/api/rdns/${ip}`);
                    const rdnsData = await rdnsResponse.json();
                    
                    html += `
                        <div class="current-ptr">
                            <strong>IP: ${ip}</strong><br>
                            Current PTR: ${rdnsData.ptr || 'No PTR record set'}<br><br>
                            <input type="text" id="ptr_${ip.replace(/\\./g, '_')}" placeholder="new.hostname.com" style="width: 300px;">
                            <button onclick="updatePtr('${ip}')">Update PTR</button>
                            <div id="msg_${ip.replace(/\\./g, '_')}"></div>
                        </div>
                    `;
                }
                document.getElementById('ips-list').innerHTML = html;
            } else {
                document.getElementById('ips-list').innerHTML = '<p class="error">No IPs found for your account.</p>';
            }
        }
        
        async function updatePtr(ip) {
            const ptr = document.getElementById(`ptr_${ip.replace(/\\./g, '_')}`).value;
            const msgDiv = document.getElementById(`msg_${ip.replace(/\\./g, '_')}`);
            
            if (!ptr) {
                msgDiv.innerHTML = '<p class="error">Please enter a hostname</p>';
                return;
            }
            
            msgDiv.innerHTML = '<p>Updating...</p>';
            
            const response = await fetch(`/api/rdns/${ip}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ptr_record: ptr })
            });
            
            const result = await response.json();
            if (result.success) {
                msgDiv.innerHTML = '<p class="success">✓ Updated! Changes take 5-10 minutes.</p>';
                setTimeout(() => location.reload(), 3000);
            } else {
                msgDiv.innerHTML = `<p class="error">Error: ${result.error}</p>`;
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
    
    # Check if user exists and password matches
    expected_password = USER_PASSWORDS.get(email)
    
    if expected_password and password == expected_password:
        session['logged_in'] = True
        session['email'] = email
        return redirect('/')
    else:
        return redirect('/?error=Invalid email or password')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

def redirect(url):
    from flask import redirect as flask_redirect
    return flask_redirect(url)

@app.route('/api/my-ips')
def get_ips():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    email = session.get('email')
    if email in USER_IPS:
        return jsonify({'ips': USER_IPS[email]})
    return jsonify({'error': 'No IPs found'}), 404

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
    new_ptr = data.get('ptr_record')
    
    if not new_ptr:
        return jsonify({'error': 'No hostname provided'}), 400
    
    if new_ptr.endswith('.'):
        new_ptr = new_ptr[:-1]
    
    client = Client(
        endpoint=OVH_ENDPOINT,
        application_key=OVH_APP_KEY,
        application_secret=OVH_APP_SECRET,
        consumer_key=OVH_CONSUMER_KEY,
    )
    
    try:
        result = client.post(f'/ip/{ip}/reverse', 
                            ipReverse=ip, 
                            reverse=new_ptr)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
