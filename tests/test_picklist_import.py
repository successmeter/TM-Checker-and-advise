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
    page = read_class_file(tmp_path / "1.txt")
    kept, dropped = page.terms, page.dropped
    assert kept == ["Adhesives for industrial purposes", "Fertilisers", "Acids"]
    assert "Class 1" in dropped and "Next" in dropped


def test_real_terms_that_look_like_page_text_are_kept(tmp_path):
    nft = ("downloadable audio and video recordings authenticated by non-fungible tokens [NFTs] featuring "
           + ", ".join(f"topic {i}" for i in range(40)))
    heading = "Paints, varnishes, lacquers; " * 12 + "colorants."
    terms = [nft, "loading dock shelters made of metal", "loading and unloading of goods", "copyright licensing",
             "search engine optimisation", "showing of films", "TV", "results analysis services"]
    note = ("Class 18 also includes unworked or semi-worked materials, namely leather, substitutes for leather and "
            "animal skins.")
    other = ("Pipes as parts of sanitary installations are in Class 11. There are pipes in Classes 6, 11, 17 and 19. "
             "The pipes in Class 11 are attached to sinks.")
    write(tmp_path, "1.txt", "\n".join(["Class 1", "Loading...", "Showing 1 to 50 of 900", "Page 2 of 18",
                                        "© IP Australia", note, other, heading] + terms))
    page = read_class_file(tmp_path / "1.txt")
    kept, dropped = page.terms, page.dropped
    assert kept == terms
    assert note in dropped and other in dropped and heading in dropped


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


PAGE_35 = """Class 35
Advertising; business management, organization and administration; office functions.
Show detail
Notes
Class 35 services are those provided by persons or enterprises that directly assist in the operation and management of another commercial or industrial enterprise. Simply because an enterprise conducts business does not classify the activity of that enterprise in Class 35.
Similarly, a claim for advertising or marketing in class 35 covers advertising or marketing services provided by professionals for the enterprises of others.
strategic business planning
advertising
Administrative services relating to compilation of data belong to Class 35. If a service is administrative in nature, it is normally classified in Class 35.
business strategic planning
"""


def test_class_heading_and_notes_are_kept_for_the_class_detail(tmp_path):
    from fastapi.testclient import TestClient
    from tm_advisor.api import create_app
    from tm_advisor.register import FixtureRegisterClient

    write(tmp_path / "pages", "35.txt", PAGE_35)
    page = read_class_file(tmp_path / "pages" / "35.txt")
    assert page.terms == ["strategic business planning", "advertising", "business strategic planning"]
    assert page.heading == "Advertising; business management, organization and administration; office functions."
    assert [n[:20] for n in page.notes] == ["Class 35 services ar", "Similarly, a claim f", "Administrative servi"]

    out = tmp_path / "picklist.json"
    import_folder(tmp_path / "pages", out, log=lambda _: None)
    write(tmp_path / "more", "25.txt", "Clothing\nFootwear\n")
    import_folder(tmp_path / "more", out, log=lambda _: None)  # a later batch keeps class 35's notes
    picklist = Picklist.load(out)
    assert picklist.class_notes[35]["heading"].startswith("Advertising; business management")

    classes = TestClient(create_app(FixtureRegisterClient([]), picklist)).get("/api/classes").json()
    c35 = next(c for c in classes if c["class_number"] == 35)
    assert c35["heading"] == page.heading and len(c35["notes"]) == 3
    assert next(c for c in classes if c["class_number"] == 1)["notes"] == []
