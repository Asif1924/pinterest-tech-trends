#!/usr/bin/env python3
"""
Helper script to manage procured products list
Usage:
  python3 manage_procured.py add "Apple AirPods Pro"
  python3 manage_procured.py add "Samsung Galaxy Watch"
  python3 manage_procured.py list
  python3 manage_procured.py remove "Apple AirPods Pro"
  python3 manage_procured.py clear
"""

import sys
import json
import os

PROCURED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "procured_products.json")

def load_procured():
    try:
        with open(PROCURED_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"procured": [], "notes": "List of procured products"}

def save_procured(data):
    with open(PROCURED_FILE, "w") as f:
        json.dump(data, f, indent=2)

def add_product(product_name):
    data = load_procured()
    if product_name not in data["procured"]:
        data["procured"].append(product_name)
        save_procured(data)
        print(f"✓ Added: {product_name}")
        print(f"Total procured: {len(data['procured'])} products")
    else:
        print(f"Already in list: {product_name}")

def remove_product(product_name):
    data = load_procured()
    if product_name in data["procured"]:
        data["procured"].remove(product_name)
        save_procured(data)
        print(f"✓ Removed: {product_name}")
    else:
        print(f"Not found: {product_name}")

def list_products():
    data = load_procured()
    if data["procured"]:
        print(f"Procured Products ({len(data['procured'])} total):")
        print("-" * 40)
        for i, product in enumerate(data["procured"], 1):
            print(f"{i}. {product}")
    else:
        print("No products marked as procured yet.")

def clear_all():
    data = load_procured()
    count = len(data["procured"])
    data["procured"] = []
    save_procured(data)
    print(f"✓ Cleared {count} products from procured list")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    action = sys.argv[1].lower()
    
    if action == "add" and len(sys.argv) > 2:
        product = " ".join(sys.argv[2:])
        add_product(product)
    elif action == "remove" and len(sys.argv) > 2:
        product = " ".join(sys.argv[2:])
        remove_product(product)
    elif action == "list":
        list_products()
    elif action == "clear":
        clear_all()
    else:
        print(__doc__)