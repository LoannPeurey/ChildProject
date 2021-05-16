from abc import ABC, abstractmethod
import argparse
import datetime
import multiprocessing as mp
import numpy as np
import os
import sys
import pandas as pd
import shutil
import subprocess
from yaml import dump

import ChildProject
from ChildProject.pipelines.pipeline import Pipeline

class AudioConverter(ABC):
    def __init__(self,
        project: ChildProject.projects.ChildProject,
        name: str,
        input_profile: str = None,
        threads: int = 0
        ):

        self.project = project
        self.name = name
        self.threads = int(threads)

        self.input_profile = input_profile

        if self.input_profile:
            input_path = os.path.join(
                self.project.path,
                ChildProject.projects.ChildProject.CONVERTED_RECORDINGS,
                self.input_profile
            )

            assert os.path.exists(input_path), \
                f'provided input profile {input_profile} does not exist'

        self.converted = pd.DataFrame()

    def output_directory(self):
        return os.path.join(
            self.project.path,
            ChildProject.projects.ChildProject.CONVERTED_RECORDINGS,
            self.name
        )

    def export_metadata(self):
        destination = os.path.join(
            self.output_directory(),
            'recordings.csv'
        )

        self.converted.set_index('converted_filename').to_csv(destination)

    @abstractmethod
    def process_recording(self, recording):
        pass

    def process(self):
        os.makedirs(
            name = self.output_directory(),
            exist_ok = True
        )

        pool = mp.Pool(processes = self.threads if self.threads > 0 else mp.cpu_count())
        self.converted = pool.map(
            self.process_recording,
            self.project.recordings.to_dict('records')
        )
        self.converted = pd.concat(self.converted)
        self.export_metadata()

    @staticmethod
    def add_parser(parsers):
        pass

class BasicConverter(AudioConverter):
    def __init__(self,
        project: ChildProject.projects.ChildProject,
        name: str,
        format: str,
        codec: str,
        sampling: int,
        split: str = None,
        threads: int = None,
        skip_existing: bool = False,
        input_profile: str = None
        ):

        super().__init__(project, name, threads = threads, input_profile = input_profile)
        
        self.format = format
        self.codec = str(codec)
        self.sampling = int(sampling)
        self.skip_existing = bool(skip_existing)

        if split is not None:
            try:
                split_time = datetime.datetime.strptime(split, '%H:%M:%S')
            except:
                raise ValueError('split should be specified as HH:MM:SS')

        self.split = split

    def process_recording(self, recording):
        if recording['recording_filename'] == 'NA':
            return pd.DataFrame()

        original_file = self.project.get_recording_path(
            recording['recording_filename'],
            self.input_profile
        )

        destination_file = os.path.join(
            self.output_directory(),
            os.path.splitext(recording['recording_filename'])[0] + '.%03d.' + self.format if self.split
            else os.path.splitext(recording['recording_filename'])[0] + '.' + self.format
        )

        os.makedirs(
            name = os.path.dirname(destination_file),
            exist_ok = True
        )

        skip = self.skip_existing and os.path.exists(destination_file)
        success = skip

        if not skip:
            args = [
                'ffmpeg', '-y',
                '-loglevel', 'error',
                '-i', original_file,
                '-c:a', self.codec,
                '-ar', str(self.sampling)
            ]

            if self.split:
                args.extend([
                    '-segment_time', self.split, '-f', 'segment'
                ])

            args.append(destination_file)

            proc = subprocess.Popen(args, stdout = subprocess.DEVNULL, stderr = subprocess.PIPE)
            (stdout, stderr) = proc.communicate()
            success = proc.returncode == 0

        if not success:
            return pd.DataFrame([{
                'original_filename': recording['recording_filename'],
                'converted_filename': "",
                'success': False,
                'error': stderr
            }])
        else:
            if self.split:
                converted_files = [
                    os.path.basename(cf)
                    for cf in glob.glob(os.path.join(self.output_directory(), os.path.splitext(recording['recording_filename'])[0] + '.*.' + self.format))
                ]
            else:
                converted_files = [os.path.splitext(recording['recording_filename'])[0] + '.' + self.format]

        return pd.DataFrame([{
            'original_filename': recording['recording_filename'],
            'converted_filename': cf,
            'success': True
        } for cf in converted_files])

    @staticmethod
    def add_parser(converters):
        parser = converters.add_parser('basic', help = 'basic audio conversion')
        parser.add_argument("--format", help = "audio format (e.g. wav)", required = True)
        parser.add_argument("--codec", help = "audio codec (e.g. pcm_s16le)", required = True)
        parser.add_argument("--sampling", help = "sampling frequency (e.g. 16000)", required = True, type = int)
        parser.add_argument("--split", help = "split duration (e.g. 15:00:00)", required = False, default = None)

class VettingConverter(AudioConverter):
    def __init__(self,
        project: ChildProject.projects.ChildProject,
        name: str,
        segments_path: str,
        threads: int = None,
        input_profile: str = None
        ):

        super().__init__(project, name, threads = threads, input_profile = input_profile)
        self.segments = pd.read_csv(segments_path)

    def process_recording(self, recording):
        import librosa
        import soundfile

        original_file = self.project.get_recording_path(
            recording['recording_filename'],
            self.input_profile
        )        

        destination_file = os.path.join(
            self.output_directory(),
            os.path.splitext(recording['recording_filename'])[0] + '.wav'
        )

        vettoed_segments = self.segments[self.segments['recording_filename'] == recording['recording_filename']]

        signal, sr = librosa.load(original_file, sr = None, mono = False)

        onsets = librosa.time_to_samples(times = vettoed_segments['segment_onset'].values/1000, sr = sr)
        offsets = librosa.time_to_samples(times = vettoed_segments['segment_offset'].values/1000, sr = sr)

        if signal.ndim == 1:
            for i in range(len(onsets)):
                signal[onsets[i]:offsets[i]] = 0

            soundfile.write(destination_file, signal, samplerate = sr)
        else:
            for i in range(len(onsets)):
                signal[:,onsets[i]:offsets[i]] = 0
            
            soundfile.write(destination_file, np.transpose(signal), samplerate = sr)

        return pd.DataFrame([{
            'original_filename': recording['recording_filename'],
            'converted_filename': os.path.splitext(recording['recording_filename'])[0] + '.wav',
            'success': True
        }])

    @staticmethod
    def add_parser(converters):
        parser = converters.add_parser('vetting', help = 'vetting')
        parser.add_argument("--segments-path", help = "path to the CSV dataframe containing the segments to be vetted", required = True)

class ChannelMapper(AudioConverter):
    def __init__(self,
        project: ChildProject.projects.ChildProject,
        name: str,
        channels: list,
        threads: int = 0,
        input_profile: str = None
        ):

        super().__init__(project, name, threads = threads, input_profile = input_profile)
    
        self.channels = [
            list(map(float, channel.split(',')))
            for channel in channels
        ]

        self.channels = np.array(self.channels)

    def process_recording(self, recording):
        import librosa
        import soundfile

        original_file = self.project.get_recording_path(
            recording['recording_filename'],
            self.input_profile
        )        

        destination_file = os.path.join(
            self.output_directory(),
            os.path.splitext(recording['recording_filename'])[0] + '.wav'
        )

        df = pd.DataFrame([{
            'original_filename': recording['recording_filename'],
            'converted_filename': os.path.splitext(recording['recording_filename'])[0] + '.wav'
        }])

        signal, sr = librosa.load(original_file, sr = None, mono = False)

        if self.channels.shape[1] != signal.shape[0]:
            print("skipping '{}' due to channel mismatch (expected {} channels, got {})".format(
                recording['recording_filename'],
                self.channels.shape[1],
                signal.shape[0]
            ))
            return df.assign(success = False)

        output = np.matmul(self.channels, signal)
        soundfile.write(destination_file, np.transpose(output), samplerate = sr)

        return df.assign(success = True)

    @staticmethod
    def add_parser(converters):
        parser = converters.add_parser('channel-mapping', help = 'channel mapping')
        parser.add_argument("--channels", help = "lists of weigths for each channel", nargs = '+')


class AudioConversionPipeline(Pipeline):
    def __init__(self):
        pass

    def run(self, path: str, name: str, converter: str, skip_existing: bool = False, threads: int = 0, func = None, **kwargs):
        parameters = locals()
        parameters = [{key: parameters[key]} for key in parameters if key not in ['self', 'kwargs']]
        parameters.extend([{key: kwargs[key]} for key in kwargs])

        self.project = ChildProject.projects.ChildProject(path)
        self.project.read()

        cnvrtr = None
        if converter == 'basic':
            cnvrtr = BasicConverter(self.project, name, threads = threads, **kwargs)
        elif converter == 'vetting':
            cnvrtr = VettingConverter(self.project, name, threads = threads, **kwargs)
        elif converter == 'channel-mapping':
            cnvrtr = ChannelMapper(self.project, name, threads = threads, **kwargs)

        if cnvrtr is None:
            raise Exception('invalid converter')

        cnvrtr.process()

        print("exported audio to {}".format(cnvrtr.output_directory()))

        date = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        parameters_path = os.path.join(cnvrtr.output_directory(), 'parameters_{}.yml'.format(date))
        dump({
            'parameters': parameters,
            'package_version': ChildProject.__version__,
            'date': date
        }, open(parameters_path, 'w+'))
        print("exported converter parameters to {}".format(parameters_path))

        return os.path.join(cnvrtr.output_directory(), 'recordings.csv'), parameters_path

    @staticmethod
    def setup_parser(parser):
        parser.add_argument('path', help = 'path to the dataset')
        parser.add_argument('name', help = 'name of the export profile')

        converters = parser.add_subparsers(help = 'converter', dest = 'converter')

        BasicConverter.add_parser(converters)
        VettingConverter.add_parser(converters)
        ChannelMapper.add_parser(converters)

        parser.add_argument('--threads', help = "amount of threads running conversions in parallel (0 = uses all available cores)", required = False, default = 0, type = int)
        parser.add_argument('--input-profile', help = "profile of input recordings (process raw recordings by default)", default = None)
        parser.add_argument('--skip-existing', dest='skip_existing', required = False, default = False, action='store_true')

