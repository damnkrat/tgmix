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
-   **Flexible Anonymization**: Automatically mask sensitive data like phone numbers, emails, author names, and custom patterns to protect privacy before sharing chat data.
-   **Data for RAG & Fine-Tuning**: The clean, structured JSON output is a perfect dataset for advanced applications. Use it to build a knowledge base for Retrieval-Augmented Generation (RAG) or to fine-tune a custom model on a specific person's conversational style.

## Roadmap

The development of TGMix is planned in stages. Here is what's available now and what to expect in the future.

#### Current Version

-   [x] **Significant Token Reduction**: By simplifying the structure and removing redundant metadata from the original Telegram export, TGMix **reduces the final token count by up to 3 times**.
-   [x] **Message Stitching**: Automatically combines messages sent by the same user in quick succession into a single, coherent entry.
-   [x] **Basic Media Handling**: Puts all media files into a separate, organized folder.
-   [x] **AI-Ready JSON Output**: Produces a single, clean `tgmix_output.json` file with a simple structure, including a map of authors and fixed reply IDs.
-   [x] **Advanced Anonymization**: A flexible system for masking sensitive data.

#### Planned for Future Releases

-   [ ] **Advanced Media Processing**: Optional conversion of voice/video messages and automatic transcription into text.
-   [ ] **Improvements for multimodal LLMs**: Optional inclusion of filenames in media for better context understanding via [MarkMyMedia-LLM](https://github.com/LaVashikk/MarkMyMedia-LLM).
-   [ ] **Official Package Manager Support**: Easy installation via AUR.

## Requirements

-   **Python 3.10+**

[//]: # (-   **FFmpeg**: You must have FFmpeg installed and accessible in your system's PATH. You can download it from the [official FFmpeg website]&#40;https://ffmpeg.org/download.html&#41;.)

## Installation
[//]: # (1.  Ensure FFmpeg is installed. Verify by running `ffmpeg -version` in your terminal.)



#### Via [PyPI](https://pypi.org/project/tgmix)
```bash
pip install -U tgmix
```

#### From GitHub (For development)
Install `tgmix` directly from this repository:
```bash
pip install git+https://github.com/damnkrat/tgmix.git
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
    To enable anonymization, add the `-a` flag:
    ```bash
    tgmix -a
    ```

#### Step 3: Use the Output

Once finished, you will find:
-   `tgmix_output.json`: The final, processed JSON file ready for your LLM.
-   `tgmix_media/`: A new folder containing all processed and copied media files.

## Configuration

You can control TGMix's behavior by editing the `tgmix_config.json` file. Create one in your project directory by running `tgmix --init`.

### Anonymization Settings

The core of the new functionality lies in the anonymization settings. Here is an example of a fully configured setup:

```json
{
  "export_json_file": "result.json",
  "media_output_dir": "tgmix_media",
  "final_output_json": "tgmix_output.json",
  "anonymize": true,
  "default_phone_region": "RU",
  "mask_presets": {
    "phone": "[PHONE]",
    "email": "[EMAIL]",
    "authors": "[AUTHOR]"
  },
  "mask_literals": {
    "Project Capture": "[SECRET_PROJECT]"
  },
  "mask_regex": {
    "\\b\\d{16}\\b": "[CARD_NUMBER]"
  }
}
```

-   `"anonymize"`: `true` or `false`. The master switch for the anonymization feature.
-   `"default_phone_region"`: A two-letter country code (e.g., "RU", "US", "GB") to help detect local phone numbers that don't have a `+` prefix. This is a tradeoff for accuracy.
-   `"mask_presets"`: A dictionary of built-in, ready-to-use masking rules. The key is the preset name, and the value is the placeholder text that will replace the found data. Available presets are:
    -   `"phone"`: Finds and replaces phone numbers. It intelligently detects both international formats (e.g., `+1-541-754-3010`) and local formats based on the `"default_phone_region"` (e.g., `8 (999) 123-45-67`).
    -   `"email"`: Finds and replaces email addresses using a robust, tested regular expression.
    -   `"authors"`: This is a special preset that anonymizes the authors themselves. It modifies the `author_map` in the final JSON, replacing the author's name with the provided template and a unique number (e.g., `[AUTHOR_1]`, `[AUTHOR_2]`).
-   `"mask_literals"`: A dictionary for replacing exact, case-insensitive phrases. The key is the phrase to find, and the value is its replacement. Perfect for redacting names, project titles, or other specific keywords.
-   `"mask_regex"`: A dictionary for replacing content based on regular expressions. The key is the regex pattern, and the value is its replacement. This gives you the power to mask any custom data format, like ID numbers, bank accounts, or tracking codes.
    > **Important:** In JSON format, the backslash `\` is an escape character. Therefore, you must **escape your backslashes** in regex patterns. For example, to match a digit (`\d`), you must write it as `\\d` in the `tgmix_config.json` file.

### Command-Line Overrides and Examples

While `tgmix_config.json` is great for setting up your default anonymization rules, you can easily override or supplement them for a specific run using command-line flags. **CLI flags always take precedence over the configuration file.**

## Command-Line Usage

You can control TGMix directly from the command line. Flags and options provided here will always take precedence over the settings in `tgmix_config.json`.

### Options

-   `path`
    (Positional Argument) The path to the directory containing the Telegram export. If omitted, TGMix will process the current directory.
-   `--init`
    Creates a `tgmix_config.json` configuration file in the current directory from a built-in template.
-   `--version`
    Displays the installed version of TGMix and exits.
-   `-a`, `--anonymize`
    Enables the anonymization feature for the current run.
-   `--no-stats`
    Disables the computation and printing of processing statistics at the end of the run.
-   `--mask-preset <preset1> <preset2> ...`
    Overrides the list of active presets from the config file. Only the presets you list here will be used.
-   `--mask-literal "phrase:replacement"`
    Overrides the `mask_literals` dictionary from your config file. You can provide multiple rules.
-   `--mask-regex "pattern:replacement"`
    Overrides the `mask_regex` dictionary from your config file. You can provide multiple rules.

#### Example 1: Enabling Anonymization with Default Rules

If your `"anonymize"` key is set to `false` in the config, you can easily enable it for a single run:

```bash
tgmix --anonymize
```
*   **What it does:** This command enables the anonymization feature and uses all the rules exactly as they are defined in your `tgmix_config.json` file.

#### Example 2: Using Only Specific Presets

Imagine you only want to anonymize authors for a particular analysis, ignoring other presets from your config.

```bash
tgmix --anonymize --mask-preset authors
```
*   **What it does:** This command overrides the `mask_presets` from your config. It will **only** anonymize author names in the `author_map`, ignoring the `phone` and `email` presets even if they are present in the JSON file.
*   **Note:** Authors are not anonymized in message text. The reason is author name can be, for example, just "a". It will just break most messages in the export. To anonymize it in message text, you need to add it to `mask_literals` or `mask_regex`.

#### Example 3: Adding a One-Time Redaction Rule

You need to redact a new project name just once, without permanently editing your config file.

```bash
tgmix --anonymize --mask-literal "Project Capture:[SECRET_PROJECT]"
```
*   **What it does:** This command uses all the default rules from your config (`presets`, `regex`) but **overrides** the `mask_literals` dictionary, adding a new, temporary rule to mask "Project Hydra".

#### Example 4: The Power User Command

This command demonstrates full control from the CLI, overriding all rule types for a highly specific task.

```bash
tgmix --anonymize \
      --mask-preset email phone \
      --mask-literal "damnkrat:[USER_A]" "secret password:[REDACTED]" \
      --mask-regex "\b\d{4}-\d{4}\b:[ID_CODE]"
```
*   **What it does:**
    *   `--anonymize`: Enables the feature.
    *   `--mask-preset email phone`: Uses **only** email and phone presets.
    *   `--mask-literal ...`: Overrides all literals from the config and uses only the two provided here.
    *   `--mask-regex ...`: Overrides all regex rules from the config and uses only the one for a custom ID code.

## License

This project is licensed under the GNU General Public License v3.0. See the `LICENSE` file for details.
