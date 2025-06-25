# llm-d Docs Link Verifier

A Python application that verifies all links on the [llm-d.ai](https://llm-d.ai) website to ensure there are no broken links (only HTTP 404 Not Found and HTTP 500 Internal Server Error are considered broken). This tool can be run locally or as a daily GitHub Action.

## Features

- 🔍 **Comprehensive Link Discovery**: Crawls the entire llm-d.ai website to find all internal and external links
- 🌐 **Smart Link Checking**: Uses efficient HEAD requests first, falling back to GET requests when needed
- ⚡ **Rate Limiting**: Configurable delays between requests to be respectful to servers
- 📊 **Detailed Reporting**: Provides comprehensive reports of broken links (HTTP 404/500 only) with source pages and error details
- 🤖 **GitHub Actions Integration**: Automated daily checks with issue creation on failure
- 🔧 **Configurable**: Customizable timeouts, delays, and target URLs

## Quick Start

### Local Usage

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the link verifier:**
   ```bash
   python link_verifier.py
   ```

3. **With custom options:**
   ```bash
   python link_verifier.py --url https://llm-d.ai --timeout 30 --delay 1.0 --verbose
   ```

### GitHub Actions (Automated)

The repository includes a GitHub Actions workflow that runs daily at 9:00 AM UTC. The workflow:

1. ✅ Checks out the repository
2. 🐍 Sets up Python 3.11
3. 📦 Installs dependencies
4. 🔍 Runs the link verification
5. 🐛 Creates an issue if broken links are found

To enable the workflow:
1. Push this repository to GitHub
2. The workflow will automatically run daily
3. You can also trigger it manually from the Actions tab

## Command Line Options

```bash
python link_verifier.py [OPTIONS]

Options:
  --url TEXT        Base URL to check (default: https://llm-d.ai)
  --timeout INT     Timeout for HTTP requests in seconds (default: 30)
  --delay FLOAT     Delay between requests in seconds (default: 1.0)
  --verbose, -v     Enable verbose logging
  --help           Show this message and exit
```

## Link Status Code Handling

The link verifier treats different HTTP status codes as follows:

### ❌ **Broken Links (Reported as Errors)**
- **HTTP 404** - Not Found
- **HTTP 500** - Internal Server Error

### ✅ **Acceptable Links (Not Reported as Errors)**
- **HTTP 200** - OK
- **HTTP 403** - Forbidden (access restricted but link exists)
- **HTTP 301/302** - Redirects (followed automatically)
- **HTTP 999** - LinkedIn anti-bot response
- **Connection timeouts** - Treated as temporary issues
- **Connection errors** - Treated as temporary issues
- **All other HTTP status codes**

This focused approach reduces false positives from sites that restrict access (like social media platforms) while still catching genuinely broken links.

## How It Works

### 1. Page Discovery
The verifier starts from the base URL (https://llm-d.ai) and:
- Parses the HTML to find all anchor tags (`<a href="...">`)
- Identifies internal pages for further crawling
- Builds a comprehensive list of all pages on the site

### 2. Link Extraction
For each discovered page, the tool:
- Extracts all links (both internal and external)
- Normalizes URLs (resolves relative paths, handles fragments)
- Removes duplicates and invalid links (mailto:, tel:)

### 3. Link Verification
Each unique link is checked by:
- First attempting a HEAD request (more efficient)
- Falling back to GET request if HEAD fails
- Following redirects automatically
- Recording response status codes and error details

### 4. Reporting
The tool provides:
- Real-time logging of progress
- Summary statistics (total links, successful, broken)
- Detailed breakdown of broken links with source pages
- Appropriate exit codes for CI/CD integration

## Sample Output

```
2024-01-15 09:00:01 - INFO - Starting link verification for https://llm-d.ai
2024-01-15 09:00:02 - INFO - Fetching page: https://llm-d.ai
2024-01-15 09:00:02 - INFO - Found internal page: https://llm-d.ai/docs
2024-01-15 09:00:03 - INFO - Found 15 pages to check
2024-01-15 09:00:05 - INFO - Found 47 total links to verify
2024-01-15 09:00:06 - INFO - ✓ Link OK: https://llm-d.ai/docs/installation
2024-01-15 09:00:07 - INFO - ✓ Link OK: https://x.com/example - HTTP 403
2024-01-15 09:00:08 - WARNING - ✗ Link broken: https://llm-d.ai/missing-page - HTTP 404 - Not Found (found on: https://llm-d.ai)

============================================================
LINK VERIFICATION RESULTS
============================================================
Total links checked: 47
Successful links: 46
Broken links: 1

============================================================
BROKEN LINKS FOUND (HTTP 404 & 500 ONLY):
============================================================

❌ BROKEN LINK: https://llm-d.ai/missing-page
   📄 Found on page: https://llm-d.ai
   💥 Error: HTTP 404 - Not Found
```

## GitHub Actions Workflow Details

The daily workflow (`.github/workflows/daily-link-check.yml`) includes:

- **Scheduled Run**: Daily at 9:00 AM UTC
- **Manual Trigger**: Can be run on-demand via GitHub UI
- **Failure Handling**: Automatically creates GitHub issues when broken links are detected
- **Issue Management**: Prevents duplicate issues for the same day

### Workflow Permissions

The workflow requires the following permissions:
- `contents: read` - To checkout the repository
- `issues: write` - To create issues on failure

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test locally with `python link_verifier.py --verbose`
5. Submit a pull request

## Configuration

### Environment Variables
- `GITHUB_TOKEN`: Automatically provided by GitHub Actions for issue creation

### Customization
You can customize the link verification by modifying:
- `timeout`: HTTP request timeout in seconds
- `delay`: Delay between requests to be respectful to servers
- `base_url`: Target website to verify (defaults to https://llm-d.ai)

## Troubleshooting

### Common Issues

1. **Rate Limiting**: If you encounter rate limiting, increase the `--delay` parameter
2. **Timeouts**: For slow connections, increase the `--timeout` parameter
3. **False Positives**: Some sites may block HEAD requests; the tool automatically falls back to GET

### Debugging

Run with verbose logging to see detailed information:
```bash
python link_verifier.py --verbose
```

## License

This project is open source and available under the MIT License.

## Support

For issues or questions:
1. Check the GitHub Issues tab
2. Review the workflow logs in GitHub Actions
3. Run locally with `--verbose` for detailed debugging information

---

**Note**: This tool is designed specifically for verifying links on [llm-d.ai](https://llm-d.ai) but can be adapted for other websites by changing the `--url` parameter. 