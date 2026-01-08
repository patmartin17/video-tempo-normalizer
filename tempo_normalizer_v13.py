#!/usr/bin/env python3
"""
Video Tempo Normalizer v13.0

Uses an ABSOLUTE BASELINE TEMPO instead of comparing to the video's own beginning.
This fixes videos that start too slow.

Baseline: 1.468 px/frame (from reference video grok-video-bf4ecaf7... first 2 seconds)
"""

import sys
import os
# Add user's site-packages to path (works when running as root)
# Check both current user and pmartin's directories
for user_dir in [os.path.expanduser('~'), '/home/pmartin']:
    user_site = os.path.join(user_dir, '.local/lib/python3.12/site-packages')
    if os.path.exists(user_site) and user_site not in sys.path:
        sys.path.insert(0, user_site)

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
import matplotlib.pyplot as plt
import os

# MINIMUM ACCEPTABLE TEMPO - floor for "too slow" videos
# Based on user feedback: ~2.0 px/frame at 24fps feels natural
# This scales with FPS (60fps = 0.8 px/frame minimum)
# If video's beginning is below this, we use the minimum instead
MIN_TEMPO_24FPS = 1.5  # Minimum acceptable - videos below this get sped up
REFERENCE_FPS = 24.0


def load_video(path):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)
    cap.release()
    
    return frames, fps, width, height


def compute_motion(frames, compensate_camera=True):
    """
    Compute motion magnitude between frames.
    
    If compensate_camera=True, subtracts global camera motion to get
    just the subject/content motion. This prevents camera pans from
    making slow videos appear fast.
    
    Also detects noise (rain, grain) via Mean/Median ratio and returns
    a noise_factor for adjustment.
    """
    motion = []
    camera_motion = []
    mean_list = []
    median_list = []
    
    for i in range(len(frames) - 1):
        g1 = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)
        g2 = cv2.cvtColor(frames[i+1], cv2.COLOR_BGR2GRAY)
        
        flow = cv2.calcOpticalFlowFarneback(
            g1, g2, None, 0.5, 3, 15, 3, 5, 1.2, 0
        )
        
        mag = np.sqrt(flow[..., 0]**2 + flow[..., 1]**2)
        mean_list.append(np.mean(mag))
        median_list.append(np.median(mag))
        
        if compensate_camera:
            # Median flow = camera motion (most pixels are background)
            median_dx = np.median(flow[..., 0])
            median_dy = np.median(flow[..., 1])
            camera_mag = np.sqrt(median_dx**2 + median_dy**2)
            camera_motion.append(camera_mag)
            
            # Subtract camera motion from flow
            flow_compensated = flow.copy()
            flow_compensated[..., 0] -= median_dx
            flow_compensated[..., 1] -= median_dy
            
            # Subject motion = what's left after removing camera motion
            mag_comp = np.sqrt(flow_compensated[..., 0]**2 + flow_compensated[..., 1]**2)
            
            # Use a blend: balance subject motion with camera motion
            subject_motion = np.mean(mag_comp)
            
            # Weight: 50% subject motion, 50% camera motion
            blended = subject_motion * 0.5 + camera_mag * 0.5
            motion.append(blended)
        else:
            motion.append(np.mean(mag))
    
    # Calculate noise factor based on Mean/Median ratio
    # High ratio (>3) = clean video, low ratio (<2) = noisy (rain, grain)
    avg_mean = np.mean(mean_list)
    avg_median = np.mean(median_list)
    if avg_median > 0.01:
        ratio = avg_mean / avg_median
    else:
        ratio = 5.0  # Assume clean if median is very low
    
    # noise_factor: 1.0 for clean videos, <1.0 for noisy videos
    # This will discount the measured motion for noisy videos
    # Max 22% discount - tuned for rain/grain scenarios
    if ratio >= 3.0:
        noise_factor = 1.0  # Clean video
    elif ratio >= 1.5:
        # Linear interpolation: ratio 3->1.5 maps to factor 1.0->0.78
        noise_factor = 0.78 + (ratio - 1.5) * (0.22 / 1.5)
    else:
        noise_factor = 0.78  # Very noisy - max 22% discount
    
    return np.array(motion), noise_factor


def compute_speed_curve_smart(raw_motion, subject_motion, fps=24.0, smoothing=10, 
                               max_speedup=2.0, max_slowdown=0.6, noise_factor=1.0):
    """
    SMART approach using BOTH raw and subject motion:
    
    1. RAW motion = total visual energy (decides if video is globally slow)
    2. SUBJECT motion = internal consistency (smooths uneven sections)
    3. NOISE_FACTOR = if noise detected, be more aggressive with borderline videos
    
    This prevents:
    - Camera movement from masking slow subjects
    - Over-speeding videos that already have good total energy
    - Rain/grain from fooling the algorithm
    """
    n = len(raw_motion)
    if n < 10:
        return np.mean(raw_motion), np.mean(raw_motion), raw_motion, np.ones(n)
    
    # Smooth both curves
    smoothed_raw = gaussian_filter1d(raw_motion, sigma=smoothing)
    smoothed_subject = gaussian_filter1d(subject_motion, sigma=smoothing)
    
    # Get beginning tempos
    ref_frames = max(10, int(fps))
    ref_frames = min(ref_frames, n // 4)
    beginning_raw = np.mean(smoothed_raw[:ref_frames])
    beginning_subject = np.mean(smoothed_subject[:ref_frames])
    
    # Calculate minimum acceptable tempo for this FPS
    min_acceptable = MIN_TEMPO_24FPS * (REFERENCE_FPS / fps)
    
    # DECISION: Use RAW motion to decide if globally slow
    # Three zones:
    # 1. Fast (raw >= min): no global speedup, just internal smoothing
    # 2. Borderline (raw 85-100% of min): very gentle nudge (almost nothing)
    # 3. Slow (raw < 85% of min): aggressive speedup to reach target
    
    borderline_threshold = min_acceptable * 0.85  # 85% of minimum (1.275 at 24fps)
    
    if beginning_raw >= min_acceptable:
        # FAST: Video has enough energy - just internal smoothing
        reference_tempo = beginning_subject
        correction_strength = 0.5  # Moderate internal smoothing
        global_speedup_needed = False
    elif beginning_raw >= borderline_threshold:
        # BORDERLINE: Treatment depends on noise detection
        pct_of_min = beginning_raw / min_acceptable
        
        if noise_factor < 0.95:
            # NOISE DETECTED: Be more aggressive (rain/grain inflating readings)
            # Scale: at 100% of min: 1.0x, at 85% of min: 1.4x
            boost = 1.0 + (1.0 - pct_of_min) * (0.4 / 0.15)
            reference_tempo = beginning_subject * min(boost, 1.4)
            correction_strength = 0.3 + (1.0 - pct_of_min) * (0.4 / 0.15)
            correction_strength = min(correction_strength, 0.7)
        else:
            # NO NOISE: Gentle treatment (video is legitimately borderline)
            reference_tempo = beginning_subject * 1.05  # Just 5% boost
            correction_strength = 0.3
        global_speedup_needed = False
    else:
        # SLOW: This is actual slow motion - aggressive speedup needed
        # User said these need 1.8-2.0x to feel normal
        target_tempo = min_acceptable * 1.2  # 20% above minimum
        reference_tempo = max(beginning_subject * 2.2, target_tempo)  # At least 2.2x subject
        correction_strength = 0.95  # Very aggressive correction
        global_speedup_needed = True
    
    if reference_tempo < 0.001:
        return beginning_raw, reference_tempo, smoothed_subject, np.ones(n)
    
    speed = np.ones(n)
    
    # Use SUBJECT motion for internal consistency
    for i in range(n):
        ratio = smoothed_subject[i] / reference_tempo
        
        # Dynamic adjustment - strength depends on zone
        if ratio < 1.0:
            # Slower than reference - speed up proportionally
            speed_needed = reference_tempo / (smoothed_subject[i] + 0.001)
            speed[i] = 1.0 + (speed_needed - 1.0) * correction_strength
            speed[i] = min(speed[i], max_speedup)
            
        elif ratio > 1.0:
            # Faster than reference - slow down proportionally
            speed_needed = reference_tempo / (smoothed_subject[i] + 0.001)
            speed[i] = 1.0 + (speed_needed - 1.0) * correction_strength
            speed[i] = max(speed[i], max_slowdown)
    
    # Heavy smoothing for gradual transitions
    speed = gaussian_filter1d(speed, sigma=smoothing)
    
    # Gentle ramp at start (don't change the beginning abruptly)
    ramp_frames = min(int(fps), n // 5)
    for i in range(ramp_frames):
        blend = i / ramp_frames
        speed[i] = 1.0 + (speed[i] - 1.0) * blend * blend
    
    return beginning_raw, reference_tempo, smoothed_subject, speed


def apply_speed_curve(frames, speed_curve):
    """
    Apply variable speed using nearest frame selection (sharp, no blur).
    """
    n = len(frames)
    
    frame_duration = 1.0 / speed_curve
    cumulative = np.cumsum(frame_duration)
    cumulative = np.insert(cumulative, 0, 0)
    
    total_output_time = cumulative[-1]
    
    avg_speed = np.mean(speed_curve)
    n_output = int(n / avg_speed)
    n_output = max(n_output, n // 3)
    
    output_times = np.linspace(0, total_output_time, n_output)
    
    output_frames = []
    for out_t in output_times:
        idx = np.searchsorted(cumulative, out_t, side='right') - 1
        idx = np.clip(idx, 0, n - 1)
        output_frames.append(frames[idx])
    
    return output_frames


def create_analysis_chart(motion_before, motion_after, baseline_tempo, speed_curve, output_path):
    """
    Create before/after analysis with absolute baseline visualization.
    """
    fig, axes = plt.subplots(3, 2, figsize=(16, 12))
    
    # Stats
    cv_before = np.std(motion_before) / np.mean(motion_before) * 100
    cv_after = np.std(motion_after) / np.mean(motion_after) * 100
    
    mean_before = np.mean(motion_before)
    mean_after = np.mean(motion_after)
    
    avg_speed = np.mean(speed_curve)
    min_speed = np.min(speed_curve)
    max_speed = np.max(speed_curve)
    
    # Row 1: Motion curves
    ax1 = axes[0, 0]
    x_before = np.arange(len(motion_before))
    smoothed_before = gaussian_filter1d(motion_before, sigma=5)
    ax1.plot(x_before, motion_before, 'b-', alpha=0.3, label='Raw')
    ax1.plot(x_before, smoothed_before, 'b-', lw=2, label='Smoothed')
    ax1.axhline(baseline_tempo, color='green', ls='--', lw=2, label=f'Beginning: {baseline_tempo:.2f}')
    ax1.axhline(mean_before, color='red', ls=':', lw=2, label=f'Video mean: {mean_before:.2f}')
    ax1.set_ylabel('Motion (px/frame)')
    ax1.set_title(f'BEFORE - Mean: {mean_before:.2f} ({mean_before/baseline_tempo*100:.0f}% of beginning)')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    
    ax2 = axes[0, 1]
    x_after = np.arange(len(motion_after))
    smoothed_after = gaussian_filter1d(motion_after, sigma=5)
    ax2.plot(x_after, motion_after, 'g-', alpha=0.3, label='Raw')
    ax2.plot(x_after, smoothed_after, 'g-', lw=2, label='Smoothed')
    ax2.axhline(baseline_tempo, color='green', ls='--', lw=2, label=f'Beginning: {baseline_tempo:.2f}')
    ax2.axhline(mean_after, color='orange', ls=':', lw=2, label=f'Video mean: {mean_after:.2f}')
    ax2.set_ylabel('Motion (px/frame)')
    ax2.set_title(f'AFTER - Mean: {mean_after:.2f} ({mean_after/baseline_tempo*100:.0f}% of beginning)')
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)
    
    # Row 2: Speed curve and deviation from baseline
    ax3 = axes[1, 0]
    x_speed = np.arange(len(speed_curve))
    ax3.plot(x_speed, speed_curve, 'purple', lw=2, label='Speed curve')
    ax3.axhline(1.0, color='black', ls='--', lw=1, label='Normal speed')
    ax3.fill_between(x_speed, speed_curve, 1.0, where=speed_curve > 1.02,
                     alpha=0.3, color='orange', label='Speedup (too slow)')
    ax3.fill_between(x_speed, speed_curve, 1.0, where=speed_curve < 0.98,
                     alpha=0.3, color='blue', label='Slowdown (too fast)')
    ax3.set_xlabel('Frame')
    ax3.set_ylabel('Speed multiplier')
    ax3.set_title(f'Speed Curve - Avg: {avg_speed:.2f}x, Range: {min_speed:.2f}x - {max_speed:.2f}x')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    ax3.set_ylim(0.5, 1.8)
    
    # Deviation from reference (beginning tempo)
    ax4 = axes[1, 1]
    dev_before = smoothed_before - baseline_tempo
    dev_after = smoothed_after - baseline_tempo
    ax4.fill_between(range(len(dev_before)), dev_before, 0, where=dev_before < 0,
                     alpha=0.4, color='red', label='Before: Below reference')
    ax4.fill_between(range(len(dev_before)), dev_before, 0, where=dev_before >= 0,
                     alpha=0.4, color='blue', label='Before: Above reference')
    ax4.plot(dev_after, 'g-', lw=2, alpha=0.8, label='After')
    ax4.axhline(0, color='black', lw=1)
    ax4.set_xlabel('Frame')
    ax4.set_ylabel('Deviation from reference')
    ax4.set_title('Deviation from Beginning Tempo (0 = matches start)')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    # Row 3: Histograms
    ax5 = axes[2, 0]
    ax5.hist(motion_before, bins=30, alpha=0.6, color='blue', label='Before', density=True)
    ax5.hist(motion_after, bins=30, alpha=0.6, color='green', label='After', density=True)
    ax5.axvline(baseline_tempo, color='red', ls='--', lw=2, label=f'Beginning: {baseline_tempo:.2f}')
    ax5.set_xlabel('Motion (px/frame)')
    ax5.set_ylabel('Density')
    ax5.set_title('Distribution vs Beginning Tempo')
    ax5.legend()
    ax5.grid(True, alpha=0.3)
    
    # Summary
    ax6 = axes[2, 1]
    ax6.axis('off')
    
    pct_before = mean_before / baseline_tempo * 100 if baseline_tempo > 0 else 100
    pct_after = mean_after / baseline_tempo * 100 if baseline_tempo > 0 else 100
    
    summary_text = f"""
    SELF-RELATIVE NORMALIZATION
    ══════════════════════════════════════
    
    REFERENCE: Beginning tempo
    = {baseline_tempo:.3f} px/frame
    
    BEFORE:
      • Mean motion: {mean_before:.3f} px/frame
      • vs Beginning: {pct_before:.0f}%
      • CV: {cv_before:.1f}%
      • Frames: {len(motion_before) + 1}
    
    AFTER:
      • Mean motion: {mean_after:.3f} px/frame
      • vs Beginning: {pct_after:.0f}%
      • CV: {cv_after:.1f}%
      • Frames: {len(motion_after) + 1}
    
    ADJUSTMENT:
      • Speed range: {min_speed:.2f}x - {max_speed:.2f}x
      • Avg speed: {avg_speed:.2f}x
    
    ══════════════════════════════════════
    Goal: Match entire video to beginning tempo
    """
    
    ax6.text(0.1, 0.5, summary_text, transform=ax6.transAxes, 
             fontsize=11, verticalalignment='center', fontfamily='monospace',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.suptitle(f'v13: Self-Relative Normalization (Beginning = {baseline_tempo:.2f} px/frame)', 
                 fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    return {
        'cv_before': cv_before,
        'cv_after': cv_after,
        'mean_before': mean_before,
        'mean_after': mean_after,
        'pct_baseline_before': pct_before,
        'pct_baseline_after': pct_after,
        'avg_speed': avg_speed,
        'min_speed': min_speed,
        'max_speed': max_speed
    }


def write_video(frames, path, fps, width, height):
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(path, fourcc, fps, (width, height))
    for f in frames:
        out.write(f)
    out.release()


def create_side_by_side(original_frames, normalized_frames, fps, output_path):
    """Create side-by-side comparison video."""
    h, w = original_frames[0].shape[:2]
    
    min_len = min(len(original_frames), len(normalized_frames))
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (w * 2, h))
    
    for i in range(min_len):
        combined = np.hstack([original_frames[i], normalized_frames[i]])
        # Add labels
        cv2.putText(combined, 'ORIGINAL', (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(combined, 'NORMALIZED', (w + 10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        out.write(combined)
    
    out.release()


def process_video(input_path, output_dir, comparison=False):
    """Process a single video with v13 normalization."""
    video_name = os.path.splitext(os.path.basename(input_path))[0]
    print(f"\n{'='*60}")
    print(f"Processing: {video_name[-20:]}")
    print(f"{'='*60}")
    
    frames, fps, width, height = load_video(input_path)
    
    # Handle invalid FPS
    if fps <= 0 or fps > 120:
        fps = REFERENCE_FPS
        print(f"  Warning: Invalid FPS detected, using {fps}fps")
    
    print(f"  Original: {len(frames)} frames @ {fps}fps ({len(frames)/fps:.2f}s)")
    
    # Compute BOTH raw and subject motion (with noise detection)
    motion_raw, noise_factor_raw = compute_motion(frames, compensate_camera=False)
    motion_subject, noise_factor = compute_motion(frames, compensate_camera=True)
    
    mean_raw = np.mean(motion_raw)
    mean_subject = np.mean(motion_subject)
    camera_contribution = mean_raw - mean_subject
    
    # Apply noise discount to raw motion (rain/grain inflates readings)
    adjusted_raw = mean_raw * noise_factor
    
    print(f"  Raw motion: {mean_raw:.3f} px/frame (total energy)")
    print(f"  Subject motion: {mean_subject:.3f} px/frame")
    print(f"  Camera motion: ~{camera_contribution:.3f} px/frame")
    if noise_factor < 0.95:
        print(f"  Noise detected: {(1-noise_factor)*100:.0f}% discount applied (rain/grain)")
        print(f"  Adjusted raw: {adjusted_raw:.3f} px/frame")
    
    # Calculate minimum acceptable tempo for this FPS
    min_acceptable = MIN_TEMPO_24FPS * (REFERENCE_FPS / fps)
    print(f"  Min acceptable ({fps:.0f}fps): {min_acceptable:.3f} px/frame")
    
    # SMART decision using RAW motion for global speed, SUBJECT for consistency
    # Apply noise discount to raw motion array (rain/grain inflates readings)
    motion_raw_adjusted = motion_raw * noise_factor
    
    beginning_raw, reference_tempo, smoothed, speed = compute_speed_curve_smart(
        motion_raw_adjusted, motion_subject, fps=fps, noise_factor=noise_factor
    )
    
    # Analyze what's happening
    ref_frames = max(10, int(fps))
    ref_frames = min(ref_frames, len(motion_raw) // 4)
    beginning_subject = np.mean(motion_subject[:ref_frames])
    ending_subject = np.mean(motion_subject[-ref_frames:])
    
    # Decision based on RAW motion (total energy) - three zones
    borderline_threshold = min_acceptable * 0.8
    
    speeds_up = ending_subject > beginning_subject * 1.2
    slows_down = ending_subject < beginning_subject * 0.8
    
    if beginning_raw < borderline_threshold:
        print(f"  STATUS: SLOW (raw {beginning_raw:.2f} < {borderline_threshold:.2f}) - full speedup")
    elif beginning_raw < min_acceptable:
        print(f"  STATUS: BORDERLINE (raw {beginning_raw:.2f}) - gentle nudge")
    elif speeds_up:
        print(f"  STATUS: GOOD tempo, but speeds up internally - smoothing")
    elif slows_down:
        print(f"  STATUS: GOOD tempo, but slows down internally - smoothing")
    else:
        print(f"  STATUS: GOOD tempo - minimal adjustment")
    
    print(f"  Reference: {reference_tempo:.3f} px/frame")
    
    avg_speed = np.mean(speed)
    print(f"  Speed adjustment: avg {avg_speed:.2f}x, range {np.min(speed):.2f}x - {np.max(speed):.2f}x")
    
    # Apply
    output_frames = apply_speed_curve(frames, speed)
    print(f"  Normalized: {len(output_frames)} frames ({len(output_frames)/fps:.2f}s)")
    
    # Analyze after
    motion_after, _ = compute_motion(output_frames, compensate_camera=True)
    mean_after = np.mean(motion_after)
    
    # Check if ending now matches beginning better
    if len(motion_after) >= ref_frames * 2:
        ending_after = np.mean(motion_after[-ref_frames:])
        print(f"  After - Ending: {ending_after:.3f} ({ending_after/beginning_subject*100:.0f}% of original beginning)")
    
    # Save normalized video
    normalized_path = os.path.join(output_dir, f"{video_name}_normalized.mp4")
    write_video(output_frames, normalized_path, fps, width, height)
    
    # Save comparison video if requested
    if comparison:
        comparison_path = os.path.join(output_dir, f"{video_name}_comparison.mp4")
        create_side_by_side(frames, output_frames, fps, comparison_path)
        print(f"  Comparison video saved!")
    
    chart_path = os.path.join(output_dir, f"{video_name}_analysis.png")
    stats = create_analysis_chart(motion_subject, motion_after, reference_tempo, speed, chart_path)
    
    print(f"  Saved to: {output_dir}/")
    
    return {
        'name': video_name[-12:],
        'pct_before': stats['pct_baseline_before'],
        'pct_after': stats['pct_baseline_after'],
        'avg_speed': stats['avg_speed']
    }


def main():
    import glob
    import argparse
    
    parser = argparse.ArgumentParser(description='Video Tempo Normalizer')
    parser.add_argument('videos', nargs='*', help='Video files to process')
    parser.add_argument('--comparison', '-c', action='store_true', 
                        help='Output side-by-side comparison videos')
    args = parser.parse_args()
    
    output_dir = "/home/pmartin/test/v13"
    os.makedirs(output_dir, exist_ok=True)
    
    # Get video files
    if args.videos:
        video_files = args.videos
    else:
        # If no arguments, look for all .mp4 files in current directory
        video_files = sorted(glob.glob("*.mp4")) + sorted(glob.glob("/home/pmartin/test/*.mp4"))
        # Remove duplicates
        video_files = sorted(list(set(video_files)))
    
    print("=" * 60)
    print("VIDEO TEMPO NORMALIZER v13.2 - Hybrid Mode")
    print("Fast videos: stay fast | Slow videos: speed up to minimum")
    print(f"Minimum: {MIN_TEMPO_24FPS:.1f} px/frame @ 24fps (scales with FPS)")
    if args.comparison:
        print("Comparison mode: ON (side-by-side videos)")
    print("=" * 60)
    print(f"Found {len(video_files)} videos")
    
    results = []
    for video_path in video_files:
        try:
            result = process_video(video_path, output_dir, comparison=args.comparison)
            results.append(result)
        except Exception as e:
            print(f"  ERROR: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("Mode: Hybrid (internal consistency + minimum tempo floor)")
    print(f"\n{'Video':<15} {'End vs Begin':<15} {'Adjustment'}")
    print("-" * 50)
    
    for r in results:
        # pct_before/after are now relative to video's own beginning
        status = "consistent" if 85 < r['pct_before'] < 115 else ("slows down" if r['pct_before'] < 85 else "speeds up")
        print(f"{r['name']:<15} {r['pct_before']:.0f}% ({status:<12}) avg {r['avg_speed']:.2f}x")
    
    print(f"\nOutputs: {output_dir}/")


if __name__ == "__main__":
    main()

