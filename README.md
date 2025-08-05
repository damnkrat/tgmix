# 💬 TGMix

TGMix is a powerful tool that processes your Telegram chat export into a AI-friendly dataset. Perfect for feeding the full context of long and complex conversations to Large Language Models (LLMs) like Claude, Gemini, GPT-4o, and more. Inspired by Repomix.

> **🛠️ Beta Version Note**
>
> Please note that TGMix is currently in a beta phase. This means that while the core features are functional, you may encounter occasional bugs or unexpected behavior with certain edge cases.
>
> Your feedback is invaluable during this stage. If you find any issues, please [report them on GitHub Issues](https://github.com/damnkrat/tgmix/issues).

## Core features

-   **Save Costs & Time**: Processing a chat history that's up to 3x smaller in token count directly translates to lower API costs for paid models (like GPT-4o and Claude 3 Opus) and significantly faster response times.
-   **Fit More Data into Context**: The token reduction is crucial for fitting large chat histories into a model's limited context window — something that is frequently impossible with raw Telegram exports.
-   **Higher Quality Analysis**: By stitching fragmented messages, you provide the LLM with a more natural and complete context. This prevents misinterpretations and leads to more accurate and insightful summaries, analyses, or role-playing sessions.
-   **Data for RAG & Fine-Tuning**: The clean, structured JSON output is a perfect dataset for advanced applications. Use it to build a knowledge base for Retrieval-Augmented Generation (RAG) or to fine-tune a custom model on a specific person's conversational style.

## Roadmap

The development of TGMix is planned in stages. Here is what's available now and what to expect in the future.

#### Current Version

-   [x] **Significant Token Reduction**: By simplifying the structure and removing redundant metadata from the original Telegram export, TGMix **reduces the final token count by up to 3 times**.
-   [x] **Message Stitching**: Automatically combines messages sent by the same user in quick succession into a single, coherent entry.
-   [x] **Basic Media Handling**: Puts all media files into a separate, organized folder.
-   [x] **AI-Ready JSON Output**: Produces a single, clean `tgmix_output.json` file with a simple structure, including a map of authors and fixed reply IDs.

#### Planned for Future Releases

-   [ ] **Advanced Media Processing**: Optional conversion of voice/video messages and automatic transcription into text.
-   [ ] **Improvements for multimodal LLMs**: Optional inclusion of filenames in media for better context understanding via [MarkMyMedia-LLM](https://github.com/LaVashikk/MarkMyMedia-LLM).
-   [ ] **Official Package Manager Support**: Easy installation via PyPI and AUR.

## Requirements

-   **Python 3.13+**
-   **FFmpeg**: You must have FFmpeg installed and accessible in your system's PATH. You can download it from the [official FFmpeg website](https://ffmpeg.org/download.html).

## Installation

#### From GitHub (For development)
1.  Ensure FFmpeg is installed. Verify by running `ffmpeg -version` in your terminal.
2.  Install `tgmix` directly from this repository:
    ```bash
    pip install git+https://github.com/damnkrat/tgmix.git
    ```

#### Via PyPI (Current method)
```bash
pip install tgmix
```

#### Via Arch User Repository (AUR) (soon)
```bash
yay -S tgmix
```

## How to Use

#### Step 1: Export Your Telegram Chat

1.  Open **Telegram Desktop**.
2.  Go to the chat you want to export.
3.  Click the three dots (⋮) in the top-right corner and select **Export chat history**.
4.  **Crucially**, in the export settings:
    -   Set the format to **"Machine-readable JSON"**.
    -   Choose a date range and media settings as desired.
5.  Let the export process complete. You will get a folder containing a `result.json` file and media subfolders.

#### Step 2: Run TGMix

1.  Navigate to your exported chat directory in your terminal.
    ```bash
    cd path/to/your/telegram_export
    ```
2.  (Optional) Create a local configuration file.
    ```bash
    tgmix --init
    ```
    This will create a `tgmix_config.json` file. You can edit it if your export has non-standard file names.

3.  Run the processor.
    ```bash
    tgmix
    ```

#### Step 3: Use the Output

Once finished, you will find:
-   `tgmix_output.json`: The final, processed JSON file ready for your LLM.
-   `tgmix_media/`: A new folder containing all processed and copied media files.

## Configuration

By running `tgmix --init`, you create a `tgmix_config.json` file. Here are the available options:

-   `export_json_file`: Name of the input JSON file from Telegram. Default: `"result.json"`.
-   `media_output_dir`: Name of the directory for processed media. Default: `"tgmix_media"`.
-   `final_output_json`: Name of the final output JSON. Default: `"tgmix_output.json"`.
-   `ffmpeg_drawtext_settings`: The FFmpeg filter string for drawing text on media.

## License

This project is licensed under the GNU General Public License v3.0. See the `LICENSE` file for details.
