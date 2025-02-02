from ChildProject.projects import ChildProject
from ChildProject.annotations import AnnotationManager
from ChildProject.tables import IndexTable
from ChildProject.converters import *
import glob
import pandas as pd
import numpy as np
import datetime
import os
import pytest
import shutil
import subprocess
import sys


def standardize_dataframe(df, columns):
    df = df[list(columns)]
    return df.sort_index(axis=1).sort_values(list(columns)).reset_index(drop=True)


@pytest.fixture(scope="function")
def project(request):
    if not os.path.exists("output/annotations"):
        shutil.copytree(src="examples/valid_raw_data", dst="output/annotations")

    project = ChildProject("output/annotations")
    yield project

    os.remove("output/annotations/metadata/annotations.csv")
    for raw_annotation in glob.glob("output/annotations/annotations/*.*/converted"):
        shutil.rmtree(raw_annotation)


def test_csv():
    converted = CsvConverter().convert("tests/data/csv.csv").fillna("NA")
    truth = pd.read_csv("tests/truth/csv.csv").fillna("NA")

    pd.testing.assert_frame_equal(
        standardize_dataframe(converted, converted.columns),
        standardize_dataframe(truth, converted.columns),
    )


def test_vtc():
    converted = VtcConverter().convert("tests/data/vtc.rttm")
    truth = pd.read_csv("tests/truth/vtc.csv").fillna("NA")

    pd.testing.assert_frame_equal(
        standardize_dataframe(converted, converted.columns),
        standardize_dataframe(truth, converted.columns),
    )


def test_vcm():
    converted = VcmConverter().convert("tests/data/vcm.rttm")
    truth = pd.read_csv("tests/truth/vcm.csv").fillna("NA")

    pd.testing.assert_frame_equal(
        standardize_dataframe(converted, converted.columns),
        standardize_dataframe(truth, converted.columns),
    )


def test_alice():
    converted = AliceConverter().convert("tests/data/alice.txt")
    truth = pd.read_csv("tests/truth/alice.csv").fillna("NA")

    pd.testing.assert_frame_equal(
        standardize_dataframe(converted, converted.columns),
        standardize_dataframe(truth, converted.columns),
    )


def test_eaf():
    converted = EafConverter().convert("tests/data/eaf.eaf")
    truth = pd.read_csv("tests/truth/eaf.csv", dtype={"transcription": str}).fillna(
        "NA"
    )

    pd.testing.assert_frame_equal(
        standardize_dataframe(converted, converted.columns),
        standardize_dataframe(truth, converted.columns),
    )


def test_eaf_any_tier():
    converted = EafConverter().convert("tests/data/eaf_any_tier.eaf", new_tiers = ['newtier', 'newtier2']) \
                              .replace('', "NA") \
                              .fillna("NA")
    truth = pd.read_csv("tests/truth/eaf_any_tier.csv", dtype={"transcription": str}).fillna(
        "NA"
    )

    pd.testing.assert_frame_equal(
        standardize_dataframe(converted, converted.columns),
        standardize_dataframe(truth, converted.columns),
    )


def test_textgrid():
    converted = TextGridConverter().convert("tests/data/textgrid.TextGrid")
    truth = pd.read_csv("tests/truth/textgrid.csv", dtype={"ling_type": str}).fillna(
        "NA"
    )

    pd.testing.assert_frame_equal(
        standardize_dataframe(converted, converted.columns),
        standardize_dataframe(truth, converted.columns),
    )


def test_cha():
    converted = ChatConverter.convert("tests/data/vandam.cha")
    truth = pd.read_csv("tests/truth/cha.csv").fillna("NA")

    pd.testing.assert_frame_equal(
        standardize_dataframe(converted, converted.columns),
        standardize_dataframe(truth, converted.columns),
    )


@pytest.mark.parametrize("its", ["example_lena_new", "example_lena_old"])
def test_its(its):
    converted = ItsConverter().convert(os.path.join("tests/data", its + ".its"))
    truth = pd.read_csv(
        os.path.join("tests/truth/its", "{}_ITS_Segments.csv".format(its))
    )  # .fillna('NA')
    check_its(converted, truth)


def test_import(project):
    am = AnnotationManager(project)

    input_annotations = pd.read_csv("examples/valid_raw_data/annotations/input.csv")
    am.import_annotations(input_annotations)
    am.read()

    assert (
        am.annotations.shape[0] == input_annotations.shape[0]
    ), "imported annotations length does not match input"

    assert all(
        [
            os.path.exists(
                os.path.join(
                    project.path,
                    "annotations",
                    a["set"],
                    "converted",
                    a["annotation_filename"],
                )
            )
            for a in am.annotations.to_dict(orient="records")
        ]
    ), "some annotations are missing"

    errors, warnings = am.validate()
    assert len(errors) == 0 and len(warnings) == 0, "malformed annotations detected"

    for dataset in ["eaf_basic", "textgrid", "eaf_solis"]:
        annotations = am.annotations[am.annotations["set"] == dataset]
        segments = am.get_segments(annotations)
        segments.drop(columns=set(annotations.columns) - {"raw_filename"}, inplace=True)
        truth = pd.read_csv("tests/truth/{}.csv".format(dataset))

        print(segments)
        print(truth)

        pd.testing.assert_frame_equal(
            standardize_dataframe(segments, set(truth.columns.tolist())),
            standardize_dataframe(truth, set(truth.columns.tolist())),
            check_less_precise=True,
        )


def test_intersect(project):
    am = AnnotationManager(project)

    input_annotations = pd.read_csv("examples/valid_raw_data/annotations/intersect.csv")
    am.import_annotations(input_annotations)

    intersection = AnnotationManager.intersection(
        am.annotations[am.annotations["set"].isin(["textgrid", "vtc_rttm"])]
    ).convert_dtypes()

    a = intersection[intersection["set"] == "textgrid"]
    b = intersection[intersection["set"] == "vtc_rttm"]

    columns = a.columns.tolist()
    columns.remove("imported_at")
    columns.remove("package_version")

    pd.testing.assert_frame_equal(
        standardize_dataframe(a, columns),
        standardize_dataframe(
            pd.read_csv("tests/truth/intersect_a.csv"), columns
        ).convert_dtypes(),
    )

    pd.testing.assert_frame_equal(
        standardize_dataframe(b, columns),
        standardize_dataframe(
            pd.read_csv("tests/truth/intersect_b.csv"), columns
        ).convert_dtypes(),
    )


def test_within_ranges(project):
    am = AnnotationManager(project)

    annotations = [
        {
            "recording_filename": "sound.wav",
            "set": "matching",
            "range_onset": onset,
            "range_offset": onset + 500,
        }
        for onset in np.arange(0, 4000, 500)
    ]

    matching_annotations = pd.DataFrame(
        [
            annotation
            for annotation in annotations
            if annotation["range_onset"] >= 1000 and annotation["range_offset"] <= 3000
        ]
    )

    am.annotations = pd.DataFrame(annotations)

    ranges = pd.DataFrame(
        [{"recording_filename": "sound.wav", "range_onset": 1000, "range_offset": 3000}]
    )

    matches = am.get_within_ranges(ranges, ["matching"])

    pd.testing.assert_frame_equal(
        standardize_dataframe(matching_annotations, matching_annotations.columns),
        standardize_dataframe(matches, matching_annotations.columns),
    )

    ranges["range_offset"] = 5000
    exception_caught = False
    try:
        matches = am.get_within_ranges(ranges, ["matching"], "raise")
    except Exception as e:
        if str(e) == "annotations from set 'matching' do not cover the whole selected range for recording 'sound.wav', 3.000s covered instead of 4.000s":
            exception_caught = True

    assert (
        exception_caught
    ), "get_within_ranges should raise an exception when annotations do not fully cover the required ranges"


def test_merge(project):
    am = AnnotationManager(project)

    input_annotations = pd.read_csv("examples/valid_raw_data/annotations/input.csv")
    input_annotations = input_annotations[
        input_annotations["set"].isin(["vtc_rttm", "alice"])
    ]
    am.import_annotations(input_annotations)
    am.read()

    am.read()
    am.merge_sets(
        left_set="vtc_rttm",
        right_set="alice",
        left_columns=["speaker_type"],
        right_columns=["phonemes", "syllables", "words"],
        output_set="alice_vtc",
    )
    am.read()

    segments = am.get_segments(am.annotations[am.annotations["set"] == "alice_vtc"])
    vtc_segments = am.get_segments(am.annotations[am.annotations["set"] == "vtc_rttm"])
    assert segments.shape[0] == vtc_segments.shape[0]
    assert segments.shape[1] == vtc_segments.shape[1] + 3

    adult_segments = (
        segments[segments["speaker_type"].isin(["FEM", "MAL"])]
        .sort_values(["segment_onset", "segment_offset"])
        .reset_index(drop=True)
    )
    alice = (
        am.get_segments(am.annotations[am.annotations["set"] == "alice"])
        .sort_values(["segment_onset", "segment_offset"])
        .reset_index(drop=True)
    )

    pd.testing.assert_frame_equal(
        adult_segments[["phonemes", "syllables", "words"]],
        alice[["phonemes", "syllables", "words"]],
    )


def test_clipping(project):
    am = AnnotationManager(project)

    input_annotations = pd.read_csv("examples/valid_raw_data/annotations/input.csv")
    am.import_annotations(input_annotations[input_annotations["set"] == "vtc_rttm"])
    am.read()

    start = 1981000
    stop = 1984000
    segments = am.get_segments(am.annotations[am.annotations["set"] == "vtc_rttm"])
    segments = am.clip_segments(segments, start, stop)

    assert (
        segments["segment_onset"].between(start, stop).all()
        and segments["segment_offset"].between(start, stop).all()
    ), "segments not properly clipped"
    assert segments.shape[0] == 2, "got {} segments, expected 2".format(
        segments.shape[0]
    )


def test_within_time_range(project):
    am = AnnotationManager(project)
    am.project.recordings = pd.read_csv("tests/data/time_range_recordings.csv")

    annotations = pd.read_csv("tests/data/time_range_annotations.csv")
    matches = am.get_within_time_range(annotations, "09:00", "20:00")

    truth = pd.read_csv("tests/truth/time_range.csv")

    pd.testing.assert_frame_equal(
        standardize_dataframe(matches, truth.columns),
        standardize_dataframe(truth, truth.columns),
    )

    exception_caught = False
    try:
        matches = am.get_within_time_range(annotations, "9am", "8pm")
    except ValueError as e:
        exception_caught = True

    assert exception_caught, "no exception was thrown despite invalid times"


def test_segments_timestamps(project):
    am = AnnotationManager(project)

    segments = pd.DataFrame(
        [
            {
                "recording_filename": "sound.wav",
                "segment_onset": 3600 * 1000,
                "segment_offset": 3600 * 1000 + 1000,
            }
        ]
    )
    segments = am.get_segments_timestamps(segments)

    truth = pd.DataFrame(
        [
            {
                "recording_filename": "sound.wav",
                "segment_onset": 3600 * 1000,
                "segment_offset": 3600 * 1000 + 1000,
                "onset_time": datetime.datetime(2020, 4, 20, 9 + 1, 0, 0),
                "offset_time": datetime.datetime(2020, 4, 20, 9 + 1, 0, 1),
            }
        ]
    )

    pd.testing.assert_frame_equal(
        standardize_dataframe(segments, truth.columns),
        standardize_dataframe(truth, truth.columns),
    )


def test_rename(project):
    am = AnnotationManager(project)

    input_annotations = pd.read_csv("examples/valid_raw_data/annotations/input.csv")
    am.import_annotations(input_annotations[input_annotations["set"] == "textgrid"])
    am.read()
    tg_count = am.annotations[am.annotations["set"] == "textgrid"].shape[0]

    am.rename_set("textgrid", "renamed")
    am.read()

    errors, warnings = am.validate()
    assert len(errors) == 0 and len(warnings) == 0, "malformed annotations detected"

    assert am.annotations[am.annotations["set"] == "textgrid"].shape[0] == 0
    assert am.annotations[am.annotations["set"] == "renamed"].shape[0] == tg_count


def custom_function(filename):
    from ChildProject.converters import VtcConverter

    df = pd.read_csv(
        filename,
        sep=" ",
        names=[
            "type",
            "file",
            "chnl",
            "tbeg",
            "tdur",
            "ortho",
            "stype",
            "name",
            "conf",
            "unk",
        ],
    )

    df["segment_onset"] = 1000 * df["tbeg"].astype(int)
    df["segment_offset"] = (1000 * (df["tbeg"] + df["tdur"])).astype(int)
    df["speaker_type"] = df["name"].map(VtcConverter.SPEAKER_TYPE_TRANSLATION)

    df.drop(
        [
            "type",
            "file",
            "chnl",
            "tbeg",
            "tdur",
            "ortho",
            "stype",
            "name",
            "conf",
            "unk",
        ],
        axis=1,
        inplace=True,
    )
    return df


def test_custom_importation(project):
    am = AnnotationManager(project)
    input = pd.DataFrame(
        [
            {
                "set": "vtc_rttm",
                "range_onset": 0,
                "range_offset": 4000,
                "recording_filename": "sound.wav",
                "time_seek": 0,
                "raw_filename": "example.rttm",
                "format": "custom",
            }
        ]
    )

    am.import_annotations(input, import_function=custom_function)
    am.read()

    errors, warnings = am.validate()
    assert len(errors) == 0


def test_set_from_path(project):
    am = AnnotationManager(project)

    assert am.set_from_path(os.path.join(project.path, "annotations/set")) == "set"
    assert am.set_from_path(os.path.join(project.path, "annotations/set/")) == "set"
    assert (
        am.set_from_path(os.path.join(project.path, "annotations/set/subset"))
        == "set/subset"
    )
    assert (
        am.set_from_path(os.path.join(project.path, "annotations/set/subset/converted"))
        == "set/subset"
    )
    assert (
        am.set_from_path(os.path.join(project.path, "annotations/set/subset/raw"))
        == "set/subset"
    )


# its
def gather_columns_to_dict(start_col, end_col, row):
    n = 1
    l = []
    while True:
        start_key = "{}{}".format(start_col, n)
        end_key = "{}{}".format(end_col, n)

        if start_key in row.keys() and not pd.isnull(row[start_key]):
            l.append({"start": row[start_key], "end": row[end_key]})
        else:
            return l

        n += 1


from functools import partial


def check_its(segments, truth):
    segments["cries"] = segments["cries"].astype(str)
    segments["utterances"] = (
        segments["utterances"]
        .apply(lambda l: [{"start": u["start"], "end": u["end"]} for u in l])
        .astype(str)
    )
    segments["vfxs"] = segments["vfxs"].astype(str)

    truth.rename(
        columns={
            "startTime": "segment_onset",
            "endTime": "segment_offset",
            "average_dB": "average_db",
            "peak_dB": "peak_db",
            "blkTypeId": "lena_block_number",
            "convTurnType": "lena_conv_turn_type",
            "convFloorType": "lena_conv_floor_type",
        },
        inplace=True,
    )

    truth["words"] = (
        truth[["maleAdultWordCnt", "femaleAdultWordCnt"]]
        .astype(float, errors="ignore")
        .fillna(0)
        .sum(axis=1)
    )
    truth["utterances_count"] = (
        truth[["femaleAdultUttCnt", "maleAdultUttCnt", "childUttCnt"]]
        .astype(float, errors="ignore")
        .fillna(0)
        .sum(axis=1)
    )
    truth["utterances_length"] = (
        truth[["femaleAdultUttLen", "maleAdultUttLen", "childUttLen"]]
        .astype(float, errors="ignore")
        .fillna(0)
        .sum(axis=1)
        .mul(1000)
        .astype(int)
    )
    truth["non_speech_length"] = (
        truth[["femaleAdultNonSpeechLen", "maleAdultNonSpeechLen"]]
        .astype(float, errors="ignore")
        .fillna(0)
        .sum(axis=1)
        .mul(1000)
        .astype(int)
    )

    truth["lena_block_type"] = truth.apply(
        lambda row: "pause" if row["blkType"] == "Pause" else row["convType"], axis=1
    )
    truth["lena_response_count"] = (
        truth["conversationInfo"]
        .apply(lambda s: "NA" if pd.isnull(s) else s.split("|")[1:-1][3])
        .astype(str)
    )

    truth["cries"] = truth.apply(
        partial(gather_columns_to_dict, "startCry", "endCry"), axis=1
    ).astype(str)
    truth["utterances"] = truth.apply(
        partial(gather_columns_to_dict, "startUtt", "endUtt"), axis=1
    ).astype(str)
    truth["vfxs"] = truth.apply(
        partial(gather_columns_to_dict, "startVfx", "endVfx"), axis=1
    ).astype(str)

    truth["segment_onset"] = (truth["segment_onset"] * 1000).astype(int)
    truth["segment_offset"] = (truth["segment_offset"] * 1000).astype(int)

    truth["lena_conv_floor_type"].fillna("NA", inplace=True)
    truth["lena_conv_turn_type"].fillna("NA", inplace=True)
    truth["lena_response_count"].fillna("NA", inplace=True)

    columns = [
        "segment_onset",
        "segment_offset",
        "average_db",
        "peak_db",
        "words",
        "utterances_count",
        "utterances_length",
        "non_speech_length",
        "lena_block_number",  #'lena_block_type',
        "lena_response_count",
        "cries",
        "utterances",
        "vfxs",
        "lena_conv_turn_type",
        "lena_conv_floor_type",
    ]

    pd.testing.assert_frame_equal(
        standardize_dataframe(truth, columns), standardize_dataframe(segments, columns)
    )

