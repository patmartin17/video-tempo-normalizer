"""
SeaArt.ai API Wrapper - Direct HTTP Version

Uses saved cookies to make direct API calls without browser automation.
This bypasses WSL networking issues.
"""
import asyncio
import json
import sys
import io
import uuid
import requests
from pathlib import Path
from urllib.parse import urljoin

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
SEAART_BASE = "https://www.seaart.ai"
API_BASE = "https://www.seaart.ai/api/v1"

# App IDs - these need to be discovered from HAR file
INTERPOLATION_APP_ID = None  # Will get from HAR
VHS_SYNTHESIS_APP_ID = None  # Will get from HAR


class SeaArtAPI:
    """SeaArt.ai API client using direct HTTP requests"""
    
    def __init__(self):
        self.session = requests.Session()
        self.cookies = {}
        self.headers = {}
        self._connected = False
    
    async def connect(self):
        """Load saved session and set up HTTP client"""
        if self._connected:
            return True
        
        # Load session
        if not SESSION_FILE.exists():
            print(f"❌ Session file not found: {SESSION_FILE}")
            print("   Please run seaart_login.py first!")
            return False
        
        with open(SESSION_FILE, 'r') as f:
            storage_state = json.load(f)
        
        # Extract cookies
        for cookie in storage_state.get('cookies', []):
            if 'seaart' in cookie.get('domain', '').lower():
                self.session.cookies.set(
                    cookie['name'],
                    cookie['value'],
                    domain=cookie.get('domain', '.seaart.ai').lstrip('.'),
                    path=cookie.get('path', '/')
                )
        
        # Set up headers
        self.headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/json',
            'Origin': SEAART_BASE,
            'Referer': f'{SEAART_BASE}/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'x-app-id': 'web_global_seaart',
            'x-browser-id': str(uuid.uuid4()).replace('-', '')[:32],
            'x-platform': 'web',
        }
        
        # Test connection by getting user info
        print("🔌 Connecting to SeaArt API...")
        try:
            resp = self.session.get(
                f"{API_BASE}/user/info",
                headers=self.headers,
                timeout=30
            )
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status', {}).get('code') == 10000:
                    user = data.get('data', {})
                    username = user.get('name', 'Unknown')
                    print(f"✅ Connected as: {username}")
                    self._connected = True
                    return True
                else:
                    print(f"⚠️  API returned: {data.get('status', {}).get('msg', 'Unknown error')}")
            else:
                print(f"⚠️  HTTP {resp.status_code}")
                
        except Exception as e:
            print(f"⚠️  Connection test failed: {e}")
        
        # Even if user info fails, we might still be able to use the API
        print("   Proceeding anyway (session may still work)...")
        self._connected = True
        return True
    
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
        
        file_size = video_path.stat().st_size
        print(f"\n📤 Uploading video: {video_path.name}")
        print(f"   Size: {file_size / 1024 / 1024:.2f} MB")
        
        # Step 1: Get presigned URL
        print("   Step 1: Getting presigned upload URL...")
        
        try:
            resp = self.session.post(
                f"{API_BASE}/resource/pre-sign/get",
                headers=self.headers,
                json={
                    "file_size": file_size,
                    "file_name": f"{uuid.uuid4()}.mp4",
                    "content_type": "application/octet-stream",
                    "category": 20
                },
                timeout=30
            )
            
            data = resp.json()
            if data.get('status', {}).get('code') != 10000:
                print(f"❌ Presign failed: {data}")
                return None
            
            file_id = data['data']['file_id']
            presigned_url = data['data']['pre_signs'][0]
            print(f"   ✅ Got presigned URL (file_id: {file_id})")
            
        except Exception as e:
            print(f"❌ Presign error: {e}")
            return None
        
        # Step 2: Upload to cloud storage
        print("   Step 2: Uploading to cloud storage...")
        
        try:
            with open(video_path, 'rb') as f:
                video_data = f.read()
            
            upload_resp = requests.put(
                presigned_url,
                data=video_data,
                headers={
                    'Content-Type': 'application/octet-stream',
                    'Content-Length': str(len(video_data))
                },
                timeout=300
            )
            
            if upload_resp.status_code not in [200, 204]:
                print(f"❌ Upload failed: HTTP {upload_resp.status_code}")
                return None
            
            print("   ✅ Uploaded to cloud storage")
            
        except Exception as e:
            print(f"❌ Upload error: {e}")
            return None
        
        # Step 3: Confirm part upload
        print("   Step 3: Confirming part upload...")
        
        try:
            resp = self.session.post(
                f"{API_BASE}/resource/pre-sign/confirmPart",
                headers=self.headers,
                json={
                    "file_id": file_id,
                    "pre_sign_url": presigned_url
                },
                timeout=30
            )
            
            data = resp.json()
            if data.get('status', {}).get('code') != 10000:
                print(f"❌ ConfirmPart failed: {data}")
                return None
            
            video_url = data['data']['url']
            print(f"   ✅ Part confirmed, URL: {video_url[:60]}...")
            
        except Exception as e:
            print(f"❌ ConfirmPart error: {e}")
            return None
        
        # Step 4: Final confirm
        print("   Step 4: Final confirmation...")
        
        try:
            resp = self.session.post(
                f"{API_BASE}/resource/pre-sign/confirm",
                headers=self.headers,
                json={"file_id": file_id},
                timeout=30
            )
            
            data = resp.json()
            if data.get('status', {}).get('code') != 10000:
                print(f"⚠️  Final confirm returned: {data}")
            
            print(f"   ✅ Upload complete!")
            return video_url
            
        except Exception as e:
            print(f"⚠️  Final confirm error (continuing): {e}")
            return video_url
    
    async def run_interpolation(self, video_url, app_id, target_fps=60, multiplier=2):
        """
        Run AI Frame Interpolation on a video.
        
        Args:
            video_url: URL of the video on SeaArt CDN
            app_id: The AI app ID for frame interpolation
            target_fps: Target frame rate (default 60)
            multiplier: Frame multiplier (default 2)
            
        Returns:
            task_id if successful, None otherwise
        """
        print(f"\n🎬 Starting Frame Interpolation...")
        print(f"   App ID: {app_id}")
        print(f"   Target FPS: {target_fps}, Multiplier: {multiplier}x")
        
        try:
            resp = self.session.post(
                f"{API_BASE}/creativity/generate/apply",
                headers={
                    **self.headers,
                    'Referer': f'{SEAART_BASE}/create/ai-app?id={app_id}'
                },
                json={
                    "apply_id": app_id,
                    "inputs": [
                        {"field": "video", "node_id": "1", "node_type": "VHS_LoadVideo", "val": video_url},
                        {"field": "Number", "node_id": "33", "node_type": "Int", "val": str(multiplier)},
                        {"field": "Number", "node_id": "16", "node_type": "Float", "val": str(target_fps)}
                    ],
                    "is_use_unlimited_free": False,
                    "task_flow_version": "v2",
                    "ss": 52
                },
                timeout=60
            )
            
            data = resp.json()
            if data.get('status', {}).get('code') != 10000:
                print(f"❌ Interpolation failed: {data}")
                return None
            
            task_id = data['data']['id']
            print(f"   ✅ Task created: {task_id}")
            return task_id
            
        except Exception as e:
            print(f"❌ Interpolation error: {e}")
            return None
    
    async def poll_task(self, task_id, max_wait_minutes=30, poll_interval=5):
        """
        Poll task status until completion.
        
        Returns:
            Dict with task result including video URL, or None if failed
        """
        print(f"\n⏳ Polling task: {task_id}")
        
        import time
        start_time = time.time()
        max_wait_seconds = max_wait_minutes * 60
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed > max_wait_seconds:
                print(f"\n❌ Timeout after {max_wait_minutes} minutes")
                return None
            
            try:
                resp = self.session.post(
                    f"{API_BASE}/task/batch-progress",
                    headers=self.headers,
                    json={"task_ids": [task_id]},
                    timeout=30
                )
                
                data = resp.json()
                items = data.get('data', {}).get('items', [])
                
                if not items:
                    await asyncio.sleep(poll_interval)
                    continue
                
                task = items[0]
                status = task.get('status', 0)
                status_desc = task.get('status_desc', 'unknown')
                progress = task.get('process', 0)
                
                print(f"\r   Status: {status_desc} | Progress: {progress}%", end='', flush=True)
                
                if status == 3:  # Finished
                    print(f"\n   ✅ Task completed!")
                    
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
                    return {'task_id': task_id, 'status': 'finished_no_output'}
                
                elif status == 4:  # Failed
                    reason = task.get('reason', 'Unknown')
                    print(f"\n❌ Task failed: {reason}")
                    return None
                
            except Exception as e:
                print(f"\n⚠️  Poll error: {e}")
            
            await asyncio.sleep(poll_interval)
    
    async def run_hd_upscale(self, video_url, parent_task_id="", artwork_id="", 
                            width=464, height=688, duration=4):
        """Run HD upscale on a video."""
        print(f"\n🔍 Starting HD Upscale...")
        
        try:
            resp = self.session.post(
                f"{API_BASE}/task/v2/video/upscale",
                headers=self.headers,
                json={
                    "parent_task_id": parent_task_id,
                    "model_no": "",
                    "model_ver_no": "",
                    "meta": {
                        "width": width,
                        "height": height,
                        "images": [video_url],
                        "comfyui_inputs": [
                            {"node_id": "1", "node_type": "VHS_LoadVideo", 
                             "field": "video", "val": video_url}
                        ],
                        "generate_video": {
                            "video_url": video_url,
                            "generate_video_duration": duration
                        }
                    },
                    "pre_task_id": parent_task_id,
                    "pre_art_work_id": artwork_id,
                    "task_uri_index": 0
                },
                timeout=60
            )
            
            data = resp.json()
            if data.get('status', {}).get('code') != 10000:
                print(f"❌ HD Upscale failed: {data}")
                return None
            
            task_id = data['data']['id']
            print(f"   ✅ Task created: {task_id}")
            return task_id
            
        except Exception as e:
            print(f"❌ HD Upscale error: {e}")
            return None
    
    async def download_video(self, video_url, output_path):
        """Download a video from SeaArt CDN."""
        print(f"\n📥 Downloading video...")
        
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
                            pct = int(downloaded * 100 / total_size)
                            print(f"\r   Progress: {pct}%", end='', flush=True)
            
            print(f"\n   ✅ Saved: {output_path}")
            return output_path
            
        except Exception as e:
            print(f"\n❌ Download failed: {e}")
            return None
    
    async def close(self):
        """Cleanup"""
        self.session.close()
        self._connected = False


async def test_api():
    """Test the API connection"""
    api = SeaArtAPI()
    
    if await api.connect():
        print("\n✅ API ready!")
        print("\n⚠️  Note: You need to provide the correct App IDs from the HAR file")
        print("   for interpolation and other AI apps to work.")
    
    await api.close()


if __name__ == "__main__":
    asyncio.run(test_api())
