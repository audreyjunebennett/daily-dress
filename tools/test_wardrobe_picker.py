import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from wardrobe_picker import PickerState, SkinEntry, WardrobePicker, find_visual_duplicates


class WardrobePickerTests(unittest.TestCase):
    def test_visual_duplicate_detection_uses_normalized_pixels(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.png"
            second = root / "second.png"
            different = root / "different.png"
            Image.new("RGBA", (64, 64), (180, 100, 140, 255)).save(first, optimize=False)
            Image.new("RGBA", (64, 64), (180, 100, 140, 255)).save(second, optimize=True)
            Image.new("RGBA", (64, 64), (10, 20, 30, 255)).save(different)

            duplicates = find_visual_duplicates(
                [SkinEntry(first, first.name), SkinEntry(second, second.name), SkinEntry(different, different.name)]
            )

            self.assertEqual(duplicates, {"first.png": 2, "second.png": 2})

    def test_choices_persist_and_organized_export_copies_without_moving_source(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "master"
            source.mkdir()
            skin = source / "outfit.png"
            Image.new("RGBA", (64, 64), (180, 100, 140, 255)).save(skin)
            original = skin.read_bytes()

            with patch.dict(os.environ, {"APPDATA": str(root / "appdata")}):
                state = PickerState(source)
                state.set("outfit.png", status="favorite", tag="dresses")
                reloaded = PickerState(source)
                self.assertEqual(reloaded.get("outfit.png"), {"status": "favorite", "tag": "dresses"})

                picker = object.__new__(WardrobePicker)
                picker.source = source
                picker.state_store = reloaded
                target = root / "organized"
                picker._copy_entries([SkinEntry(skin, "outfit.png")], target, include_status=True)

            self.assertTrue((target / "Favorite" / "Dresses" / "outfit.png").is_file())
            self.assertTrue(skin.is_file())
            self.assertEqual(skin.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
