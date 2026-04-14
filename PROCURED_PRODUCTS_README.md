PROCURED PRODUCTS TRACKING SYSTEM
==================================

The Trending Tech Products job now tracks which products have been procured 
and highlights this information in the email notifications.

FEATURES:
---------
1. Email clearly shows NEW vs ALREADY PROCURED products
2. CSV includes a "Procured" column (Yes/No)
3. New products are highlighted at the top of the email
4. Already procured products are listed separately

HOW TO MANAGE PROCURED PRODUCTS:
---------------------------------

1. ADD A PRODUCT AS PROCURED:
   cd ~/.hermes/scripts
   python3 manage_procured.py add "Apple AirPods Pro"
   python3 manage_procured.py add "Samsung Galaxy Watch 6"

2. VIEW ALL PROCURED PRODUCTS:
   python3 manage_procured.py list

3. REMOVE A PRODUCT FROM PROCURED LIST:
   python3 manage_procured.py remove "Apple AirPods Pro"

4. CLEAR ALL PROCURED PRODUCTS:
   python3 manage_procured.py clear

5. EDIT MANUALLY (if needed):
   Edit the file: ~/.hermes/scripts/procured_products.json
   Format:
   {
     "procured": [
       "Apple AirPods Pro",
       "Samsung Galaxy Watch",
       "Product Name Here"
     ]
   }

MATCHING LOGIC:
---------------
- Products are matched using case-insensitive partial matching
- If "Apple AirPods" is in procured list, it will match:
  - "Apple AirPods Pro"
  - "Apple AirPods Pro 2"
  - "New Apple AirPods"
- This helps catch variations of the same product

EMAIL FORMAT:
-------------
The email now shows:
- Total product count
- Number of NEW products (not procured)
- Number of ALREADY PROCURED products
- Detailed list of new products to consider (top 10)
- List of already procured products (for reference)

CSV FORMAT:
-----------
The CSV file includes an additional "Procured" column:
- "Yes" for products already procured
- "No" for new products

EXAMPLE EMAIL OUTPUT:
---------------------
Total: 20 products | New: 15 | Already Procured: 5
============================================================

🆕 NEW PRODUCTS TO CONSIDER (15):
----------------------------------------
1. Dyson V15 Detect Vacuum
   Category: Smart Home
   Why Trending: Reddit r/gadgets (1,234 upvotes)

2. Sony WH-1000XM5 Headphones
   Category: Audio
   Why Trending: Amazon bestseller

[... more new products ...]

✓ ALREADY PROCURED (5):
----------------------------------------
  • Apple AirPods Pro (Audio)
  • Samsung Galaxy Watch 6 (Wearables)
  • Ring Video Doorbell (Smart Home)
  [... more procured products ...]

TIPS:
-----
1. Update the procured list after each purchase
2. Use partial product names for broader matching
3. The system checks for procured products on every job run
4. Email makes it easy to see what's new vs what you already have

FILES:
------
- Script: ~/.hermes/scripts/trending_tech_products.py (main job)
- Procured list: ~/.hermes/scripts/procured_products.json  
- Manager: ~/.hermes/scripts/manage_procured.py
- Config: ~/.hermes/scripts/pinterest_config.json