import os
import re
import subprocess
from tqdm import tqdm
from tqdm.contrib.concurrent import thread_map
import time
import sys
import traceback
import tempfile
import zipfile
import concurrent.futures
import random

# === ANSI COLOR CODES AND SCI-FI UI ELEMENTS ===
COLOR_GREEN = '\033[92m'
COLOR_YELLOW = '\033[93m'
COLOR_BLUE = '\033[94m'
COLOR_RED = '\033[91m'
RESET_COLOR = '\033[0m'
SEPARATOR = f"{COLOR_BLUE}:::{RESET_COLOR}"
HEADER_LINE = f"{COLOR_BLUE}:::{'='*54}:::{RESET_COLOR}"
STATUS_OK = f"{COLOR_GREEN}[OK]{RESET_COLOR}"
STATUS_FAIL = f"{COLOR_RED}[FAIL]{RESET_COLOR}"
ARROW_RIGHT = f"{COLOR_BLUE}>>>{RESET_COLOR}"
ARROW_LEFT = f"{COLOR_BLUE}<<<{RESET_COLOR}"
ERROR_PREFIX = f"{COLOR_RED}!!!{RESET_COLOR} ERROR:"
WARNING_PREFIX = f"{COLOR_YELLOW}>>> WARNING:{RESET_COLOR}"
INFO_PREFIX = f"{COLOR_BLUE}:::{RESET_COLOR}" # Generic info prefix

# === CONFIGURATION ===
DEFAULT_CBZ_DIR = "/storage/emulated/0/Movies/.createVid/.cbz" # Default CBZ directory
DEFAULT_ZIP_DIR = "/storage/emulated/0/Movies/.createVid/.zip" # Default ZIP directory (for archives)
DEFAULT_MUSIC_DIR = "/storage/emulated/0/Android/media/com.android.vending/.SUS/aydi" # Default Music directory
DEFAULT_OUTPUT_VIDEO_DIR = "/storage/emulated/0/Movies/.createVid/ProcessedVideos" # Default directory for output videos

# List of supported image extensions (case-insensitive)
IMAGE_EXTENSIONS = (".webp", ".jpg", ".jpeg", ".png")
# List of supported audio extensions (case-insensitive)
AUDIO_EXTENSIONS = (".mp3", ".wav", ".aac", ".flac", ".opus", ".ogg")
# List of supported archive extensions
ARCHIVE_EXTENSIONS = (".cbz", ".zip")

FPS = 2
DURATION_PER_FRAME = 1 / FPS # Calculated from FPS

# Audio Fade Configuration (in seconds)
AUDIO_FADE_IN_DURATION = 2.0
AUDIO_FADE_OUT_DURATION = 2.0 # Fade out at the end of the video duration

# Number of worker threads for parallel processing.
NUM_WORKERS = os.cpu_count() * 2 if os.cpu_count() else 4

# Regex to parse FFmpeg progress line (time)
FFMPEG_PROGRESS_REGEX = re.compile(r"frame=\s*\d+\s+.*?time=(\d{2}:\d{2}:\d{2}\.\d{2})")
FFMPEG_DURATION_REGEX = re.compile(r"Duration: (\d{2}:\d{2}:\d{2}\.\d{2})")


# === UTILITY FUNCTIONS ===

def natural_key(s):
    """
    Sort strings naturally (i.e., numerically and lexicographically).
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]

def parse_time_to_seconds(time_str):
    """
    Parses FFmpeg time string (HH:MM:SS.ms) into total seconds.
    """
    try:
        parts = time_str.split(':')
        if len(parts) != 3:
            return 0.0 # Invalid format

        h = float(parts[0])
        m = float(parts[1])
        s = float(parts[2])
        return h * 3600 + m * 60 + s
    except ValueError:
        return 0.0 # Handle potential parsing errors

def get_user_directory(prompt, default_dir):
    """Prompts the user for a directory, uses default if empty, validates."""
    while True:
        user_input = input(f"{ARROW_RIGHT} Enter {prompt} directory (empty for default: {COLOR_YELLOW}{default_dir}{RESET_COLOR})\n{ARROW_RIGHT} > ").strip()
        chosen_dir = user_input if user_input else default_dir

        if not os.path.isdir(chosen_dir):
            print(f"{ERROR_PREFIX} Directory not found: {chosen_dir}")
            create_prompt = f"{ARROW_RIGHT} Create directory '{chosen_dir}'? [{COLOR_GREEN}Y{RESET_COLOR}/{COLOR_RED}n{RESET_COLOR}]: "
            create_choice = input(create_prompt).strip().lower()
            if create_choice in ['y', 'yes', '']:
                try:
                    os.makedirs(chosen_dir)
                    print(f"{INFO_PREFIX} Directory created: {chosen_dir}")
                    return os.path.abspath(chosen_dir)
                except OSError as e:
                    print(f"{ERROR_PREFIX} Failed to create directory {chosen_dir}: {e}")
            else:
                print(f"{WARNING_PREFIX} Directory not created. Please provide a valid existing directory.")
        else:
            # Return the absolute path to be safe
            return os.path.abspath(chosen_dir)

def list_files_by_extensions(directory, extensions, include_subdirs=False):
    """Lists files in a directory matching specified extensions, sorted naturally."""
    if not os.path.isdir(directory):
         print(f"{WARNING_PREFIX} Directory not found for listing: {directory}")
         return []

    all_files = []
    if include_subdirs:
        for root, _, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(extensions):
                    all_files.append(os.path.join(root, file))
    else:
        for file in os.listdir(directory):
            full_path = os.path.join(directory, file)
            if os.path.isfile(full_path) and file.lower().endswith(extensions):
                all_files.append(full_path)

    all_files.sort(key=natural_key)
    return all_files

def get_user_selection(file_list, file_type="file", allow_range=True):
    """Displays a numbered list of files and prompts user for selection."""
    if not file_list:
        print(f"{WARNING_PREFIX} No {file_type}s found in the selected directory.")
        return []

    print(f"\n{ARROW_RIGHT} Available {file_type}s:")
    for i, file_path in enumerate(file_list):
        # Display only the basename for cleaner output
        display_name = os.path.basename(file_path)
        print(f"{INFO_PREFIX} {i+1}. {display_name}")

    selection_prompt = f"{ARROW_RIGHT} Select {file_type}(s) by number (e.g., 1,3, 5-7)" if allow_range else f"{ARROW_RIGHT} Select {file_type} by number (e.g., 1)"
    selection_prompt += f" (1-{len(file_list)}):\n{ARROW_RIGHT} > "

    selected_indices = set() # Use a set to avoid duplicates

    while True:
        user_input = input(selection_prompt).strip()
        if not user_input:
             print(f"{WARNING_PREFIX} No selection made. Please try again.")
             continue

        try:
            parts = user_input.split(',')
            valid_selection = True
            current_indices = set()

            for part in parts:
                part = part.strip()
                if '-' in part and allow_range:
                    # Handle range selection (e.g., 3-5)
                    range_parts = part.split('-')
                    if len(range_parts) != 2:
                        print(f"{WARNING_PREFIX} Invalid range format: {part}")
                        valid_selection = False
                        break
                    start_str, end_str = range_parts
                    try:
                        start = int(start_str)
                        end = int(end_str)
                        if not (1 <= start <= len(file_list) and 1 <= end <= len(file_list) and start <= end):
                            print(f"{WARNING_PREFIX} Invalid range: {part} (out of bounds or inverted)")
                            valid_selection = False
                            break
                        # Add indices from start to end (inclusive)
                        current_indices.update(range(start - 1, end)) # Convert to 0-based index

                    except ValueError:
                        print(f"{WARNING_PREFIX} Invalid number in range: {part}")
                        valid_selection = False
                        break
                else:
                    # Handle single number selection (e.g., 1)
                    try:
                        index = int(part)
                        if not (1 <= index <= len(file_list)):
                            print(f"{WARNING_PREFIX} Invalid number: {index} (out of bounds)")
                            valid_selection = False
                            break
                        # Add single index
                        current_indices.add(index - 1) # Convert to 0-based index

                    except ValueError:
                        print(f"{WARNING_PREFIX} Invalid input: '{part}'. Please use numbers or ranges.")
                        valid_selection = False
                        break

            if valid_selection and current_indices:
                if not allow_range and len(current_indices) > 1:
                    print(f"{WARNING_PREFIX} Multiple selections are not allowed for {file_type}.")
                    continue # Ask again for single selection

                selected_indices.update(current_indices) # Add validated indices to the main set
                break # Exit loop after successful parsing of all parts

            elif valid_selection and not current_indices:
                 print(f"{WARNING_PREFIX} No valid numbers or ranges found in input.")
                 # Loop will continue

        except Exception as e:
            # Catch any unexpected errors during parsing
            print(f"{ERROR_PREFIX} An unexpected error occurred during selection parsing: {e}")
            traceback.print_exc()
            valid_selection = False # Treat as invalid

        # If input was invalid, loop continues

    # Return the list of selected file paths based on sorted indices
    selected_files = [file_list[i] for i in sorted(selected_indices)]

    if not selected_files:
         print(f"{WARNING_PREFIX} No {file_type}s were successfully selected.")

    return selected_files


# === PROCESSING WORKER FUNCTIONS (Operating on a given folder) ===
# These remain largely the same, operating on files relative to a passed folder

def _verify_single_image_ffmpeg(image_name, folder):
    """
    Worker function to verify a single image using FFmpeg.
    Returns the image_name if successful, None otherwise.
    Prints error if verification fails.
    """
    image_path = os.path.join(folder, image_name)
    cmd = [
        "ffmpeg",
        "-v", "error",
        "-i", image_path,
        "-vf", "scale=1:1", # Apply a dummy filter to force decoding/processing
        "-f", "null",
        "-"
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            error_output = result.stderr.decode('utf-8', errors='ignore')
            sys.stderr.write(f"{ERROR_PREFIX} Verification failed for {os.path.basename(image_path)}:\n{error_output.strip()}\n")
            return None

        return image_name

    except FileNotFoundError:
        sys.stderr.write(f"{ERROR_PREFIX} FFmpeg executable not found during verification of {os.path.basename(image_path)}. Aborting verification.\n")
        return None
    except Exception as e:
        sys.stderr.write(f"{ERROR_PREFIX} Unexpected error during verification of {os.path.basename(image_path)}: {e}\n")
        return None

def _resave_single_image_magick(image_name, folder):
    """
    Worker function to resave a single image using ImageMagick.
    Overwrites the original file if successful.
    Returns the image_name if successful, None otherwise.
    Prints error if resaving fails.
    """
    original_path = os.path.join(folder, image_name)
    temp_path = None

    try:
        suffix = os.path.splitext(image_name)[1]
        fd, temp_path = tempfile.mkstemp(suffix=suffix, dir=folder)
        os.close(fd)

        magick_cmd = [
            "magick",
            original_path,
            "+profile", "*", # Remove all metadata profiles
            temp_path
        ]

        result = subprocess.run(magick_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        os.replace(temp_path, original_path)

        return image_name

    except FileNotFoundError:
        sys.stderr.write(f"{ERROR_PREFIX} ImageMagick 'magick' executable not found during resaving of {os.path.basename(original_path)}. Aborting resaving.\n")
        return None

    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"{ERROR_PREFIX} ImageMagick resaving failed for {os.path.basename(original_path)}:\n{e.stderr.decode('utf-8', errors='ignore').strip()}\n")
        if temp_path and os.path.exists(temp_path):
             os.remove(temp_path)
        return None

    except Exception as e:
        sys.stderr.write(f"{ERROR_PREFIX} Unexpected error during resaving of {os.path.basename(original_path)}: {e}\n")
        if temp_path and os.path.exists(temp_path):
             os.remove(temp_path)
        return None

# === CORE PROCESSING FUNCTIONS ===

def extract_archive(archive_path, destination_folder, extensions):
    """
    Extracts image files from a CBZ or ZIP archive to a destination folder.
    Returns a list of names (relative to destination_folder) of extracted image files, sorted naturally.
    """
    print(f"{ARROW_RIGHT} Initiating archive extraction protocol for {os.path.basename(archive_path)}")
    extracted_files_count = 0
    try:
        if archive_path.lower().endswith(".cbz") or archive_path.lower().endswith(".zip"):
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                all_members = zip_ref.infolist()
                image_members = [
                    m for m in all_members
                    if not m.is_dir() and m.filename.lower().endswith(extensions)
                ]
                if not image_members:
                    raise FileNotFoundError(f"No image files ({', '.join(extensions)}) found in the archive.")

                print(f"{INFO_PREFIX} Archive contains {len(image_members)} potential image files.")
                for member in tqdm(image_members, desc=f"{ARROW_RIGHT} Transferring archive components", unit="file", ncols=100):
                    zip_ref.extract(member, destination_folder)
                    extracted_files_count += 1
        else:
            # This function should only be called with supported archive types, but as a safeguard:
            raise ValueError(f"{ERROR_PREFIX} Unsupported archive format: {archive_path}")

    except FileNotFoundError as e:
        # This specific FileNotFoundError for archive_path is handled in main
        # Re-raising might not be necessary here depending on desired flow, but keep for clarity
        raise FileNotFoundError(f"{ERROR_PREFIX} Source archive file not found at specified path: {archive_path}")
    except zipfile.BadZipFile:
        raise zipfile.BadZipFile(f"{ERROR_PREFIX} Invalid or corrupted archive file: {archive_path}")
    except Exception as e:
        raise Exception(f"{ERROR_PREFIX} An error occurred during archive extraction: {e}")

    # After extraction, collect and sort the actual file paths (relative to destination_folder)
    found_image_paths_relative = []
    for root, _, files in os.walk(destination_folder):
        for file in files:
            if file.lower().endswith(extensions):
                rel_path = os.path.relpath(os.path.join(root, file), destination_folder)
                found_image_paths_relative.append(rel_path)

    found_image_paths_relative.sort(key=natural_key)

    if not found_image_paths_relative:
        raise FileNotFoundError(f"{ERROR_PREFIX} No image files found in the extracted temporary directory ({destination_folder}) after scanning and sorting.")

    print(f"{ARROW_LEFT} Extraction protocol complete. {extracted_files_count} files extracted, {len(found_image_paths_relative)} images prepared.")
    return found_image_paths_relative


def write_ffmpeg_input_list(images_relative_paths, base_folder, duration_per_frame):
    """
    Write the FFmpeg input list file with images and duration for each.
    'images_relative_paths' list contains paths relative to 'base_folder'.
    """
    input_list_path = os.path.join(base_folder, "ffmpeg_input.txt")
    with open(input_list_path, "w") as f:
        for img_rel_path in images_relative_paths:
            # FFmpeg needs forward slashes and proper escaping for spaces/special characters
            full_path = os.path.join(base_folder, img_rel_path).replace("\\", "/")
            # Escape single quotes within the path itself to prevent misinterpretation by FFmpeg's concat demuxer
            escaped_full_path = full_path.replace("'", "'\\''")
            f.write(f"file '{escaped_full_path}'\n")
            f.write(f"duration {duration_per_frame:.4f}\n")
        # The last frame needs to be listed again to maintain its duration
        if images_relative_paths:
             full_path = os.path.join(base_folder, images_relative_paths[-1]).replace("\\", "/")
             escaped_full_path = full_path.replace("'", "'\\''")
             f.write(f"file '{escaped_full_path}'\n")
    return input_list_path


def run_ffmpeg(input_list_path, audio_file, output_file, fps, num_input_images, duration_per_frame, fade_in_dur, fade_out_dur):
    """
    Run the FFmpeg command to combine images and audio into a video.
    Includes audio fade-in/out and applies scaling/blurring for background.
    Parses FFmpeg stderr for progress (based on video frames) and updates a tqdm bar.
    Discards non-progress output.
    """
    # Ensure output directory exists
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True) # Use exist_ok=True to avoid error if it already exists
            print(f"{INFO_PREFIX} Creating output directory: {output_dir}")
        except OSError as e:
            print(f"{WARNING_PREFIX} Error creating output directory {output_dir}: {e}")
            print(f"{INFO_PREFIX} Attempting to save in the current directory instead.")
            output_file = os.path.basename(output_file) # Fallback to current dir


    cmd = [
        "ffmpeg",
        "-y", # Overwrite output files without asking
        "-hide_banner", # Hide FFmpeg version and build info
        "-loglevel", "info", # Log INFO level messages, useful for debugging and progress
        "-f", "concat",
        "-safe", "0", # Allow absolute paths in the concat list
        "-i", input_list_path,
        "-stream_loop", "-1", # Loop audio indefinitely if it's shorter than video
        "-i", audio_file,
        "-filter_complex",
        # Explanation of the filter_complex:
        # [0:v] -> refers to the video stream from the first input (the concat list of images)
        # split=2[bg][fg] -> splits the video stream into two identical copies, named 'bg' (background) and 'fg' (foreground)
        # [bg]scale=1280:720,boxblur=10:1[blurred] -> takes the 'bg' stream, scales it to 1280x720, applies a box blur of 10 pixels with a sigma of 1, and labels the output 'blurred'
        # [fg]scale=-1:720[fgscaled] -> takes the 'fg' stream, scales it to a height of 720 pixels while maintaining aspect ratio for width (-1), and labels it 'fgscaled'
        # [blurred][fgscaled]overlay=(W-w)/2:(H-h)/2,setdar=16/9[v] -> overlays the 'fgscaled' video onto the 'blurred' video.
        #   (W-w)/2:(H-h)/2 centers the foreground video on the background.
        #   W,H are width/height of background; w,h are width/height of foreground.
        #   setdar=16/9 -> ensures the output video has a 16:9 display aspect ratio.
        #   [v] -> labels the final video output stream 'v'.
        "[0:v]split=2[bg][fg];[bg]scale=1280:720,boxblur=10:1[blurred];[fg]scale=-1:720[fgscaled];[blurred][fgscaled]overlay=(W-w)/2:(H-h)/2,setdar=16/9[v]",
        "-map", "[v]", # Map the processed video stream to the output
        "-map", "1:a", # Map the audio stream from the second input to the output
        "-c:v", "libx264", # Use H.264 codec for video
        "-r", str(fps), # Set the output frame rate
        "-pix_fmt", "yuv420p", # Pixel format for broad compatibility
        "-shortest", # Finish encoding when the shortest input stream ends (audio in this case, potentially)
    ]

    # Calculate expected video duration based on the number of unique images and duration per frame
    # FFmpeg concat list has num_images + 1 lines if last frame is repeated, or num_images if not.
    # Our write_ffmpeg_input_list includes the last frame twice, so num_input_images + 1 entries.
    expected_video_duration = (num_input_images + 1) * duration_per_frame

    # --- Add Audio Fade Filter ---
    actual_fade_in_duration = min(fade_in_dur, expected_video_duration)
    actual_fade_out_duration = min(fade_out_dur, expected_video_duration)
    # Start fade out at a time that ensures it completes by the end of the video duration
    fade_out_start_time = max(0, expected_video_duration - actual_fade_out_duration)

    audio_filters = []
    if actual_fade_in_duration > 0:
        audio_filters.append(f"afade=t=in:st=0:d={actual_fade_in_duration:.4f}")
    if actual_fade_out_duration > 0 and fade_out_start_time >= 0:
         # Ensure fade out doesn't start before the video ends
         audio_filters.append(f"afade=t=out:st={fade_out_start_time:.4f}:d={actual_fade_out_duration:.4f}")

    if audio_filters:
        cmd.extend(["-af", ",".join(audio_filters)])
        print(f"{INFO_PREFIX} Applying audio filters: {','.join(audio_filters)}")

    cmd.append(output_file)


    print(HEADER_LINE)
    print(f"{ARROW_RIGHT} Executing core processing sequence (FFmpeg)")
    # print("Command:", cmd) # Uncomment for detailed command debugging
    print(HEADER_LINE)


    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1 # Line buffering
    )

    # --- Parse FFmpeg stderr for progress ---
    total_audio_duration_seconds = 0.0
    progress_bar = None

    print(f"{INFO_PREFIX} System initializing FFmpeg process...")

    try:
        while True:
            line = process.stderr.readline()
            if not line and process.poll() is not None:
                # Process finished, read any final discardable output
                # remaining_output, _ = process.communicate() # Not needed if we only parse stderr
                break # Exit loop if process has exited and no more lines

            if not line: # If line is empty but process not exited, wait a bit
                time.sleep(0.01)
                continue

            # Parse for detected audio duration
            duration_match = FFMPEG_DURATION_REGEX.search(line)
            if duration_match:
                 duration_str = duration_match.group(1)
                 total_audio_duration_seconds = parse_time_to_seconds(duration_str)
                 print(f"{INFO_PREFIX} Detected audio duration: {duration_str} ({total_audio_duration_seconds:.2f} seconds)")
                 continue

            # Parse for frame/time progress
            progress_match = FFMPEG_PROGRESS_REGEX.search(line)
            if progress_match:
                 # Initialize tqdm bar only when first progress line is encountered
                 if progress_bar is None and expected_video_duration > 0:
                      print(f"\n{INFO_PREFIX} Encoding stream initiated.")
                      progress_bar = tqdm(total=expected_video_duration, desc=f"{ARROW_RIGHT} Encoding Progress", unit="s", unit_scale=True, ncols=100, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]')

                 if progress_bar is not None:
                    current_time_str = progress_match.group(1)
                    current_seconds = parse_time_to_seconds(current_time_str)
                    # Update progress bar only if current time is ahead of its recorded position
                    update_delta = max(0, current_seconds - progress_bar.n)
                    if update_delta > 0 or current_seconds > progress_bar.n:
                         progress_bar.update(update_delta)
                    continue

            # Discard any other line that doesn't match progress or duration
            pass


        # --- Process finished ---
        if progress_bar:
             # Ensure the progress bar reaches 100% if the video duration was calculable
             if expected_video_duration > 0:
                 progress_bar.n = expected_video_duration
                 progress_bar.refresh()
             progress_bar.close()
        else:
             print(f"\n{WARNING_PREFIX} FFmpeg encoding progress bar was not displayed. Check FFmpeg output above for details.")

        returncode = process.wait() # Wait for the process to truly finish and get its return code

        if returncode != 0:
            print(f"\n{ERROR_PREFIX} Core processing sequence terminated with errors. FFmpeg exited with code {returncode}.")
            # Attempt to read remaining stderr if any, for more error context
            remaining_stderr = process.stderr.read()
            if remaining_stderr:
                 print(f"{INFO_PREFIX} FFmpeg stderr output:\n{remaining_stderr.strip()}")
            raise subprocess.CalledProcessError(returncode, cmd)
        else:
            print(f"\n{ARROW_LEFT} Core processing sequence complete. Status: {STATUS_OK}")
            print(HEADER_LINE)


    except Exception as e:
        # Ensure progress bar is closed if an exception occurs
        if progress_bar and not progress_bar.closed:
            progress_bar.close()

        # If the process is still running, try to terminate it
        if process.poll() is None:
             try:
                 process.terminate() # Send SIGTERM
                 process.wait(timeout=2) # Wait a short time for it to exit
             except subprocess.TimeoutExpired:
                 process.kill() # If still running, force kill (SIGKILL)
             except Exception as kill_err:
                 print(f"{WARNING_PREFIX} Error terminating FFmpeg process: {kill_err}")

        print(f"\n{ERROR_PREFIX} An unexpected system error occurred during core processing: {e}")
        traceback.print_exc()
        raise # Re-raise the exception to be caught by the caller

# === FUNCTION TO PROCESS A SINGLE ARCHIVE ===

def process_single_archive(archive_file_path, audio_file_path, fps, duration_per_frame, image_extensions, audio_fade_in_duration, audio_fade_out_duration, skip_magick, output_video_dir):
    """
    Handles the full processing pipeline for a single CBZ or ZIP archive.
    Returns True on success, False on recoverable failure (skips to next archive).
    Raises unrecoverable exceptions (like FFmpeg not found).
    """
    try:
        print(f"\n{HEADER_LINE}")
        print(f"{ARROW_RIGHT} Processing Archive: {os.path.basename(archive_file_path)}")
        print(HEADER_LINE)

        archive_dir = os.path.dirname(archive_file_path)
        archive_base_name = os.path.basename(archive_file_path)
        output_base_name, _ = os.path.splitext(archive_base_name)
        # Sanitize the output filename to be safe for file systems
        output_base_name = re.sub(r'[^\w\s.-]', '', output_base_name)
        output_base_name = output_base_name.strip()
        if not output_base_name:
             output_base_name = "processed_video" # Fallback name

        # Determine the output path
        # If a specific output_video_dir was provided, use it. Otherwise, use the archive's directory.
        final_output_dir = output_video_dir if output_video_dir else archive_dir
        output_file = os.path.join(final_output_dir, f"{output_base_name}.mp4")

        print(f"{INFO_PREFIX} Destination video filename: {os.path.basename(output_file)}")
        print(f"{INFO_PREFIX} Destination directory: {os.path.dirname(output_file)}\n")


        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"{ARROW_RIGHT} Allocating temporary processing unit: {temp_dir}")

            print(HEADER_LINE)
            try:
                 # Use the generic extract_archive function
                 extracted_image_paths_relative = extract_archive(archive_file_path, temp_dir, image_extensions)
                 print(f"{INFO_PREFIX} {len(extracted_image_paths_relative)} image files extracted and sorted.")
            except (FileNotFoundError, zipfile.BadZipFile, Exception) as e:
                 print(f"{ERROR_PREFIX} Extraction failed: {e}")
                 return False

            print(HEADER_LINE)

            if not extracted_image_paths_relative:
                 print(f"{ERROR_PREFIX} No usable images found in archive after extraction and initial sorting.")
                 return False

            images_after_resave_relative = extracted_image_paths_relative

            magick_available = False
            try:
                subprocess.run(["magick", "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                magick_available = True
            except (FileNotFoundError, subprocess.CalledProcessError):
                pass

            if magick_available and not skip_magick:
                print(HEADER_LINE)
                print(f"{ARROW_RIGHT} Initiating Image Data Reconstruction Protocol...")
                # Use thread_map for parallel processing of images
                resave_results_relative = thread_map(
                    lambda img_name: _resave_single_image_magick(img_name, temp_dir),
                    images_after_resave_relative,
                    max_workers=NUM_WORKERS,
                    desc=f"{ARROW_RIGHT} Data Stream Reconstruction",
                    unit="image",
                    ncols=100
                )
                # Filter out None results (failed resaves)
                images_after_resave_relative = [img_name for img_name in resave_results_relative if img_name is not None]

                print(f"\n{ARROW_LEFT} Reconstruction protocol complete. {len(images_after_resave_relative)} images ready for verification.")
                if len(images_after_resave_relative) < len(extracted_image_paths_relative):
                     print(f"{WARNING_PREFIX} {len(extracted_image_paths_relative) - len(images_after_resave_relative)} images were identified as unstable and excluded by reconstruction.")
                print(HEADER_LINE)
            elif skip_magick:
                print(HEADER_LINE)
                print(f"{INFO_PREFIX} Image Data Reconstruction Protocol skipped by user.")
                print(HEADER_LINE)


            if not images_after_resave_relative:
                 print(f"{ERROR_PREFIX} No images available after attempting ImageMagick resave.")
                 return False

            print(HEADER_LINE)
            print(f"{ARROW_RIGHT} Initiating Data Stream Integrity Verification Protocol...")
            # Use thread_map for parallel verification
            verify_results_relative = thread_map(
                 lambda img_name: _verify_single_image_ffmpeg(img_name, temp_dir),
                 images_after_resave_relative,
                 max_workers=NUM_WORKERS,
                 desc=f"{ARROW_RIGHT} Verifying Image Data",
                 unit="image",
                 ncols=100
            )
            # Filter out None results (failed verifications)
            final_images_for_ffmpeg_relative = [img_name for img_name in verify_results_relative if img_name is not None]

            print(f"\n{ARROW_LEFT} Verification protocol complete. {len(final_images_for_ffmpeg_relative)} data streams cleared for processing.")
            if len(final_images_for_ffmpeg_relative) < len(images_after_resave_relative):
                print(f"{WARNING_PREFIX} {len(images_after_resave_relative) - len(final_images_for_ffmpeg_relative)} data streams failed integrity check and were excluded.")
            print(HEADER_LINE)


            if not final_images_for_ffmpeg_relative:
                print(f"{ERROR_PREFIX} No usable images found after all checks (ImageMagick resave attempt and FFmpeg verification).")
                return False

            print(HEADER_LINE)
            print(f"{ARROW_RIGHT} Generating data manifest...")
            input_list_path = write_ffmpeg_input_list(final_images_for_ffmpeg_relative, temp_dir, DURATION_PER_FRAME)
            print(f"{INFO_PREFIX} Manifest location: {input_list_path}")
            print(f"{ARROW_LEFT} Data manifest generation complete.")
            print(HEADER_LINE)

            # Run FFmpeg for the core video creation
            run_ffmpeg(input_list_path, audio_file_path, output_file, fps, len(final_images_for_ffmpeg_relative), DURATION_PER_FRAME, AUDIO_FADE_IN_DURATION, AUDIO_FADE_OUT_DURATION)

            # --- Move processed files ---
            print(HEADER_LINE)
            print(f"{ARROW_RIGHT} Initiating file organization protocol...")

            # Ensure the video output directory exists
            if not os.path.exists(final_output_dir):
                try:
                    os.makedirs(final_output_dir, exist_ok=True)
                    print(f"{INFO_PREFIX} Created output video directory: {final_output_dir}")
                except OSError as e:
                    print(f"{ERROR_PREFIX} Failed to create output video directory {final_output_dir}: {e}")
                    # If we can't create the output dir, we can't move the video. Report failure.
                    print(f"{WARNING_PREFIX} Unable to organize files. Video saved at: {output_file}")
                    return False # Treat as a partial failure due to organization

            # Move the created video file to the designated output directory
            if output_file != os.path.join(final_output_dir, os.path.basename(output_file)): # If output_file is not already in final_output_dir
                try:
                    final_video_path = os.path.join(final_output_dir, os.path.basename(output_file))
                    os.rename(output_file, final_video_path)
                    print(f"{INFO_PREFIX} Moved video to: {os.path.basename(final_video_path)}")
                    output_file = final_video_path # Update output_file to its new location
                except OSError as e:
                    print(f"{ERROR_PREFIX} Failed to move video file {os.path.basename(output_file)} to {final_output_dir}: {e}")
                    print(f"{WARNING_PREFIX} Video remains at its original location: {output_file}")
                    # Continue processing, but log the failure.

            # Move the original archive file to the CBZ/ZIP directory
            if archive_dir != final_output_dir: # If original archive dir is different from video dir
                # Determine target directory for archive based on extension
                target_archive_dir = None
                if archive_file_path.lower().endswith(".cbz"):
                    # Ensure .cbz directory exists
                    target_archive_dir = DEFAULT_CBZ_DIR # Assume this is already set by user input or default
                elif archive_file_path.lower().endswith(".zip"):
                    # Ensure .zip directory exists
                    target_archive_dir = DEFAULT_ZIP_DIR # Assume this is already set by user input or default

                if target_archive_dir:
                    if not os.path.exists(target_archive_dir):
                        try:
                            os.makedirs(target_archive_dir, exist_ok=True)
                            print(f"{INFO_PREFIX} Created archive directory: {target_archive_dir}")
                        except OSError as e:
                            print(f"{ERROR_PREFIX} Failed to create archive directory {target_archive_dir}: {e}")
                            print(f"{WARNING_PREFIX} Original archive remains at: {archive_file_path}")
                            # Continue processing, but log the failure.

                    if target_archive_dir and os.path.exists(target_archive_dir):
                        try:
                            new_archive_path = os.path.join(target_archive_dir, os.path.basename(archive_file_path))
                            os.rename(archive_file_path, new_archive_path)
                            print(f"{INFO_PREFIX} Moved archive to: {os.path.basename(new_archive_path)}")
                            archive_file_path = new_archive_path # Update original path for clarity if needed later
                        except OSError as e:
                            print(f"{ERROR_PREFIX} Failed to move archive file {os.path.basename(archive_file_path)} to {target_archive_dir}: {e}")
                            print(f"{WARNING_PREFIX} Original archive remains at: {archive_file_path}")
                            # Continue processing, but log the failure.
                else:
                    print(f"{WARNING_PREFIX} Could not determine target directory for archive '{os.path.basename(archive_file_path)}'. Original archive remains at: {archive_file_path}")
            else:
                print(f"{INFO_PREFIX} Archive and video output directories are the same. No archive move necessary.")


            print(f"{ARROW_LEFT} File organization protocol complete.")
            print(HEADER_LINE)


        print(f"\n{ARROW_LEFT} Temporary processing unit deallocated for {os.path.basename(archive_file_path)}.")
        return True

    except (FileNotFoundError, zipfile.BadZipFile, subprocess.CalledProcessError) as e:
        if isinstance(e, FileNotFoundError) or isinstance(e, zipfile.BadZipFile):
             print(f"\n{ERROR_PREFIX} File System or Archive Error during processing of {os.path.basename(archive_file_path)}: {e}")
        elif isinstance(e, subprocess.CalledProcessError):
             print(f"\n{ERROR_PREFIX} External Process Execution Failure during processing of {os.path.basename(archive_file_path)}.")
             failed_cmd = getattr(e, 'cmd', 'Unknown command')
             print(f"{INFO_PREFIX} Command: {' '.join(map(str, failed_cmd)) if isinstance(failed_cmd, list) else failed_cmd}")
             print(f"{INFO_PREFIX} Return Code: {e.returncode}")
        print(f"\n{WARNING_PREFIX} Skipping {os.path.basename(archive_file_path)} due to the above error.")
        print(HEADER_LINE)
        return False

    except Exception as e:
        print(f"\n{ERROR_PREFIX} An unexpected system error occurred during processing of {os.path.basename(archive_file_path)}: {e}")
        traceback.print_exc()
        print(f"\n{WARNING_PREFIX} Skipping {os.path.basename(archive_file_path)} due to the above error.")
        print(HEADER_LINE)
        return False


# === MAIN EXECUTION ===
def main():
    print(HEADER_LINE)
    print(f"{COLOR_BLUE}        SYSTEM STATUS INQUIRY{RESET_COLOR}")
    print(HEADER_LINE)

    print(f"{ARROW_RIGHT} Checking system dependencies...")
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"{INFO_PREFIX} FFmpeg module detected. {STATUS_OK}")
    except (FileNotFoundError, subprocess.CalledProcessError):
         print(f"{INFO_PREFIX} FFmpeg module not found. {STATUS_FAIL}")
         print(f"{ERROR_PREFIX} Please ensure FFmpeg is installed and accessible in your system's PATH.")
         sys.exit(1)

    magick_available = False
    try:
        subprocess.run(["magick", "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"{INFO_PREFIX} ImageMagick module detected. Resaving protocol available. {STATUS_OK}")
        magick_available = True
    except (FileNotFoundError, subprocess.CalledProcessError):
         print(f"{INFO_PREFIX} ImageMagick module not found. Resaving protocol will be skipped. {STATUS_OK}")

    skip_magick_reconstruction = False
    if magick_available:
        while True:
            prompt = f"{ARROW_RIGHT} Run Image Reconstruction Protocol (recommended for stability)? [{COLOR_GREEN}Y{RESET_COLOR}/{COLOR_RED}n{RESET_COLOR}]: "
            user_choice = input(prompt).strip().lower()
            if user_choice in ['y', 'yes', '']:
                skip_magick_reconstruction = False
                print(f"{INFO_PREFIX} Image Reconstruction Protocol is {COLOR_GREEN}ENABLED{RESET_COLOR}.")
                break
            elif user_choice in ['n', 'no']:
                skip_magick_reconstruction = True
                print(f"{INFO_PREFIX} Image Reconstruction Protocol is {COLOR_RED}DISABLED{RESET_COLOR}.")
                break
            else:
                print(f"{WARNING_PREFIX} Invalid input. Please enter 'y' or 'n'.")
    else:
        skip_magick_reconstruction = True


    print(f"{ARROW_LEFT} Dependency check complete.")

    try:
        print(HEADER_LINE)
        print(f"{COLOR_BLUE}        OPERATION: ARCHIVE to Video Conversion Batch{RESET_COLOR}")
        print(HEADER_LINE)

        # --- Get Archive Files ---
        # Ask for both CBZ and ZIP directories, or use defaults
        cbz_dir = get_user_directory("CBZ archive", DEFAULT_CBZ_DIR)
        zip_dir = get_user_directory("ZIP archive", DEFAULT_ZIP_DIR)
        output_video_dir = get_user_directory("output video", DEFAULT_OUTPUT_VIDEO_DIR)


        # Combine and list all archives
        all_archive_files = []
        all_archive_files.extend(list_files_by_extensions(cbz_dir, (".cbz",)))
        all_archive_files.extend(list_files_by_extensions(zip_dir, (".zip",)))

        # Sort the combined list of archives naturally
        all_archive_files.sort(key=natural_key)

        if not all_archive_files:
            print(f"{ERROR_PREFIX} No CBZ or ZIP archives found in the specified directories.")
            print(HEADER_LINE)
            sys.exit(0)

        # Present all found archives for selection
        selected_archive_paths = get_user_selection(all_archive_files, file_type="archive (CBZ/ZIP)", allow_range=True)

        if not selected_archive_paths:
            print(f"\n{WARNING_PREFIX} No archives selected. Operation cancelled.")
            print(HEADER_LINE)
            sys.exit(0)

        print(f"\n{INFO_PREFIX} {len(selected_archive_paths)} archive file(s) selected for processing.")

        # --- Get Audio File ---
        print(HEADER_LINE)
        music_dir = get_user_directory("music", DEFAULT_MUSIC_DIR)
        # List music files, scanning subdirectories
        music_files_all = list_files_by_extensions(music_dir, AUDIO_EXTENSIONS, include_subdirs=True)

        if not music_files_all:
             print(f"{ERROR_PREFIX} No audio files found in the music directory: {music_dir}")
             print(HEADER_LINE)
             sys.exit(0)

        # Prompt user to select a single audio file
        selected_audio_paths = get_user_selection(music_files_all, file_type="audio file", allow_range=False)

        if not selected_audio_paths:
             print(f"\n{WARNING_PREFIX} No audio file selected. Operation cancelled.")
             print(HEADER_LINE)
             sys.exit(0)

        audio_file_path = selected_audio_paths[0] # get_user_selection ensures only one if allow_range=False
        print(f"\n{INFO_PREFIX} Selected audio file: {os.path.basename(audio_file_path)}")

        if not os.path.exists(audio_file_path):
             # This shouldn't happen if selection worked, but double check
             raise FileNotFoundError(f"{ERROR_PREFIX} Selected audio file not found at specified path: {audio_file_path}")

        print(f"{INFO_PREFIX} Target frame rate: {FPS} FPS")
        print(f"{INFO_PREFIX} Duration per frame: {DURATION_PER_FRAME:.2f} s")
        if AUDIO_FADE_IN_DURATION > 0 or AUDIO_FADE_OUT_DURATION > 0:
             print(f"{INFO_PREFIX} Audio fade-in duration: {AUDIO_FADE_IN_DURATION:.2f} s")
             print(f"{INFO_PREFIX} Audio fade-out duration: {AUDIO_FADE_OUT_DURATION:.2f} s")
        else:
             print(f"{INFO_PREFIX} Audio fading: Disabled")
        print(HEADER_LINE)


        # --- Process Selected Archives ---
        print(f"\n{ARROW_RIGHT} Initiating batch processing sequence for {len(selected_archive_paths)} archive file(s)...")
        print(HEADER_LINE)

        successful_count = 0
        failed_files = []

        # If multiple archives are selected, pick a random audio file for each
        if len(selected_archive_paths) > 1:
            print(f"{INFO_PREFIX} Multiple archives selected. A random audio file will be chosen for each.")
            # Ensure we have enough unique music files to pick from, or reuse if not
            available_music_files = music_files_all[:] # Create a copy
            if len(available_music_files) < len(selected_archive_paths):
                print(f"{WARNING_PREFIX} Not enough unique audio files for each archive. Audio files will be reused.")
                # If there are fewer music files than archives, we'll cycle through them.
                pass # The logic below handles cycling.

        for i, archive_path in enumerate(selected_archive_paths):
             print(f"\n{COLOR_BLUE}--- Processing File {i+1} of {len(selected_archive_paths)} ---{RESET_COLOR}")

             # Select audio file: either the single selected one, or a random one if multiple archives
             current_audio_file = audio_file_path
             if len(selected_archive_paths) > 1:
                 if available_music_files:
                     current_audio_file = random.choice(available_music_files)
                 else:
                     # This case should ideally not happen if music_files_all was populated
                     print(f"{ERROR_PREFIX} No music files available to pick from for archive {os.path.basename(archive_path)}. Using original selection.")
                     current_audio_file = audio_file_path


             success = process_single_archive(
                 archive_path,
                 current_audio_file, # Use the potentially randomized audio file
                 FPS,
                 DURATION_PER_FRAME,
                 IMAGE_EXTENSIONS,
                 AUDIO_FADE_IN_DURATION,
                 AUDIO_FADE_OUT_DURATION,
                 skip_magick_reconstruction,
                 output_video_dir # Pass the target video output directory
             )
             if success:
                 successful_count += 1
             else:
                 failed_files.append(os.path.basename(archive_path))
             print(f"{COLOR_BLUE}--- Finished File {i+1} of {len(selected_archive_paths)} ---{RESET_COLOR}")


        # --- Batch Summary ---
        print(HEADER_LINE)
        print(f"{COLOR_BLUE}        BATCH PROCESSING SUMMARY{RESET_COLOR}")
        print(HEADER_LINE)
        print(f"{INFO_PREFIX} Total archives selected: {len(selected_archive_paths)}")
        print(f"{INFO_PREFIX} Successfully processed: {successful_count} {STATUS_OK}")
        print(f"{INFO_PREFIX} Failed to process: {len(failed_files)} {STATUS_FAIL}")

        if failed_files:
            print(f"{WARNING_PREFIX} Failed archives:")
            for f in failed_files:
                print(f"{SEPARATOR} - {f}")

        print(HEADER_LINE)


    except (FileNotFoundError, zipfile.BadZipFile, subprocess.CalledProcessError) as e:
        if isinstance(e, FileNotFoundError) or isinstance(e, zipfile.BadZipFile):
             print(f"\n{ERROR_PREFIX} File System or Archive Error: {e}")
        elif isinstance(e, subprocess.CalledProcessError):
             print(f"\n{ERROR_PREFIX} External Process Execution Failure.")
             failed_cmd = getattr(e, 'cmd', 'Unknown command')
             print(f"{INFO_PREFIX} Command: {' '.join(map(str, failed_cmd)) if isinstance(failed_cmd, list) else failed_cmd}")
             print(f"{INFO_PREFIX} Return Code: {e.returncode}")
             print(f"{INFO_PREFIX} Review execution flow and process output above.")

        print(HEADER_LINE)
        sys.exit(1)

    except Exception as e:
        print(f"\n{ERROR_PREFIX} An unexpected system error occurred: {e}")
        traceback.print_exc()
        print(HEADER_LINE)
        sys.exit(1)

    print()


if __name__ == "__main__":
    main()
