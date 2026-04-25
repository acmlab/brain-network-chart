import math

from mcp_server.civet_skills import (
    inspect_civet_folder,
    load_cortical_thickness_map,
    run_civet_qc_check,
    visualize_civet_surface,
)


def test_valid_civet_folder_inspection(tmp_path):
    subject = tmp_path / "sub-001"
    (subject / "native").mkdir(parents=True)
    (subject / "final").mkdir()
    (subject / "mask").mkdir()
    (subject / "classify").mkdir()
    (subject / "surfaces").mkdir()
    (subject / "thickness").mkdir()
    (subject / "qc").mkdir()
    (subject / "verify").mkdir()
    (subject / "logs").mkdir()

    (subject / "native" / "sub-001_native_t1.mnc").write_text("native")
    (subject / "final" / "sub-001_final.mnc").write_text("final")
    (subject / "mask" / "sub-001_brain_mask.mnc").write_text("mask")
    (subject / "classify" / "sub-001_classification.mnc").write_text("class")
    (subject / "surfaces" / "sub-001_left_white.obj").write_text("surface")
    (subject / "thickness" / "sub-001_thickness.txt").write_text("1 2 3")
    (subject / "qc" / "sub-001_qc.csv").write_text("subject_id,MASK_ERROR\nsub-001,1\n")
    (subject / "verify" / "sub-001_verify.png").write_text("png")
    (subject / "logs" / "civet.log").write_text("log")

    result = inspect_civet_folder(str(subject))

    assert result["status"] == "ok"
    assert result["n_files_scanned"] == 9
    for group in (
        "native_images",
        "final_images",
        "masks",
        "classification_files",
        "surfaces",
        "thickness_files",
        "qc_tables",
        "verify_images",
        "logs",
    ):
        assert result["groups"][group]["count"] >= 1


def test_missing_folder_returns_error(tmp_path):
    result = inspect_civet_folder(str(tmp_path / "missing"))

    assert result["status"] == "error"
    assert "does not exist" in result["message"]


def test_qc_pass_case(tmp_path):
    qc_file = tmp_path / "qc.tsv"
    qc_file.write_text(
        "subject_id\tMASK_ERROR\tLEFT_INTER\tRIGHT_INTER\tSURFACE_INTERSECTIONS\n"
        "sub-001\t10\t100\t25\t500\n"
    )

    result = run_civet_qc_check(str(qc_file), subject_id="sub-001")

    assert result["status"] == "ok"
    assert result["problems"] == []
    assert result["n_rows_checked"] == 1


def test_qc_warning_case(tmp_path):
    qc_file = tmp_path / "qc.txt"
    qc_file.write_text(
        "subject_id MASK_ERROR LEFT_INTER RIGHT_INTER SURFACE_INTERSECTIONS\n"
        "sub-001 11 101 99 501\n"
    )

    result = run_civet_qc_check(str(qc_file), subject_id="sub-001")

    assert result["status"] == "warning"
    assert [problem["metric"] for problem in result["problems"]] == [
        "MASK_ERROR",
        "LEFT_INTER",
        "SURFACE_INTERSECTIONS",
    ]


def test_missing_qc_file_returns_error(tmp_path):
    result = run_civet_qc_check(str(tmp_path / "missing.csv"))

    assert result["status"] == "error"
    assert "does not exist" in result["message"]


def test_valid_thickness_file_summary(tmp_path):
    thickness_file = tmp_path / "thickness.txt"
    thickness_file.write_text("1.0 2.0\n3.0 4.0\n")

    result = load_cortical_thickness_map(str(thickness_file))

    assert result["status"] == "ok"
    assert result["n_vertices"] == 4
    assert result["mean_thickness"] == 2.5
    assert math.isclose(result["std_thickness"], 1.118033988749895)
    assert result["min_thickness"] == 1.0
    assert result["max_thickness"] == 4.0
    assert result["preview_values"] == [1.0, 2.0, 3.0, 4.0]


def test_thickness_file_with_bad_tokens_returns_warning(tmp_path):
    thickness_file = tmp_path / "thickness.txt"
    thickness_file.write_text("1.0 bad -2.0 12.5 nope\n")

    result = load_cortical_thickness_map(str(thickness_file))

    assert result["status"] == "warning"
    assert result["n_vertices"] == 3
    assert result["n_skipped_tokens"] == 2
    assert any("non-numeric" in warning for warning in result["warnings"])
    assert any("Negative" in warning for warning in result["warnings"])
    assert any("Unusually large" in warning for warning in result["warnings"])


def test_missing_thickness_file_returns_error(tmp_path):
    result = load_cortical_thickness_map(str(tmp_path / "missing.txt"))

    assert result["status"] == "error"
    assert "does not exist" in result["message"]


def test_visualize_civet_surface_generates_html(tmp_path):
    surface = tmp_path / "tiny.obj"
    surface.write_text(
        "\n".join(
            [
                "v 0 0 0",
                "v 1 0 0",
                "v 0 1 0",
                "f 1 2 3",
            ]
        )
    )

    result = visualize_civet_surface(str(surface), output_dir=str(tmp_path / "outputs"))

    assert result["status"] == "ok"
    assert result["n_vertices"] == 3
    assert result["n_faces"] == 1
    assert result["warnings"] == []
    assert result["figure_path"].endswith("tiny_surface.html")
    assert (tmp_path / "outputs" / "tiny_surface.html").exists()


def test_visualize_civet_surface_with_overlay(tmp_path):
    surface = tmp_path / "tiny.obj"
    surface.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    overlay = tmp_path / "overlay.txt"
    overlay.write_text("0.1 0.2 0.3\n")

    result = visualize_civet_surface(
        str(surface),
        overlay_path=str(overlay),
        output_dir=str(tmp_path / "outputs"),
    )

    assert result["status"] == "ok"
    assert result["overlay_path"] == str(overlay)
    html = (tmp_path / "outputs" / "tiny_surface.html").read_text()
    assert "Overlay" in html


def test_visualize_civet_surface_overlay_length_mismatch_returns_error(tmp_path):
    surface = tmp_path / "tiny.obj"
    surface.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    overlay = tmp_path / "overlay.txt"
    overlay.write_text("0.1 0.2\n")

    result = visualize_civet_surface(str(surface), overlay_path=str(overlay))

    assert result["status"] == "error"
    assert "Overlay length does not match" in result["message"]
    assert result["n_vertices"] == 3
    assert result["n_faces"] == 1


def test_visualize_civet_surface_parse_failure_returns_error(tmp_path):
    surface = tmp_path / "broken.obj"
    surface.write_text("not an obj\n")

    result = visualize_civet_surface(str(surface), output_dir=str(tmp_path / "outputs"))

    assert result["status"] == "error"
    assert "Could not parse surface file" in result["message"]
