from pathlib import Path

import pytest

from crdis.container import is_rpt, list_streams

REPO = Path(__file__).resolve().parent.parent
SAMPLES = REPO / "samples"

SAMPLE_FILES = [
    SAMPLES / "001_empty" / "report.rpt",
    SAMPLES / "002_one_label" / "report.rpt",
]


@pytest.mark.parametrize("path", SAMPLE_FILES)
def test_is_rpt(path: Path) -> None:
    assert path.exists(), f"missing sample {path}"
    assert is_rpt(path)


@pytest.mark.parametrize("path", SAMPLE_FILES)
def test_expected_streams_present(path: Path) -> None:
    """Every CRforVS 13.x .rpt we've seen has these 5 stream names."""
    expected = {
        "\x05SummaryInformation",
        "Contents",
        "CrystalReportDesignerStream",
        "QESession",
        "ReportInfo",
    }
    streams = list_streams(path)
    assert {s.name for s in streams} == expected
