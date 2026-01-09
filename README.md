# Video Tempo Normalizer + SeaArt Enhancement Pipeline

Fixes inconsistent frame rates and speeds in AI-generated videos (Grok Imagine, etc), with optional integration with SeaArt.ai for frame interpolation and HD upscaling.

AI video generators often produce videos with "clunky" tempo - they start fast and then slow down unnaturally. This tool analyzes motion patterns and normalizes the speed to feel more natural and consistent.

## Features

### Tempo Normalization (Local)
- **Optical flow analysis** - Measures actual pixel motion, not just frame timing
- **Camera motion compensation** - Separates subject motion from camera pans
- **Noise detection** - Handles rain, grain, and other visual noise that can skew readings
- **Hybrid tempo adjustment** - Fast videos stay fast, slow videos get sped up to a natural minimum
- **Smooth transitions** - Gradual speed changes prevent jerkiness
- **Side-by-side comparison** - Optional output showing before/after

### SeaArt Pipeline (Optional)
- **Frame Interpolation** - Boost to 60fps using AI
- **HD Upscaling** - Enhance resolution
- **4-Way Comparison** - Grid video showing all processing stages

## Installation

```bash
# Core dependencies
pip install opencv-python-headless numpy scipy matplotlib

# SeaArt pipeline (optional)
pip install playwright requests
playwright install chromium
```

## Usage

### Basic Tempo Normalization

Process all .mp4 files in current directory:
```bash
python tempo_normalizer_v13.py
```

Process specific video(s):
```bash
python tempo_normalizer_v13.py video1.mp4 video2.mp4
```

Generate side-by-side comparison videos:
```bash
python tempo_normalizer_v13.py --comparison
# or
python tempo_normalizer_v13.py -c video.mp4
```

### SeaArt Enhancement Pipeline

#### 1. First-time setup - Login to SeaArt
```bash
python seaart_login.py
# Chrome opens → Login to SeaArt.ai → Session saved automatically
```

#### 2. Run the full pipeline
```bash
python seaart_pipeline.py video.mp4
```

This will:
1. Upload to SeaArt for 60fps frame interpolation
2. Download and run local tempo normalization
3. Upload for HD upscaling
4. Create 4-way comparison video

#### Pipeline options:
```bash
# Skip frame interpolation
python seaart_pipeline.py video.mp4 --skip-interpolation

# Skip HD upscaling
python seaart_pipeline.py video.mp4 --skip-hd

# Skip tempo normalization
python seaart_pipeline.py video.mp4 --skip-tempo
```

### Create Comparison Videos

4-way grid:
```bash
python create_comparison.py original.mp4 interpolated.mp4 tempo_fixed.mp4 hd_fixed.mp4 -o comparison.mp4
```

Side-by-side:
```bash
python create_comparison.py before.mp4 after.mp4 -s -o comparison.mp4
```

## Output

- **Tempo normalizer**: Outputs to `v13/` folder
- **SeaArt pipeline**: Outputs to `pipeline_output/{timestamp}_{uuid}/`
  - `00_original.mp4` - Input video
  - `01_interpolated.mp4` - 60fps version
  - `02_tempo_fixed.mp4` - Normalized tempo
  - `03_hd_fixed.mp4` - HD upscaled
  - `04_comparison.mp4` - 4-way grid

## How It Works

### Tempo Normalization
1. **Analyze** - Computes optical flow between frames to measure motion magnitude
2. **Classify** - Determines if video is fast, borderline, or slow based on beginning tempo
3. **Compute speed curve** - Calculates dynamic speed adjustments to normalize tempo
4. **Apply** - Resamples frames according to speed curve (no interpolation = sharp output)

### SeaArt Pipeline
1. **Upload** - Get presigned URL → Upload to GCS → Confirm
2. **Process** - Submit to AI app → Poll for completion
3. **Download** - Fetch result from CDN

## Configuration

### Tempo Normalizer Parameters
In `tempo_normalizer_v13.py`:
- `MIN_TEMPO_24FPS = 1.5` - Minimum acceptable motion (px/frame at 24fps)
- `max_speedup = 2.0` - Maximum speedup factor
- `max_slowdown = 0.6` - Maximum slowdown factor  
- `smoothing = 10` - Gaussian smoothing for speed curve

### SeaArt App IDs
In `seaart_api.py`:
- `INTERPOLATION_APP_ID` - AI Frame Interpolation app
- `VHS_SYNTHESIS_APP_ID` - VHS Video Synthesis app (for uploads)

## Files

| File | Description |
|------|-------------|
| `tempo_normalizer_v13.py` | Core tempo normalization script |
| `seaart_login.py` | SeaArt session saver |
| `seaart_api.py` | SeaArt API wrapper |
| `seaart_pipeline.py` | Full enhancement pipeline |
| `create_comparison.py` | Comparison video creator |

## License

MIT
