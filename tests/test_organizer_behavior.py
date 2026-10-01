import os
import tempfile
import unittest

import main
from data_processing_common import execute_operations


class OrganizerBehaviorTests(unittest.TestCase):
    def test_validate_output_path_rejects_nested_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = os.path.join(tmpdir, 'input')
            os.makedirs(input_dir)
            nested_output = os.path.join(input_dir, 'organized')

            with self.assertRaises(ValueError):
                main.validate_output_path(input_dir, nested_output)

    def test_normalize_user_input_paths_expands_home_and_strips_quotes(self):
        normalized = main.normalize_path(r'"C:\Users\ggutm\Downloads"')
        self.assertEqual(normalized, r'C:\Users\ggutm\Downloads')

        home_dir = os.path.expanduser('~')
        self.assertEqual(main.normalize_path('~\\Downloads'), os.path.join(home_dir, 'Downloads'))

    def test_initialize_models_uses_huggingface_fallback_when_nexa_is_unavailable(self):
        original_image = main.image_inference
        original_text = main.text_inference
        original_vlm = main.NexaVLMInference
        original_txt = main.NexaTextInference
        main.image_inference = None
        main.text_inference = None
        main.NexaVLMInference = None
        main.NexaTextInference = None

        class FakeTextInference:
            def create_completion(self, prompt):
                return {'choices': [{'text': 'summary'}]}

        class FakeImageInference:
            def _chat(self, prompt, image_path):
                return iter([{'choices': [{'delta': {'content': 'fake description'}}]}])

        main._load_hf_backends = lambda: (FakeImageInference(), FakeTextInference())

        try:
            main.initialize_models()
            self.assertIsNotNone(main.image_inference)
            self.assertIsNotNone(main.text_inference)
        finally:
            main.image_inference = original_image
            main.text_inference = original_text
            main.NexaVLMInference = original_vlm
            main.NexaTextInference = original_txt
            main._load_hf_backends = None

    def test_execute_operations_falls_back_to_copy_when_hardlink_is_unsupported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, 'source.txt')
            dest_dir = os.path.join(tmpdir, 'dest')
            os.makedirs(dest_dir)
            dest = os.path.join(dest_dir, 'copy.txt')

            with open(source, 'w', encoding='utf-8') as f:
                f.write('hello')

            original_link = os.link
            os.link = lambda *args, **kwargs: (_ for _ in ()).throw(OSError('unsupported'))
            try:
                execute_operations([
                    {'source': source, 'destination': dest, 'link_type': 'hardlink'}
                ], dry_run=False, silent=True, log_file=None)
            finally:
                os.link = original_link

            self.assertTrue(os.path.exists(dest))
            with open(dest, 'r', encoding='utf-8') as f:
                self.assertEqual(f.read(), 'hello')


if __name__ == '__main__':
    unittest.main()
