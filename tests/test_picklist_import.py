import json

import pytest

from tm_advisor.picklist import Picklist
from tm_advisor.picklist_import import class_files, import_folder, read_class_file


def write(folder, name, text):
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")


def test_pasted_page_keeps_terms_and_drops_page_furniture(tmp_path):
    write(tmp_path, "1.txt", "Class 1\nShowing 1-50 of 1234\nAdhesives for industrial purposes\n\n\tFertilisers  \n"
                             "Fertilisers\n2\nNext\nAcids\n")
    kept, dropped = read_class_file(tmp_path / "1.txt")
    assert kept == ["Adhesives for industrial purposes", "Fertilisers", "Acids"]
    assert "Class 1" in dropped and "Next" in dropped


def test_real_terms_that_look_like_page_text_are_kept(tmp_path):
    terms = ["loading dock shelters made of metal", "loading and unloading of goods", "copyright licensing",
             "search engine optimisation", "showing of films", "TV", "results analysis services"]
    note = ("Class 18 also includes unworked or semi-worked materials, namely leather, substitutes for leather and "
            "animal skins.")
    other = ("Pipes as parts of sanitary installations are in Class 11. There are pipes in Classes 6, 11, 17 and 19. "
             "The pipes in Class 11 are attached to sinks.")
    write(tmp_path, "1.txt", "\n".join(["Class 1", "Loading...", "Showing 1 to 50 of 900", "Page 2 of 18",
                                        "© IP Australia", note, other] + terms))
    kept, dropped = read_class_file(tmp_path / "1.txt")
    assert kept == terms
    assert note in dropped and other in dropped


def test_file_names(tmp_path):
    for name in ("1.txt", "class 2.txt", "Class_45.txt", "46.txt", "notes.txt"):
        write(tmp_path, name, "x")
    assert sorted(class_files(tmp_path)) == [1, 2, 45]


def test_import_in_batches_keeps_earlier_classes(tmp_path):
    out = tmp_path / "picklist.json"
    write(tmp_path / "a", "1.txt", "Adhesives for industrial purposes\nFertilisers\n")
    write(tmp_path / "a", "25.txt", "Clothing\nFootwear\n")
    import_folder(tmp_path / "a", out, log=lambda _: None)
    write(tmp_path / "b", "35.txt", "Strategic business planning\nAdvertising\n")
    change = import_folder(tmp_path / "b", out, log=lambda _: None)
    assert change.after == 6
    picklist = Picklist.load(out)
    assert not picklist.is_sample
    assert picklist.match(25, "Footwear") and picklist.match(35, "Advertising")
    assert "copied by hand" in json.loads(out.read_text())["source"]


def test_empty_file_changes_nothing(tmp_path):
    write(tmp_path, "3.txt", "Class 3\nNext\n")
    with pytest.raises(SystemExit, match="no terms"):
        import_folder(tmp_path, tmp_path / "p.json", log=lambda _: None)
    assert not (tmp_path / "p.json").exists()
