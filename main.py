import os
import sys
import time

from file_utils import (
    display_directory_tree,
    collect_file_paths,
    separate_files_by_type,
    read_file_data
)

from data_processing_common import (
    compute_operations,
    execute_operations,
    process_files_by_date,
    process_files_by_type,
)

from text_data_processing import (
    process_text_files
)

from image_data_processing import (
    process_image_files
)

from output_filter import filter_specific_output  # Import the context manager

try:
    from nexa.gguf import NexaVLMInference, NexaTextInference
except ImportError:  # pragma: no cover - runtime dependency is optional until install
    NexaVLMInference = None
    NexaTextInference = None


class HFTextInferenceAdapter:
    """Minimal adapter for Hugging Face text generation pipelines."""

    def __init__(self, pipe):
        self.pipe = pipe

    def create_completion(self, prompt):
        outputs = self.pipe(
            prompt,
            max_new_tokens=300,
            do_sample=True,
            temperature=0.5,
            return_full_text=False,
        )
        generated_text = outputs[0].get('generated_text', '').strip() if isinstance(outputs, list) else str(outputs).strip()
        return {'choices': [{'text': generated_text}]}


class HFImageInferenceAdapter:
    """Minimal adapter for Hugging Face image captioning pipelines."""

    def __init__(self, pipe):
        self.pipe = pipe

    def _chat(self, prompt, image_path):
        description = self.pipe(image_path, max_new_tokens=128)[0].get('generated_text', '').strip()

        def generator():
            yield {'choices': [{'delta': {'content': description}}]}

        return generator()


def _load_hf_backends():
    """Load the local Hugging Face fallback if the Nexa SDK is unavailable."""
    try:
        from transformers import pipeline
    except ImportError as exc:  # pragma: no cover - install dependency is required
        raise RuntimeError(
            "Neither the Nexa SDK nor Hugging Face transformers are available. Install with "
            "'pip install -r requirements.txt' or 'pip install transformers torch'."
        ) from exc

    text_model = os.environ.get('LOCAL_TEXT_MODEL', 'TinyLlama/TinyLlama-1.1B-Chat-v1.0')
    image_model = os.environ.get('LOCAL_IMAGE_MODEL', 'Salesforce/blip-image-captioning-base')

    text_pipe = pipeline('text-generation', model=text_model, tokenizer=text_model, device_map='auto')
    image_pipe = pipeline('image-to-text', model=image_model, device_map='auto')
    return HFImageInferenceAdapter(image_pipe), HFTextInferenceAdapter(text_pipe)

def ensure_nltk_data():
    """Ensure that NLTK data is downloaded efficiently and quietly."""
    import nltk
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)
    nltk.download('wordnet', quiet=True)

# Initialize models
image_inference = None
text_inference = None

def initialize_models():
    """Initialize the models if they haven't been initialized yet."""
    global image_inference, text_inference
    if image_inference is not None and text_inference is not None:
        return

    if NexaVLMInference is not None and NexaTextInference is not None:
        model_path = "llava-v1.6-vicuna-7b:q4_0"
        model_path_text = "Llama3.2-3B-Instruct:q3_K_M"

        with filter_specific_output():
            image_inference = NexaVLMInference(
                model_path=model_path,
                local_path=None,
                stop_words=[],
                temperature=0.3,
                max_new_tokens=3000,
                top_k=3,
                top_p=0.2,
                profiling=False,
            )

            text_inference = NexaTextInference(
                model_path=model_path_text,
                local_path=None,
                stop_words=[],
                temperature=0.5,
                max_new_tokens=3000,
                top_k=3,
                top_p=0.3,
                profiling=False,
            )
        print("**----------------------------------------------**")
        print("**       Image inference model initialized      **")
        print("**       Text inference model initialized       **")
        print("**----------------------------------------------**")
        return

    try:
        image_inference, text_inference = _load_hf_backends()
    except RuntimeError:
        raise RuntimeError(
            "No supported local model backend was found. Install either the Nexa SDK or the Hugging Face local runtime "
            "with 'pip install -r requirements.txt' or 'pip install transformers torch'."
        )

    print("**----------------------------------------------**")
    print("**      Hugging Face inference backend ready    **")
    print("**----------------------------------------------**")

def simulate_directory_tree(operations, base_path):
    """Simulate the directory tree based on the proposed operations."""
    tree = {}
    for op in operations:
        rel_path = os.path.relpath(op['destination'], base_path)
        parts = rel_path.split(os.sep)
        current_level = tree
        for part in parts:
            if part not in current_level:
                current_level[part] = {}
            current_level = current_level[part]
    return tree

def print_simulated_tree(tree, prefix=''):
    """Print the simulated directory tree."""
    pointers = ['├── '] * (len(tree) - 1) + ['└── '] if tree else []
    for pointer, key in zip(pointers, tree):
        print(prefix + pointer + key)
        if tree[key]:  # If there are subdirectories or files
            extension = '│   ' if pointer == '├── ' else '    '
            print_simulated_tree(tree[key], prefix + extension)

def get_yes_no(prompt):
    """Prompt the user for a yes/no response."""
    while True:
        response = input(prompt).strip().lower()
        if response in ('yes', 'y'):
            return True
        elif response in ('no', 'n'):
            return False
        elif response == '/exit':
            print("Exiting program.")
            sys.exit()
        else:
            print("Please enter 'yes' or 'no'. To exit, type '/exit'.")

def get_mode_selection():
    """Prompt the user to select a mode."""
    while True:
        print("Please choose the mode to organize your files:")
        print("1. By Content")
        print("2. By Date")
        print("3. By Type")
        response = input("Enter 1, 2, or 3 (or type '/exit' to exit): ").strip()
        if response == '/exit':
            print("Exiting program.")
            sys.exit()
        elif response == '1':
            return 'content'
        elif response == '2':
            return 'date'
        elif response == '3':
            return 'type'
        else:
            print("Invalid selection. Please enter 1, 2, or 3. To exit, type '/exit'.")


def normalize_path(path):
    """Expand user variables and strip wrapper quotes from user-entered paths."""
    if path is None:
        return path

    normalized = str(path).strip()
    if not normalized:
        return normalized

    normalized = normalized.strip('"\'')
    normalized = os.path.expanduser(normalized)
    normalized = os.path.expandvars(normalized)
    return os.path.normpath(normalized)


def validate_output_path(input_path, output_path):
    """Reject output directories that would recurse into the source directory."""
    input_abs = os.path.abspath(normalize_path(input_path))
    output_abs = os.path.abspath(normalize_path(output_path))

    if output_abs == input_abs:
        raise ValueError("Output directory must be different from the input directory.")

    try:
        common_path = os.path.commonpath([input_abs, output_abs])
    except ValueError:
        return output_abs

    if common_path == input_abs:
        raise ValueError("Output directory cannot be inside the input directory.")

    return output_abs


def main():
    # Ensure NLTK data is downloaded efficiently and quietly
    ensure_nltk_data()

    # Display silent mode explanation before asking
    print("-" * 50)
    print("**NOTE: Silent mode logs all outputs to a text file instead of displaying them in the terminal.")
    silent_mode = get_yes_no("Would you like to enable silent mode? (yes/no): ")
    if silent_mode:
        log_file = 'operation_log.txt'
    else:
        log_file = None

    while True:
        # Paths configuration
        if not silent_mode:
            print("-" * 50)

        # Get input and output paths once per directory
        input_path = normalize_path(input("Enter the path of the directory you want to organize: ").strip())
        while not os.path.exists(input_path):
            message = f"Input path {input_path} does not exist. Please enter a valid path."
            if silent_mode:
                with open(log_file, 'a') as f:
                    f.write(message + '\n')
            else:
                print(message)
            input_path = normalize_path(input("Enter the path of the directory you want to organize: ").strip())

        # Confirm successful input path
        message = f"Input path successfully uploaded: {input_path}"
        if silent_mode:
            with open(log_file, 'a') as f:
                f.write(message + '\n')
        else:
            print(message)
        if not silent_mode:
            print("-" * 50)

        # Default output path is a folder named "organized_folder" in the same directory as the input path
        while True:
            output_path = normalize_path(input("Enter the path to store organized files and folders (press Enter to use 'organized_folder' in the input directory): ").strip())
            if not output_path:
                # Get the parent directory of the input path and append 'organized_folder'
                output_path = os.path.join(os.path.dirname(input_path), 'organized_folder')

            try:
                output_path = validate_output_path(input_path, output_path)
                break
            except ValueError as exc:
                message = f"Invalid output path: {exc} Please choose another directory."
                if silent_mode:
                    with open(log_file, 'a') as f:
                        f.write(message + '\n')
                else:
                    print(message)

        # Confirm successful output path
        message = f"Output path successfully set to: {output_path}"
        if silent_mode:
            with open(log_file, 'a') as f:
                f.write(message + '\n')
        else:
            print(message)
        if not silent_mode:
            print("-" * 50)

        # Start processing files
        start_time = time.time()
        file_paths = collect_file_paths(input_path)
        end_time = time.time()

        message = f"Time taken to load file paths: {end_time - start_time:.2f} seconds"
        if silent_mode:
            with open(log_file, 'a') as f:
                f.write(message + '\n')
        else:
            print(message)
        if not silent_mode:
            print("-" * 50)
            print("Directory tree before organizing:")
            display_directory_tree(input_path)

            print("*" * 50)

        # Loop for selecting sorting methods
        while True:
            mode = get_mode_selection()

            if mode == 'content':
                # Proceed with content mode
                # Initialize models once
                if not silent_mode:
                    print("Checking if the model is already downloaded. If not, downloading it now.")
                initialize_models()

                if not silent_mode:
                    print("*" * 50)
                    print("The file upload was successful. Processing may take a few minutes.")
                    print("*" * 50)

                # Separate files by type
                image_files, text_files = separate_files_by_type(file_paths)

                # Prepare text tuples for processing
                text_tuples = []
                for fp in text_files:
                    # Use read_file_data to read the file content
                    text_content = read_file_data(fp)
                    if text_content is None:
                        message = f"Unsupported or unreadable text file format: {fp}"
                        if silent_mode:
                            with open(log_file, 'a') as f:
                                f.write(message + '\n')
                        else:
                            print(message)
                        continue  # Skip unsupported or unreadable files
                    text_tuples.append((fp, text_content))

                # Process files sequentially
                data_images = process_image_files(image_files, image_inference, text_inference, silent=silent_mode, log_file=log_file)
                data_texts = process_text_files(text_tuples, text_inference, silent=silent_mode, log_file=log_file)

                # Prepare for copying and renaming
                renamed_files = set()
                processed_files = set()

                # Combine all data
                all_data = data_images + data_texts

                # Compute the operations
                operations = compute_operations(
                    all_data,
                    output_path,
                    renamed_files,
                    processed_files
                )

            elif mode == 'date':
                # Process files by date
                operations = process_files_by_date(file_paths, output_path, dry_run=False, silent=silent_mode, log_file=log_file)
            elif mode == 'type':
                # Process files by type
                operations = process_files_by_type(file_paths, output_path, dry_run=False, silent=silent_mode, log_file=log_file)
            else:
                print("Invalid mode selected.")
                return

            # Simulate and display the proposed directory tree
            print("-" * 50)
            message = "Proposed directory structure:"
            if silent_mode:
                with open(log_file, 'a') as f:
                    f.write(message + '\n')
            else:
                print(message)
                print(os.path.abspath(output_path))
                simulated_tree = simulate_directory_tree(operations, output_path)
                print_simulated_tree(simulated_tree)
                print("-" * 50)

            # Ask user if they want to proceed
            proceed = get_yes_no("Would you like to proceed with these changes? (yes/no): ")
            if proceed:
                # Create the output directory now
                os.makedirs(output_path, exist_ok=True)

                # Perform the actual file operations
                message = "Performing file operations..."
                if silent_mode:
                    with open(log_file, 'a') as f:
                        f.write(message + '\n')
                else:
                    print(message)
                execute_operations(
                    operations,
                    dry_run=False,
                    silent=silent_mode,
                    log_file=log_file
                )

                message = "The files have been organized successfully."
                if silent_mode:
                    with open(log_file, 'a') as f:
                        f.write("-" * 50 + '\n' + message + '\n' + "-" * 50 + '\n')
                else:
                    print("-" * 50)
                    print(message)
                    print("-" * 50)
                break  # Exit the sorting method loop after successful operation
            else:
                # Ask if the user wants to try another sorting method
                another_sort = get_yes_no("Would you like to choose another sorting method? (yes/no): ")
                if another_sort:
                    continue  # Loop back to mode selection
                else:
                    print("Operation canceled by the user.")
                    break  # Exit the sorting method loop

        # Ask if the user wants to organize another directory
        another_directory = get_yes_no("Would you like to organize another directory? (yes/no): ")
        if not another_directory:
            break  # Exit the main loop


if __name__ == '__main__':
    main()
