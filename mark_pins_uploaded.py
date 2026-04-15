#!/usr/bin/env python3
"""
Pinterest Pin Status Updater
Helper script to mark pins as 'uploaded' after successful manual CSV upload.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

def log(message):
    """Log with timestamp"""
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"[{timestamp}] {message}")

def mark_pins_uploaded(limit=None):
    """Mark pins with status 'pending_upload' as 'uploaded'"""
    pins_dir = Path.home() / '.hermes' / 'pinterest_pins'
    if not pins_dir.exists():
        log("No pinterest_pins directory found")
        return 0
    
    updated_count = 0
    processed_count = 0
    
    for json_file in pins_dir.glob('*.json'):
        try:
            with open(json_file, 'r') as f:
                pin_data = json.load(f)
            
            if pin_data.get('status') == 'pending_upload':
                if limit and processed_count >= limit:
                    break
                    
                pin_data['status'] = 'uploaded'
                pin_data['uploaded_at'] = datetime.now(timezone.utc).isoformat()
                
                with open(json_file, 'w') as f:
                    json.dump(pin_data, f, indent=2)
                
                log(f"Marked as uploaded: {json_file.name}")
                updated_count += 1
                processed_count += 1
                
        except Exception as e:
            log(f"Error processing {json_file}: {e}")
    
    log(f"Updated {updated_count} pins to 'uploaded' status")
    return updated_count

def main():
    """Main function"""
    limit = None
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
            log(f"Limiting to {limit} pins")
        except ValueError:
            log("Invalid limit argument, processing all pending pins")
    
    log("=== Pinterest Pin Status Updater ===")
    updated = mark_pins_uploaded(limit)
    
    if updated > 0:
        log(f"Successfully marked {updated} pins as uploaded")
    else:
        log("No pending pins found to update")

if __name__ == "__main__":
    main()