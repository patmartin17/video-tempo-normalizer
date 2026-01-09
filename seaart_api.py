"""
SeaArt.ai API Wrapper

Provides functions to interact with SeaArt.ai's internal API:
- Upload videos
- Run AI apps (frame interpolation, VHS synthesis)
- Poll task progress
- HD upscale videos
- Download results

Requires a saved session from seaart_login.py
"""
import asyncio
import json
import sys
import io
import uuid
import subprocess
import platform
import requests
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

# Constants
SESSION_FILE = Path(__file__).parent / "seaart_session.json"
SEAART_URL = "https://www.seaart.ai"
DEBUG_PORT = 9224

# App IDs discovered from HAR
INTERPOLATION_APP_ID = "d3hrfgte878c73e722pg"  # AI Frame Interpolation
VHS_SYNTHESIS_APP_ID = "d5fu2ele878c73d3jmi0"  # VHS Video Synthesis


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


def get_request_headers(page_url="https://www.seaart.ai"):
    """Generate required headers for SeaArt API calls"""
    return {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'Origin': 'https://www.seaart.ai',
        'Referer': page_url,
        'x-app-id': 'web_global_seaart',
        'x-browser-id': str(uuid.uuid4()).replace('-', '')[:32],
        'x-device-id': str(uuid.uuid4()),
        'x-eyes': 'true',
        'x-gray-tag': str(uuid.uuid4()),
        'x-page-id': str(uuid.uuid4()),
        'x-platform': 'web',
        'x-request-id': str(uuid.uuid4()),
        'x-timezone': 'UTC',
    }


class SeaArtAPI:
    """SeaArt.ai API client using browser session"""
    
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.storage_state = None
        self._connected = False
    
    async def connect(self):
        """Connect to Chrome via CDP or start new instance"""
        if self._connected:
            return True
        
        # Load session
        if not SESSION_FILE.exists():
            print(f"❌ Session file not found: {SESSION_FILE}")
            print("   Please run seaart_login.py first!")
            return False
        
        with open(SESSION_FILE, 'r') as f:
            self.storage_state = json.load(f)
        
        self.playwright = await async_playwright().start()
        
        # Try to connect to existing Chrome
        try:
            self.browser = await self.playwright.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
            print("✅ Connected to existing Chrome instance")
        except Exception:
            print("🌐 Starting Chrome with debugging...")
            chrome_path = get_chrome_path()
            if not chrome_path:
                print("❌ Chrome not found!")
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
            
            if platform.system() == 'Windows':
                subprocess.Popen(chrome_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                subprocess.Popen(chrome_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            await asyncio.sleep(5)
            
            # Connect
            for i in range(5):
                try:
                    self.browser = await self.playwright.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
                    print("✅ Connected to Chrome!")
                    break
                except Exception:
                    if i < 4:
                        await asyncio.sleep(2)
                    else:
                        print("❌ Failed to connect to Chrome")
                        return False
        
        # Get or create context
        contexts = self.browser.contexts
        if contexts:
            self.context = contexts[0]
        else:
            self.context = await self.browser.new_context()
        
        # Get or create page
        pages = self.context.pages
        if pages:
            self.page = pages[0]
        else:
            self.page = await self.context.new_page()
        
        # Apply session (cookies and localStorage)
        await self._apply_session()
        
        # Navigate to SeaArt
        print("🌐 Navigating to SeaArt.ai...")
        await self.page.goto(SEAART_URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2)
        
        self._connected = True
        return True
    
    async def _apply_session(self):
        """Apply saved session (cookies and localStorage)"""
        # Apply cookies
        cookies = self.storage_state.get('cookies', [])
        if cookies:
            seaart_cookies = [c for c in cookies if 'seaart' in c.get('domain', '').lower()]
            if seaart_cookies:
                await self.context.add_cookies(seaart_cookies)
                print(f"✅ Applied {len(seaart_cookies)} SeaArt cookies")
        
        # Apply localStorage after navigating to domain
        # Will be done after page load
    
    async def _apply_localstorage(self):
        """Apply localStorage from saved session"""
        if 'origins' in self.storage_state:
            for origin_data in self.storage_state['origins']:
                if 'seaart' in origin_data.get('origin', '').lower() and 'localStorage' in origin_data:
                    await self.page.evaluate("""
                        (items) => {
                            items.forEach(item => {
                                localStorage.setItem(item.name, item.value);
                            });
                        }
                    """, origin_data['localStorage'])
                    print(f"✅ Applied localStorage items")
                    break
    
    async def upload_video(self, video_path):
        """
        Upload a video file to SeaArt.
        
        Args:
            video_path: Path to the video file
            
        Returns:
            Video URL on SeaArt CDN, or None if failed
        """
        video_path = Path(video_path)
        if not video_path.exists():
            print(f"❌ Video file not found: {video_path}")
            return None
        
        print(f"\n📤 Uploading video: {video_path.name}")
        print(f"   Size: {video_path.stat().st_size / 1024 / 1024:.2f} MB")
        
        # Read video file
        with open(video_path, 'rb') as f:
            video_data = f.read()
        
        # Step 1: Get presigned URL
        print("   Step 1: Getting presigned upload URL...")
        
        headers = get_request_headers(self.page.url)
        
        presign_result = await self.page.evaluate("""
            async (args) => {
                const { fileName, fileSize, headers } = args;
                try {
                    const response = await fetch('https://www.seaart.ai/api/v1/resource/pre-sign/get', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            ...headers
                        },
                        credentials: 'include',
                        body: JSON.stringify({
                            file_size: fileSize,
                            file_name: fileName,
                            content_type: 'application/octet-stream',
                            category: 20
                        })
                    });
                    
                    if (!response.ok) {
                        return { error: `HTTP ${response.status}: ${await response.text()}` };
                    }
                    
                    return await response.json();
                } catch (error) {
                    return { error: error.message };
                }
            }
        """, {
            "fileName": f"{uuid.uuid4()}.mp4",
            "fileSize": len(video_data),
            "headers": headers
        })
        
        if 'error' in presign_result:
            print(f"❌ Failed to get presigned URL: {presign_result['error']}")
            return None
        
        if presign_result.get('status', {}).get('code') != 10000:
            print(f"❌ Presign failed: {presign_result}")
            return None
        
        data = presign_result.get('data', {})
        file_id = data.get('file_id')
        pre_signs = data.get('pre_signs', [])
        
        if not pre_signs:
            print(f"❌ No presigned URLs returned")
            return None
        
        presigned_url = pre_signs[0]
        print(f"   ✅ Got presigned URL (file_id: {file_id})")
        
        # Step 2: Upload to Google Cloud Storage
        print("   Step 2: Uploading to cloud storage...")
        
        try:
            upload_response = requests.put(
                presigned_url,
                data=video_data,
                headers={
                    'Content-Type': 'application/octet-stream',
                    'Content-Length': str(len(video_data))
                },
                timeout=300
            )
            
            if upload_response.status_code not in [200, 204]:
                print(f"❌ Upload failed: {upload_response.status_code}")
                return None
            
            print("   ✅ Uploaded to cloud storage")
        except Exception as e:
            print(f"❌ Upload error: {e}")
            return None
        
        # Step 3: Confirm upload complete
        print("   Step 3: Confirming upload...")
        
        confirm_result = await self.page.evaluate("""
            async (args) => {
                const { fileId, presignUrl, headers } = args;
                try {
                    const response = await fetch('https://www.seaart.ai/api/v1/resource/pre-sign/upload-complete', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            ...headers
                        },
                        credentials: 'include',
                        body: JSON.stringify({
                            file_id: fileId,
                            pre_sign_url: presignUrl
                        })
                    });
                    
                    if (!response.ok) {
                        return { error: `HTTP ${response.status}: ${await response.text()}` };
                    }
                    
                    return await response.json();
                } catch (error) {
                    return { error: error.message };
                }
            }
        """, {
            "fileId": file_id,
            "presignUrl": presigned_url,
            "headers": headers
        })
        
        if 'error' in confirm_result:
            print(f"❌ Confirm failed: {confirm_result['error']}")
            return None
        
        video_url = confirm_result.get('data', {}).get('url')
        if video_url:
            print(f"   ✅ Upload confirmed!")
            print(f"   📍 URL: {video_url}")
            return video_url
        else:
            print(f"❌ No URL in confirm response: {confirm_result}")
            return None
    
    async def run_interpolation(self, video_url, target_fps=60, multiplier=2):
        """
        Run AI Frame Interpolation on a video.
        
        Args:
            video_url: URL of the video on SeaArt CDN
            target_fps: Target frame rate (default 60)
            multiplier: Frame multiplier (default 2)
            
        Returns:
            task_id if successful, None otherwise
        """
        print(f"\n🎬 Starting Frame Interpolation...")
        print(f"   Video: {video_url[:60]}...")
        print(f"   Target FPS: {target_fps}, Multiplier: {multiplier}x")
        
        headers = get_request_headers(f"{SEAART_URL}/create/ai-app?id={INTERPOLATION_APP_ID}")
        
        result = await self.page.evaluate("""
            async (args) => {
                const { applyId, videoUrl, multiplier, targetFps, headers } = args;
                try {
                    const response = await fetch('https://www.seaart.ai/api/v1/creativity/generate/apply', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            ...headers
                        },
                        credentials: 'include',
                        body: JSON.stringify({
                            apply_id: applyId,
                            inputs: [
                                { field: "video", node_id: "1", node_type: "VHS_LoadVideo", val: videoUrl },
                                { field: "Number", node_id: "33", node_type: "Int", val: String(multiplier) },
                                { field: "Number", node_id: "16", node_type: "Float", val: String(targetFps) }
                            ],
                            is_use_unlimited_free: false,
                            task_flow_version: "v2",
                            ss: 52
                        })
                    });
                    
                    if (!response.ok) {
                        return { error: `HTTP ${response.status}: ${await response.text()}` };
                    }
                    
                    return await response.json();
                } catch (error) {
                    return { error: error.message };
                }
            }
        """, {
            "applyId": INTERPOLATION_APP_ID,
            "videoUrl": video_url,
            "multiplier": multiplier,
            "targetFps": target_fps,
            "headers": headers
        })
        
        if 'error' in result:
            print(f"❌ Interpolation request failed: {result['error']}")
            return None
        
        if result.get('status', {}).get('code') != 10000:
            print(f"❌ Interpolation failed: {result}")
            return None
        
        task_id = result.get('data', {}).get('id')
        if task_id:
            print(f"   ✅ Task created: {task_id}")
            return task_id
        else:
            print(f"❌ No task_id in response: {result}")
            return None
    
    async def run_hd_upscale(self, video_url, parent_task_id, artwork_id, width=464, height=688, duration=4):
        """
        Run HD upscale on a video.
        
        Args:
            video_url: URL of the video to upscale
            parent_task_id: Task ID from previous operation
            artwork_id: Artwork ID from previous operation
            width, height: Video dimensions
            duration: Video duration in seconds
            
        Returns:
            task_id if successful, None otherwise
        """
        print(f"\n🔍 Starting HD Upscale...")
        print(f"   Video: {video_url[:60]}...")
        
        headers = get_request_headers(f"{SEAART_URL}/create/ai-app?id={VHS_SYNTHESIS_APP_ID}")
        
        result = await self.page.evaluate("""
            async (args) => {
                const { videoUrl, parentTaskId, artworkId, width, height, duration, headers } = args;
                try {
                    const response = await fetch('https://www.seaart.ai/api/v1/task/v2/video/upscale', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            ...headers
                        },
                        credentials: 'include',
                        body: JSON.stringify({
                            parent_task_id: parentTaskId,
                            model_no: "",
                            model_ver_no: "",
                            meta: {
                                extra_prompt: "",
                                prompt: "",
                                local_prompt: "",
                                width: width,
                                height: height,
                                steps: 0,
                                init_images: null,
                                seed: 0,
                                lora_models: null,
                                hi_res_arg: null,
                                smart_edit: null,
                                guidance_scale: 0,
                                left_margin: 0,
                                up_margin: 0,
                                image: "",
                                images: [videoUrl],
                                vae: "None",
                                refiner_mode: 0,
                                lcm_mode: 0,
                                embeddings: null,
                                generate: { anime_enhance: 0, mode: 0, gen_mode: 0, prompt_magic_mode: 0 },
                                comfyui_inputs: [
                                    { node_id: "1", node_type: "VHS_LoadVideo", field: "video", val: videoUrl, type: 0, extra_data: null }
                                ],
                                generate_video: {
                                    video_url: videoUrl,
                                    generate_video_duration: duration
                                }
                            },
                            pre_task_id: parentTaskId,
                            pre_art_work_id: artworkId,
                            task_uri_index: 0
                        })
                    });
                    
                    if (!response.ok) {
                        return { error: `HTTP ${response.status}: ${await response.text()}` };
                    }
                    
                    return await response.json();
                } catch (error) {
                    return { error: error.message };
                }
            }
        """, {
            "videoUrl": video_url,
            "parentTaskId": parent_task_id,
            "artworkId": artwork_id,
            "width": width,
            "height": height,
            "duration": duration,
            "headers": headers
        })
        
        if 'error' in result:
            print(f"❌ HD Upscale request failed: {result['error']}")
            return None
        
        if result.get('status', {}).get('code') != 10000:
            print(f"❌ HD Upscale failed: {result}")
            return None
        
        task_id = result.get('data', {}).get('id')
        if task_id:
            print(f"   ✅ Task created: {task_id}")
            return task_id
        else:
            print(f"❌ No task_id in response: {result}")
            return None
    
    async def poll_task(self, task_id, max_wait_minutes=30, poll_interval=5):
        """
        Poll task status until completion.
        
        Args:
            task_id: Task ID to poll
            max_wait_minutes: Maximum wait time
            poll_interval: Seconds between polls
            
        Returns:
            Dict with task result including video URL, or None if failed
        """
        print(f"\n⏳ Polling task: {task_id}")
        
        headers = get_request_headers(self.page.url)
        start_time = asyncio.get_event_loop().time()
        max_wait_seconds = max_wait_minutes * 60
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            
            if elapsed > max_wait_seconds:
                print(f"\n❌ Timeout: Task did not complete within {max_wait_minutes} minutes")
                return None
            
            result = await self.page.evaluate("""
                async (args) => {
                    const { taskIds, headers } = args;
                    try {
                        const response = await fetch('https://www.seaart.ai/api/v1/task/batch-progress', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                ...headers
                            },
                            credentials: 'include',
                            body: JSON.stringify({ task_ids: taskIds })
                        });
                        
                        if (!response.ok) {
                            return { error: `HTTP ${response.status}: ${await response.text()}` };
                        }
                        
                        return await response.json();
                    } catch (error) {
                        return { error: error.message };
                    }
                }
            """, {
                "taskIds": [task_id],
                "headers": headers
            })
            
            if 'error' in result:
                print(f"\n⚠️  Poll error: {result['error']}")
                await asyncio.sleep(poll_interval)
                continue
            
            items = result.get('data', {}).get('items', [])
            if not items:
                await asyncio.sleep(poll_interval)
                continue
            
            task = items[0]
            status = task.get('status', 0)
            status_desc = task.get('status_desc', 'unknown')
            process = task.get('process', 0)
            
            # Status: 1=waiting, 2=processing, 3=finish
            print(f"\r   Status: {status_desc} | Progress: {process}%", end='', flush=True)
            
            if status == 3:  # Finished
                print(f"\n   ✅ Task completed!")
                
                # Extract result
                img_uris = task.get('img_uris', [])
                artwork_nos = task.get('pub_artwork_nos', [])
                
                if img_uris:
                    video_info = img_uris[0]
                    return {
                        'task_id': task_id,
                        'video_url': video_info.get('url'),
                        'cover_url': video_info.get('cover_url'),
                        'width': video_info.get('width'),
                        'height': video_info.get('height'),
                        'duration': video_info.get('duration'),
                        'artwork_id': artwork_nos[0] if artwork_nos else video_info.get('artwork_no')
                    }
                else:
                    print(f"⚠️  Task finished but no output found")
                    return {'task_id': task_id, 'status': 'finished_no_output'}
            
            elif status == 4:  # Failed
                reason = task.get('reason', 'Unknown')
                print(f"\n❌ Task failed: {reason}")
                return None
            
            await asyncio.sleep(poll_interval)
    
    async def download_video(self, video_url, output_path):
        """
        Download a video from SeaArt CDN.
        
        Args:
            video_url: URL of the video
            output_path: Where to save the video
            
        Returns:
            Path to downloaded file, or None if failed
        """
        print(f"\n📥 Downloading video...")
        print(f"   From: {video_url[:60]}...")
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            response = requests.get(video_url, stream=True, timeout=300)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = int(downloaded * 100 / total_size)
                            print(f"\r   Downloading: {percent}% ({downloaded/1024/1024:.1f} MB)", end='', flush=True)
            
            print(f"\n   ✅ Saved to: {output_path}")
            print(f"   Size: {output_path.stat().st_size / 1024 / 1024:.2f} MB")
            return output_path
        except Exception as e:
            print(f"\n❌ Download failed: {e}")
            return None
    
    async def close(self):
        """Close browser and cleanup"""
        print("\n🔒 Closing browser...")
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            print("✅ Browser closed")
        except Exception as e:
            print(f"⚠️  Error closing browser: {e}")
        self._connected = False


# Convenience function for standalone use
async def test_api():
    """Test the API with a sample video"""
    api = SeaArtAPI()
    
    try:
        if not await api.connect():
            return
        
        print("\n✅ API connected successfully!")
        print("   Ready to process videos.")
        
        # Keep alive for testing
        input("\nPress Enter to close...")
        
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(test_api())

