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
DEFAULT_CBZ_DIR = "/storage/67DC-DBA3/Android/media/com.google.android.keep/.~```~_/.•••```/local/extra" # Default CBZ directory
DEFAULT_MUSIC_DIR = "/storage/emulated/0/Android/media/com.android.vending/.SUS/aydi" # Default Music directory

# List of supported image extensions (case-insensitive)
IMAGE_EXTENSIONS = (".webp", ".jpg", ".jpeg", ".png")
# List of supported audio extensions (case-insensitive)
AUDIO_EXTENSIONS = (".mp3", ".wav", ".aac", ".flac", ".ogg")

FPS = 4
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
        user_input = input(f"{ARROW_RIGHT} Enter {prompt} directory (empty for default): {COLOR_YELLOW}{default_dir}{RESET_COLOR}\n{ARROW_RIGHT} > ").strip()
        chosen_dir = user_input if user_input else default_dir

        if not os.path.isdir(chosen_dir):
            print(f"{ERROR_PREFIX} Directory not found: {chosen_dir}")
        else:
            # Return the absolute path to be safe
            return os.path.abspath(chosen_dir)

def list_files_by_extensions(directory, extensions):
    """Lists files in a directory matching specified extensions, sorted naturally."""
    if not os.path.isdir(directory):
         return [] # Should not happen if get_user_directory is used first

    files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f)) and f.lower().endswith(extensions)]
    files.sort(key=natural_key)
    return files

def get_user_selection(file_list, file_type="file", allow_range=True):
    """Displays a numbered list of files and prompts user for selection."""
    if not file_list:
        print(f"{WARNING_PREFIX} No {file_type}s found in the selected directory.")
        return []

    print(f"\n{ARROW_RIGHT} Available {file_type}s:")
    for i, file_name in enumerate(file_list):
        # Show relative path if files are not directly in the selected dir (e.g. music in subfolders)
        display_name = os.path.basename(file_name) # Default to basename
        # Could add logic here to show parent folder if needed, but basename is usually clean
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

    # Return the list of selected files based on sorted indices
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
            "+profile", "*",
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

def extract_cbz(cbz_path, destination_folder, extensions):
    """
    Extracts image files from a CBZ archive to a destination folder.
    Returns a list of names (relative to destination_folder) of extracted image files, sorted naturally.
    """
    print(f"{ARROW_RIGHT} Initiating CBZ extraction protocol for {os.path.basename(cbz_path)}")
    try:
        with zipfile.ZipFile(cbz_path, 'r') as zip_ref:
            image_members = [
                m for m in zip_ref.infolist()
                if not m.is_dir() and m.filename.lower().endswith(extensions)
            ]
            if not image_members:
                 raise FileNotFoundError(f"No image files ({', '.join(extensions)}) found in the CBZ archive.")

            print(f"{INFO_PREFIX} Archive contains {len(image_members)} potential image files.")
            for member in tqdm(image_members, desc=f"{ARROW_RIGHT} Transferring archive components", unit="file", ncols=100):
                 zip_ref.extract(member, destination_folder)

    except FileNotFoundError:
        # This specific FileNotFoundError for cbz_path is already checked in main
        # Re-raising might not be necessary here depending on desired flow, but keep for clarity
        raise FileNotFoundError(f"{ERROR_PREFIX} Source CBZ file not found at specified path: {cbz_path}")
    except zipfile.BadZipFile:
        raise zipfile.BadZipFile(f"{ERROR_PREFIX} Invalid or corrupted CBZ file: {cbz_path}")
    except Exception as e:
        raise Exception(f"{ERROR_PREFIX} An error occurred during CBZ extraction: {e}")

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

    print(f"{ARROW_LEFT} Extraction protocol complete. {len(found_image_paths_relative)} images prepared.")
    return found_image_paths_relative


def write_ffmpeg_input_list(images_relative_paths, base_folder, duration_per_frame):
    """
    Write the FFmpeg input list file with images and duration for each.
    'images_relative_paths' list contains paths relative to 'base_folder'.
    """
    input_list_path = os.path.join(base_folder, "ffmpeg_input.txt")
    with open(input_list_path, "w") as f:
        for img_rel_path in images_relative_paths:
            full_path = os.path.join(base_folder, img_rel_path).replace("\\", "/")
            f.write(f"file '{full_path.replace("'", "'\\''")}'\n")
            f.write(f"duration {duration_per_frame:.4f}\n")
        if images_relative_paths:
             full_path = os.path.join(base_folder, images_relative_paths[-1]).replace("\\", "/")
             f.write(f"file '{full_path.replace("'", "'\\''")}'\n")
    return input_list_path


# Corrected run_ffmpeg definition to include duration_per_frame
def run_ffmpeg(input_list_path, audio_file, output_file, fps, num_input_images, duration_per_frame, fade_in_dur, fade_out_dur):
    """
    Run the FFmpeg command to combine images and audio into a video.
    Includes audio fade-in/out.
    Parses FFmpeg stderr for progress (based on video frames) and updates a tqdm bar.
    Discards non-progress output.
    """
    # Ensure output directory exists
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"{INFO_PREFIX} Creating output directory: {output_dir}")
        except OSError as e:
            print(f"{WARNING_PREFIX} Error creating output directory {output_dir}: {e}")
            print(f"{INFO_PREFIX} Attempting to save in the current directory instead.")
            output_file = os.path.basename(output_file) # Fallback to current dir


    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel", "info",
        "-f", "concat",
        "-safe", "0",
        "-i", input_list_path,
        "-stream_loop", "-1",
        "-i", audio_file,
        "-filter_complex",
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1280:720,boxblur=10:1[blurred];"
        "[fg]scale=-1:720[fgscaled];"
        "[blurred][fgscaled]overlay=(W-w)/2:(H-h)/2,setdar=16/9[v]",
        "-map", "[v]",
        "-map", "1:a",
        "-c:v", "libx264",
        "-r", str(fps),
        "-pix_fmt", "yuv420p",
        "-shortest",
    ]

    # Calculate expected video duration based on images
    # The concat list has num_input_images + 1 entry for the last frame repeat
    expected_video_duration = (num_input_images + 1) * duration_per_frame

    # --- Add Audio Fade Filter ---
    actual_fade_in_duration = min(fade_in_dur, expected_video_duration)
    actual_fade_out_duration = min(fade_out_dur, expected_video_duration)
    fade_out_start_time = max(0, expected_video_duration - actual_fade_out_duration)

    audio_filters = []
    if actual_fade_in_duration > 0:
        audio_filters.append(f"afade=t=in:st=0:d={actual_fade_in_duration:.4f}")
    if actual_fade_out_duration > 0 and fade_out_start_time >= 0:
         audio_filters.append(f"afade=t=out:st={fade_out_start_time:.4f}:d={actual_fade_out_duration:.4f}")

    if audio_filters:
        cmd.extend(["-af", ",".join(audio_filters)])
        print(f"{INFO_PREFIX} Applying audio filters: {','.join(audio_filters)}")


    cmd.append(output_file)


    print(HEADER_LINE)
    print(f"{ARROW_RIGHT} Executing core processing sequence (FFmpeg)")
    # print("Command:", cmd)
    print(HEADER_LINE)


    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    # --- Parse FFmpeg stderr for progress ---
    total_audio_duration_seconds = 0.0
    progress_bar = None

    print(f"{INFO_PREFIX} System initializing FFmpeg process...")

    try:
        while True:
            line = process.stderr.readline()
            if not line:
                if process.poll() is not None:
                    # Process finished, read any final discardable output
                    remaining_output, _ = process.communicate()
                    break
                time.sleep(0.01)
                continue

            duration_match = FFMPEG_DURATION_REGEX.search(line)
            if duration_match:
                 duration_str = duration_match.group(1)
                 total_audio_duration_seconds = parse_time_to_seconds(duration_str)
                 print(f"{INFO_PREFIX} Detected audio duration: {duration_str} ({total_audio_duration_seconds:.2f} seconds)")
                 continue

            progress_match = FFMPEG_PROGRESS_REGEX.search(line)
            if progress_match:
                 if progress_bar is None and expected_video_duration > 0:
                      print(f"\n{INFO_PREFIX} Encoding stream initiated.")
                      progress_bar = tqdm(total=expected_video_duration, desc=f"{ARROW_RIGHT} Encoding Progress", unit="s", unit_scale=True, ncols=100, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]')

                 if progress_bar is not None:
                    current_time_str = progress_match.group(1)
                    current_seconds = parse_time_to_seconds(current_time_str)
                    update_delta = max(0, current_seconds - progress_bar.n)
                    if update_delta > 0 or current_seconds > progress_bar.n:
                         progress_bar.update(update_delta)
                    continue

            # Discard any other line
            pass


        # --- Process finished ---
        if progress_bar:
             if expected_video_duration > 0:
                 progress_bar.n = expected_video_duration
                 progress_bar.refresh()
             progress_bar.close()
        else:
             print(f"\n{WARNING_PREFIX} FFmpeg encoding progress bar was not displayed.")

        returncode = process.wait()

        if returncode != 0:
            print(f"\n{ERROR_PREFIX} Core processing sequence terminated with errors. Code: {returncode}")
            raise subprocess.CalledProcessError(returncode, cmd)
        else:
            print(f"\n{ARROW_LEFT} Core processing sequence complete. Status: {STATUS_OK}")
            print(HEADER_LINE)


    except Exception as e:
        if progress_bar and not progress_bar.closed:
            progress_bar.close()

        if process.poll() is None:
             try:
                 remaining_output, _ = process.communicate(timeout=1)
             except subprocess.TimeoutExpired:
                 pass

        print(f"\n{ERROR_PREFIX} An unexpected system error occurred during core processing: {e}")
        raise

# === FUNCTION TO PROCESS A SINGLE CBZ ===

def process_single_cbz(cbz_file_path, audio_file_path, fps, duration_per_frame, image_extensions, audio_fade_in_duration, audio_fade_out_duration):
    """
    Handles the full processing pipeline for a single CBZ file.
    Returns True on success, False on recoverable failure (skips to next CBZ).
    Raises unrecoverable exceptions (like FFmpeg not found).
    """
    try:
        print(f"\n{HEADER_LINE}")
        print(f"{ARROW_RIGHT} Processing CBZ: {os.path.basename(cbz_file_path)}")
        print(HEADER_LINE)

        cbz_directory = os.path.dirname(cbz_file_path)
        cbz_base_name = os.path.basename(cbz_file_path)
        output_base_name, _ = os.path.splitext(cbz_base_name)
        output_base_name = re.sub(r'[^\w\s.-]', '', output_base_name)
        output_base_name = output_base_name.strip()
        if not output_base_name:
             output_base_name = "output_video_sequence"

        output_file = os.path.join(cbz_directory, f"{output_base_name}.mp4")

        print(f"{INFO_PREFIX} Destination video filename: {os.path.basename(output_file)}")
        print(f"{INFO_PREFIX} Destination directory: {os.path.dirname(output_file)}\n")


        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"{ARROW_RIGHT} Allocating temporary processing unit: {temp_dir}")

            print(HEADER_LINE)
            try:
                 extracted_image_paths_relative = extract_cbz(cbz_file_path, temp_dir, image_extensions)
                 print(f"{INFO_PREFIX} {len(extracted_image_paths_relative)} image files extracted and sorted.")
            except (FileNotFoundError, zipfile.BadZipFile, Exception) as e:
                 print(f"{ERROR_PREFIX} Extraction failed: {e}")
                 return False

            print(HEADER_LINE)

            if not extracted_image_paths_relative:
                 print(f"{ERROR_PREFIX} No usable images found in CBZ after extraction and initial sorting.")
                 return False

            images_after_resave_relative = extracted_image_paths_relative

            magick_available = False
            try:
                subprocess.run(["magick", "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                magick_available = True
            except (FileNotFoundError, subprocess.CalledProcessError):
                pass

            if magick_available:
                print(HEADER_LINE)
                print(f"{ARROW_RIGHT} Initiating Image Data Reconstruction Protocol...")
                resave_results_relative = thread_map(
                    lambda img_name: _resave_single_image_magick(img_name, temp_dir),
                    images_after_resave_relative,
                    max_workers=NUM_WORKERS,
                    desc=f"{ARROW_RIGHT} Data Stream Reconstruction",
                    unit="image",
                    ncols=100
                )
                images_after_resave_relative = [img_name for img_name in resave_results_relative if img_name is not None]

                print(f"\n{ARROW_LEFT} Reconstruction protocol complete. {len(images_after_resave_relative)} images ready for verification.")
                if len(images_after_resave_relative) < len(extracted_image_paths_relative):
                     print(f"{WARNING_PREFIX} {len(extracted_image_paths_relative) - len(images_after_resave_relative)} images were identified as unstable and excluded.")
                print(HEADER_LINE)


            if not images_after_resave_relative:
                 print(f"{ERROR_PREFIX} No images available after attempting ImageMagick resave.")
                 return False

            print(HEADER_LINE)
            print(f"{ARROW_RIGHT} Initiating Data Stream Integrity Verification Protocol...")
            verify_results_relative = thread_map(
                 lambda img_name: _verify_single_image_ffmpeg(img_name, temp_dir),
                 images_after_resave_relative,
                 max_workers=NUM_WORKERS,
                 desc=f"{ARROW_RIGHT} Verifying Image Data",
                 unit="image",
                 ncols=100
            )
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
            input_list_path = write_ffmpeg_input_list(final_images_for_ffmpeg_relative, temp_dir, DURATION_PER_FRAME) # Use global DURATION_PER_FRAME
            print(f"{INFO_PREFIX} Manifest location: {input_list_path}")
            print(f"{ARROW_LEFT} Data manifest generation complete.")
            print(HEADER_LINE)

            # Corrected call to run_ffmpeg, passing DURATION_PER_FRAME
            run_ffmpeg(input_list_path, audio_file_path, output_file, FPS, len(final_images_for_ffmpeg_relative), DURATION_PER_FRAME, AUDIO_FADE_IN_DURATION, AUDIO_FADE_OUT_DURATION)


        print(f"\n{ARROW_LEFT} Temporary processing unit deallocated for {os.path.basename(cbz_file_path)}.")
        return True

    except (FileNotFoundError, zipfile.BadZipFile, subprocess.CalledProcessError) as e:
        if isinstance(e, FileNotFoundError) or isinstance(e, zipfile.BadZipFile):
             print(f"\n{ERROR_PREFIX} File System or Archive Error during processing of {os.path.basename(cbz_file_path)}: {e}")
        elif isinstance(e, subprocess.CalledProcessError):
             print(f"\n{ERROR_PREFIX} External Process Execution Failure during processing of {os.path.basename(cbz_file_path)}.")
             failed_cmd = getattr(e, 'cmd', 'Unknown command')
             print(f"{INFO_PREFIX} Command: {' '.join(map(str, failed_cmd)) if isinstance(failed_cmd, list) else failed_cmd}")
             print(f"{INFO_PREFIX} Return Code: {e.returncode}")
        print(f"\n{WARNING_PREFIX} Skipping {os.path.basename(cbz_file_path)} due to the above error.")
        print(HEADER_LINE)
        return False

    except Exception as e:
        print(f"\n{ERROR_PREFIX} An unexpected system error occurred during processing of {os.path.basename(cbz_file_path)}: {e}")
        traceback.print_exc()
        print(f"\n{WARNING_PREFIX} Skipping {os.path.basename(cbz_file_path)} due to the above error.")
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

    try:
        subprocess.run(["magick", "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"{INFO_PREFIX} ImageMagick module detected. Resaving protocol enabled. {STATUS_OK}")
    except (FileNotFoundError, subprocess.CalledProcessError):
         print(f"{INFO_PREFIX} ImageMagick module not found. Resaving protocol will be skipped. {STATUS_OK}")


    print(f"{ARROW_LEFT} Dependency check complete.")

    try:
        print(HEADER_LINE)
        print(f"{COLOR_BLUE}        OPERATION: CBZ to Video Conversion Batch{RESET_COLOR}")
        print(HEADER_LINE)

        # --- Get CBZ Files ---
        cbz_dir = get_user_directory("CBZ file", DEFAULT_CBZ_DIR)
        cbz_files = list_files_by_extensions(cbz_dir, (".cbz",)) # List only .cbz files
        selected_cbz_basenames = get_user_selection(cbz_files, file_type="CBZ file(s)", allow_range=True)

        if not selected_cbz_basenames:
            print(f"\n{WARNING_PREFIX} No CBZ files selected. Operation cancelled.")
            print(HEADER_LINE)
            sys.exit(0)

        selected_cbz_paths = [os.path.join(cbz_dir, name) for name in selected_cbz_basenames]
        print(f"\n{INFO_PREFIX} {len(selected_cbz_paths)} CBZ file(s) selected for processing.")

        # --- Get Audio File ---
        print(HEADER_LINE)
        music_dir = get_user_directory("music", DEFAULT_MUSIC_DIR)
        music_files = list_files_by_extensions(music_dir, AUDIO_EXTENSIONS)
        # Include walking subdirectories for music files
        all_music_paths = []
        print(f"{ARROW_RIGHT} Scanning music directory and subdirectories...")
        for root, _, files in os.walk(music_dir):
            for file in files:
                if file.lower().endswith(AUDIO_EXTENSIONS):
                    all_music_paths.append(os.path.join(root, file))
        all_music_paths.sort(key=natural_key) # Sort music files too

        # Pass the full paths to get_user_selection
        selected_audio_paths = get_user_selection(all_music_paths, file_type="audio file", allow_range=False)

        if not selected_audio_paths:
             print(f"\n{WARNING_PREFIX} No audio file selected. Operation cancelled.")
             print(HEADER_LINE)
             sys.exit(0)

        # Get the single selected audio file path
        audio_file_path = selected_audio_paths[0] # get_user_selection ensures only one if allow_range=False
        print(f"\n{INFO_PREFIX} Selected audio file: {audio_file_path}")

        if not os.path.exists(audio_file_path):
             # This shouldn't happen if selection worked, but double check
             raise FileNotFoundError(f"{ERROR_PREFIX} Selected audio file not found at specified path: {audio_file_path}")

        print(f"{INFO_PREFIX} Target frame rate: {FPS} FPS")
        print(f"{INFO_PREFIX} Duration per frame: {DURATION_PER_FRAME:.2f} s") # Print duration per frame
        if AUDIO_FADE_IN_DURATION > 0 or AUDIO_FADE_OUT_DURATION > 0:
             print(f"{INFO_PREFIX} Audio fade-in duration: {AUDIO_FADE_IN_DURATION:.2f} s")
             print(f"{INFO_PREFIX} Audio fade-out duration: {AUDIO_FADE_OUT_DURATION:.2f} s")
        else:
             print(f"{INFO_PREFIX} Audio fading: Disabled")
        print(HEADER_LINE)


        # --- Process Selected CBZ Files ---
        print(f"\n{ARROW_RIGHT} Initiating batch processing sequence for {len(selected_cbz_paths)} CBZ file(s)...")
        print(HEADER_LINE)

        successful_count = 0
        failed_files = []

        for i, cbz_path in enumerate(selected_cbz_paths):
             print(f"\n{COLOR_BLUE}--- Processing File {i+1} of {len(selected_cbz_paths)} ---{RESET_COLOR}")
             success = process_single_cbz(
                 cbz_path,
                 audio_file_path,
                 FPS, # Pass FPS
                 DURATION_PER_FRAME, # Pass DURATION_PER_FRAME
                 IMAGE_EXTENSIONS,
                 AUDIO_FADE_IN_DURATION,
                 AUDIO_FADE_OUT_DURATION
             )
             if success:
                 successful_count += 1
             else:
                 failed_files.append(os.path.basename(cbz_path))
             print(f"{COLOR_BLUE}--- Finished File {i+1} of {len(selected_cbz_paths)} ---{RESET_COLOR}")


        # --- Batch Summary ---
        print(HEADER_LINE)
        print(f"{COLOR_BLUE}        BATCH PROCESSING SUMMARY{RESET_COLOR}")
        print(HEADER_LINE)
        print(f"{INFO_PREFIX} Total CBZ files selected: {len(selected_cbz_paths)}")
        print(f"{INFO_PREFIX} Successfully processed: {successful_count} {STATUS_OK}")
        print(f"{INFO_PREFIX} Failed to process: {len(failed_files)} {STATUS_FAIL}")

        if failed_files:
             print(f"{WARNING_PREFIX} Failed files:")
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
