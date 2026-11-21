import unittest
import argparse

import numpy as np

import main


class FeatureTests(unittest.TestCase):
    def test_feature_vector_is_fixed_size_for_gray_and_color(self):
        gray = np.zeros((240, 320), dtype=np.uint8)
        color = np.zeros((80, 120, 3), dtype=np.uint8)

        gray_features = main.extract_features(gray)
        color_features = main.extract_features(color)

        self.assertEqual(gray_features.shape, color_features.shape)
        self.assertGreater(gray_features.size, 0)
        self.assertTrue(np.isfinite(gray_features).all())

    def test_invalid_images_are_rejected(self):
        with self.assertRaises(ValueError):
            main.extract_features(None)


class ThresholdTests(unittest.TestCase):
    def test_classifier_marks_uncertain_probability_for_review(self):
        class StubClassifier:
            classes_ = np.asarray(["BUENA", "DANADA"])

            def predict_proba(self, _features):
                return np.asarray([[0.5, 0.5]])

        original_extract = main.extract_features
        try:
            main.extract_features = lambda _image: np.zeros(2, dtype=np.float32)
            label, probability = main.classify_image(StubClassifier(), np.zeros((8, 8)), 0.70)
        finally:
            main.extract_features = original_extract

        self.assertEqual(label, "REVISAR")
        self.assertEqual(probability, 0.5)

    def test_threshold_arguments_must_be_inside_supported_range(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            main.positive_threshold("0.5")
        with self.assertRaises(argparse.ArgumentTypeError):
            main.positive_interval("0")

    def test_safe_source_removes_credentials_and_query(self):
        source = "rtsp://operator:secret@camera.local:554/live?token=private"
        self.assertEqual(main.safe_source(source), "rtsp://camera.local:554/live")


if __name__ == "__main__":
    unittest.main()
