import os
import subprocess
import time
import threading
import socket
import logging
from flask import Flask, render_template, send_file, request, redirect, url_for, jsonify
import glob
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/home/boazburnett/projects/abr-glass/ABR_Glass_V0/webserver.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('network_server')

# Configuration
RECORDINGS_DIR = os.path.dirname(os.path.abspath(__file__))  # Directory where recordings are saved
HOME_SSID = "YourHomeWiFiName"   # Change to your home WiFi name
HOME_PASSWORD = "YourPassword"    # Change to your home WiFi password
AP_MODE_ACTIVE = False
CONVERSION_IN_PROGRESS = False

app = Flask(__name__)

# Get IP address
def get_ip_address():
    try:
        # Try to get the IP address when connected to a network
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        logger.error(f"Error getting IP address: {e}")
        # If in AP mode, return the static IP
        if AP_MODE_ACTIVE:
            return "192.168.4.1"
        return "Not connected"

# Check if connected to WiFi
def is_connected_to_wifi():
    try:
        result = subprocess.run(["iwgetid"], capture_output=True, text=True)
        return HOME_SSID in result.stdout
    except Exception as e:
        logger.error(f"Error checking WiFi connection: {e}")
        return False

# Activate WiFi client mode
def activate_client_mode():
    global AP_MODE_ACTIVE
    logger.info("Activating client mode...")
    
    try:
        # Stop AP services
        subprocess.run(["sudo", "systemctl", "stop", "hostapd"])
        subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"])
        
        # Restart WiFi
        subprocess.run(["sudo", "systemctl", "restart", "dhcpcd"])
        
        # Connect to home network
        wpa_config = f"""
        ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
        update_config=1
        country=US

        network={{
            ssid="{HOME_SSID}"
            psk="{HOME_PASSWORD}"
            key_mgmt=WPA-PSK
        }}
        """
        
        with open("/tmp/wpa_supplicant.conf", "w") as f:
            f.write(wpa_config)
        
        subprocess.run(["sudo", "cp", "/tmp/wpa_supplicant.conf", "/etc/wpa_supplicant/wpa_supplicant.conf"])
        subprocess.run(["sudo", "wpa_cli", "-i", "wlan0", "reconfigure"])
        
        # Wait for connection
        time.sleep(10)
        AP_MODE_ACTIVE = False
    except Exception as e:
        logger.error(f"Error activating client mode: {e}")

# Activate AP mode
def activate_ap_mode():
    global AP_MODE_ACTIVE
    logger.info("Activating AP mode...")
    
    try:
        # Stop client services
        subprocess.run(["sudo", "systemctl", "stop", "dhcpcd"])
        
        # Restart AP services
        subprocess.run(["sudo", "systemctl", "start", "dhcpcd"])
        subprocess.run(["sudo", "systemctl", "start", "hostapd"])
        subprocess.run(["sudo", "systemctl", "start", "dnsmasq"])
        
        # Wait for services to start
        time.sleep(5)
        AP_MODE_ACTIVE = True
    except Exception as e:
        logger.error(f"Error activating AP mode: {e}")

# Network manager thread
def network_manager():
    global AP_MODE_ACTIVE
    
    while True:
        try:
            if is_connected_to_wifi():
                if AP_MODE_ACTIVE:
                    activate_client_mode()
                logger.info("Connected to home network")
            else:
                if not AP_MODE_ACTIVE:
                    activate_ap_mode()
                logger.info("Running in AP mode")
            
            # Check every 60 seconds
            time.sleep(60)
        except Exception as e:
            logger.error(f"Error in network manager: {e}")
            time.sleep(60)  # Retry after 60 seconds

# Generate HTML template
def generate_template():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>ABR Glass - Recordings</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
            }
            h1 {
                color: #333;
            }
            .file {
                border: 1px solid #ddd;
                padding: 10px;
                margin-bottom: 10px;
                border-radius: 5px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .file-info {
                flex-grow: 1;
            }
            .file-actions {
                display: flex;
                gap: 10px;
            }
            button, .button {
                background-color: #4CAF50;
                border: none;
                color: white;
                padding: 8px 12px;
                text-align: center;
                text-decoration: none;
                display: inline-block;
                font-size: 14px;
                margin: 4px 2px;
                cursor: pointer;
                border-radius: 4px;
            }
            .delete {
                background-color: #f44336;
            }
            .status {
                padding: 10px;
                background-color: #f8f9fa;
                border-radius: 5px;
                margin-bottom: 20px;
            }
            .alert {
                padding: 10px;
                background-color: #ffe066;
                color: #806600;
                border-radius: 5px;
                margin-bottom: 20px;
                display: {% if conversion_in_progress %}block{% else %}none{% endif %};
            }
            .refresh {
                background-color: #2196F3;
                margin-bottom: 20px;
            }
        </style>
        <script>
            function checkConversionStatus() {
                fetch('/conversion_status')
                    .then(response => response.json())
                    .then(data => {
                        var alert = document.getElementById('conversion-alert');
                        if (data.conversion_in_progress) {
                            alert.style.display = 'block';
                        } else {
                            alert.style.display = 'none';
                            // Refresh the page if conversion just completed
                            if (alert.getAttribute('data-visible') === 'true') {
                                window.location.reload();
                            }
                        }
                        alert.setAttribute('data-visible', data.conversion_in_progress);
                    });
            }
            
            // Check status every 5 seconds
            setInterval(checkConversionStatus, 5000);
            
            // Initial check on load
            window.onload = checkConversionStatus;
        </script>
    </head>
    <body>
        <h1>ABR Glass - Recordings</h1>
        <div class="status">
            <p><strong>Network Mode:</strong> {% if ap_mode_active %}AP Mode (ABR-Glass){% else %}Connected to WiFi{% endif %}</p>
            <p><strong>IP Address:</strong> {{ ip_address }}</p>
            <p><strong>Storage Used:</strong> {{ storage_used }}</p>
        </div>
        
        <div id="conversion-alert" class="alert" data-visible="{% if conversion_in_progress %}true{% else %}false{% endif %}">
            <p><strong>Video conversion in progress!</strong> A new video is currently being processed. Please wait until it completes before downloading files.</p>
        </div>
        
        <button onclick="window.location.reload();" class="refresh">Refresh Page</button>
        
        <h2>Recordings</h2>
        {% if files %}
            {% for file in files %}
            <div class="file">
                <div class="file-info">
                    <strong>{{ file.name }}</strong><br>
                    Date: {{ file.date }}<br>
                    Size: {{ file.size }}
                </div>
                <div class="file-actions">
                    <a href="{{ url_for('download_file', filename=file.name) }}" class="button">Download</a>
                    <form method="post" action="{{ url_for('delete_file') }}" onsubmit="return confirm('Are you sure you want to delete this file?');">
                        <input type="hidden" name="filename" value="{{ file.name }}">
                        <button type="submit" class="delete">Delete</button>
                    </form>
                </div>
            </div>
            {% endfor %}
        {% else %}
            <p>No recordings found.</p>
        {% endif %}
    </body>
    </html>
    """
    
    try:
        os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"), exist_ok=True)
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates/index.html"), "w") as f:
            f.write(html)
    except Exception as e:
        logger.error(f"Error generating template: {e}")

# Flask routes
@app.route('/')
def index():
    global CONVERSION_IN_PROGRESS
    try:
        # Get all video files
        video_files = glob.glob(os.path.join(RECORDINGS_DIR, "*.mp4")) + glob.glob(os.path.join(RECORDINGS_DIR, "*.mkv"))
        files = []
        
        for file_path in video_files:
            file_name = os.path.basename(file_path)
            file_stats = os.stat(file_path)
            file_size = file_stats.st_size / (1024 * 1024)  # Size in MB
            file_date = datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            files.append({
                'name': file_name,
                'date': file_date,
                'size': f"{file_size:.2f} MB"
            })
        
        # Sort files by date (newest first)
        files.sort(key=lambda x: x['date'], reverse=True)
        
        # Calculate storage used
        total_size = sum(os.path.getsize(f) for f in video_files) if video_files else 0
        storage_used = f"{total_size / (1024 * 1024 * 1024):.2f} GB"
        
        return render_template('index.html', 
                            files=files, 
                            ap_mode_active=AP_MODE_ACTIVE,
                            ip_address=get_ip_address(),
                            storage_used=storage_used,
                            conversion_in_progress=CONVERSION_IN_PROGRESS)
    except Exception as e:
        logger.error(f"Error in index route: {e}")
        return f"Error loading page: {str(e)}", 500

@app.route('/conversion_status')
def conversion_status():
    global CONVERSION_IN_PROGRESS
    return jsonify({'conversion_in_progress': CONVERSION_IN_PROGRESS})

@app.route('/download/<filename>')
def download_file(filename):
    try:
        return send_file(os.path.join(RECORDINGS_DIR, filename), as_attachment=True)
    except Exception as e:
        logger.error(f"Error downloading file {filename}: {e}")
        return f"Error downloading file: {str(e)}", 500

@app.route('/delete', methods=['POST'])
def delete_file():
    try:
        filename = request.form.get('filename')
        if filename:
            try:
                os.remove(os.path.join(RECORDINGS_DIR, filename))
                logger.info(f"Deleted file: {filename}")
            except Exception as e:
                logger.error(f"Error deleting file {filename}: {e}")
        return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"Error in delete route: {e}")
        return redirect(url_for('index'))
    

# Add this function to network_server.py
def check_conversion_status():
    """Checks if video conversion is in progress."""
    global CONVERSION_IN_PROGRESS
    try:
        status_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conversion_status.txt")
        if os.path.exists(status_file):
            with open(status_file, "r") as f:
                status = f.read().strip()
            CONVERSION_IN_PROGRESS = (status == "1")
        else:
            CONVERSION_IN_PROGRESS = False
    except Exception as e:
        logger.error(f"Error checking conversion status: {e}")
        CONVERSION_IN_PROGRESS = False

# Add this to the network_manager function
def status_checker():
    """Thread to check conversion status periodically."""
    while True:
        check_conversion_status()
        time.sleep(2)

# And start this thread in the main function
status_thread = threading.Thread(target=status_checker)
status_thread.daemon = True
status_thread.start()


# Main function
def main():
    try:
        # Create templates directory
        os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"), exist_ok=True)
        
        # Generate template
        generate_template()
        
        # Start network manager thread
        network_thread = threading.Thread(target=network_manager)
        network_thread.daemon = True
        network_thread.start()
        
        # Start Flask server
        logger.info("Starting web server...")
        app.run(host='0.0.0.0', port=80, debug=False, threaded=True)
    except Exception as e:
        logger.error(f"Error in main function: {e}")

if __name__ == "__main__":
    main()
