import numpy as np
import pandas as pd

from ChildProject.metrics import gamma, segments_to_annotation, segments_to_grid, grid_to_vector, vectors_to_annotation_task, conf_matrix

def test_gamma():
    segments = pd.read_csv('tests/data/gamma.csv')

    value = gamma(
        segments,
        'speaker_type',
        alpha = 3,
        beta = 1,
        precision_level = 0.01
    )

    assert 0.28 <= value <= 0.31

def test_segments_to_grid():
    segments = pd.read_csv('tests/data/grid.csv')
    grid = segments_to_grid(segments, 0, 10, 1, 'speaker_type', ['CHI', 'FEM'])

    truth = np.array([
        [1, 0, 0, 0],
        [1, 0, 0, 0],
        [0, 1, 0, 0],
        [0, 1, 0, 0],
        [0, 0, 0, 1],
        [0, 0, 0, 1],
        [1, 1, 1, 0],
        [1, 1, 1, 0],
        [0, 1, 0, 0],
        [0, 0, 0, 1]
    ])

    np.testing.assert_array_equal(
        grid, truth
    )

def test_grid_to_vectors():
    segments = pd.read_csv('tests/data/grid.csv')
    grid = segments_to_grid(segments, 0, 10, 1, 'speaker_type', ['CHI', 'FEM'])
    vector = grid_to_vector(grid, ['CHI', 'FEM', 'overlap', 'none'])

    truth = np.array([
        'CHI', 'CHI', 'FEM', 'FEM', 'none',
        'none', 'overlap', 'overlap', 'FEM', 'none'
    ])

    np.testing.assert_array_equal(
        vector, truth
    )

def test_conf_matrix():
    segments = pd.read_csv('tests/data/confmatrix.csv')
    categories = ['CHI', 'FEM']

    confmat = conf_matrix(
        segments_to_grid(segments[segments['set'] == 'Alice'], 0, 20, 1, 'speaker_type', categories),
        segments_to_grid(segments[segments['set'] == 'Bob'], 0, 20, 1, 'speaker_type', categories),
        categories + ['overlap', 'none']
    )

    truth = np.array([
        [5, 5, 0, 0],
        [0, 2, 0, 3],
        [0, 0, 0, 0],
        [0, 0, 0, 5]
    ])

    np.testing.assert_array_equal(
        confmat, truth
    )

def test_alpha():
    segments = pd.read_csv('tests/data/alpha.csv')

    categories = list(segments['speaker_type'].unique())
    sets = list(segments['set'].unique())

    vectors = [
        grid_to_vector(
            segments_to_grid(
                segments[segments['set'] == s],
                0,
                segments['segment_offset'].max(),
                1,
                'speaker_type',
                categories
            ),
            categories + ['overlap', 'none']
        )
        for s in sets
    ]

    task = vectors_to_annotation_task(*vectors, drop = ['none'])
    alpha = task.alpha()

    assert np.isclose(alpha, 0.743421052632, rtol = 0.001, atol = 0.0001)