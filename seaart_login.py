"""
SeaArt.ai Session Saver - Login Helper

PURPOSE:
- Authenticate with SeaArt.ai and save session for future use
- Uses real Chrome via CDP (Chrome DevTools Protocol) to bypass automation detection
- Saves session to seaart_session.json

WHEN TO RUN:
- First time setup
- When session expires
- If you see login pages when running pipeline scripts

OUTPUT:
- seaart_session.json (saved browser session with cookies + localStorage)
- Chrome profile in temp folder for session persistence

WORKFLOW POSITION:
[1] Login → [2] Run Pipeline
"""
import asyncio
import json
import sys
import io
import subprocess
import platform
from pathlib import Path
from playwright.async_api import async_playwright

# Fix console encoding
if sys.platform == 'win32':
    try:
        if not hasattr(sys.stdout, '_wrapped_for_utf8'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
            sys.stdout._wrapped_for_utf8 = True
            sys.stderr._wrapped_for_utf8 = True
    except (AttributeError, ValueError):
        pass

SESSION_FILE = Path(__file__).parent / "seaart_session.json"
SEAART_URL = "https://www.seaart.ai"
DEBUG_PORT = 9224  # Different port from Grok (9222) and TensorPix (9223)


def get_chrome_path():
    """Find Chrome executable"""
    chrome_paths = {
        'windows': [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
        ],
        'darwin': [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ],
        'linux': [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/snap/bin/chromium",
        ]
    }
    
    os_name = platform.system().lower()
    for path in chrome_paths.get(os_name, []):
        if isinstance(path, Path):
            if path.exists():
                return str(path)
        elif Path(path).exists():
            return path
    
    return None


def get_temp_dir():
    """Get temp directory for Chrome profile"""
    if platform.system() == 'Windows':
        return Path.home() / "AppData" / "Local" / "Temp" / "chrome_seaart_login"
    else:
        return Path.home() / ".cache" / "chrome_seaart_login"


async def start_chrome_with_debugging():
    """Start real Chrome with remote debugging enabled"""
    chrome_path = get_chrome_path()
    
    if not chrome_path:
        print("❌ ERROR: Chrome not found. Please install Google Chrome.")
        return False
    
    temp_dir = get_temp_dir()
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    chrome_args = [
        chrome_path,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={temp_dir}",
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        SEAART_URL,
    ]
    
    print(f"🌐 Starting Chrome with debugging port {DEBUG_PORT}...")
    print(f"   Chrome: {chrome_path}")
    print(f"   Profile: {temp_dir}")
    
    try:
        # Platform-specific process creation
        if platform.system() == 'Windows':
            subprocess.Popen(
                chrome_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        else:
            subprocess.Popen(
                chrome_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        
        # Wait for Chrome to start and CDP to be ready
        print("   Waiting for Chrome to initialize...")
        await asyncio.sleep(5)
        
        # Verify CDP is ready
        import urllib.request
        for i in range(10):
            try:
                urllib.request.urlopen(f"http://localhost:{DEBUG_PORT}/json", timeout=1)
                print("   ✅ Chrome CDP is ready!")
                return True
            except:
                await asyncio.sleep(1)
        
        print("   ⚠️  Could not verify CDP, but continuing anyway...")
        return True
    except Exception as e:
        print(f"❌ ERROR: Failed to start Chrome: {e}")
        return False


async def main():
    print("=" * 70)
    print("🎨 SeaArt.ai Login Helper - Using REAL Chrome")
    print("=" * 70)
    print()
    print("This will:")
    print("  1. Start your REAL Chrome browser (not automated)")
    print("  2. Connect to it via Chrome DevTools Protocol")
    print("  3. Navigate to SeaArt.ai")
    print("  4. Wait 90 seconds for you to login")
    print("  5. Save your session automatically")
    print()
    print("SeaArt won't detect this as automation! ✅")
    print()
    
    playwright = None
    browser = None
    context = None
    
    try:
        # Start real Chrome
        if not await start_chrome_with_debugging():
            return
        
        # Connect to Chrome via CDP
        print("🔌 Connecting to Chrome...")
        playwright = await async_playwright().start()
        
        try:
            browser = await playwright.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
            contexts = browser.contexts
            if contexts:
                context = contexts[0]
                pages = context.pages
                if pages:
                    page = pages[0]
                else:
                    page = await context.new_page()
            else:
                context = await browser.new_context()
                page = await context.new_page()
            
            print("✅ Connected to Chrome!")
            
            # Navigate to SeaArt if not already there
            current_url = page.url
            if "seaart.ai" not in current_url.lower():
                print(f"📱 Navigating to {SEAART_URL}...")
                await page.goto(SEAART_URL, wait_until="networkidle", timeout=60000)
            else:
                print(f"📍 Already on SeaArt: {current_url}")
            
            print()
            print("=" * 70)
            print("⏳ WAITING 90 SECONDS FOR YOU TO LOGIN")
            print("=" * 70)
            print()
            print("Please login to SeaArt.ai in the Chrome window.")
            print("You can login with Google, Discord, or email.")
            print()
            print("Counting down:")
            
            # Countdown with updates - check login status
            for i in range(90, 0, -10):
                try:
                    current_url = page.url
                    # Check if we're on a logged-in page (not login page)
                    if "login" not in current_url.lower() and "signin" not in current_url.lower():
                        print(f"  ⏰ {i} seconds remaining... (Looks like you might be logged in!)")
                    else:
                        print(f"  ⏰ {i} seconds remaining...")
                except:
                    print(f"  ⏰ {i} seconds remaining...")
                await asyncio.sleep(10)
            
            print()
            print("⏱️  Time's up! Saving session...")
            
            # Verify we're logged in
            current_url = page.url
            print(f"📍 Current URL: {current_url}")
            
            # Wait a bit more to ensure all cookies are set
            print("   Waiting for all cookies to be set...")
            await asyncio.sleep(3)
            
            # Save browser state
            print("\n💾 Saving session...")
            storage_state = await context.storage_state()
            
            with open(SESSION_FILE, 'w') as f:
                json.dump(storage_state, f, indent=2)
            
            cookie_count = len(storage_state.get('cookies', []))
            origin_count = len(storage_state.get('origins', []))
            
            print(f"✅ Session saved to: {SESSION_FILE}")
            print(f"   Cookies: {cookie_count}")
            print(f"   Origins with localStorage: {origin_count}")
            
            # Check if actually logged in
            seaart_cookies = [c for c in storage_state.get('cookies', []) if 'seaart' in c.get('domain', '').lower()]
            print(f"   SeaArt cookies: {len(seaart_cookies)}")
            
            if len(seaart_cookies) < 3:
                print("\n⚠️  WARNING: Few SeaArt cookies found!")
                print("   You may not be fully logged in.")
                print("   Try running this script again and complete the login.")
            else:
                print("\n✅ Appears to be logged in!")
            
            print()
            print("=" * 70)
            print("✅ SUCCESS!")
            print("=" * 70)
            print()
            print("Your session has been saved!")
            print("The pipeline scripts will now use this session automatically.")
            print()
            print("Chrome will stay open. You can close it manually.")
            print("Press Ctrl+C to close this script.")
            print()
            
            # Keep connection alive
            await asyncio.Event().wait()
            
        except Exception as e:
            print(f"❌ Error connecting to Chrome: {e}")
            print()
            print("Make sure Chrome started successfully.")
            print("You can also start Chrome manually with:")
            print(f'   chrome --remote-debugging-port={DEBUG_PORT} --user-data-dir="{get_temp_dir()}"')
            import traceback
            traceback.print_exc()
            
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user...")
        # Still try to save session
        try:
            if context:
                print("💾 Saving session before closing...")
                storage_state = await context.storage_state()
                with open(SESSION_FILE, 'w') as f:
                    json.dump(storage_state, f, indent=2)
                print("✅ Session saved!")
        except Exception as e:
            print(f"⚠️  Could not save session: {e}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if playwright:
            await playwright.stop()
        print("✅ Done! Chrome will stay open.")


if __name__ == "__main__":
    asyncio.run(main())

