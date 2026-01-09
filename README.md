# AI Video Tempo Normalizer + SeaArt Enhancement Pipeline

**Turn clunky AI-generated videos into smooth, natural-looking footage.**

AI video generators (Grok Imagine, Runway, etc.) often produce videos with inconsistent tempo - they start fast and slow down unnaturally, making them feel "obviously AI." This tool analyzes motion patterns using optical flow and normalizes the speed to feel natural and consistent.

Combined with SeaArt.ai's frame interpolation (60fps) and HD upscaling, you get professional-quality output from a single command.

## What This Does

```
Input:  Clunky 24fps AI video with uneven tempo
Output: Smooth 60fps HD video with natural, consistent speed
```

### The Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│  INPUT: Raw Grok/AI Video                                           │
│  (clunky tempo, low fps, low resolution)                            │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 1: Frame Interpolation (SeaArt.ai)                           │
│  • Upload video to SeaArt                                           │
│  • AI generates intermediate frames                                  │
│  • Download smooth 60fps version                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 2: Tempo Normalization (Local)                               │
│  • Analyze motion using optical flow                                 │
│  • Detect camera movement vs subject movement                        │
│  • Compute dynamic speed curve                                       │
│  • Resample frames for consistent tempo                              │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 3: HD Upscale (SeaArt.ai)                                    │
│  • Upload tempo-fixed video                                          │
│  • AI upscales to HD resolution                                      │
│  • Download final HD version                                         │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 4: Comparison Video                                          │
│  • FFmpeg creates 2x2 grid showing all stages                        │
│  ┌─────────────┬─────────────┐                                      │
│  │  Original   │ Interpolated│                                      │
│  ├─────────────┼─────────────┤                                      │
│  │ Tempo Fixed │  HD Fixed   │                                      │
│  └─────────────┴─────────────┘                                      │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  OUTPUT: Professional video with                                     │
│  • 60fps smooth motion                                               │
│  • Natural, consistent tempo                                         │
│  • HD resolution                                                     │
│  • Side-by-side comparison                                           │
└─────────────────────────────────────────────────────────────────────┘
```

## Installation

### Prerequisites

- Python 3.8+
- Node.js (for session saving on Windows/WSL)
- FFmpeg (for comparison videos)
- A SeaArt.ai account (free tier works)

### Install Dependencies

```bash
# Python packages
pip install opencv-python-headless numpy scipy matplotlib requests

# Node.js package (for session saver)
npm install ws

# FFmpeg (Ubuntu/Debian)
sudo apt install ffmpeg

# FFmpeg (Windows) - download from https://ffmpeg.org/download.html
```

## Quick Start

### 1. Save Your SeaArt Session (One-Time Setup)

The pipeline needs your SeaArt login cookies to make API calls. We save these using a Node.js script that connects to your browser.

**Why Node.js instead of Python?**

If you're on WSL (Windows Subsystem for Linux), Python cannot connect to Windows browser's localhost due to WSL2 network isolation. Node.js running on Windows CAN connect, so we use it for session capture.

#### Step-by-Step:

1. **Close ALL browser windows** (important - browser must start fresh with debug port)

2. **Start your browser with remote debugging** (Windows CMD or PowerShell):

   **For Brave:**
   ```cmd
   "C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe" --remote-debugging-port=9224 https://www.seaart.ai
   ```

   **For Chrome:**
   ```cmd
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9224 https://www.seaart.ai
   ```

   **For Edge:**
   ```cmd
   "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9224 https://www.seaart.ai
   ```

3. **Login to SeaArt.ai** in the browser window that opens (if not already logged in)

4. **Run the session saver** (from Windows CMD in the project folder):
   ```cmd
   node save_session.js
   ```

   Or from WSL:
   ```bash
   /mnt/c/Windows/System32/cmd.exe /c "cd /d C:\path\to\project && node save_session.js"
   ```

5. **Verify**: You should see "SUCCESS! Session saved." and a `seaart_session.json` file

### 2. Run the Full Pipeline

```bash
python seaart_pipeline.py your_grok_video.mp4
```

That's it! The pipeline will:
1. Upload to SeaArt for 60fps interpolation
2. Download and run local tempo normalization
3. Upload for HD upscaling
4. Create 4-way comparison video

### Output

```
pipeline_output/{timestamp}_{uuid}/
├── 00_original.mp4      # Your input video
├── 01_interpolated.mp4  # 60fps smooth version
├── 02_tempo_fixed.mp4   # Tempo normalized
├── 03_hd_fixed.mp4      # HD upscaled final
└── 04_comparison.mp4    # 2x2 grid comparison
```

## Usage Options

### Full Pipeline
```bash
python seaart_pipeline.py video.mp4
```

### Skip Steps
```bash
# Skip frame interpolation (use if already 60fps)
python seaart_pipeline.py video.mp4 --skip-interpolation

# Skip HD upscaling
python seaart_pipeline.py video.mp4 --skip-hd

# Skip tempo normalization
python seaart_pipeline.py video.mp4 --skip-tempo
```

### Tempo Normalizer Only (No SeaArt)
```bash
# Process all .mp4 files in current directory
python tempo_normalizer.py

# Process specific videos
python tempo_normalizer.py video1.mp4 video2.mp4

# Generate side-by-side comparison
python tempo_normalizer.py --comparison video.mp4
```

### Create Comparison Videos
```bash
# 4-way grid
python create_comparison.py v1.mp4 v2.mp4 v3.mp4 v4.mp4 -o comparison.mp4

# Side-by-side (2 videos)
python create_comparison.py before.mp4 after.mp4 -s -o comparison.mp4
```

## How Tempo Normalization Works

### The Problem

AI video generators produce inconsistent motion:
- Videos often start fast and slow down
- Frame-to-frame motion varies wildly
- Camera movements can mask subject motion
- Environmental effects (rain, grain) add noise

### The Solution

1. **Optical Flow Analysis**
   - Compute dense optical flow between every frame pair (Farneback method)
   - Measure pixel displacement magnitude as motion proxy

2. **Camera Motion Compensation**
   - Calculate median flow (represents camera movement)
   - Subtract from total flow to isolate subject motion
   - Blend both signals (50/50) for final motion estimate

3. **Noise Detection**
   - Compare mean vs median flow magnitudes
   - High mean/median ratio = noisy video (rain, grain)
   - Apply discount factor to prevent over-speeding noisy videos

4. **Hybrid Speed Calculation**
   - Use video's own beginning tempo as baseline
   - Apply minimum acceptable tempo floor (1.5 px/frame @ 24fps)
   - Fast videos stay fast, slow videos get sped up
   - Smooth speed curve with Gaussian filter (no jerky transitions)

5. **Frame Resampling**
   - Map new timeline to original frames
   - No interpolation/blending = sharp output
   - Skip frames to speed up, repeat to slow down

## Configuration

### Tempo Normalizer Parameters

In `tempo_normalizer.py`:

```python
MIN_TEMPO_24FPS = 1.5  # Minimum acceptable motion (px/frame at 24fps)
max_speedup = 2.0      # Maximum speedup factor
max_slowdown = 0.6     # Maximum slowdown factor
smoothing = 10         # Gaussian smoothing sigma for speed curve
```

### SeaArt App IDs

In `seaart_pipeline.py`:

```python
INTERPOLATION_APP_ID = "d3hrfgte878c73e722pg"  # AI Frame Interpolation
VHS_SYNTHESIS_APP_ID = "d5fu2ele878c73d3jmi0"  # VHS Video Synthesis (for uploads)
```

These are discovered from network traffic. If SeaArt changes their app IDs, you'll need to:
1. Open browser DevTools (F12) → Network tab
2. Use the apps on SeaArt.ai
3. Look for requests to `/api/v1/creativity/generate/apply`
4. Find the `apply_id` in the request body

## File Structure

```
├── seaart_pipeline.py      # Main orchestrator - runs the full pipeline
├── seaart_api.py           # SeaArt API wrapper (upload, poll, download)
├── tempo_normalizer.py     # Core tempo normalization algorithm
├── create_comparison.py    # FFmpeg-based comparison video creator
├── save_session.js         # Node.js session saver (browser → cookies)
├── seaart_session.json     # Saved session (gitignored)
├── requirements.txt        # Python dependencies
└── pipeline_output/        # Generated videos (gitignored)
```

## API Details

### SeaArt API Flow

1. **Upload Video**
   - `POST /api/v1/resource/pre-sign/get` → Get presigned URL
   - `PUT {presigned_url}` → Upload to Google Cloud Storage
   - `POST /api/v1/resource/pre-sign/confirmPart` → Confirm part
   - `POST /api/v1/resource/pre-sign/confirm` → Finalize

2. **Run AI App**
   - `POST /api/v1/creativity/generate/apply` → Start task
   - Returns `task_id`

3. **Poll Progress**
   - `POST /api/v1/task/batch-progress` → Check status
   - Status: 1=waiting, 2=processing, 3=finished, 4=failed

4. **Download Result**
   - Direct GET to CDN URL from task result

### Session Format

`seaart_session.json` uses Playwright's storage_state format:

```json
{
  "cookies": [
    {
      "name": "cookie_name",
      "value": "cookie_value",
      "domain": ".seaart.ai",
      "path": "/",
      "expires": 1234567890,
      "httpOnly": false,
      "secure": true,
      "sameSite": "Lax"
    }
  ],
  "origins": []
}
```

## Troubleshooting

### "Cannot connect to browser on port 9224"
- Close ALL browser windows completely
- Start browser with `--remote-debugging-port=9224`
- Make sure no other process is using port 9224

### "HTTP 404" on SeaArt connection
- This is normal for the user info endpoint
- The actual API calls will still work if you're logged in

### "Session may still work" warning
- The user endpoint returned 404 but cookies are valid
- Pipeline should work - try running it

### Videos not speeding up enough
- Increase `MIN_TEMPO_24FPS` in tempo_normalizer.py
- Current default: 1.5 px/frame

### WSL can't connect to Windows browser
- Use the Node.js save_session.js script
- Run Node from Windows CMD, not WSL

## Contributing

This project was built iteratively through conversation, solving real problems:
- Started with basic optical flow → too blurry
- Added camera motion compensation → better accuracy  
- Implemented noise detection → handles rain/grain
- Created hybrid approach → fast stays fast, slow speeds up
- Integrated SeaArt API → full automation

Feel free to open issues or PRs!

## License

MIT
