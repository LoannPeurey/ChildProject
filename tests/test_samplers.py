import os
import pandas as pd
import pytest
import shutil

from ChildProject.projects import ChildProject
from ChildProject.pipelines.samplers import (
    PeriodicSampler,
    RandomVocalizationSampler,
    EnergyDetectionSampler,
    HighVolubilitySampler,
    SamplerPipeline
)

@pytest.fixture(scope='function')
def project(request):
    if not os.path.exists("output/samplers"):
        shutil.copytree(src = "examples/valid_raw_data", dst = "output/samplers")

    project = ChildProject("output/samplers")
    project.read()
    yield project

def test_periodic(project):
    project = ChildProject('output/samplers')
    project.read()
    
    project.recordings = project.recordings.merge(
        project.compute_recordings_duration(),
        left_on = 'recording_filename',
        right_on = 'recording_filename'
    )

    sampler = PeriodicSampler(
        project = project,
        length = 1000,
        period = 1000,
        recordings = ['sound.wav']
    )
    sampler.sample()

    duration = project.recordings[project.recordings['recording_filename'] == 'sound.wav']['duration'].iloc[0]

    assert len(sampler.segments) == int(duration/(1000+1000))

def test_energy_detection(project):
    project = ChildProject('output/samplers')
    project.read()

    sampler = EnergyDetectionSampler(
        project = project,
        windows_length = 100,
        windows_spacing = 100,
        windows_count = 1,
        threshold = 0.98,
        low_freq = 200,
        high_freq = 1000,
        threads = 1,
        by = 'recording_filename'
    )
    sampler.sample()

    pd.testing.assert_frame_equal(
        sampler.segments[['segment_onset', 'segment_offset']],
        pd.DataFrame([[1900, 2000], [1900, 2000]], columns = ['segment_onset', 'segment_offset'])
    )
    
    # group by child_id
    sampler = EnergyDetectionSampler(
        project = project,
        windows_length = 100,
        windows_spacing = 100,
        windows_count = 1,
        threshold = 0.99,
        low_freq = 200,
        high_freq = 1000,
        by = 'child_id',
        threads = 1
    )
    sampler.sample()

    pd.testing.assert_frame_equal(
        sampler.segments[['recording_filename', 'segment_onset', 'segment_offset']],
        pd.DataFrame([['sound.wav', 1900, 2000]], columns = ['recording_filename', 'segment_onset', 'segment_offset'])
    ) 

def test_filter(project):
    project = ChildProject('output/samplers')
    project.read()

    sampler = PeriodicSampler(
        project = project,
        length = 1000,
        period = 1000,
        recordings = ['sound.wav']
    )
    recordings = sampler.get_recordings()
    assert recordings['recording_filename'].tolist() == ['sound.wav']

    sampler = PeriodicSampler(
        project = project,
        length = 1000,
        period = 1000,
        recordings = pd.Series(['sound.wav'])
    )
    recordings = sampler.get_recordings()
    assert recordings['recording_filename'].tolist() == ['sound.wav']

    sampler = PeriodicSampler(
        project = project,
        length = 1000,
        period = 1000,
        recordings = pd.DataFrame({'recording_filename': ['sound.wav']})
    )
    recordings = sampler.get_recordings()
    assert recordings['recording_filename'].tolist() == ['sound.wav']

    recordings = pd.DataFrame({'recording_filename': ['sound.wav']})\
        .to_csv('output/samplers/filter.csv')
    sampler = PeriodicSampler(
        project = project,
        length = 1000,
        period = 1000,
        recordings = 'output/samplers/filter.csv'
    )
    recordings = sampler.get_recordings()
    assert recordings['recording_filename'].tolist() == ['sound.wav']