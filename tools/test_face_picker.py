from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from face_picker import FacePicker, discover_faces


class FacePickerTests(unittest.TestCase):
    def test_face_gallery_discovers_nested_source_skins(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            nested = source / "Dresses"
            nested.mkdir(parents=True)
            Image.new("RGBA", (64, 64), (10, 20, 30, 255)).save(source / "one.png")
            Image.new("RGBA", (64, 64), (40, 50, 60, 255)).save(nested / "two.png")
            (source / "not-a-skin.txt").write_text("ignored", encoding="utf-8")

            entries = discover_faces(source)

            self.assertEqual({entry.relative for entry in entries}, {"one.png", "Dresses/two.png"})
            self.assertEqual(FacePicker._card_name("a_very-long-face-name"), "a very long face name")


if __name__ == "__main__":
    unittest.main()
