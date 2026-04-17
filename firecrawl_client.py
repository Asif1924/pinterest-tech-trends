#!/usr/bin/env python3
"""
Firecrawl API Client for Pinterest Automation Pipeline
Hybrid approach: Uses Firecrawl for complex sites, fallback to urllib for simple ones
"""

import json
import time
import urllib.request
import urllib.parse
from typing import Dict, List, Optional, Tuple
from datetime import datetime

class FirecrawlHybridClient:
    """Hybrid web scraping client - Firecrawl API + urllib fallback"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.base_url = "https://api.firecrawl.dev/v0"  # V0 API for now
        self.has_firecrawl = api_key and api_key != "YOUR_FIRECRAWL_API_KEY_HERE"
        
        # Performance tracking
        self.stats = {
            "firecrawl_success": 0,
            "firecrawl_failed": 0,
            "urllib_success": 0,
            "urllib_failed": 0,
            "total_time_firecrawl": 0,
            "total_time_urllib": 0
        }
    
    def _make_firecrawl_request(self, endpoint: str, data: Dict = None, method: str = "POST") -> Dict:
        """Make API request to Firecrawl"""
        if not self.has_firecrawl:
            return {"error": "No Firecrawl API key configured"}
            
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        if data:
            req_data = json.dumps(data).encode('utf-8')
        else:
            req_data = None
            
        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            return {"error": str(e)}
    
    def _urllib_fallback(self, url: str, timeout: int = 15) -> Dict:
        """Fallback to urllib for simple scraping"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/json",
            "Accept-Language": "en-US,en;q=0.9"
        }
        
        req = urllib.request.Request(url, headers=headers)
        
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                return {
                    "success": True,
                    "content": content,
                    "method": "urllib",
                    "url": url
                }
        except Exception as e:
            return {"error": str(e), "method": "urllib"}
    
    def scrape_smart(self, url: str, prefer_firecrawl: bool = True, 
                     formats: List[str] = None) -> Tuple[Dict, str]:
        """
        Smart scraping with automatic fallback
        
        Returns: (result_dict, method_used)
        """
        start_time = time.time()
        
        # Determine if site needs JavaScript (use Firecrawl)
        needs_js = any(domain in url for domain in [
            "amazon.com", "pinterest.com", "twitter.com", "x.com",
            "instagram.com", "facebook.com", "linkedin.com",
            "producthunt.com", "techcrunch.com"
        ])
        
        # Try Firecrawl first if available and preferred
        if self.has_firecrawl and (prefer_firecrawl or needs_js):
            if formats is None:
                formats = ["markdown", "links", "metadata"]
            
            result = self._make_firecrawl_request("/scrape", {
                "url": url,
                "pageOptions": {
                    "waitFor": 2000 if needs_js else 0  # Wait for JS to load
                }
            })
            
            elapsed = time.time() - start_time
            
            if "error" not in result and result.get("success"):
                self.stats["firecrawl_success"] += 1
                self.stats["total_time_firecrawl"] += elapsed
                # Normalize response format
                if result.get("data"):
                    result["markdown"] = result["data"].get("markdown", result["data"].get("content", ""))
                    result["content"] = result["data"].get("content", result["markdown"])
                return result, "firecrawl"
            else:
                self.stats["firecrawl_failed"] += 1
                
                # Fallback to urllib if Firecrawl fails
                if not needs_js:
                    result = self._urllib_fallback(url)
                    elapsed = time.time() - start_time
                    
                    if "error" not in result:
                        self.stats["urllib_success"] += 1
                        self.stats["total_time_urllib"] += elapsed
                        return result, "urllib_fallback"
                    else:
                        self.stats["urllib_failed"] += 1
                        return result, "failed"
                        
                return result, "firecrawl_failed"
        
        # Use urllib directly for simple sites
        else:
            result = self._urllib_fallback(url)
            elapsed = time.time() - start_time
            
            if "error" not in result:
                self.stats["urllib_success"] += 1
                self.stats["total_time_urllib"] += elapsed
                return result, "urllib"
            else:
                self.stats["urllib_failed"] += 1
                return result, "urllib_failed"
    
    def search_web(self, query: str, limit: int = 10) -> Dict:
        """Search the web using Firecrawl"""
        if not self.has_firecrawl:
            return {"error": "Firecrawl API key required for search"}
            
        return self._make_firecrawl_request("/search", {
            "query": query,
            "limit": limit
        })
    
    def crawl_site(self, url: str, max_pages: int = 5) -> Dict:
        """Crawl multiple pages from a website"""
        if not self.has_firecrawl:
            return {"error": "Firecrawl API key required for crawling"}
            
        return self._make_firecrawl_request("/crawl", {
            "url": url,
            "maxPages": max_pages,
            "waitFor": 1000
        })
    
    def extract_products(self, url: str) -> List[Dict]:
        """Extract product data from e-commerce pages"""
        if not self.has_firecrawl:
            # Fallback to basic extraction
            html, _ = self.scrape_smart(url, prefer_firecrawl=False)
            return self._parse_products_from_html(html.get("content", ""))
            
        result = self._make_firecrawl_request("/scrape", {
            "url": url,
            "formats": ["markdown", "links", "metadata", "extract"],
            "extract": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "products": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "price": {"type": "string"},
                                    "description": {"type": "string"},
                                    "image": {"type": "string"},
                                    "link": {"type": "string"},
                                    "rating": {"type": "number"}
                                }
                            }
                        }
                    }
                }
            }
        })
        
        if result.get("success") and result.get("extract"):
            return result["extract"].get("products", [])
        return []
    
    def _parse_products_from_html(self, html: str) -> List[Dict]:
        """Basic product extraction from HTML (fallback)"""
        products = []
        # Simple regex-based extraction (your existing logic)
        import re
        
        # Find product patterns
        product_patterns = [
            r'<h[1-3][^>]*>([^<]+)</h[1-3]>',  # Headers
            r'data-product-title="([^"]+)"',
            r'class="product-name"[^>]*>([^<]+)<'
        ]
        
        for pattern in product_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches[:10]:  # Limit to 10 products
                if len(match) > 10 and len(match) < 200:
                    products.append({
                        "name": match.strip(),
                        "source": "html_parse"
                    })
        
        return products
    
    def get_stats_report(self) -> str:
        """Generate performance comparison report"""
        total_fc = self.stats["firecrawl_success"] + self.stats["firecrawl_failed"]
        total_ur = self.stats["urllib_success"] + self.stats["urllib_failed"]
        
        report = [
            "\n═══════════════════════════════════════════════════════",
            "          SCRAPING PERFORMANCE COMPARISON",
            "═══════════════════════════════════════════════════════",
            "",
            "FIRECRAWL API:",
            f"  ✅ Success: {self.stats['firecrawl_success']}",
            f"  ❌ Failed:  {self.stats['firecrawl_failed']}",
            f"  ⏱️  Avg Time: {self.stats['total_time_firecrawl'] / max(total_fc, 1):.2f}s" if total_fc > 0 else "  ⏱️  Avg Time: N/A",
            f"  📊 Success Rate: {(self.stats['firecrawl_success'] / max(total_fc, 1)) * 100:.1f}%" if total_fc > 0 else "  📊 Success Rate: N/A",
            "",
            "URLLIB (Standard Library):",
            f"  ✅ Success: {self.stats['urllib_success']}",
            f"  ❌ Failed:  {self.stats['urllib_failed']}",
            f"  ⏱️  Avg Time: {self.stats['total_time_urllib'] / max(total_ur, 1):.2f}s" if total_ur > 0 else "  ⏱️  Avg Time: N/A",
            f"  📊 Success Rate: {(self.stats['urllib_success'] / max(total_ur, 1)) * 100:.1f}%" if total_ur > 0 else "  📊 Success Rate: N/A",
            "",
            "OVERALL:",
            f"  📈 Total Requests: {total_fc + total_ur}",
            f"  🔥 Firecrawl Used: {total_fc} ({(total_fc / max(total_fc + total_ur, 1)) * 100:.1f}%)" if (total_fc + total_ur) > 0 else "  🔥 Firecrawl Used: 0 (0%)",
            f"  📦 Urllib Used: {total_ur} ({(total_ur / max(total_fc + total_ur, 1)) * 100:.1f}%)" if (total_fc + total_ur) > 0 else "  📦 Urllib Used: 0 (0%)",
            "",
            "═══════════════════════════════════════════════════════"
        ]
        
        return "\n".join(report)


def test_comparison():
    """Run comparison test between Firecrawl and urllib"""
    
    # Initialize client with your API key
    client = FirecrawlHybridClient(api_key="fc-62d49b766f354e7481c8bd5107f4620a")
    
    test_urls = [
        ("Reddit /r/gadgets", "https://www.reddit.com/r/gadgets/hot.json"),
        ("TechCrunch", "https://techcrunch.com"),
        ("Product Hunt", "https://www.producthunt.com"),
        ("Amazon Tech", "https://www.amazon.com/Best-Sellers-Electronics/zgbs/electronics"),
        ("The Verge", "https://www.theverge.com/tech"),
        ("TechRadar", "https://www.techradar.com/best/best-gadgets")
    ]
    
    print("\n🔬 STARTING HYBRID SCRAPING TEST")
    print("=" * 60)
    
    for name, url in test_urls:
        print(f"\n📍 Testing: {name}")
        print(f"   URL: {url}")
        
        # Try with Firecrawl preference
        result, method = client.scrape_smart(url, prefer_firecrawl=True)
        
        if "error" not in result:
            content_len = len(str(result.get("content", result.get("markdown", ""))))
            print(f"   ✅ Success via {method}")
            print(f"   📄 Content size: {content_len:,} chars")
        else:
            print(f"   ❌ Failed: {result.get('error', 'Unknown error')[:50]}...")
    
    # Print performance report
    print(client.get_stats_report())


if __name__ == "__main__":
    test_comparison()