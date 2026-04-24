"""Pinterest CSV upload automation using Playwright (FR1-FR5, FR7, FR9)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from playwright.sync_api import (
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from config import Config

LOGIN_URL = "https://www.pinterest.com/login/"
BULK_CREATE_URL = "https://www.pinterest.com/settings/import"
SETTINGS_URL = "https://www.pinterest.com/settings/"

# Modular selectors — centralized so UI changes only require edits here (Risk §9).
SELECTORS = {
    "email": "input[type='email'], input[name='id'], input#email",
    "password": "input[type='password']",
    "login_submit": "button[type='submit'], div[data-test-id='registerFormSubmitButton'] button",
    "logged_in_marker": "[data-test-id='header-profile'], [data-test-id='header-avatar']",
    "file_input": "input[type='file']",
    "upload_confirm": "button:has-text('Upload'), button:has-text('Import'), button:has-text('Submit')",
}


@dataclass
class RunResult:
    success: bool
    message: str
    screenshot: Path | None = None


class PinterestCSVUploader:
    def __init__(self, config: Config, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger

    def _screenshot(self, page: Page, label: str) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.config.artifacts_dir / f"{ts}_{label}.png"
        try:
            page.screenshot(path=str(path), full_page=True)
            self.logger.info(f"📸 Artifact saved: {path}")
            return path
        except Exception as e:
            self.logger.warning(f"⚠️  Screenshot failed: {e}")
            return None

    def _handle_login(self, page: Page) -> bool:
        """Handle Pinterest login."""
        self.logger.info("🔑 Starting login sequence...")
        
        try:
            # Navigate to login
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=15000)
            self.logger.info("✅ Reached Pinterest login page")
            
            # Enter email
            self.logger.info("Entering email...")
            email_selector = SELECTORS["email"]
            page.wait_for_selector(email_selector, timeout=10000)
            page.fill(email_selector, self.config.email)
            self.logger.info(f"✅ Email entered: {self.config.email}")
            
            # Enter password
            self.logger.info("Entering password...")
            page.fill(SELECTORS["password"], self.config.password)
            self.logger.info("✅ Password entered")
            
            # Submit login
            self.logger.info("Submitting login form...")
            page.click(SELECTORS["login_submit"])
            
            # Wait for login to complete
            self.logger.info("Waiting for login to complete...")
            page.wait_for_selector(SELECTORS["logged_in_marker"], timeout=30000)
            self.logger.info("✅ Login successful!")
            
            # Take screenshot after login
            self._screenshot(page, "after_login")
            
            return True
            
        except PlaywrightTimeoutError as e:
            self.logger.error(f"❌ Login timeout: {e}")
            self._screenshot(page, "login_timeout")
            return False
        except Exception as e:
            self.logger.error(f"❌ Login failed: {e}")
            self._screenshot(page, "login_error")
            return False

    def _upload_csv(self, page: Page, csv_path: str) -> bool:
        """Upload CSV file."""
        self.logger.info(f"📤 Uploading CSV: {csv_path}")
        
        try:
            # Navigate to import page
            self.logger.info(f"Navigating to {BULK_CREATE_URL}...")
            page.goto(BULK_CREATE_URL, wait_until="domcontentloaded", timeout=20000)
            self._screenshot(page, "import_page")
            
            # Wait for file input
            self.logger.info("Waiting for file input...")
            page.wait_for_selector(SELECTORS["file_input"], timeout=30000)
            self.logger.info("✅ File input found")
            
            # Upload file
            self.logger.info(f"Uploading CSV file: {csv_path}")
            page.set_input_files(SELECTORS["file_input"], csv_path)
            self.logger.info("✅ CSV file set")
            
            # Wait for upload button
            self.logger.info("Waiting for upload confirmation button...")
            upload_button_selector = SELECTORS["upload_confirm"]
            page.wait_for_selector(upload_button_selector, timeout=10000)
            
            # Click upload
            self.logger.info("Clicking upload button...")
            page.click(upload_button_selector)
            self.logger.info("✅ Upload submitted")
            
            # Wait for success (page change or success message)
            page.wait_for_load_state("networkidle", timeout=15000)
            self._screenshot(page, "upload_complete")
            
            return True
            
        except PlaywrightTimeoutError as e:
            self.logger.error(f"❌ Upload timeout: {e}")
            self._screenshot(page, "upload_timeout")
            return False
        except Exception as e:
            self.logger.error(f"❌ Upload failed: {e}")
            self._screenshot(page, "upload_error")
            return False

    def run(self) -> RunResult:
        """Execute the upload workflow."""
        self.logger.info("🚀 Pinterest CSV Uploader starting...")
        
        browser = None
        context = None
        try:
            with sync_playwright() as p:
                # Launch browser
                self.logger.info("Launching browser...")
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    ignore_https_errors=True,
                )
                page = context.new_page()
                
                # Login
                if not self._handle_login(page):
                    return RunResult(success=False, message="Login failed")
                
                # Upload CSV
                if not self._upload_csv(page, str(self.config.csv_path)):
                    return RunResult(success=False, message="CSV upload failed")
                
                self.logger.info("✅ Upload workflow completed successfully")
                return RunResult(success=True, message="CSV uploaded successfully")
                
        except Exception as e:
            self.logger.error(f"❌ Workflow error: {e}")
            return RunResult(success=False, message=str(e))
        finally:
            if context:
                context.close()
            if browser:
                browser.close()
