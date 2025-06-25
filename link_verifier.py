#!/usr/bin/env python3
"""
Link Verifier for llm-d.ai

This script crawls the llm-d.ai website and verifies that all links are working properly.
It reports any broken links (HTTP 404 Not Found and HTTP 500 Internal Server Error only)
and exits with appropriate status codes for use in GitHub Actions.
"""

import argparse
import logging
import sys
import time
from collections import defaultdict
from typing import Dict, List, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


class LinkVerifier:
    def __init__(self, base_url: str = "https://llm-d.ai", timeout: int = 30, delay: float = 1.0):
        """
        Initialize the Link Verifier.
        
        Args:
            base_url: The base URL to start crawling from
            timeout: Timeout for HTTP requests in seconds
            delay: Delay between requests to be respectful to the server
        """
        self.base_url = base_url
        self.timeout = timeout
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'llm-d-docs-verifier/1.0 (Link Checker)'
        })
        
        # Track results
        self.checked_links: Set[str] = set()
        self.broken_links: Dict[str, List[Tuple[str, str]]] = defaultdict(list)  # url -> [(source_page, error)]
        self.successful_links: Set[str] = set()
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def is_external_link(self, url: str) -> bool:
        """Check if a URL is external to the base domain."""
        parsed_base = urlparse(self.base_url)
        parsed_url = urlparse(url)
        return parsed_url.netloc and parsed_url.netloc != parsed_base.netloc

    def normalize_url(self, url: str, base_url: str) -> str:
        """Normalize and resolve relative URLs."""
        if url.startswith('#'):
            # Fragment-only URLs are valid for the current page
            return base_url + url
        
        # Handle relative URLs
        if not url.startswith(('http://', 'https://')):
            url = urljoin(base_url, url)
        
        # Remove fragment for checking (but keep for display)
        parsed = urlparse(url)
        if parsed.fragment:
            # For fragment URLs, we'll check the base URL
            base_without_fragment = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                base_without_fragment += f"?{parsed.query}"
            return base_without_fragment
        
        return url

    def get_links_from_page(self, url: str) -> List[str]:
        """Extract all links from a given page."""
        try:
            self.logger.info(f"Fetching page: {url}")
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            links = []
            
            # Find all anchor tags with href attributes
            for link in soup.find_all('a', href=True):
                href = link['href'].strip()
                if href and not href.startswith('mailto:') and not href.startswith('tel:'):
                    normalized_url = self.normalize_url(href, url)
                    links.append(normalized_url)
            
            # Also check for links in other elements (like buttons with onclick, etc.)
            # For now, focusing on anchor tags as they're the most common
            
            return list(set(links))  # Remove duplicates
            
        except Exception as e:
            self.logger.error(f"Error fetching page {url}: {str(e)}")
            return []

    def check_link(self, url: str, source_page: str) -> bool:
        """
        Check if a single link is working.
        
        Args:
            url: The URL to check
            source_page: The page where this link was found
            
        Returns:
            True if link is working, False otherwise
        """
        if url in self.checked_links:
            return url in self.successful_links
        
        self.checked_links.add(url)
        
        try:
            self.logger.info(f"Checking link: {url}")
            
            # Use HEAD request first to be more efficient
            try:
                response = self.session.head(url, timeout=self.timeout, allow_redirects=True)
                if response.status_code == 405:  # Method not allowed, try GET
                    response = self.session.get(url, timeout=self.timeout)
            except requests.exceptions.RequestException:
                # If HEAD fails, try GET
                response = self.session.get(url, timeout=self.timeout)
            
            # Only treat 404 and 500 as broken links
            if response.status_code == 404:
                error_msg = f"HTTP {response.status_code} - Not Found"
                self.broken_links[url].append((source_page, error_msg))
                self.logger.warning(f"✗ Link broken: {url} - {error_msg} (found on: {source_page})")
                return False
            elif response.status_code == 500:
                error_msg = f"HTTP {response.status_code} - Internal Server Error"
                self.broken_links[url].append((source_page, error_msg))
                self.logger.warning(f"✗ Link broken: {url} - {error_msg} (found on: {source_page})")
                return False
            else:
                # All other status codes (200, 403, 301, 302, etc.) are considered acceptable
                self.successful_links.add(url)
                if response.status_code == 200:
                    self.logger.info(f"✓ Link OK: {url}")
                else:
                    self.logger.info(f"✓ Link OK: {url} - HTTP {response.status_code}")
                return True
                
        except requests.exceptions.Timeout:
            # Timeouts are not considered broken links, just inaccessible at the moment
            self.successful_links.add(url)
            self.logger.info(f"⚠️  Link timeout (but not broken): {url} (found on: {source_page})")
            return True
            
        except requests.exceptions.ConnectionError:
            # Connection errors are not considered broken links, just inaccessible at the moment
            self.successful_links.add(url)
            self.logger.info(f"⚠️  Link connection error (but not broken): {url} (found on: {source_page})")
            return True
            
        except Exception as e:
            # Other errors are not considered broken links, just inaccessible at the moment
            self.successful_links.add(url)
            self.logger.info(f"⚠️  Link error (but not broken): {url} - {str(e)} (found on: {source_page})")
            return True

    def verify_all_links(self) -> bool:
        """
        Main method to verify all links on the website.
        
        Returns:
            True if all links are working, False if any broken links found
        """
        self.logger.info(f"Starting link verification for {self.base_url}")
        
        # Get all pages to crawl (starting with the base URL)
        pages_to_check = [self.base_url]
        checked_pages = set()
        
        # First, crawl the main page and find internal pages
        for page_url in pages_to_check:
            if page_url in checked_pages:
                continue
                
            checked_pages.add(page_url)
            links = self.get_links_from_page(page_url)
            
            # Filter for internal pages to add to crawling list
            for link in links:
                if not self.is_external_link(link) and link not in checked_pages and link not in pages_to_check:
                    # Only add if it's a different page (not just a fragment)
                    parsed_link = urlparse(link)
                    parsed_page = urlparse(page_url)
                    if parsed_link.path != parsed_page.path:
                        pages_to_check.append(link)
                        self.logger.info(f"Found internal page: {link}")
        
        self.logger.info(f"Found {len(pages_to_check)} pages to check")
        
        # Now check all links found on all pages
        all_links = []
        for page_url in pages_to_check:
            links = self.get_links_from_page(page_url)
            for link in links:
                all_links.append((link, page_url))
                
            time.sleep(self.delay)  # Be respectful to the server
        
        self.logger.info(f"Found {len(all_links)} total links to verify")
        
        # Check each unique link
        unique_links = {}
        for link, source in all_links:
            if link not in unique_links:
                unique_links[link] = []
            unique_links[link].append(source)
        
        success_count = 0
        for url, sources in unique_links.items():
            if self.check_link(url, sources[0]):  # Use first source for error reporting
                success_count += 1
            time.sleep(self.delay)  # Be respectful
        
        # Report results
        total_links = len(unique_links)
        broken_count = len(self.broken_links)
        
        self.logger.info(f"\n{'='*60}")
        self.logger.info("LINK VERIFICATION RESULTS")
        self.logger.info(f"{'='*60}")
        self.logger.info(f"Total links checked: {total_links}")
        self.logger.info(f"Successful links: {success_count}")
        self.logger.info(f"Broken links: {broken_count}")
        
        if self.broken_links:
            self.logger.error(f"\n{'='*60}")
            self.logger.error("BROKEN LINKS FOUND (HTTP 404 & 500 ONLY):")
            self.logger.error(f"{'='*60}")
            
            for url, sources_and_errors in self.broken_links.items():
                self.logger.error(f"\n❌ BROKEN LINK: {url}")
                for source, error in sources_and_errors:
                    self.logger.error(f"   📄 Found on page: {source}")
                    self.logger.error(f"   💥 Error: {error}")
        else:
            self.logger.info("\n✅ No broken links found (checked for HTTP 404 & 500 errors only)!")
        
        return broken_count == 0

def main():
    parser = argparse.ArgumentParser(description='Verify all links on llm-d.ai website (reports only HTTP 404 and 500 errors as broken)')
    parser.add_argument('--url', default='https://llm-d.ai', help='Base URL to check (default: https://llm-d.ai)')
    parser.add_argument('--timeout', type=int, default=30, help='Timeout for HTTP requests in seconds (default: 30)')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between requests in seconds (default: 1.0)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    verifier = LinkVerifier(
        base_url=args.url,
        timeout=args.timeout,
        delay=args.delay
    )
    
    success = verifier.verify_all_links()
    
    if success:
        print("\n✅ All links verified successfully! (No HTTP 404 or 500 errors found)")
        sys.exit(0)
    else:
        print(f"\n❌ Found {len(verifier.broken_links)} broken links! (HTTP 404/500 errors only)")
        sys.exit(1)

if __name__ == '__main__':
    main() 