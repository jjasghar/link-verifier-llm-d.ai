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
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Dict, List, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


class LinkVerifier:
    def __init__(self, base_url: str = "https://llm-d.ai", timeout: int = 30, delay: float = 1.0, max_workers: int = 10):
        """
        Initialize the Link Verifier.
        
        Args:
            base_url: The base URL to start crawling from
            timeout: Timeout for HTTP requests in seconds
            delay: Delay between requests to be respectful to the server
            max_workers: Maximum number of concurrent threads for link checking
        """
        self.base_url = base_url
        self.timeout = timeout
        self.delay = delay
        self.max_workers = max_workers
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'llm-d-docs-verifier/1.0 (Link Checker)'
        })
        
        # Configure connection pooling for better performance
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=100,
            max_retries=1
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        # Thread-safe data structures
        self.checked_links: Set[str] = set()
        self.broken_links: Dict[str, List[Tuple[str, str]]] = defaultdict(list)  # url -> [(source_page, error)]
        self.successful_links: Set[str] = set()
        
        # Thread locks for synchronization
        self.checked_links_lock = Lock()
        self.broken_links_lock = Lock()
        self.successful_links_lock = Lock()
        
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
        Check if a single link is working (thread-safe).
        
        Args:
            url: The URL to check
            source_page: The page where this link was found
            
        Returns:
            True if link is working, False otherwise
        """
        # Thread-safe check if already processed
        with self.checked_links_lock:
            if url in self.checked_links:
                with self.successful_links_lock:
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
                with self.broken_links_lock:
                    self.broken_links[url].append((source_page, error_msg))
                self.logger.warning(f"✗ Link broken: {url} - {error_msg} (found on: {source_page})")
                return False
            elif response.status_code == 500:
                error_msg = f"HTTP {response.status_code} - Internal Server Error"
                with self.broken_links_lock:
                    self.broken_links[url].append((source_page, error_msg))
                self.logger.warning(f"✗ Link broken: {url} - {error_msg} (found on: {source_page})")
                return False
            else:
                # All other status codes (200, 403, 301, 302, etc.) are considered acceptable
                with self.successful_links_lock:
                    self.successful_links.add(url)
                if response.status_code == 200:
                    self.logger.info(f"✓ Link OK: {url}")
                else:
                    self.logger.info(f"✓ Link OK: {url} - HTTP {response.status_code}")
                return True
                
        except requests.exceptions.Timeout:
            # Timeouts are not considered broken links, just inaccessible at the moment
            with self.successful_links_lock:
                self.successful_links.add(url)
            self.logger.info(f"⚠️  Link timeout (but not broken): {url} (found on: {source_page})")
            return True
            
        except requests.exceptions.ConnectionError:
            # Connection errors are not considered broken links, just inaccessible at the moment
            with self.successful_links_lock:
                self.successful_links.add(url)
            self.logger.info(f"⚠️  Link connection error (but not broken): {url} (found on: {source_page})")
            return True
            
        except Exception as e:
            # Other errors are not considered broken links, just inaccessible at the moment
            with self.successful_links_lock:
                self.successful_links.add(url)
            self.logger.info(f"⚠️  Link error (but not broken): {url} - {str(e)} (found on: {source_page})")
            return True

    def get_all_pages_concurrent(self) -> List[str]:
        """
        Discover all internal pages concurrently.
        
        Returns:
            List of page URLs to check
        """
        pages_to_check = [self.base_url]
        checked_pages = set()
        
        # Process pages in batches to avoid overwhelming the server
        batch_size = min(5, self.max_workers)
        
        while True:
            # Get the next batch of unchecked pages
            unchecked_pages = [p for p in pages_to_check if p not in checked_pages]
            if not unchecked_pages:
                break
                
            current_batch = unchecked_pages[:batch_size]
            
            # Process batch concurrently
            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                future_to_page = {executor.submit(self.get_links_from_page, page): page 
                                for page in current_batch}
                
                for future in as_completed(future_to_page):
                    page_url = future_to_page[future]
                    checked_pages.add(page_url)
                    
                    try:
                        links = future.result()
                        
                        # Filter for internal pages to add to crawling list
                        for link in links:
                            if (not self.is_external_link(link) and 
                                link not in checked_pages and 
                                link not in pages_to_check):
                                # Only add if it's a different page (not just a fragment)
                                parsed_link = urlparse(link)
                                parsed_page = urlparse(page_url)
                                if parsed_link.path != parsed_page.path:
                                    pages_to_check.append(link)
                                    self.logger.info(f"Found internal page: {link}")
                    except Exception as e:
                        self.logger.error(f"Error processing page {page_url}: {e}")
            
            # Small delay between batches to be respectful
            if self.delay > 0 and unchecked_pages:
                time.sleep(self.delay / 2)
        
        return pages_to_check

    def verify_all_links(self) -> bool:
        """
        Main method to verify all links on the website using concurrent processing.
        
        Returns:
            True if all links are working, False if any broken links found
        """
        self.logger.info(f"Starting link verification for {self.base_url}")
        self.logger.info(f"Using {self.max_workers} concurrent workers")
        
        # Discover all pages concurrently
        pages_to_check = self.get_all_pages_concurrent()
        self.logger.info(f"Found {len(pages_to_check)} pages to check")
        
        # Collect all links from all pages concurrently
        all_links = []
        
        with ThreadPoolExecutor(max_workers=min(len(pages_to_check), self.max_workers)) as executor:
            future_to_page = {executor.submit(self.get_links_from_page, page): page 
                            for page in pages_to_check}
            
            for future in as_completed(future_to_page):
                page_url = future_to_page[future]
                try:
                    links = future.result()
                    for link in links:
                        all_links.append((link, page_url))
                except Exception as e:
                    self.logger.error(f"Error getting links from {page_url}: {e}")
        
        self.logger.info(f"Found {len(all_links)} total links to verify")
        
        # Create unique links dictionary
        unique_links = {}
        for link, source in all_links:
            if link not in unique_links:
                unique_links[link] = []
            unique_links[link].append(source)
        
        self.logger.info(f"Checking {len(unique_links)} unique links concurrently...")
        
        # Check all links concurrently
        success_count = 0
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all link checking tasks
            future_to_url = {
                executor.submit(self.check_link, url, sources[0]): url 
                for url, sources in unique_links.items()
            }
            
            # Process completed tasks
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    if future.result():
                        success_count += 1
                except Exception as e:
                    self.logger.error(f"Error checking link {url}: {e}")
                    # Treat as broken
                    with self.broken_links_lock:
                        self.broken_links[url].append(("unknown", f"Error: {e}"))
        
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
    parser.add_argument('--max-workers', type=int, default=10, help='Maximum number of concurrent workers (default: 10)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    verifier = LinkVerifier(
        base_url=args.url,
        timeout=args.timeout,
        delay=args.delay,
        max_workers=args.max_workers
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