
---

# CBZ to Video Converter Script

This Python script automates the process of converting Comic Book Archive files (`.cbz`) into video files (`.mp4`). It extracts images from the CBZ, processes them using ImageMagick for compatibility, verifies them with FFmpeg, combines them with a selected audio track, applies audio fade effects, and encodes the final video with a real-time progress bar and a sci-fi themed command-line interface.

The script supports processing multiple CBZ files in a batch.

## ✨ Features

*   **CBZ Extraction:** Automatically extracts images from `.cbz` (ZIP archives) into a temporary directory.
*   **Image Processing:** Uses ImageMagick (`magick`) to re-save images, stripping potentially problematic metadata that can interfere with FFmpeg.
*   **Image Verification:** Uses FFmpeg (`ffmpeg`) to perform a basic decoding and scaling check on each image after processing to ensure compatibility before video creation.
*   **Interactive File Selection:** Prompts the user to select the directory containing CBZ files and allows selecting multiple files via numbered lists, ranges (e.g., `1,3,5-7`), and comma-separated values.
*   **Audio Selection:** Prompts the user to select a single audio file from a specified directory and its subdirectories.
*   **Audio Integration:** Loops the selected audio track to match the video duration and cuts it off at the end of the video sequence using FFmpeg's `-shortest` flag.
*   **Audio Fades:** Applies configurable fade-in and fade-out effects to the audio track.
*   **Video Encoding:** Uses FFmpeg (`libx264`) to encode the image sequence and audio into an MP4 file.
*   **Background/Foreground Effect:** Applies a common filter to scale and blur the video for a background effect, overlaying the main image centered.
*   **Progress Bar:** Displays a real-time progress bar during the FFmpeg encoding phase, representing the time elapsed relative to the calculated video duration.
*   **Temporary File Cleanup:** Automatically manages and cleans up temporary directories and files used during processing.
*   **Batch Processing:** Processes multiple selected CBZ files sequentially.
*   **Sci-Fi UI:** Provides a themed command-line interface with ANSI colors (requires terminal support for colors, e.g., Termux).
*   **Error Handling:** Catches and reports errors during various stages (file not found, extraction issues, processing failures, FFmpeg errors) and skips problematic files in batch mode.

## 📋 Prerequisites

Before running the script, you need to have the following installed on your system:

1.  **Python 3:** The script is written in Python 3.
2.  **FFmpeg:** Required for image verification, scaling, filtering, audio handling, and video encoding.
3.  **ImageMagick:** Required for re-saving and cleaning up image metadata. The `magick` command should be available in your PATH.
4.  **`tqdm` Python Library:** Used for displaying progress bars.

### Installation on Termux (Android)

If you are running this on Android using Termux, you can install the prerequisites using `pkg` and `pip`:

```bash
pkg update && pkg upgrade
pkg install ffmpeg imagemagick python
pip install tqdm
```

### Installation on other Systems (Linux/macOS/Windows)

Use your system's package manager (apt, brew, chocolatey) or download official binaries for FFmpeg and ImageMagick. Install `tqdm` using pip:

```bash
# On Linux (Debian/Ubuntu):
sudo apt update
sudo apt install ffmpeg imagemagick python3 python3-pip
pip install tqdm

# On macOS (using Homebrew):
brew install ffmpeg imagemagick
pip3 install tqdm

# On Windows (using Chocolatey - requires admin):
choco install ffmpeg imagemagick
pip install tqdm
```

## 🚀 Getting Started

1.  Save the script code as a Python file (e.g., `cbz_to_video.py`).
2.  Make sure the prerequisites are installed and the `ffmpeg` and `magick` commands are in your system's PATH.
3.  Open your terminal or command prompt.
4.  Navigate to the directory where you saved the script.
5.  Run the script using the Python interpreter:

    ```bash
    python cbz_to_video.py
    ```
    or, if using Termux:
    ```bash
    runnew cbz_to_video.py
    ```

6.  Follow the on-screen prompts to select your CBZ directory, CBZ file(s), and audio file.

## 🖥️ Usage Examples

When you run the script, it will first check for dependencies and then present you with prompts.

**Example 1: Selecting a single CBZ and a single Audio File**

```
:::======================================================:::
        SYSTEM STATUS INQUIRY
:::======================================================:::
>>> Checking system dependencies...
::: FFmpeg module detected. [OK]
::: ImageMagick module detected. Resaving protocol enabled. [OK]
<<< Dependency check complete.
:::======================================================:::
        OPERATION: CBZ to Video Conversion Batch
:::======================================================:::
>>> Enter CBZ file directory (empty for default): /storage/67DC-DBA3/Android/media/com.google.android.keep/.~```~_/.•••```/local/extra
>>> > /path/to/your/cbz/folder

>>> Available CBZ file(s):
::: 1. MyComicBook Vol 1.cbz
::: 2. Another Comic.cbz
::: 3. Comic Series #3.cbz
>>> Select CBZ file(s) by number (e.g., 1,3, 5-7) (1-3):
>>> > 1

::: 1 CBZ file(s) selected for processing.
:::======================================================:::
>>> Enter music directory (empty for default): /storage/emulated/0/Android/media/com.android.vending/.SUS/aydi
>>> > /path/to/your/music/folder

>>> Scanning music directory and subdirectories...
>>> Available audio files:
::: 1. AwesomeTrack.mp3
::: 2. AnotherSong.wav
::: 3. BackgroundMusic.ogg
>>> Select audio file by number (e.g., 1) (1-3):
>>> > 1

::: Selected audio file: /path/to/your/music/folder/AwesomeTrack.mp3
::: Target frame rate: 4 FPS
::: Duration per frame: 0.25 s
::: Audio fade-in duration: 2.00 s
::: Audio fade-out duration: 2.00 s
:::======================================================:::

>>> Initiating batch processing sequence for 1 CBZ file(s)...
:::======================================================:::

--- Processing File 1 of 1 ---

:::======================================================:::
>>> Processing CBZ: MyComicBook Vol 1.cbz
:::======================================================:::
::: Destination video filename: MyComicBook Vol 1.mp4
::: Destination directory: /path/to/your/cbz/folder

>>> Allocating temporary processing unit: /tmp/tmpXYZ

:::======================================================:::
>>> Initiating CBZ extraction protocol for MyComicBook Vol 1.cbz
::: Archive contains 150 potential image files.
>>> Transferring archive components: 100%|██████████| 150/150 [00:00<00:00, 1200file/s]
<<< Extraction protocol complete. 150 images prepared.
::: 150 image files extracted and sorted.
:::======================================================:::

:::======================================================:::
>>> Initiating Image Data Reconstruction Protocol...
>>> Data Stream Reconstruction: 100%|██████████| 150/150 [00:10<00:00, 15.00image/s]

<<< Reconstruction protocol complete. 150 images ready for verification.
:::======================================================:::

:::======================================================:::
>>> Initiating Data Stream Integrity Verification Protocol...
>>> Verifying Image Data: 100%|██████████| 150/150 [00:08<00:00, 18.75image/s]

<<< Verification protocol complete. 150 data streams cleared for processing.
:::======================================================:::

:::======================================================:::
>>> Generating data manifest...
::: Manifest location: /tmp/tmpXYZ/ffmpeg_input.txt
<<< Data manifest generation complete.
:::======================================================:::

:::======================================================:::
>>> Executing core processing sequence (FFmpeg)
:::======================================================:::
::: System initializing FFmpeg process...
::: Detected audio duration: 00:03:30.00 (210.00 seconds)

>>> Encoding stream initiated.
>>> Encoding Progress: 100%|████████████████████████████████████████| 37.75/37.75 [00:12<00:00, 3.00s/s]
<<< Core processing sequence complete. Status: [OK]
:::======================================================:::

<<< Temporary processing unit deallocated for MyComicBook Vol 1.cbz.

--- Finished File 1 of 1 ---

:::======================================================:::
        BATCH PROCESSING SUMMARY
:::======================================================:::
::: Total CBZ files selected: 1
::: Successfully processed: 1 [OK]
::: Failed to process: 0 [FAIL]
:::======================================================:::

```

**Example 2: Selecting multiple CBZ files using ranges and comma**

```
... (Initial checks and directory prompts are similar) ...

>>> Available CBZ file(s):
::: 1. Comic A.cbz
::: 2. Comic B.cbz
::: 3. Comic C.cbz
::: 4. Comic D.cbz
::: 5. Comic E.cbz
>>> Select CBZ file(s) by number (e.g., 1,3, 5-7) (1-5):
>>> > 1, 3-5

::: 4 CBZ file(s) selected for processing.
... (Audio selection is similar) ...

>>> Initiating batch processing sequence for 4 CBZ file(s)...
:::======================================================:::

--- Processing File 1 of 4 ---
... (Processing for Comic A.cbz) ...
--- Finished File 1 of 4 ---

--- Processing File 2 of 4 ---
... (Processing for Comic C.cbz) ...
--- Finished File 2 of 4 ---

--- Processing File 3 of 4 ---
... (Processing for Comic D.cbz) ...
--- Finished File 3 of 4 ---

--- Processing File 4 of 4 ---
... (Processing for Comic E.cbz) ...
--- Finished File 4 of 4 ---

:::======================================================:::
        BATCH PROCESSING SUMMARY
:::======================================================:::
::: Total CBZ files selected: 4
::: Successfully processed: 4 [OK]
::: Failed to process: 0 [FAIL]
:::======================================================:::
```

**Example 3: Handling a Failed File in Batch**

If one of the files in a batch fails during processing (e.g., ImageMagick error on a corrupt image), you'll see an error message printed *during* the processing of that specific file, and the script will mark it as failed but continue with the rest of the batch.

```
... (Batch starts) ...
--- Processing File 1 of 3 ---
... (Processing for File 1 - Success) ...
--- Finished File 1 of 3 ---

--- Processing File 2 of 3 ---
:::======================================================:::
>>> Processing CBZ: BadComic.cbz
:::======================================================:::
... (Extraction, Resaving steps) ...
>>> Data Stream Reconstruction: 50%|████████████████████████████| 5/10 [00:01<00:01,  4.00image/s]
!!! ERROR: ImageMagick resaving failed for page_006.jpg:
magick: Invalid image data @ error/jpeg.c/JPEGErrorHandler/345.
>>> Data Stream Reconstruction: 60%|███████████████████████████████| 6/10 [00:01<00:00,  4.33image/s]... (Resaving continues for other images)...
<<< Reconstruction protocol complete. 9 images ready for verification.
>>> WARNING: 1 images were identified as unstable and excluded.
... (Verification and FFmpeg steps will then run with the remaining 9 images, but will likely still fail or be very short) ...

!!! ERROR: Core processing sequence terminated with errors. Code: 1
>>> WARNING: Skipping BadComic.cbz due to the above error.
:::======================================================:::
--- Finished File 2 of 3 ---

--- Processing File 3 of 3 ---
... (Processing for File 3 - Success) ...
--- Finished File 3 of 3 ---

:::======================================================:::
        BATCH PROCESSING SUMMARY
:::======================================================:::
::: Total CBZ files selected: 3
::: Successfully processed: 2 [OK]
::: Failed to process: 1 [FAIL]
>>> WARNING: Failed files:
::: - BadComic.cbz
:::======================================================:::

```

## ⚙️ Configuration

You can modify the following variables at the top of the script to customize its behavior:

```python
# === CONFIGURATION ===
DEFAULT_CBZ_DIR = "/storage/67DC-DBA3/Android/media/com.google.android.keep/.~```~_/.•••```/local/extra" # Default CBZ directory
DEFAULT_MUSIC_DIR = "/storage/emulated/0/Android/media/com.android.vending/.SUS/aydi" # Default Music directory

# List of supported image extensions (case-insensitive)
IMAGE_EXTENSIONS = (".webp", ".jpg", ".jpeg", ".png")
# List of supported audio extensions (case-insensitive)
AUDIO_EXTENSIONS = (".mp3", ".wav", ".aac", ".flac", ".ogg")

FPS = 4 # Frames per second for the output video
# DURATION_PER_FRAME is calculated from FPS (1/FPS)

# Audio Fade Configuration (in seconds)
AUDIO_FADE_IN_DURATION = 2.0 # Duration of the audio fade-in at the start
AUDIO_FADE_OUT_DURATION = 2.0 # Duration of the audio fade-out at the end of the video

# Number of worker threads for parallel processing.
# Adjust based on your device's CPU cores. os.cpu_count() * 2 is a common heuristic.
NUM_WORKERS = os.cpu_count() * 2 if os.cpu_count() else 4
```

## 🐛 Troubleshooting

*   **`ffmpeg` or `magick` not found:** Ensure FFmpeg and ImageMagick are correctly installed and their executable directories are included in your system's PATH environment variable. The script performs checks at the start.
*   **`tqdm` module not found:** Install the `tqdm` Python library using `pip install tqdm`.
*   **Invalid Directory:** Double-check the path you entered or the `DEFAULT_CBZ_DIR`/`DEFAULT_MUSIC_DIR` in the script.
*   **Invalid Selection:** Ensure you are entering numbers corresponding to the list, separated by commas (`,`), or valid ranges (`start-end`) if allowed for that prompt.
*   **CBZ Extraction Failed:** The CBZ file might be corrupted or not a valid ZIP archive. Try opening it with a standard ZIP utility. It might also not contain files with the configured `IMAGE_EXTENSIONS`.
*   **Image Processing/Verification Failed:** Some images within the CBZ might be corrupted or in a non-standard format that ImageMagick or FFmpeg cannot handle. The script will print specific errors for problematic files and attempt to skip them in batch mode. Re-saving such images manually in a robust image editor might help, or you may need to exclude them from the CBZ.
*   **Permissions:** Ensure the script has read access to the CBZ and audio files, and write access to the directory where the script is run (for the output video if fallback occurs) and the temporary directory (usually handled by `tempfile`, but can sometimes be restricted). It also needs write access to the directory where the original CBZ is located to save the output video there.
*   **No FFmpeg Progress Bar:** This can happen for very short videos or if FFmpeg encounters an error very early in the encoding process. The script will print a warning in this case. The verbose FFmpeg output is intentionally hidden unless it fails before the bar starts.

If you encounter persistent issues, review the output printed by the script just before a "Failed" message or an unhandled exception for clues.

## 📄 License

This script is provided "as is" without any specific license. Feel free to use, modify, and distribute it as you see fit.

## 🙏 Credits

*   Built upon functionality provided by FFmpeg and ImageMagick.
*   Uses the `tqdm` library for progress bars.

---
