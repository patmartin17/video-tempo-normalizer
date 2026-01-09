"""
SeaArt Video Enhancement Pipeline

Complete pipeline to process Grok-generated videos:
1. Upload raw video to SeaArt
2. Run AI Frame Interpolation (60fps)
3. Download interpolated video
4. Run local tempo normalization (tempo_normalizer.py)
5. Upload tempo-fixed video to SeaArt
6. Run HD upscale
7. Download final HD video
8. Create 4-way comparison video

Usage:
    python seaart_pipeline.py <input_video.mp4>
    python seaart_pipeline.py <input_video.mp4> --skip-interpolation
    python seaart_pipeline.py <input_video.mp4> --skip-hd
    python seaart_pipeline.py <input_video.mp4> --app-id <interpolation_app_id>
"""

# App IDs from HAR file
INTERPOLATION_APP_ID = "d3hrfgte878c73e722pg"  # AI Frame Interpolation
VHS_SYNTHESIS_APP_ID = "d5fu2ele878c73d3jmi0"  # VHS Video Synthesis
import asyncio
import argparse
import subprocess
import sys
import io
import uuid
from pathlib import Path
from datetime import datetime

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

# Import our modules
from seaart_api import SeaArtAPI
from create_comparison import create_4way_comparison

# Paths
SCRIPT_DIR = Path(__file__).parent
TEMPO_NORMALIZER = SCRIPT_DIR / "tempo_normalizer.py"
OUTPUT_BASE_DIR = SCRIPT_DIR / "pipeline_output"


def run_tempo_normalizer(input_video, output_dir):
    """
    Run the tempo normalizer script on a video.
    
    Args:
        input_video: Path to input video
        output_dir: Directory for output
        
    Returns:
        Path to normalized video, or None if failed
    """
    print(f"\n🎵 Running Tempo Normalizer...")
    print(f"   Input: {input_video}")
    
    input_video = Path(input_video)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # The tempo normalizer outputs to normalized_output/ folder by default
    # We need to run it and then find the output
    try:
        # Copy input to a temp location the normalizer can find
        temp_input = output_dir / f"tempo_input_{input_video.name}"
        
        import shutil
        shutil.copy2(input_video, temp_input)
        
        # Run the normalizer
        result = subprocess.run(
            [sys.executable, str(TEMPO_NORMALIZER), str(temp_input)],
            cwd=str(SCRIPT_DIR),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        if result.returncode != 0:
            print(f"❌ Tempo normalizer failed:")
            print(result.stderr)
            return None
        
        print(result.stdout)
        
        # Find the output file in normalized_output/
        norm_dir = SCRIPT_DIR / "normalized_output"
        if norm_dir.exists():
            # Find the most recently created normalized file
            normalized_files = list(norm_dir.glob("*_normalized.mp4"))
            if normalized_files:
                # Get the one matching our input name
                input_stem = input_video.stem.replace("tempo_input_", "")
                for nf in normalized_files:
                    if input_stem in nf.stem or temp_input.stem in nf.stem:
                        # Move to our output dir
                        final_output = output_dir / f"02_tempo_fixed.mp4"
                        shutil.move(str(nf), str(final_output))
                        print(f"   ✅ Saved to: {final_output}")
                        
                        # Cleanup temp input
                        temp_input.unlink(missing_ok=True)
                        return final_output
                
                # If no match, take the most recent
                normalized_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                final_output = output_dir / f"02_tempo_fixed.mp4"
                shutil.move(str(normalized_files[0]), str(final_output))
                print(f"   ✅ Saved to: {final_output}")
                temp_input.unlink(missing_ok=True)
                return final_output
        
        print(f"❌ Could not find normalized output")
        return None
        
    except Exception as e:
        print(f"❌ Error running tempo normalizer: {e}")
        import traceback
        traceback.print_exc()
        return None


async def run_pipeline(input_video, skip_interpolation=False, skip_hd=False, skip_tempo=False):
    """
    Run the complete video enhancement pipeline.
    
    Args:
        input_video: Path to input Grok video
        skip_interpolation: Skip frame interpolation step
        skip_hd: Skip HD upscale step
        skip_tempo: Skip tempo normalization step
    """
    input_video = Path(input_video)
    if not input_video.exists():
        print(f"❌ Input video not found: {input_video}")
        return False
    
    # Create output directory with UUID
    pipeline_uuid = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = OUTPUT_BASE_DIR / f"{timestamp}_{pipeline_uuid}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("🎬 SEAART VIDEO ENHANCEMENT PIPELINE")
    print("=" * 70)
    print(f"\nInput: {input_video.name}")
    print(f"Output: {output_dir}")
    print(f"\nSteps:")
    print(f"  1. Frame Interpolation (60fps): {'SKIP' if skip_interpolation else 'YES'}")
    print(f"  2. Tempo Normalization: {'SKIP' if skip_tempo else 'YES'}")
    print(f"  3. HD Upscale: {'SKIP' if skip_hd else 'YES'}")
    print(f"  4. Create Comparison: YES")
    print("=" * 70)
    
    # Copy original to output dir
    import shutil
    original_copy = output_dir / "00_original.mp4"
    shutil.copy2(input_video, original_copy)
    print(f"\n✅ Copied original to: {original_copy.name}")
    
    # Track all video paths for comparison
    video_paths = {
        'original': original_copy,
        'interpolated': None,
        'tempo_fixed': None,
        'hd_fixed': None
    }
    
    # Initialize API
    api = SeaArtAPI()
    
    try:
        # Connect to SeaArt
        print("\n" + "=" * 70)
        print("CONNECTING TO SEAART")
        print("=" * 70)
        
        if not await api.connect():
            print("❌ Failed to connect to SeaArt")
            return False
        
        current_video_url = None
        current_task_result = None
        
        # Stage 1: Frame Interpolation
        if not skip_interpolation:
            print("\n" + "=" * 70)
            print("STAGE 1: FRAME INTERPOLATION (60fps)")
            print("=" * 70)
            
            # Upload original video
            uploaded_url = await api.upload_video(original_copy)
            if not uploaded_url:
                print("❌ Failed to upload video for interpolation")
                return False
            
            # Run interpolation
            task_id = await api.run_interpolation(uploaded_url, INTERPOLATION_APP_ID, target_fps=60, multiplier=2)
            if not task_id:
                print("❌ Failed to start interpolation")
                return False
            
            # Poll for completion
            result = await api.poll_task(task_id)
            if not result or not result.get('video_url'):
                print("❌ Interpolation task failed")
                return False
            
            current_video_url = result['video_url']
            current_task_result = result
            
            # Download interpolated video
            interpolated_path = output_dir / "01_interpolated.mp4"
            downloaded = await api.download_video(current_video_url, interpolated_path)
            if not downloaded:
                print("❌ Failed to download interpolated video")
                return False
            
            video_paths['interpolated'] = interpolated_path
            print(f"✅ Stage 1 complete: {interpolated_path.name}")
        else:
            print("\n⏭️  Skipping Stage 1: Frame Interpolation")
            video_paths['interpolated'] = original_copy  # Use original as fallback
        
        # Stage 2: Tempo Normalization (Local)
        if not skip_tempo:
            print("\n" + "=" * 70)
            print("STAGE 2: TEMPO NORMALIZATION (Local)")
            print("=" * 70)
            
            # Use interpolated video if available, otherwise original
            input_for_tempo = video_paths['interpolated'] or original_copy
            
            tempo_fixed = run_tempo_normalizer(input_for_tempo, output_dir)
            if not tempo_fixed:
                print("⚠️  Tempo normalization failed, using input as-is")
                video_paths['tempo_fixed'] = input_for_tempo
            else:
                video_paths['tempo_fixed'] = tempo_fixed
                print(f"✅ Stage 2 complete: {tempo_fixed.name}")
        else:
            print("\n⏭️  Skipping Stage 2: Tempo Normalization")
            video_paths['tempo_fixed'] = video_paths['interpolated'] or original_copy
        
        # Stage 3: HD Upscale
        if not skip_hd:
            print("\n" + "=" * 70)
            print("STAGE 3: HD UPSCALE")
            print("=" * 70)
            
            # Upload tempo-fixed video
            tempo_video = video_paths['tempo_fixed']
            uploaded_url = await api.upload_video(tempo_video)
            if not uploaded_url:
                print("❌ Failed to upload video for HD upscale")
                # Continue without HD
                video_paths['hd_fixed'] = tempo_video
            else:
                # Get video info for upscale request
                # Use previous task result if available, otherwise use defaults
                if current_task_result:
                    width = current_task_result.get('width', 464)
                    height = current_task_result.get('height', 688)
                    duration = current_task_result.get('duration', 4)
                    parent_task_id = current_task_result.get('task_id', '')
                    artwork_id = current_task_result.get('artwork_id', '')
                else:
                    width, height, duration = 464, 688, 4
                    parent_task_id, artwork_id = '', ''
                
                # Run HD upscale
                task_id = await api.run_hd_upscale(
                    uploaded_url,
                    parent_task_id,
                    artwork_id,
                    width=width,
                    height=height,
                    duration=duration
                )
                
                if not task_id:
                    print("⚠️  Failed to start HD upscale, using tempo-fixed video")
                    video_paths['hd_fixed'] = tempo_video
                else:
                    # Poll for completion
                    result = await api.poll_task(task_id)
                    if not result or not result.get('video_url'):
                        print("⚠️  HD upscale task failed, using tempo-fixed video")
                        video_paths['hd_fixed'] = tempo_video
                    else:
                        # Download HD video
                        hd_path = output_dir / "03_hd_fixed.mp4"
                        downloaded = await api.download_video(result['video_url'], hd_path)
                        if not downloaded:
                            print("⚠️  Failed to download HD video, using tempo-fixed")
                            video_paths['hd_fixed'] = tempo_video
                        else:
                            video_paths['hd_fixed'] = hd_path
                            print(f"✅ Stage 3 complete: {hd_path.name}")
        else:
            print("\n⏭️  Skipping Stage 3: HD Upscale")
            video_paths['hd_fixed'] = video_paths['tempo_fixed']
        
        # Stage 4: Create Comparison Video
        print("\n" + "=" * 70)
        print("STAGE 4: CREATE COMPARISON VIDEO")
        print("=" * 70)
        
        comparison_path = output_dir / "04_comparison.mp4"
        
        # Create 4-way comparison
        success = create_4way_comparison(
            original=video_paths['original'],
            interpolated=video_paths['interpolated'],
            tempo_fixed=video_paths['tempo_fixed'],
            hd_fixed=video_paths['hd_fixed'],
            output_path=comparison_path
        )
        
        if success:
            print(f"✅ Stage 4 complete: {comparison_path.name}")
        else:
            print("⚠️  Failed to create comparison video")
        
        # Final Summary
        print("\n" + "=" * 70)
        print("🎉 PIPELINE COMPLETE!")
        print("=" * 70)
        print(f"\nOutput directory: {output_dir}")
        print(f"\nGenerated files:")
        for name, path in video_paths.items():
            if path and path.exists():
                size_mb = path.stat().st_size / 1024 / 1024
                print(f"  • {path.name} ({size_mb:.2f} MB)")
        
        if comparison_path.exists():
            size_mb = comparison_path.stat().st_size / 1024 / 1024
            print(f"  • {comparison_path.name} ({size_mb:.2f} MB)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await api.close()


def main():
    parser = argparse.ArgumentParser(
        description="SeaArt Video Enhancement Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python seaart_pipeline.py video.mp4 --interpolation-app-id abc123
  python seaart_pipeline.py video.mp4 --skip-interpolation
  python seaart_pipeline.py video.mp4 --skip-hd
  python seaart_pipeline.py video.mp4 --skip-tempo
        """
    )
    
    parser.add_argument('input_video', help='Path to input video file')
    parser.add_argument('--interpolation-app-id', '-i', 
                       help='App ID for Frame Interpolation (from HAR file)')
    parser.add_argument('--skip-interpolation', '-si', action='store_true',
                       help='Skip frame interpolation step')
    parser.add_argument('--skip-hd', '-sh', action='store_true',
                       help='Skip HD upscale step')
    parser.add_argument('--skip-tempo', '-st', action='store_true',
                       help='Skip tempo normalization step')
    
    args = parser.parse_args()
    
    # Update global app IDs if provided
    global INTERPOLATION_APP_ID
    if args.interpolation_app_id:
        INTERPOLATION_APP_ID = args.interpolation_app_id
    
    # Run the pipeline
    success = asyncio.run(run_pipeline(
        args.input_video,
        skip_interpolation=args.skip_interpolation,
        skip_hd=args.skip_hd,
        skip_tempo=args.skip_tempo
    ))
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

