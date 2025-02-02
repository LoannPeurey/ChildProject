from abc import ABC, abstractmethod
import argparse
import datetime
import multiprocessing as mp
import numpy as np
import pandas as pd
from typing import Union, List

import ChildProject
from ChildProject.pipelines.pipeline import Pipeline

pipelines = {}


class Metrics(ABC):
    def __init__(
        self,
        project: ChildProject.projects.ChildProject,
        by: str = "recording_filename",
        recordings: Union[str, List[str], pd.DataFrame] = None,
        from_time: str = None,
        to_time: str = None,
        rec_cols: str = None,
        child_cols: str = None,
    ):

        self.project = project
        self.am = ChildProject.annotations.AnnotationManager(self.project)

        #necessary columns to construct the metrics
        join_columns = {
            "recording_filename",
            "child_id",
            "duration",
            "session_id",
            "session_offset",
        }
        #get existing columns of the dataset for recordings
        correct_cols = set(self.project.recordings.columns)
        if by not in correct_cols: exit("<{}> is not specified in this dataset, cannot extract by it, change your --by option".format(by))
        if rec_cols:
            #when user requests recording columns, build the list and verify they exist (warn otherwise)
            rec_cols=set(rec_cols.split(","))
            for i in rec_cols:
                if i not in correct_cols:
                    print("Warning, requested column <{}> does not exist in recordings.csv, ignoring this column. existing columns are : {}".format(i,correct_cols))
            rec_cols &= correct_cols
            #add wanted columns to the one we already get
            join_columns.update(rec_cols)
        self.rec_cols = rec_cols
        
        join_columns &= correct_cols
        
        #join dataset annotation with their info in recordings.csv
        self.am.annotations = self.am.annotations.merge(
            self.project.recordings[list(join_columns)],
            left_on="recording_filename",
            right_on="recording_filename",
        )
        
        #get existing columns of the dataset for children
        correct_cols = set(self.project.children.columns)
        if child_cols:
            #when user requests children columns, build the list and verify they exist (warn otherwise)
            child_cols = set(child_cols.split(","))
            child_cols.add("child_id")
            for i in child_cols:
                if i not in correct_cols:
                    print("Warning, requested column <{}> does not exist in children.csv, ignoring this column. existing columns are : {}".format(i,correct_cols))
            child_cols &= correct_cols
            self.child_cols = child_cols
    
            #join dataset annotation with their info in children.csv
            self.am.annotations = self.am.annotations.merge(
                self.project.children[list(child_cols)],
                left_on="child_id",
                right_on="child_id",
            )
        else:
            self.child_cols = None
        
        self.by = by
        self.segments = pd.DataFrame()

        self.recordings = Pipeline.recordings_from_list(recordings)

        self.from_time = from_time
        self.to_time = to_time

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        pipelines[cls.SUBCOMMAND] = cls

    @abstractmethod
    def extract(self):
        pass

    def retrieve_segments(self, sets: List[str], unit: str):
        annotations = self.am.annotations[self.am.annotations[self.by] == unit]
        annotations = annotations[annotations["set"].isin(sets)]

        if self.from_time and self.to_time:
            annotations = self.am.get_within_time_range(
                annotations, self.from_time, self.to_time, errors="coerce"
            )

        try:
            segments = self.am.get_segments(annotations)
        except Exception as e:
            print(str(e))
            return pd.DataFrame(), pd.DataFrame()

        # prevent overflows
        segments["duration"] = (
            (segments["segment_offset"] / 1000 - segments["segment_onset"] / 1000)
            .astype(float)
            .fillna(0)
        )

        return annotations, segments


class LenaMetrics(Metrics):
    """LENA metrics extractor. 
    Extracts a number of metrics from the LENA .its annotations.

    :param project: ChildProject instance of the target dataset.
    :type project: ChildProject.projects.ChildProject
    :param set: name of the set associated to the .its annotations
    :type set: str
    :param types: list of LENA vocalization/noise types (e.g. OLN, TVN)
    :type types: list
    :param recordings: recordings to sample from; if None, all recordings will be sampled, defaults to None
    :type recordings: Union[str, List[str], pd.DataFrame], optional
    :param from_time: If specified (in HH:MM format), ignore annotations outside of the given time-range, defaults to None
    :type from_time: str, optional
    :param to_time:  If specified (in HH:MM format), ignore annotations outside of the given time-range, defaults to None
    :type to_time: str, optional
    :param rec_cols: columns from recordings.csv to include in the outputted metrics (optional), recording_filename,session_id,child_id,duration are always included if possible and dont need to be specified. Any column that is not unique for a given unit (eg date_iso for a child_id being recorded on multiple days) will output a <NA> value
    :type rec_cols: str, optional
    :param child_cols: columns from children.csv to include in the outputted metrics (optional), None by default
    :type child_cols: str, optional
    :param by: units to sample from, defaults to 'recording_filename'
    :type by: str, optional
    :param threads: amount of threads to run on, defaults to 1
    :type threads: int, optional
    """

    SUBCOMMAND = "lena"

    def __init__(
        self,
        project: ChildProject.projects.ChildProject,
        set: str,
        types: list = [],
        recordings: Union[str, List[str], pd.DataFrame] = None,
        from_time: str = None,
        to_time: str = None,       
        rec_cols: str = None,
        child_cols: str = None,
        by: str = "recording_filename",
        threads: int = 1,
    ):

        super().__init__(project, by, recordings, from_time, to_time, rec_cols, child_cols)

        self.set = set
        self.types = types
        self.threads = int(threads)

        if self.set not in self.am.annotations["set"].values:
            raise ValueError(
                f"annotation set '{self.set}' was not found in the index; "
                "check spelling and make sure the set was properly imported."
            )

    def _process_unit(self, unit: str):
        import ast

        metrics = {self.by: unit}
        annotations, its = self.retrieve_segments([self.set], unit)

        speaker_types = ["FEM", "MAL", "CHI", "OCH"]
        adults = ["FEM", "MAL"]

        if "speaker_type" in its.columns:
            its = its[
                (its["speaker_type"].isin(speaker_types))
                | (its["lena_speaker"].isin(self.types))
            ]
        else:
            return metrics

        if len(its) == 0:
            return metrics

        unit_duration = (
            annotations["range_offset"] - annotations["range_onset"]
        ).sum() / 1000

        its_agg = its.groupby("speaker_type").agg(
            voc_ph=("duration", "count"),
            voc_dur_ph=("duration", "sum"),
            avg_voc_dur=("duration", "mean"),
            wc_ph=("words", "sum"),
        )

        for speaker in speaker_types:
            if speaker not in its_agg.index:
                continue

            metrics["voc_{}_ph".format(speaker.lower())] = (
                3600 / unit_duration
            ) * its_agg.loc[speaker, "voc_ph"]
            metrics["voc_dur_{}_ph".format(speaker.lower())] = (
                3600 / unit_duration
            ) * its_agg.loc[speaker, "voc_dur_ph"]
            metrics["avg_voc_dur_{}".format(speaker.lower())] = its_agg.loc[
                speaker, "avg_voc_dur"
            ]

            if speaker in adults:
                metrics["wc_{}_ph".format(speaker.lower())] = (
                    3600 / unit_duration
                ) * its_agg.loc[speaker, "wc_ph"]

        if len(self.types):
            its_agg = its.groupby("lena_speaker").agg(
                voc_ph=("duration", "count"),
                voc_dur_ph=("duration", "sum"),
                avg_voc_dur=("duration", "mean"),
            )

        for lena_type in self.types:
            if lena_type not in its_agg.index:
                continue

            metrics["voc_{}_ph".format(lena_type.lower())] = (
                3600 / unit_duration
            ) * its_agg.loc[lena_type, "voc_ph"]
            metrics["voc_dur_{}_ph".format(lena_type.lower())] = (
                3600 / unit_duration
            ) * its_agg.loc[lena_type, "voc_dur_ph"]
            metrics["avg_voc_dur_{}".format(lena_type.lower())] = its_agg.loc[
                lena_type, "avg_voc_dur"
            ]

        chi = its[its["speaker_type"] == "CHI"]
        cries = chi["cries"].apply(lambda x: len(ast.literal_eval(x))).sum()
        vfxs = chi["vfxs"].apply(lambda x: len(ast.literal_eval(x))).sum()
        utterances = chi["utterances_count"].sum()

        metrics["lp_n"] = utterances / (utterances + cries + vfxs)
        metrics["lp_dur"] = chi["utterances_length"].sum() / (
            chi["child_cry_vfx_len"].sum() + chi["utterances_length"].sum()
        )

        metrics["wc_adu_ph"] = its["words"].sum() * 3600 / unit_duration

        #add info for child_id and duration to the dataframe
        metrics["child_id"] = self.project.recordings[
            self.project.recordings[self.by] == unit
        ]["child_id"].iloc[0]
        metrics["duration"] = unit_duration
        
        #get and add to dataframe children.csv columns asked
        if self.child_cols:
            for label in self.child_cols:
                metrics[label]=self.project.children[
                        self.project.children["child_id"] == metrics["child_id"]
                ][label].iloc[0]
                
        #get and add to dataframe recordings.csv columns asked
        if self.rec_cols:
            for label in self.rec_cols:
                #for every unit drop the duplicates for that column
                value=self.project.recordings[
                        self.project.recordings[self.by] == unit
                ][label].drop_duplicates()
                #check that there is only one row remaining (ie this column has a unique value for that unit)
                if len(value) == 1:
                    metrics[label]=value.iloc[0]
                #otherwise, leave the column as NA
                else:
                    metrics[label]="NA"

        return metrics

    def extract(self):
        recordings = self.project.get_recordings_from_list(self.recordings)

        if self.threads == 1:
            self.metrics = pd.DataFrame(
                [self._process_unit(unit) for unit in recordings[self.by].unique()]
            )
        else:
            with mp.Pool(
                processes=self.threads if self.threads >= 1 else mp.cpu_count()
            ) as pool:
                self.metrics = pd.DataFrame(
                    pool.map(self._process_unit, recordings[self.by].unique())
                )

        self.metrics.set_index(self.by, inplace=True)
        return self.metrics

    @staticmethod
    def add_parser(subparsers, subcommand):
        parser = subparsers.add_parser(subcommand, help="LENA metrics")
        parser.add_argument("set", help="name of the LENA its annotations set")
        parser.add_argument(
            "--types",
            help="list of LENA vocalizaton types to include",
            choices=[
                "TVF",
                "FAN",
                "OLN",
                "SIL",
                "NOF",
                "CXF",
                "OLF",
                "CHF",
                "MAF",
                "TVN",
                "NON",
                "CXN",
                "CHN",
                "MAN",
                "FAF",
            ],
            nargs="+", default=[],
        )
        parser.add_argument(
            "--threads", help="amount of threads to run on", default=1, type=int
        )


class AclewMetrics(Metrics):
    """ACLEW metrics extractor.
    Extracts a number of metrics from the ACLEW pipeline annotations, which includes:

     - The Voice Type Classifier by Lavechin et al. (arXiv:2005.12656)
     - The Automatic LInguistic Unit Count Estimator (ALICE) by Räsänen et al. (doi:10.3758/s13428-020-01460-x)
     - The VoCalisation Maturity model (VCMNet) by Al Futaisi et al. (doi:10.1145/3340555.3353751)

    :param project: ChildProject instance of the target dataset.
    :type project: ChildProject.projects.ChildProject
    :param vtc: name of the set associated to the VTC annotations
    :type vtc: str
    :param alice: name of the set associated to the ALICE annotations
    :type alice: str
    :param vcm: name of the set associated to the VCM annotations
    :type vcm: str
    :param recordings: recordings to sample from; if None, all recordings will be sampled, defaults to None
    :type recordings: Union[str, List[str], pd.DataFrame], optional
    :param from_time: If specified (in HH:MM format), ignore annotations outside of the given time-range, defaults to None
    :type from_time: str, optional
    :param to_time:  If specified (in HH:MM format), ignore annotations outside of the given time-range, defaults to None
    :type to_time: str, optional
    :param rec_cols: columns from recordings.csv to include in the outputted metrics (optional), recording_filename,session_id,child_id,duration are always included if possible and dont need to be specified. Any column that is not unique for a given unit (eg date_iso for a child_id being recorded on multiple days) will output a <NA> value
    :type rec_cols: str, optional
    :param child_cols: columns from children.csv to include in the outputted metrics (optional), None by default
    :type child_cols: str, optional
    :param by: units to sample from, defaults to 'recording_filename'
    :type by: str, optional
    :param threads: amount of threads to run on, defaults to 1
    :type threads: int, optional
    """

    SUBCOMMAND = "aclew"

    def __init__(
        self,
        project: ChildProject.projects.ChildProject,
        vtc: str = "vtc",
        alice: str = "alice",
        vcm: str = "vcm",
        recordings: Union[str, List[str], pd.DataFrame] = None,
        from_time: str = None,
        to_time: str = None,
        rec_cols: str = None,
        child_cols: str = None,
        by: str = "recording_filename",
        threads: int = 1,
    ):

        super().__init__(project, by, recordings, from_time, to_time, rec_cols, child_cols)

        self.vtc = vtc
        self.alice = alice
        self.vcm = vcm
        self.threads = int(threads)
        
        if self.vtc not in self.am.annotations["set"].values:
            raise ValueError(
                f"The VTC set '{self.vtc}' was not found in the index; "
                "check spelling and make sure the set was properly imported."
            )

        if self.alice not in self.am.annotations["set"].values:
            print(f"The ALICE set ('{self.alice}') was not found in the index.")

        if self.vcm not in self.am.annotations["set"].values:
            print(f"The VCM set ('{self.vcm}') was not found in the index.")

    def _process_unit(self, unit: str):
        metrics = {self.by: unit}
        annotations, segments = self.retrieve_segments(
            [self.vtc, self.alice, self.vcm], unit
        )

        speaker_types = ["FEM", "MAL", "CHI", "OCH"]
        adults = ["FEM", "MAL"]

        if "speaker_type" in segments.columns:
            segments = segments[segments["speaker_type"].isin(speaker_types)]
        else:
            return metrics

        if len(segments) == 0:
            return metrics

        vtc_ann = annotations[annotations["set"] == self.vtc]
        unit_duration = (vtc_ann["range_offset"] - vtc_ann["range_onset"]).sum() / 1000

        vtc = segments[segments["set"] == self.vtc]
        alice = segments[segments["set"] == self.alice]
        vcm = segments[segments["set"] == self.vcm]

        vtc_agg = vtc.groupby("speaker_type").agg(
            voc_ph=("duration", "count"),
            voc_dur_ph=("duration", "sum"),
            avg_voc_dur=("duration", "mean"),
        )

        for speaker in speaker_types:
            if speaker not in vtc_agg.index:
                continue

            metrics["voc_{}_ph".format(speaker.lower())] = (
                3600 / unit_duration
            ) * vtc_agg.loc[speaker, "voc_ph"]
            metrics["voc_dur_{}_ph".format(speaker.lower())] = (
                3600 / unit_duration
            ) * vtc_agg.loc[speaker, "voc_dur_ph"]
            metrics["avg_voc_dur_{}".format(speaker.lower())] = vtc_agg.loc[
                speaker, "avg_voc_dur"
            ]
        
        if len(alice):
            alice_agg = alice.groupby("speaker_type").agg(
                wc_ph=("words", "sum"),
                sc_ph=("syllables", "sum"),
                pc_ph=("phonemes", "sum"),
            )

            for speaker in adults:
                if speaker not in alice_agg.index:
                    continue

                metrics["wc_{}_ph".format(speaker.lower())] = (
                    3600 / unit_duration
                ) * alice_agg.loc[speaker, "wc_ph"]
                metrics["sc_{}_ph".format(speaker.lower())] = (
                    3600 / unit_duration
                ) * alice_agg.loc[speaker, "sc_ph"]
                metrics["pc_{}_ph".format(speaker.lower())] = (
                    3600 / unit_duration
                ) * alice_agg.loc[speaker, "pc_ph"]

            metrics["wc_adu_ph"] = alice["words"].sum() * 3600 / unit_duration
            metrics["sc_adu_ph"] = alice["syllables"].sum() * 3600 / unit_duration
            metrics["pc_adu_ph"] = alice["phonemes"].sum() * 3600 / unit_duration

        if len(vcm):
            vcm_agg = (
                vcm[vcm["speaker_type"] == "CHI"]
                .groupby("vcm_type")
                .agg(
                    voc_chi_ph=("duration", "count"),
                    voc_dur_chi_ph=("duration", "sum",),
                    avg_voc_dur_chi=("duration", "mean"),
                )
            )

            metrics["cry_voc_chi_ph"] = (3600 / unit_duration) * (
                vcm_agg.loc["Y", "voc_chi_ph"] if "Y" in vcm_agg.index else 0
            )
            metrics["cry_voc_dur_chi_ph"] = (3600 / unit_duration) * (
                vcm_agg.loc["Y", "voc_dur_chi_ph"] if "Y" in vcm_agg.index else 0
            )

            if "Y" in vcm_agg.index:
                metrics["avg_cry_voc_dur_chi"] = (3600 / unit_duration) * vcm_agg.loc[
                    "Y", "avg_voc_dur_chi"
                ]

            metrics["can_voc_chi_ph"] = (3600 / unit_duration) * (
                vcm_agg.loc["C", "voc_chi_ph"] if "C" in vcm_agg.index else 0
            )
            metrics["can_voc_dur_chi_ph"] = (3600 / unit_duration) * (
                vcm_agg.loc["C", "voc_dur_chi_ph"] if "C" in vcm_agg.index else 0
            )

            if "C" in vcm_agg.index:
                metrics["avg_can_voc_dur_chi"] = (3600 / unit_duration) * vcm_agg.loc[
                    "C", "avg_voc_dur_chi"
                ]

            metrics["non_can_voc_chi_ph"] = (3600 / unit_duration) * (
                vcm_agg.loc["N", "voc_chi_ph"] if "N" in vcm_agg.index else 0
            )
            metrics["non_can_voc_dur_chi_ph"] = (3600 / unit_duration) * (
                vcm_agg.loc["N", "voc_dur_chi_ph"] if "N" in vcm_agg.index else 0
            )

            if "N" in vcm_agg.index:
                metrics["avg_non_can_voc_dur_chi"] = (
                    3600 / unit_duration
                ) * vcm_agg.loc["N", "avg_voc_dur_chi"]

            speech_voc = metrics["can_voc_chi_ph"] + metrics["non_can_voc_chi_ph"]
            speech_dur = (
                metrics["can_voc_dur_chi_ph"] + metrics["non_can_voc_dur_chi_ph"]
            )

            cry_voc = metrics["cry_voc_chi_ph"]
            cry_dur = metrics["cry_voc_dur_chi_ph"]

            if speech_voc + cry_voc:
                metrics["lp_n"] = speech_voc / (speech_voc + cry_voc)
                metrics["cp_n"] = metrics["can_voc_chi_ph"] / speech_voc

                metrics["lp_dur"] = speech_dur / (speech_dur + cry_dur)
                metrics["cp_dur"] = metrics["can_voc_dur_chi_ph"] / speech_dur

        #get child_id and duration that are always given
        metrics["child_id"] = self.project.recordings[
            self.project.recordings[self.by] == unit
        ]["child_id"].iloc[0]
        metrics["duration"] = unit_duration
        
        #get and add to dataframe children.csv columns asked
        if self.child_cols:
            for label in self.child_cols:
                metrics[label]=self.project.children[
                        self.project.children["child_id"] == metrics["child_id"]
                ][label].iloc[0]
                
        #get and add to dataframe recordings.csv columns asked
        if self.rec_cols:
            for label in self.rec_cols:
                #for every unit drop the duplicates for that column
                value=self.project.recordings[
                        self.project.recordings[self.by] == unit
                ][label].drop_duplicates()
                #check that there is only one row remaining (ie this column has a unique value for that unit)
                if len(value) == 1:
                    metrics[label]=value.iloc[0]
                #otherwise, leave the column as NA
                else:
                    metrics[label]="NA"
        
        return metrics

    def extract(self):
        recordings = self.project.get_recordings_from_list(self.recordings)

        if self.threads == 1:
            self.metrics = pd.DataFrame(
                [self._process_unit(unit) for unit in recordings[self.by].unique()]
            )
        else:
            with mp.Pool(
                processes=self.threads if self.threads >= 1 else mp.cpu_count()
            ) as pool:
                self.metrics = pd.DataFrame(
                    pool.map(self._process_unit, recordings[self.by].unique())
                )

        self.metrics.set_index(self.by, inplace=True)
        return self.metrics

    @staticmethod
    def add_parser(subparsers, subcommand):
        parser = subparsers.add_parser(subcommand, help="LENA metrics")
        parser.add_argument("--vtc", help="vtc set", default="vtc")
        parser.add_argument("--alice", help="alice set", default="alice")
        parser.add_argument("--vcm", help="vcm set", default="vcm")
        parser.add_argument(
            "--threads", help="amount of threads to run on", default=1, type=int
        )


class PeriodMetrics(Metrics):
    """Time-aggregated metrics extractor.

    Aggregates vocalizations for each time-of-the-day-unit based on a period specified by the user.
    For instance, if the period is set to ``15Min`` (i.e. 15 minutes), vocalization rates will be reported for each
    recording and time-unit (e.g. 09:00 to 09:15, 09:15 to 09:30, etc.).

    The output dataframe has ``rp`` rows, where ``r`` is the amount of recordings (or children if the ``--by`` option is set to ``child_id``), ``p`` is the 
    amount of time-bins per day (i.e. 24 x 4 = 96 for a 15-minute period).

    The output dataframe includes a ``period`` column that contains the onset of each time-unit in HH:MM:SS format.
    The ``duration`` columns contains the total amount of annotations covering each time-bin, in milliseconds.

    If ``--by`` is set to e.g. ``child_id``, then the values for each time-bin will be the average rates across
    all the recordings of every child.

    :param project: ChildProject instance of the target dataset
    :type project: ChildProject.projects.ChildProject
    :param set: name of the set of annotations to derive the metrics from
    :type set: str
    :param period: Time-period. Values should be formatted as `pandas offset aliases <https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#offset-aliases>`__. For instance, `15Min` corresponds to a 15 minute period; `2H` corresponds to a 2 hour period.
    :type period: str
    :param period_origin: NotImplemented, defaults to None
    :type period_origin: str, optional
    :param recordings: white-list of recordings to process, defaults to None
    :type recordings: Union[str, List[str], pd.DataFrame], optional
    :param from_time: If specified (in HH:MM format), ignore annotations outside of the given time-range, defaults to None
    :type from_time: str, optional
    :param to_time:  If specified (in HH:MM format), ignore annotations outside of the given time-range, defaults to None
    :type to_time: str, optional
    :param rec_cols: columns from recordings.csv to include in the outputted metrics (optional), recording_filename,session_id,child_id,duration are always included if possible and dont need to be specified. Any column that is not unique for a given unit (eg date_iso for a child_id being recorded on multiple days) will output a <NA> value
    :type rec_cols: str, optional
    :param child_cols: columns from children.csv to include in the outputted metrics (optional), None by default
    :type child_cols: str, optional
    :param by: units to sample from, defaults to 'recording_filename'
    :type by: str, optional
    :param threads: amount of threads to run on, defaults to 1
    :type threads: int, optional
    """

    SUBCOMMAND = "period"

    def __init__(
        self,
        project: ChildProject.projects.ChildProject,
        set: str,
        period: str,
        period_origin: str = None,
        recordings: Union[str, List[str], pd.DataFrame] = None,
        from_time: str = None,
        to_time: str = None,
        rec_cols: str = None,
        child_cols: str = None,
        by: str = "recording_filename",
        threads: int = 1,
    ):

        super().__init__(project, by, recordings, from_time, to_time, rec_cols, child_cols)

        self.set = set
        self.threads = int(threads)

        self.period = period
        self.period_origin = period_origin

        if self.period_origin is not None:
            raise NotImplementedError("period-origin is not supported yet")

        if self.set not in self.am.annotations["set"].values:
            raise ValueError(
                f"'{self.set}' was not found in the index; "
                "check spelling and make sure the set was properly imported."
            )

        self.periods = pd.date_range(
            start=datetime.datetime(1900, 1, 1, 0, 0, 0, 0),
            end=datetime.datetime(1900, 1, 2, 0, 0, 0, 0),
            freq=self.period,
            closed="left",
        )

    def _process_unit(self, unit: str):
        annotations, segments = self.retrieve_segments([self.set], unit)

        # retrieve timestamps for each vocalization, ignoring the day of occurence
        segments = self.am.get_segments_timestamps(segments, ignore_date=True)

        # dropping segments for which no time information is available
        segments.dropna(subset=["onset_time"], inplace=True)

        # update the timestamps so that all vocalizations appear
        # to happen on the same day
        segments["onset_time"] -= pd.to_timedelta(
            86400
            * ((segments["onset_time"] - self.periods[0]).dt.total_seconds() // 86400),
            unit="s",
        )

        if len(segments) == 0:
            return pd.DataFrame()

        # calculate length of available annotations within each bin.
        # this is necessary in order to calculate correct rates
        bins = np.array(
            [dt.total_seconds() for dt in self.periods - self.periods[0]] + [86400]
        )

        # retrieve the timestamps for all annotated portions of the recordings
        annotations = self.am.get_segments_timestamps(
            annotations, ignore_date=True, onset="range_onset", offset="range_offset"
        )

        # calculate time elapsed since the first time bin
        annotations["onset_time"] = (
            annotations["onset_time"]
            .apply(lambda dt: (dt - self.periods[0]).total_seconds())
            .astype(int)
        )
        annotations["offset_time"] = (
            annotations["offset_time"]
            .apply(lambda dt: (dt - self.periods[0]).total_seconds())
            .astype(int)
        )

        # split annotations to intervals each within a 0-24h range
        annotations["stops"] = annotations.apply(
            lambda row: [row["onset_time"]]
            + list(
                86400
                * np.arange(
                    (row["onset_time"] // 86400) + 1,
                    (row["offset_time"] // 86400) + 1,
                    1,
                )
            )
            + [row["offset_time"]],
            axis=1,
        )

        annotations = annotations.explode("stops")
        annotations["onset"] = annotations["stops"]
        annotations["offset"] = annotations["stops"].shift(-1)

        annotations.dropna(subset=["offset"], inplace=True)
        annotations["onset"] = annotations["onset"].astype(int) % 86400
        annotations["offset"] = (annotations["offset"] - 1e-4) % 86400

        durations = [
            (
                annotations["offset"].clip(bins[i], bins[i + 1])
                - annotations["onset"].clip(bins[i], bins[i + 1])
            ).sum()
            for i, t in enumerate(bins[:-1])
        ]

        durations = pd.Series(durations, index=self.periods)
        metrics = pd.DataFrame(index=self.periods)

        grouper = pd.Grouper(key="onset_time", freq=self.period, closed="left")

        speaker_types = ["FEM", "MAL", "CHI", "OCH"]
        adults = ["FEM", "MAL"]

        for speaker in speaker_types:
            vocs = segments[segments["speaker_type"] == speaker].groupby(grouper)

            vocs = vocs.agg(
                voc_ph=("segment_onset", "count"),
                voc_dur_ph=("duration", "sum"),
                avg_voc_dur=("duration", "mean"),
            )

            metrics["voc_{}_ph".format(speaker.lower())] = (
                vocs["voc_ph"].reindex(self.periods, fill_value=0) * 3600 / durations
            )
            metrics["voc_dur_{}_ph".format(speaker.lower())] = (
                vocs["voc_dur_ph"].reindex(self.periods, fill_value=0)
                * 3600
                / durations
            )
            metrics["avg_voc_dur_{}".format(speaker.lower())] = vocs[
                "avg_voc_dur"
            ].reindex(self.periods)

        #add duration and child_id to dataframe as they are always given
        metrics["duration"] = (durations * 1000).astype(int)
        metrics[self.by] = unit
        metrics["child_id"] = self.project.recordings[
            self.project.recordings[self.by] == unit
        ]["child_id"].iloc[0]
        
        #get and add to dataframe children.csv columns asked
        if self.child_cols:
            for label in self.child_cols:
                metrics[label]=self.project.children[
                        self.project.children["child_id"] == metrics["child_id"].iloc[0]
                ][label].iloc[0]
                
        #get and add to dataframe recordings.csv columns asked
        if self.rec_cols:
            for label in self.rec_cols:
                #for every unit drop the duplicates for that column
                value=self.project.recordings[
                        self.project.recordings[self.by] == unit
                ][label].drop_duplicates()
                #check that there is only one row remaining (ie this column has a unique value for that unit)
                if len(value) == 1:
                    metrics[label]=value.iloc[0]
                #otherwise, leave the column as NA
                else:
                    metrics[label]="NA"
        
        return metrics

    def extract(self):
        recordings = self.project.get_recordings_from_list(self.recordings)

        if self.threads == 1:
            self.metrics = pd.concat(
                [self._process_unit(unit) for unit in recordings[self.by].unique()]
            )
        else:
            with mp.Pool(
                processes=self.threads if self.threads >= 1 else mp.cpu_count()
            ) as pool:
                self.metrics = pd.concat(
                    pool.map(self._process_unit, recordings[self.by].unique())
                )

        if len(self.metrics):
            self.metrics["period"] = self.metrics.index.strftime("%H:%M:%S")
            self.metrics.set_index(self.by, inplace=True)

        return self.metrics

    @staticmethod
    def add_parser(subparsers, subcommand):
        parser = subparsers.add_parser(subcommand, help="LENA metrics")
        parser.add_argument("--set", help="annotations set", required=True)

        parser.add_argument(
            "--period",
            help="time units to aggregate (optional); equivalent to ``pandas.Grouper``'s freq argument.",
            required=True,
        )

        parser.add_argument(
            "--period-origin",
            help="time origin of each time period; equivalent to ``pandas.Grouper``'s origin argument.",
            default=None,
        )

        parser.add_argument(
            "--threads", help="amount of threads to run on", default=1, type=int
        )


class MetricsPipeline(Pipeline):
    def __init__(self):
        self.metrics = []

    def run(self, path, destination, pipeline, func=None, **kwargs):
        self.project = ChildProject.projects.ChildProject(path)
        self.project.read()

        if pipeline not in pipelines:
            raise NotImplementedError(f"invalid pipeline '{pipeline}'")

        metrics = pipelines[pipeline](self.project, **kwargs)
        metrics.extract()

        self.metrics = metrics.metrics
        self.metrics.to_csv(destination)

        return self.metrics

    @staticmethod
    def setup_parser(parser):
        parser.add_argument("path", help="path to the dataset")
        parser.add_argument("destination", help="segments destination")

        subparsers = parser.add_subparsers(help="pipeline", dest="pipeline")
        for pipeline in pipelines:
            pipelines[pipeline].add_parser(subparsers, pipeline)

        parser.add_argument(
            "--recordings",
            help="path to a CSV dataframe containing the list of recordings to sample from (by default, all recordings will be sampled). The CSV should have one column named recording_filename.",
            default=None,
        )

        parser.add_argument(
            "--by",
            help="units to sample from (default behavior is to sample by recording)",
            choices=["recording_filename", "session_id", "child_id"],
            default="recording_filename",
        )

        parser.add_argument(
            "-f",
            "--from-time",
            help="time range start in HH:MM format (optional)",
            default=None,
        )

        parser.add_argument(
            "-t",
            "--to-time",
            help="time range end in HH:MM format (optional)",
            default=None,
        )
        
        parser.add_argument(
            "--rec-cols",
            help="columns from recordings.csv to include in the outputted metrics (optional), NA if ambiguous",
            default=None,
        )
        
        parser.add_argument(
            "--child-cols",
            help="columns from children.csv to include in the outputted metrics (optional)",
            default=None,
        )
