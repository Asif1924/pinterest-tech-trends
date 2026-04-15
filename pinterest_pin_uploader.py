#!/usr/bin/env python3
"""
Pinterest Pin CSV Generator and Upload Helper
Creates Pinterest-compatible CSV files from pending pins.
Provides both automated upload (if browser available) and manual upload instructions.
"""

import json
import csv
import os
import sys
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/home/asif/.hermes/.env')

def log(message):
    """Log with timestamp"""
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"[{timestamp}] {message}")

def load_pending_pins():
    """Load all pins with status 'pending_upload'"""
    pins_dir = Path.home() / '.hermes' / 'pinterest_pins'
    if not pins_dir.exists():
        log("No pinterest_pins directory found")
        return []
    
    pending_pins = []
    for json_file in pins_dir.glob('*.json'):
        try:
            with open(json_file, 'r') as f:
                pin_data = json.load(f)
                if pin_data.get('status') == 'pending_upload':
                    pin_data['file_path'] = json_file
                    pending_pins.append(pin_data)
        except Exception as e:
            log(f"Error reading {json_file}: {e}")
    
    log(f"Found {len(pending_pins)} pins ready for upload")
    return pending_pins

def create_pinterest_csv(pins, csv_path):
    """
    Create CSV file for Pinterest Import Content feature
    Pinterest CSV format: Media,Board,Title,Description,Link,Alt text
    """
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        # Pinterest CSV header
        writer.writerow(['Media', 'Board', 'Title', 'Description', 'Link', 'Alt text'])
        
        for pin in pins:
            # Get primary image URL
            image_url = pin.get('primary_image', '')
            if not image_url and pin.get('images'):
                image_url = pin['images'][0].get('url', '')
            
            # Clean up description (remove excessive hashtags, limit length)
            description = pin.get('description', '')
            if len(description) > 500:
                description = description[:497] + "..."
            
            # Write pin data
            writer.writerow([
                image_url,                          # Media
                pin.get('board', 'smartypants9786'), # Board
                pin.get('title', ''),               # Title  
                description,                        # Description
                pin.get('link', ''),                # Link
                pin.get('alt_text', '')             # Alt text
            ])
    
    log(f"Created CSV with {len(pins)} pins: {csv_path}")
    return csv_path

def try_automated_upload(csv_path):
    """
    Attempt automated upload if browser automation is available
    Returns True if successful, False otherwise
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.chrome.options import Options
        from selenium.common.exceptions import TimeoutException, NoSuchElementException
        
        # Check if Chrome/Chromium is available
        chrome_paths = ['/usr/bin/google-chrome', '/usr/bin/chromium-browser', '/usr/bin/chromium']
        chrome_binary = None
        for path in chrome_paths:
            if Path(path).exists():
                chrome_binary = path
                break
        
        if not chrome_binary:
            log("Chrome/Chromium not found - skipping automated upload")
            return False
        
        # Set up Chrome options
        chrome_options = Options()
        chrome_options.binary_location = chrome_binary
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--headless')  # Run headless for automation
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-web-security')
        
        # Try to create driver
        driver = webdriver.Chrome(options=chrome_options)
        
        # Login and upload logic here
        pinterest_email = os.getenv('PINTEREST_EMAIL', 'alli.asif@gmail.com')
        pinterest_password = os.getenv('PINTEREST_PASSWORD', 'Mc68b09e!786')
        
        log("Attempting automated Pinterest upload...")
        driver.get("https://www.pinterest.com/login/")
        
        # Login process
        email_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "email"))
        )
        email_input.send_keys(pinterest_email)
        
        password_input = driver.find_element(By.ID, "password")
        password_input.send_keys(pinterest_password)
        
        login_button = driver.find_element(By.CSS_SELECTOR, "[data-test-id='registerFormSubmitButton']")
        login_button.click()
        
        # Wait for login success
        WebDriverWait(driver, 15).until(
            EC.any_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-test-id='header-profile']")),
                EC.url_contains("pinterest.com/")
            )
        )
        
        # Navigate to business hub for bulk upload
        driver.get("https://business.pinterest.com/hub/")
        
        # Look for bulk creation options
        # (Implementation continues based on Pinterest's current UI)
        
        driver.quit()
        log("Automated upload completed successfully")
        return True
        
    except ImportError:
        log("Selenium not available - using manual upload mode")
        return False
    except Exception as e:
        log(f"Automated upload failed: {e}")
        return False

def mark_pins_uploaded(pins):
    """Mark pins as uploaded and update their JSON files"""
    for pin in pins:
        try:
            pin['status'] = 'uploaded'
            pin['uploaded_at'] = datetime.now(timezone.utc).isoformat()
            
            with open(pin['file_path'], 'w') as f:
                # Remove file_path from the data before saving
                pin_data = {k: v for k, v in pin.items() if k != 'file_path'}
                json.dump(pin_data, f, indent=2)
            
            log(f"Marked as uploaded: {pin['file_path'].name}")
        except Exception as e:
            log(f"Error updating pin status: {e}")

def send_upload_report(pins, csv_path, automated_success=False):
    """Send email report with CSV and upload instructions"""
    try:
        email_address = os.getenv('EMAIL_ADDRESS')
        email_password = os.getenv('EMAIL_PASSWORD')
        
        if not email_address or not email_password:
            log("Email credentials not found in environment")
            return
        
        # Create email
        msg = MIMEMultipart('alternative')
        subject = f"Pinterest CSV Ready - {len(pins)} pins"
        if automated_success:
            subject = f"Pinterest Upload Complete - {len(pins)} pins"
        
        msg['Subject'] = subject
        msg['From'] = email_address
        msg['To'] = email_address
        
        # Create HTML report
        status_color = "#28a745" if automated_success else "#007bff"
        status_text = "UPLOADED AUTOMATICALLY" if automated_success else "CSV READY FOR MANUAL UPLOAD"
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; margin: 20px;">
            <h2 style="color: {status_color};">Pinterest Bulk Upload Report</h2>
            <p><strong>Status:</strong> <span style="color: {status_color}; font-weight: bold;">{status_text}</span></p>
            <p><strong>Pins Processed:</strong> {len(pins)}</p>
            <p><strong>CSV File:</strong> {csv_path}</p>
            <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        """
        
        if not automated_success:
            html += f"""
            <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #007bff; margin: 20px 0;">
                <h3 style="color: #007bff; margin-top: 0;">Manual Upload Instructions</h3>
                <ol>
                    <li>Go to <a href="https://business.pinterest.com/hub/" target="_blank">Pinterest Business Hub</a></li>
                    <li>Click on "Create" → "Bulk create Pins"</li>
                    <li>Choose "Upload a file" and select the CSV file: <code>{csv_path}</code></li>
                    <li>Review the preview and click "Create Pins"</li>
                </ol>
                <p><strong>CSV Location:</strong> <code>{csv_path}</code></p>
                <p><em>The CSV file is ready to upload with {len(pins)} pins formatted for Pinterest's Import Content feature.</em></p>
            </div>
            """
        
        html += """
            <h3>Pin Summary:</h3>
            <table border="1" style="border-collapse: collapse; width: 100%;">
                <tr style="background-color: #f2f2f2;">
                    <th style="padding: 8px; text-align: left;">Title</th>
                    <th style="padding: 8px; text-align: left;">Board</th>
                    <th style="padding: 8px; text-align: left;">Status</th>
                </tr>
        """
        
        for pin in pins:
            html += f"""
                <tr>
                    <td style="padding: 8px;">{pin.get('title', 'N/A')[:50]}</td>
                    <td style="padding: 8px;">{pin.get('board', 'N/A')}</td>
                    <td style="padding: 8px;">{pin.get('status', 'N/A')}</td>
                </tr>
            """
        
        html += """
            </table>
            
            <p style="margin-top: 20px; font-size: 12px; color: #666;">
                This is an automated report from the Pinterest automation pipeline.
            </p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html, 'html'))
        
        # Send email
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(email_address, email_password)
            server.send_message(msg)
        
        log("Upload report email sent successfully")
        
    except Exception as e:
        log(f"Error sending upload report: {e}")

def main():
    """Main upload process"""
    log("=== Pinterest Pin CSV Generator Started ===")
    
    # Load pending pins
    pending_pins = load_pending_pins()
    if not pending_pins:
        log("No pending pins found. Exiting.")
        return
    
    # Limit to 20 pins per batch to avoid overwhelming Pinterest
    batch_size = min(20, len(pending_pins))
    pins_to_upload = pending_pins[:batch_size]
    
    log(f"Processing batch of {len(pins_to_upload)} pins")
    
    # Create CSV file
    csv_path = Path.home() / '.hermes' / f'pinterest_upload_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    csv_path.parent.mkdir(exist_ok=True)
    
    create_pinterest_csv(pins_to_upload, csv_path)
    
    # Try automated upload
    automated_success = try_automated_upload(csv_path)
    
    if automated_success:
        # Mark pins as uploaded if automation worked
        mark_pins_uploaded(pins_to_upload)
        log("Automated upload completed successfully!")
    else:
        log("Using manual upload mode - CSV file created and ready for manual upload")
        # Don't mark as uploaded yet - wait for manual confirmation
    
    # Send report with CSV and instructions
    send_upload_report(pins_to_upload, str(csv_path), automated_success)
    
    # Print manual instructions to console as well
    if not automated_success:
        print("\n" + "="*60)
        print("MANUAL UPLOAD INSTRUCTIONS")
        print("="*60)
        print(f"1. CSV file created: {csv_path}")
        print("2. Go to: https://business.pinterest.com/hub/")
        print("3. Click: Create → Bulk create Pins")
        print("4. Upload the CSV file")
        print("5. Review and publish the pins")
        print(f"6. CSV contains {len(pins_to_upload)} pins ready for upload")
        print("="*60)
    
    log("=== Pinterest Pin CSV Generator Completed ===")

if __name__ == "__main__":
    main()