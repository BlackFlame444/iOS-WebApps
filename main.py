from flask import Flask, render_template_string, request, jsonify, session
import requests
from bs4 import BeautifulSoup
import random
import urllib.request
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)

class SearchApp:
    def __init__(self, api_key=None):
        # API key can be passed during initialization or set later
        self.NUMVERIFY_API_KEY = api_key
        self.USERAGENTS = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Linux; Android 10; SM-G970F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",
        ]
        self.HTMLWEB_URL = "https://htmlweb.ru/geo/api.php?json&telcod="
        self.NUMVERIFY_URL = "http://apilayer.net/api/validate?access_key="
        self.OK_LOGIN_URL = 'https://www.ok.ru/dk?st.cmd=anonymMain&st.accRecovery=on&st.error=errors.password.wrong'
        self.OK_RECOVER_URL = 'https://www.ok.ru/dk?st.cmd=anonymRecoveryAfterFailedLogin&st._aid=LeftColumn_Login_ForgotPassword'

    def set_api_key(self, api_key):
        """Set or update the API key"""
        self.NUMVERIFY_API_KEY = api_key

    def check_internet(self):
        try:
            urllib.request.urlopen('https://google.com', timeout=5)
            return True
        except:
            return False

    def get_address_by_coordinates(self, latitude, longitude):
        try:
            address_url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={latitude}&lon={longitude}"
            address_response = urllib.request.urlopen(address_url)
            address_data = json.load(address_response)
            if "address" in address_data:
                return self.sort_address(address_data["address"])
            return "Address not found"
        except Exception as e:
            return f"Error getting address: {e}"

    def sort_address(self, address):
        address_order = ["road", "house_number", "village", "town", "suburb", "postcode"]
        sorted_address = {}
        for key in address_order:
            if key in address:
                sorted_address[key] = address[key]
        return sorted_address

    def translate_address(self, address):
        translations = {
            "road": "Street",
            "house_number": "House Number",
            "village": "Village",
            "town": "Town",
            "suburb": "District",
            "postcode": "Postal Code"
        }
        translated_address = {}
        for key, value in address.items():
            translated_key = translations.get(key, key.capitalize())
            translated_address[translated_key] = value
        return translated_address

    def check_login(self, telcode):
        try:
            headers = {"User-Agent": random.choice(self.USERAGENTS)}
            session = requests.Session()
            session.get(f'{self.OK_LOGIN_URL}&st.email={telcode}', timeout=10)
            request = session.get(self.OK_RECOVER_URL, timeout=10)
            root_soup = BeautifulSoup(request.content, 'html.parser')
            
            if root_soup.find('div', {'data-l': 'registrationContainer,offer_contact_rest'}):
                account_info = root_soup.find('div', {'class': 'ext-registration_tx taCenter'})
                masked_phone = telcode
                
                if account_info:
                    name = account_info.find('div', {'class': 'ext-registration_username_header'})
                    name = name.get_text() if name else "Unknown"
                    
                    account_info_elements = account_info.findAll('div', {'class': 'lstp-t'})
                    if account_info_elements and len(account_info_elements) >= 2:
                        profile_info = account_info_elements[0].get_text()
                        profile_registered = account_info_elements[1].get_text()
                    else:
                        profile_info = "Unknown"
                        profile_registered = "Unknown"
                
                return {
                    "source": "Odnoklassniki",
                    "phone": masked_phone,
                    "name": name,
                    "profile_info": profile_info,
                    "registered": profile_registered
                }
            
            if root_soup.find('div', {'data-l': 'registrationContainer,home_rest'}):
                return 'not associated'
            
            return None
        except Exception as e:
            return f"Error: {e}"

    def phone_search(self, telcode):
        results = []
        
        # Check if API key is set
        if not self.NUMVERIFY_API_KEY:
            return {"error": "Numverify API key not set. Please enter your API key above."}

        if not telcode or not telcode.startswith("+") or not telcode[1:].isdigit():
            return {"error": "Phone number must start with '+' and contain only digits!"}

        if not self.check_internet():
            return {"error": "No internet connection!"}

        headers = {"User-Agent": random.choice(self.USERAGENTS)}
        
        # HTMLWEB request
        try:
            response = requests.get(self.HTMLWEB_URL + telcode, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                htmlweb_data = {
                    "source": "HTMLWEB",
                    "phone_code": f"+{data.get('country', {}).get('telcod', 'Unknown')}",
                    "country": data.get("country", {}).get("fullname", "Unknown"),
                    "district": data.get("okrug", "Unknown"),
                    "region": data.get("region", {}).get("name", "Unknown"),
                    "city": data.get("0", {}).get("name", "Unknown"),
                    "latitude": data.get("0", {}).get("latitude", "Unknown"),
                    "longitude": data.get("0", {}).get("longitude", "Unknown"),
                    "timezone": f"+{data.get('0', {}).get('time_zone', data.get('time_zone', 'Unknown'))} UTC",
                    "operator": data.get("0", {}).get("oper", "Unknown")
                }
                results.append(htmlweb_data)
                
                # Get address if coordinates available
                if htmlweb_data["latitude"] != "Unknown" and htmlweb_data["longitude"] != "Unknown":
                    address = self.get_address_by_coordinates(htmlweb_data["latitude"], htmlweb_data["longitude"])
                    if isinstance(address, dict):
                        htmlweb_data["address"] = self.translate_address(address)
            else:
                results.append({"source": "HTMLWEB", "error": f"HTTP Error: {response.status_code}"})
        except Exception as e:
            results.append({"source": "HTMLWEB", "error": str(e)})

        # Numverify request
        try:
            response = requests.get(f"{self.NUMVERIFY_URL}{self.NUMVERIFY_API_KEY}&number={telcode}", headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("valid", False):
                    numverify_data = {
                        "source": "Numverify",
                        "number": data.get('international_format', 'Unknown'),
                        "country": data.get('country_name', 'Unknown'),
                        "operator": data.get('carrier', 'Unknown'),
                        "type": data.get('line_type', 'Unknown')
                    }
                    results.append(numverify_data)
                else:
                    results.append({"source": "Numverify", "error": "Number invalid or information unavailable"})
            else:
                results.append({"source": "Numverify", "error": f"HTTP Error: {response.status_code}"})
        except Exception as e:
            results.append({"source": "Numverify", "error": str(e)})

        # Odnoklassniki check
        ok_result = self.check_login(telcode)
        if isinstance(ok_result, dict):
            results.append(ok_result)
        elif ok_result == 'not associated':
            results.append({"source": "Odnoklassniki", "status": "Number not associated with account"})
        else:
            results.append({"source": "Odnoklassniki", "error": str(ok_result)})

        # Additional sources
        valid = telcode.replace('+', '')
        additional_sources = {
            "validity_check": f"https://smsc.ru/testhlr/?phone={valid}",
            "extended_search": f"https://reveng.ee/search?q={telcode}"
        }
        results.append({"additional_sources": additional_sources})

        return results

# Global search app instance
search_app = SearchApp()

# HTML Template with API key input
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>0DAY SEARCH</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            background-color: #000000;
            color: white;
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
        }
        .header {
            color: #800080;
            font-size: 24px;
            font-weight: bold;
            margin-bottom: 20px;
        }
        .container {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        .api-key-section {
            margin-bottom: 15px;
            padding: 15px;
            background-color: #1a1a1a;
            border-radius: 5px;
            border-left: 4px solid #4B0082;
        }
        .api-key-section h3 {
            margin-top: 0;
            color: #800080;
        }
        .input-section {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        input[type="text"] {
            flex: 1;
            padding: 15px;
            font-size: 16px;
            background-color: #333333;
            color: white;
            border: 1px solid #800080;
            border-radius: 5px;
        }
        input[type="password"] {
            flex: 1;
            padding: 15px;
            font-size: 16px;
            background-color: #333333;
            color: white;
            border: 1px solid #800080;
            border-radius: 5px;
        }
        button {
            padding: 15px 25px;
            background-color: #4B0082;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            white-space: nowrap;
        }
        button:hover {
            background-color: #000000;
        }
        .results {
            background-color: #1C1C1C;
            padding: 20px;
            border-radius: 5px;
            max-height: 400px;
            overflow-y: auto;
        }
        .result-item {
            margin-bottom: 15px;
            padding: 10px;
            background-color: #333333;
            border-radius: 5px;
        }
        .error {
            color: #ff4444;
            background-color: #331111;
            padding: 10px;
            border-radius: 5px;
            border-left: 4px solid #ff4444;
        }
        .success {
            color: #44ff44;
            background-color: #113311;
            padding: 10px;
            border-radius: 5px;
            border-left: 4px solid #44ff44;
        }
        .warning {
            color: #ffaa00;
            background-color: #332200;
            padding: 10px;
            border-radius: 5px;
            border-left: 4px solid #ffaa00;
        }
        .footer {
            margin-top: 20px;
            font-size: 12px;
            color: #888;
        }
        .api-status {
            display: inline-block;
            padding: 5px 10px;
            border-radius: 15px;
            font-size: 12px;
            margin-left: 10px;
        }
        .api-set {
            background-color: #113311;
            color: #44ff44;
        }
        .api-not-set {
            background-color: #331111;
            color: #ff4444;
        }
        .instructions {
            background-color: #1a1a1a;
            padding: 15px;
            border-radius: 5px;
            font-size: 14px;
            margin-bottom: 20px;
        }
        .instructions h4 {
            margin-top: 0;
            color: #800080;
        }
    </style>
</head>
<body>
    <div class="header">0DAY SEARCH</div>
    
    <div class="instructions">
        <h4>How to get your API Key:</h4>
        <ol>
            <li>Go to <a href="https://numverify.com" style="color: #800080;" target="_blank">numverify.com</a></li>
            <li>Sign up for a free account</li>
            <li>Get your API key from the dashboard</li>
            <li>Enter it below (it will be saved for this session)</li>
        </ol>
    </div>
    
    <div class="container">
        <div class="api-key-section">
            <h3>Numverify API Key 
                <span class="api-status {{ 'api-set' if api_key_set else 'api-not-set' }}">
                    {{ '✓ SET' if api_key_set else '✗ NOT SET' }}
                </span>
            </h3>
            <form method="POST" action="/set-api-key">
                <div class="input-section">
                    <input type="password" name="api_key" placeholder="Enter your Numverify API key" value="{{ current_api_key }}">
                    <button type="submit">Save API Key</button>
                </div>
            </form>
            {% if api_key_message %}
                <div class="{{ api_key_message_type }}">{{ api_key_message }}</div>
            {% endif %}
        </div>

        <form method="POST" action="/">
            <div class="input-section">
                <input type="text" name="phone_number" placeholder="Enter phone number (e.g., +79123456789)" value="{{ phone_number }}">
                <button type="submit">SEARCH</button>
            </div>
        </form>
        
        {% if results %}
        <div class="results">
            <h3>Search Results:</h3>
            {% for result in results %}
                <div class="result-item">
                    <strong>Source: {{ result.source }}</strong><br>
                    {% if result.error %}
                        <span class="error">Error: {{ result.error }}</span>
                    {% else %}
                        {% for key, value in result.items() %}
                            {% if key not in ['source', 'error'] %}
                                {% if key == 'additional_sources' %}
                                    <strong>Additional Sources:</strong><br>
                                    {% for source_name, source_url in value.items() %}
                                        • <a href="{{ source_url }}" target="_blank" style="color: #800080;">{{ source_name|replace('_', ' ')|title }}</a><br>
                                    {% endfor %}
                                {% elif key == 'address' %}
                                    <strong>Address:</strong><br>
                                    {% for addr_key, addr_value in value.items() %}
                                        &nbsp;&nbsp;{{ addr_key }}: {{ addr_value }}<br>
                                    {% endfor %}
                                {% else %}
                                    {{ key|replace('_', ' ')|title }}: {{ value }}<br>
                                {% endif %}
                            {% endif %}
                        {% endfor %}
                    {% endif %}
                </div>
            {% endfor %}
        </div>
        {% endif %}
        
        {% if error %}
        <div class="error">
            {{ error }}
        </div>
        {% endif %}
        
        <div class="footer">
            © 2025 dev by tt volfran | API Key is stored in your session and not saved on server
        </div>
    </div>
    
    <script>
        // Simple client-side validation
        document.addEventListener('DOMContentLoaded', function() {
            const apiKeyInput = document.querySelector('input[name="api_key"]');
            const phoneInput = document.querySelector('input[name="phone_number"]');
            
            if (apiKeyInput && !apiKeyInput.value) {
                apiKeyInput.focus();
            }
            
            // Show/hide API key
            if (apiKeyInput) {
                const toggleVisibility = document.createElement('button');
                toggleVisibility.type = 'button';
                toggleVisibility.textContent = '👁';
                toggleVisibility.style.background = 'transparent';
                toggleVisibility.style.border = 'none';
                toggleVisibility.style.color = '#800080';
                toggleVisibility.style.cursor = 'pointer';
                toggleVisibility.style.marginLeft = '5px';
                
                toggleVisibility.addEventListener('click', function() {
                    if (apiKeyInput.type === 'password') {
                        apiKeyInput.type = 'text';
                        toggleVisibility.textContent = '👁‍🗨';
                    } else {
                        apiKeyInput.type = 'password';
                        toggleVisibility.textContent = '👁';
                    }
                });
                
                apiKeyInput.parentNode.appendChild(toggleVisibility);
            }
        });
    </script>
</body>
</html>
'''

@app.route('/', methods=['GET', 'POST'])
def index():
    results = None
    error = None
    phone_number = ""
    api_key_set = bool(session.get('numverify_api_key'))
    current_api_key = session.get('numverify_api_key', '')
    
    # Mask the API key for display
    display_api_key = ""
    if current_api_key:
        if len(current_api_key) > 8:
            display_api_key = current_api_key[:4] + "*" * (len(current_api_key) - 8) + current_api_key[-4:]
        else:
            display_api_key = "*" * len(current_api_key)
    
    if request.method == 'POST':
        phone_number = request.form.get('phone_number', '')
        if phone_number:
            # Update the search app with current API key
            search_app.set_api_key(session.get('numverify_api_key'))
            
            results = search_app.phone_search(phone_number)
            if isinstance(results, dict) and 'error' in results:
                error = results['error']
                results = None
    
    return render_template_string(HTML_TEMPLATE, 
                                results=results, 
                                error=error, 
                                phone_number=phone_number,
                                api_key_set=api_key_set,
                                current_api_key=display_api_key,
                                api_key_message=session.pop('api_key_message', None),
                                api_key_message_type=session.pop('api_key_message_type', ''))

@app.route('/set-api-key', methods=['POST'])
def set_api_key():
    api_key = request.form.get('api_key', '').strip()
    
    if api_key:
        session['numverify_api_key'] = api_key
        session['api_key_message'] = "API key saved successfully! It will be stored for this session."
        session['api_key_message_type'] = "success"
        
        # Test the API key
        search_app.set_api_key(api_key)
        try:
            test_response = requests.get(f"http://apilayer.net/api/validate?access_key={api_key}&number=+15555555555", timeout=5)
            if test_response.status_code == 200:
                session['api_key_message'] = "API key saved and validated successfully!"
            else:
                session['api_key_message'] = "API key saved but validation failed. Please check your key."
                session['api_key_message_type'] = "warning"
        except:
            session['api_key_message'] = "API key saved but could not validate. Please check your connection."
            session['api_key_message_type'] = "warning"
    else:
        session['api_key_message'] = "Please enter a valid API key."
        session['api_key_message_type'] = "error"
    
    return redirect('/')

@app.route('/clear-api-key', methods=['POST'])
def clear_api_key():
    session.pop('numverify_api_key', None)
    search_app.set_api_key(None)
    session['api_key_message'] = "API key cleared."
    session['api_key_message_type'] = "success"
    return redirect('/')

@app.route('/api/search/<phone_number>')
def api_search(phone_number):
    search_app.set_api_key(session.get('numverify_api_key'))
    results = search_app.phone_search(phone_number)
    return jsonify(results)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)