# Video Tempo Normalizer

Fixes inconsistent frame rates and speeds in AI-generated videos (Grok Imagine, etc).

AI video generators often produce videos with "clunky" tempo - they start fast and then slow down unnaturally. This tool analyzes motion patterns and normalizes the speed to feel more natural and consistent.

## Features

- **Optical flow analysis** - Measures actual pixel motion, not just frame timing
- **Camera motion compensation** - Separates subject motion from camera pans
- **Noise detection** - Handles rain, grain, and other visual noise that can skew readings
- **Hybrid tempo adjustment** - Fast videos stay fast, slow videos get sped up to a natural minimum
- **Smooth transitions** - Gradual speed changes prevent jerkiness
- **Side-by-side comparison** - Optional output showing before/after

## Installation

```bash
pip install opencv-python numpy scipy matplotlib
```

## Usage

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

## Output

- Normalized videos saved to `v13/` folder
- Analysis charts showing motion before/after
- Optional comparison videos showing original vs normalized side-by-side

## How It Works

1. **Analyze** - Computes optical flow between frames to measure motion magnitude
2. **Classify** - Determines if video is fast, borderline, or slow based on beginning tempo
3. **Compute speed curve** - Calculates dynamic speed adjustments to normalize tempo
4. **Apply** - Resamples frames according to speed curve (no interpolation = sharp output)

## Parameters

In `tempo_normalizer_v13.py`:
- `MIN_TEMPO_24FPS = 1.5` - Minimum acceptable motion (px/frame at 24fps)
- `max_speedup = 2.0` - Maximum speedup factor
- `max_slowdown = 0.6` - Maximum slowdown factor  
- `smoothing = 10` - Gaussian smoothing for speed curve

## License

MIT
