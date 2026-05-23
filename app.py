from flask import Flask, request, jsonify, render_template_string
from ovh import Client
import os
import socket

app = Flask(__name__)

# Your OVH credentials from environment
OVH_ENDPOINT = os.environ.get('OVH_ENDPOINT', 'ovh-eu')
OVH_APP_KEY = os.environ.get('OVH_APP_KEY')
OVH_APP_SECRET = os.environ.get('OVH_APP_SECRET')
OVH_CONSUMER_KEY = os.environ.get('OVH_CONSUMER_KEY')

# Your users (email -> list of IPs)
USER_IPS = {}
for key, value in os.environ.items():
    if key.startswith('USER_'):
        email = key.replace('USER_', '').replace('_', '@')
        USER_IPS[email] = [value]

# Simple HTML page
HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>rDNS Manager</title>
    <style>
        body { font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px; }
        input, button { padding: 10px; margin: 5px; }
        .success { color: green; }
        .error { color: red; }
        .current-ptr { background: #f0f0f0; padding: 10px; border-radius: 5px; margin: 10px 0; }
    </style>
</head>
<body>
    <h1>🔧 Reverse DNS Manager</h1>
    <div id="login">
        <h3>Login with your email</h3>
        <input type="email" id="email" placeholder="your@email.com">
        <button onclick="login()">Login</button>
    </div>
    <div id="dashboard" style="display:none;">
        <h3 id="userEmail"></h3>
        <div id="ipInfo"></div>
        <button onclick="logout()">Logout</button>
    </div>

    <script>
        async function login() {
            const email = document.getElementById('email').value;
            localStorage.setItem('email', email);
            await loadDashboard();
        }
        
        async function loadDashboard() {
            const email = localStorage.getItem('email');
            if (!email) return;
            
            const response = await fetch('/api/my-ips', {
                headers: { 'X-User-Email': email }
            });
            const data = await response.json();
            
            if (data.ips && data.ips.length > 0) {
                document.getElementById('login').style.display = 'none';
                document.getElementById('dashboard').style.display = 'block';
                document.getElementById('userEmail').innerHTML = `Logged in as: ${email}`;
                
                const ip = data.ips[0];
                const rdnsResponse = await fetch(`/api/rdns/${ip}`, {
                    headers: { 'X-User-Email': email }
                });
                const rdnsData = await rdnsResponse.json();
                
                document.getElementById('ipInfo').innerHTML = `
                    <h4>IP: ${ip}</h4>
                    <div class="current-ptr">
                        <strong>Current PTR:</strong><br>
                        ${rdnsData.ptr || 'No PTR record set'}
                    </div>
                    <input type="text" id="newPtr" placeholder="new.hostname.com" style="width: 300px;">
                    <button onclick="updatePtr('${ip}')">Update PTR</button>
                    <div id="message"></div>
                `;
            }
        }
        
        async function updatePtr(ip) {
            const ptr = document.getElementById('newPtr').value;
            const msgDiv = document.getElementById('message');
            
            if (!ptr) {
                msgDiv.innerHTML = '<p class="error">Please enter a hostname</p>';
                return;
            }
            
            msgDiv.innerHTML = '<p>Updating...</p>';
            
            const response = await fetch(`/api/rdns/${ip}`, {
                method: 'PUT',
                headers: {
                    'X-User-Email': localStorage.getItem('email'),
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ ptr_record: ptr })
            });
            
            const result = await response.json();
            if (result.success) {
                msgDiv.innerHTML = '<p class="success">✓ Updated successfully! Changes will take 5-10 minutes to propagate.</p>';
                setTimeout(() => loadDashboard(), 3000);
            } else {
                msgDiv.innerHTML = `<p class="error">Error: ${result.error}</p>`;
            }
        }
        
        function logout() {
            localStorage.clear();
            location.reload();
        }
        
        if (localStorage.getItem('email')) {
            loadDashboard();
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return HTML

@app.route('/api/my-ips')
def get_ips():
    email = request.headers.get('X-User-Email')
    if email in USER_IPS:
        return jsonify({'ips': USER_IPS[email]})
    return jsonify({'error': 'Unauthorized'}), 401

@app.route('/api/rdns/<ip>')
def get_rdns(ip):
    email = request.headers.get('X-User-Email')
    if email not in USER_IPS:
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Try DNS lookup first
    try:
        ptr = socket.gethostbyaddr(ip)[0]
        return jsonify({'ptr': ptr})
    except:
        return jsonify({'ptr': None})

@app.route('/api/rdns/<ip>', methods=['PUT'])
def update_rdns(ip):
    email = request.headers.get('X-User-Email')
    if email not in USER_IPS:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    new_ptr = data.get('ptr_record')
    
    if not new_ptr:
        return jsonify({'error': 'No hostname provided'}), 400
    
    # Remove trailing dot if present
    if new_ptr.endswith('.'):
        new_ptr = new_ptr[:-1]
    
    client = Client(
        endpoint=OVH_ENDPOINT,
        application_key=OVH_APP_KEY,
        application_secret=OVH_APP_SECRET,
        consumer_key=OVH_CONSUMER_KEY,
    )
    
    try:
        # Method: Use POST to /ip/{ip}/reverse
        result = client.post(f'/ip/{ip}/reverse', 
                            ipReverse=ip, 
                            reverse=new_ptr)
        
        return jsonify({'success': True})
        
    except Exception as e:
        error_msg = str(e)
        print(f"First attempt failed: {error_msg}")
        
        # Alternative method with IP block
        try:
            parts = ip.split('.')
            ip_block = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
            
            # Try to delete existing first
            try:
                client.delete(f'/ip/{ip_block}/reverse/{ip}')
            except:
                pass
            
            # Create new
            client.post(f'/ip/{ip_block}/reverse', 
                       ipReverse=ip, 
                       reverse=new_ptr)
            
            return jsonify({'success': True})
            
        except Exception as e2:
            return jsonify({'error': f'Both methods failed: {str(e2)}'}), 500

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
