from setuptools import setup, find_packages
import ChildProject

requires = {
    'core': ['pandas', 'xlrd', 'jinja2', 'numpy>=1.16.5', 'pympi-ling', 'lxml', 'sox', 'datalad', 'requests<2.25.0'],
    'samplers': ['PyYAML'],
    'zooniverse': ['panoptes_client', 'pydub']
}

setup(
    name='ChildProject',
    version = ChildProject.__version__,
    description='LAAC@LSCP',
    url='https://github.com/LAAC-LSCP/ChildRecordsData',
    author='Lucas',
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
    install_requires=requires['core'] + requires['samplers'] + requires['zooniverse'],
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'child-project=ChildProject.cmdline:main',
        ],
    },
    zip_safe=False
)
