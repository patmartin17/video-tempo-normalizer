"""
Create 4-Way Comparison Video

Creates a 2x2 grid video showing:
┌─────────────┬─────────────┐
│  Original   │ Interpolated│
│  (Grok)     │  (60fps)    │
├─────────────┼─────────────┤
│ Tempo Fixed │  HD Fixed   │
│  (v13)      │  (SeaArt)   │
└─────────────┴─────────────┘

Each quadrant is labeled with its processing stage.

Usage:
    python create_comparison.py original.mp4 interpolated.mp4 tempo_fixed.mp4 hd_fixed.mp4 -o comparison.mp4
"""
import subprocess
import sys
import io
from pathlib import Path
import shutil

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


def find_ffmpeg():
    """Find FFmpeg executable"""
    # Check if in PATH
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        return ffmpeg_path
    
    # Check common Windows locations
    if sys.platform == 'win32':
        common_paths = [
            Path('C:/ffmpeg/bin/ffmpeg.exe'),
            Path('C:/Program Files/ffmpeg/bin/ffmpeg.exe'),
            Path.home() / 'ffmpeg/bin/ffmpeg.exe',
        ]
        for path in common_paths:
            if path.exists():
                return str(path)
    
    return None


def get_video_info(video_path):
    """Get video dimensions and duration using ffprobe"""
    ffprobe = shutil.which('ffprobe')
    if not ffprobe:
        # Try common locations
        if sys.platform == 'win32':
            for path in [Path('C:/ffmpeg/bin/ffprobe.exe'), Path.home() / 'ffmpeg/bin/ffprobe.exe']:
                if path.exists():
                    ffprobe = str(path)
                    break
    
    if not ffprobe:
        return None
    
    try:
        result = subprocess.run([
            ffprobe, '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,duration',
            '-of', 'json',
            str(video_path)
        ], capture_output=True, text=True)
        
        import json
        data = json.loads(result.stdout)
        stream = data.get('streams', [{}])[0]
        return {
            'width': int(stream.get('width', 0)),
            'height': int(stream.get('height', 0)),
            'duration': float(stream.get('duration', 0))
        }
    except:
        return None


def create_4way_comparison(original, interpolated, tempo_fixed, hd_fixed, output_path,
                          target_width=1920, target_height=1080):
    """
    Create a 4-way comparison video with labels.
    
    Args:
        original: Path to original video
        interpolated: Path to interpolated (60fps) video
        tempo_fixed: Path to tempo-fixed video
        hd_fixed: Path to HD upscaled video
        output_path: Where to save the comparison
        target_width: Output video width
        target_height: Output video height
        
    Returns:
        True if successful, False otherwise
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print("❌ FFmpeg not found! Please install FFmpeg.")
        return False
    
    # Convert to Path objects
    original = Path(original)
    interpolated = Path(interpolated) if interpolated else original
    tempo_fixed = Path(tempo_fixed) if tempo_fixed else original
    hd_fixed = Path(hd_fixed) if hd_fixed else original
    output_path = Path(output_path)
    
    # Verify files exist
    for name, path in [('Original', original), ('Interpolated', interpolated),
                       ('Tempo Fixed', tempo_fixed), ('HD Fixed', hd_fixed)]:
        if not path.exists():
            print(f"⚠️  {name} video not found: {path}, using original")
    
    # Calculate grid dimensions (2x2)
    cell_width = target_width // 2
    cell_height = target_height // 2
    
    print(f"\n🎬 Creating 4-way comparison video...")
    print(f"   Grid: {target_width}x{target_height} ({cell_width}x{cell_height} per cell)")
    
    # Labels for each quadrant
    labels = [
        "Original (Grok)",
        "Interpolated (60fps)",
        "Tempo Fixed (v13)",
        "HD Upscaled"
    ]
    
    # Build FFmpeg complex filter
    # Scale each video to cell size, add labels, then stack in 2x2 grid
    filter_complex = []
    
    # Scale each input to cell size
    for i in range(4):
        filter_complex.append(
            f"[{i}:v]scale={cell_width}:{cell_height}:force_original_aspect_ratio=decrease,"
            f"pad={cell_width}:{cell_height}:(ow-iw)/2:(oh-ih)/2:black,"
            f"drawtext=text='{labels[i]}':fontsize=24:fontcolor=white:borderw=2:bordercolor=black:"
            f"x=(w-text_w)/2:y=20[v{i}]"
        )
    
    # Stack videos: top row, bottom row, then vstack
    filter_complex.append("[v0][v1]hstack=inputs=2[top]")
    filter_complex.append("[v2][v3]hstack=inputs=2[bottom]")
    filter_complex.append("[top][bottom]vstack=inputs=2[outv]")
    
    # Join filter
    filter_str = ';'.join(filter_complex)
    
    # Build FFmpeg command
    cmd = [
        ffmpeg,
        '-y',  # Overwrite output
        '-i', str(original),
        '-i', str(interpolated) if interpolated.exists() else str(original),
        '-i', str(tempo_fixed) if tempo_fixed.exists() else str(original),
        '-i', str(hd_fixed) if hd_fixed.exists() else str(original),
        '-filter_complex', filter_str,
        '-map', '[outv]',
        '-c:v', 'libx264',
        '-preset', 'medium',
        '-crf', '23',
        '-pix_fmt', 'yuv420p',
        '-shortest',  # End when shortest input ends
        str(output_path)
    ]
    
    print(f"   Running FFmpeg...")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        if result.returncode != 0:
            print(f"❌ FFmpeg error:")
            print(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
            return False
        
        if output_path.exists():
            size_mb = output_path.stat().st_size / 1024 / 1024
            print(f"   ✅ Comparison video created!")
            print(f"   📍 {output_path}")
            print(f"   📦 Size: {size_mb:.2f} MB")
            return True
        else:
            print(f"❌ Output file not created")
            return False
            
    except Exception as e:
        print(f"❌ Error running FFmpeg: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_side_by_side(video1, video2, output_path, label1="Before", label2="After"):
    """
    Create a simple side-by-side comparison (2 videos).
    
    Args:
        video1: Path to first video (left)
        video2: Path to second video (right)
        output_path: Where to save
        label1: Label for first video
        label2: Label for second video
        
    Returns:
        True if successful
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print("❌ FFmpeg not found!")
        return False
    
    video1 = Path(video1)
    video2 = Path(video2)
    output_path = Path(output_path)
    
    if not video1.exists() or not video2.exists():
        print(f"❌ Input videos not found")
        return False
    
    # Get video info to determine output size
    info = get_video_info(video1)
    if info:
        cell_width = info['width']
        cell_height = info['height']
    else:
        cell_width, cell_height = 480, 720
    
    print(f"\n🎬 Creating side-by-side comparison...")
    
    filter_complex = (
        f"[0:v]scale={cell_width}:{cell_height}:force_original_aspect_ratio=decrease,"
        f"pad={cell_width}:{cell_height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"drawtext=text='{label1}':fontsize=20:fontcolor=white:borderw=2:bordercolor=black:"
        f"x=(w-text_w)/2:y=15[v0];"
        f"[1:v]scale={cell_width}:{cell_height}:force_original_aspect_ratio=decrease,"
        f"pad={cell_width}:{cell_height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"drawtext=text='{label2}':fontsize=20:fontcolor=white:borderw=2:bordercolor=black:"
        f"x=(w-text_w)/2:y=15[v1];"
        f"[v0][v1]hstack=inputs=2[outv]"
    )
    
    cmd = [
        ffmpeg,
        '-y',
        '-i', str(video1),
        '-i', str(video2),
        '-filter_complex', filter_complex,
        '-map', '[outv]',
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '23',
        '-pix_fmt', 'yuv420p',
        '-shortest',
        str(output_path)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and output_path.exists():
            print(f"   ✅ Side-by-side comparison created: {output_path.name}")
            return True
        else:
            print(f"❌ Failed to create comparison")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Create comparison videos")
    parser.add_argument('videos', nargs='*', help='Input videos (1-4)')
    parser.add_argument('-o', '--output', default='comparison.mp4', help='Output path')
    parser.add_argument('--width', type=int, default=1920, help='Output width')
    parser.add_argument('--height', type=int, default=1080, help='Output height')
    parser.add_argument('--side-by-side', '-s', action='store_true', 
                       help='Create 2-way side-by-side instead of 4-way grid')
    
    args = parser.parse_args()
    
    if not args.videos:
        print("Usage: python create_comparison.py video1.mp4 video2.mp4 [video3.mp4 video4.mp4] -o output.mp4")
        return
    
    if args.side_by_side or len(args.videos) == 2:
        # 2-way comparison
        if len(args.videos) < 2:
            print("❌ Need 2 videos for side-by-side comparison")
            return
        create_side_by_side(args.videos[0], args.videos[1], args.output)
    else:
        # 4-way comparison
        videos = args.videos + [args.videos[-1]] * (4 - len(args.videos))  # Pad with last video
        create_4way_comparison(
            videos[0], videos[1], videos[2], videos[3],
            args.output,
            target_width=args.width,
            target_height=args.height
        )


if __name__ == "__main__":
    main()

