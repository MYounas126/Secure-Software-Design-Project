import argparse
import sys
import logging
import os
import chardet
import re
from CodeReview import gitCode
from CodeReview import CodeReviewAI
from scrapers import scrape_js_sync
import openai
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)

def valid_url(url):
    """Validate the URL format."""
    regex = re.compile(
        r'^(?:http|ftp)s?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|'
        r'\[?[A-F0-9]*:[A-F0-9:]+\]?)'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return re.match(regex, url) is not None

def is_text_file(file_path):
    """Check if a file is likely to be a text file."""
    # Common text file extensions
    text_extensions = [
        '.py', '.txt', '.md', '.html', '.css', '.js', '.json', 
        '.yml', '.yaml', '.csv', '.env', '.sh', '.bat', '.ps1'
    ]
    
    # Skip binary extensions
    binary_extensions = [
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg',
        '.exe', '.dll', '.so', '.zip', '.tar', '.gz', '.pdf', '.bin'
    ]
    
    # Check extensions first
    lower_file = file_path.lower()
    if any(lower_file.endswith(ext) for ext in binary_extensions):
        return False
    if any(lower_file.endswith(ext) for ext in text_extensions):
        return True
    
    # Check file content
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(1024)
            if not chunk:  # Empty file
                return True
            if b'\x00' in chunk:  # Null bytes indicate binary
                return False
            # Check if most characters are printable
            printable = sum(32 <= byte <= 126 or byte in (9, 10, 13) for byte in chunk)
            return (printable / len(chunk)) > 0.7
    except Exception:
        return False

def analyze_files(local_repo_path):
    """Analyze files in the local repository with Windows path handling."""
    if not os.path.exists(local_repo_path):
        logging.error(f"Path does not exist: {local_repo_path}")
        return
    
    for root, dirs, files in os.walk(local_repo_path):
        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for filename in files:
            file_path = os.path.normpath(os.path.join(root, filename))
            
            # Skip binary/hidden files
            if not is_text_file(file_path):
                logging.debug(f"Skipping non-text file: {file_path}")
                continue
                
            try:
                # Read with encoding detection
                with open(file_path, 'rb') as f:
                    raw_content = f.read()
                
                # Detect encoding
                try:
                    result = chardet.detect(raw_content)
                    encoding = result['encoding'] if result['confidence'] > 0.7 else 'utf-8'
                    content = raw_content.decode(encoding, errors='replace')
                    
                    # Process file content
                    logging.info(f"Analyzing: {file_path}")
                    analysis = CodeReviewAI.analyze_file_contents(content, file_path)
                    if analysis:
                        logging.info(f"Analysis results for {file_path}")
                        
                except UnicodeDecodeError as e:
                    logging.warning(f"Decoding failed for {file_path}: {e}")
                    continue
                    
            except PermissionError:
                logging.warning(f"Permission denied for {file_path}")
                continue
            except Exception as e:
                logging.error(f"Error processing {file_path}: {e}")
                continue

def main():
    """Main function with enhanced error handling."""
    parser = argparse.ArgumentParser(
        description="Analyze code from a GitHub repository or a local path.",
        epilog="Example usage:\n  python cli.py --url https://github.com/user/repo\n  python cli.py --path C:\\path\\to\\repo"
    )
    parser.add_argument('--url', type=str, help="GitHub repository URL to analyze")
    parser.add_argument('--path', type=str, help="Local directory path to analyze")
    parser.add_argument('--js', type=str, help="URL to analyze JavaScript")
    parser.add_argument('--recursive', action='store_true', help="Enable recursive JavaScript scraping")
    
    try:
        args = parser.parse_args()
    except SystemExit:
        logging.error("Invalid arguments. Use --help for usage information.")
        sys.exit(1)

    # Validate arguments
    if args.url and not valid_url(args.url):
        logging.error("Invalid URL format")
        sys.exit(1)
    if args.path and not os.path.exists(args.path):
        logging.error(f"Path does not exist: {args.path}")
        sys.exit(1)

    try:
        if args.url:
            logging.info(f"Analyzing repository: {args.url}")
            gitCode.analyze_repository(args.url)
        elif args.path:
            logging.info(f"Analyzing local path: {args.path}")
            analyze_files(args.path)
        elif args.js:
            logging.info(f"Scraping JavaScript: {args.js} (recursive={args.recursive})")
            scrape_js_sync(args.js, args.recursive)
        else:
            parser.print_help()
    except openai.error.InvalidRequestError as e:
        logging.error(f"OpenAI API error: {e}")
    except openai.error.RateLimitError as e:
        logging.error(f"Rate limit exceeded: {e}")
    except KeyboardInterrupt:
        logging.info("Operation cancelled by user")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()