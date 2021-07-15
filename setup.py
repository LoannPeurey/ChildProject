from setuptools import setup, find_packages
import ChildProject

requires = {
    'core': ['pandas>=0.25.0', 'jinja2', 'numpy>=1.16.5', 'sox', 'datalad', 'requests<2.25.0'],
    'annotations': ['lxml', 'pyarrow', 'pympi-ling', 'pylangacq', 'python-dateutil>=2.8.1', 'tables'],
    'metrics': ['pyannote.metrics; python_version >= "3.7.0"', 'pygamma-agreement; python_version >= "3.6.0"', 'nltk', 'sklearn'],
    'audio': ['librosa', 'pydub', 'pysoundfile'],
    'samplers': ['PyYAML'],
    'zooniverse': ['panoptes-client'],
    'eaf-builder': ['importlib-resources']
}

setup(
    name='ChildProject',
    version = ChildProject.__version__,
    description='LAAC@LSCP',
    url='https://github.com/LAAC-LSCP/ChildProject',
    author='Lucas Gautheron',
    author_email='lucas.gautheron@gmail.com',
    license='MIT',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: Unix',
        'Programming Language :: Python',
        'Topic :: Scientific/Engineering',
    ],
    packages=find_packages(),
    install_requires=requires['core'] + requires['annotations'] + requires['audio'] + requires['metrics'] + requires['samplers'] + requires['zooniverse'] + requires['eaf-builder'],
    include_package_data=True,
    package_data={'ChildProject': ['templates/*.*']},
    entry_points={
        'console_scripts': [
            'child-project=ChildProject.cmdline:main',
        ],
    },
    zip_safe=False
)
