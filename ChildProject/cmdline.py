#!/usr/bin/env python3
from ChildProject.projects import ChildProject   
from ChildProject.annotations import AnnotationManager
from ChildProject.pipelines import *

import argparse
import os
import pandas as pd
import sys

parser = argparse.ArgumentParser()
subparsers = parser.add_subparsers()

def arg(*name_or_flags, **kwargs):
    return (list(name_or_flags), kwargs)

def subcommand(args=[], parent = subparsers):
    def decorator(func):
        parser = parent.add_parser(func.__name__.replace('_', '-'), description=func.__doc__)
        for arg in args:
            parser.add_argument(*arg[0], **arg[1])
        parser.set_defaults(func=func)
    return decorator

def register_pipeline(subcommand, cls):
    _parser = subparsers.add_parser(subcommand, description = cls.__doc__)
    cls.setup_parser(_parser)
    _parser.set_defaults(func = lambda args: cls().run(**vars(args)))

@subcommand([
    arg("source", help = "project path"),
    arg('--ignore-files', dest='ignore_files', required = False, default = False, action = 'store_true'),
    arg('--check-annotations', dest='check_annotations', required = False, default = False, action = 'store_true')
])
def validate(args):
    """validate the consistency of the dataset returning detailed errors and warnings"""

    project = ChildProject(args.source)
    errors, warnings = project.validate(args.ignore_files)

    if args.check_annotations:
        am = AnnotationManager(project)
        errors.extend(am.errors)
        warnings.extend(am.warnings)

    for error in errors:
        print("error: {}".format(error), file = sys.stderr)

    for warning in warnings:
        print("warning: {}".format(warning))

    if len(errors) > 0:
        print("validation failed, {} error(s) occured".format(len(errors)), file = sys.stderr)
        sys.exit(1)

@subcommand([
    arg("source", help = "project path"),
    arg("--annotations", help = "path to input annotations index (csv)", default = ""),
    arg("--threads", help = "amount of threads to run on", type = int, default = 0)
] + [
    arg("--{}".format(col.name), help = col.description, type = str, default = None)
    for col in AnnotationManager.INDEX_COLUMNS
    if not col.generated
])
def import_annotations(args):
    """convert and import a set of annotations"""

    project = ChildProject(args.source)
    errors, warnings = project.validate(ignore_files = True)

    if len(errors) > 0:
        print("validation failed, {} error(s) occured".format(len(errors)), file = sys.stderr)
        sys.exit(1)

    if args.annotations:
        annotations = pd.read_csv(args.annotations)
    else:
        annotations = pd.DataFrame([{col.name: getattr(args, col.name) for col in AnnotationManager.INDEX_COLUMNS if not col.generated}])

    am = AnnotationManager(project)
    am.import_annotations(annotations, args.threads)

    errors, warnings = am.validate()

    if len(am.errors) > 0:
        print("importation completed with {} errors and {} warnings".format(len(am.errors)+len(errors), len(warnings)), file = sys.stderr)
        print("\n".join(am.errors), file = sys.stderr)
        print("\n".join(errors), file = sys.stderr)
        print("\n".join(warnings))

@subcommand([
    arg("source", help = "project path"),
    arg("--left-set", help = "left set", required = True),
    arg("--right-set", help = "right set", required = True),
    arg("--left-columns", help = "comma-separated columns to merge from the left set", required = True),
    arg("--right-columns", help = "comma-separated columns to merge from the right set", required = True),
    arg("--output-set", help = "name of the output set", required = True)
])
def merge_annotations(args):
    project = ChildProject(args.source)
    errors, warnings = project.validate(ignore_files = True)

    if len(errors) > 0:
        print("validation failed, {} error(s) occured".format(len(errors)), file = sys.stderr)
        sys.exit(1)

    am = AnnotationManager(project)
    am.read()
    am.merge_sets(
        left_set = args.left_set,
        right_set = args.right_set,
        left_columns = args.left_columns.split(','),
        right_columns = args.right_columns.split(','),
        output_set = args.output_set
    )

@subcommand([
    arg("source", help = "project path"),
    arg("--set", help = "set to remove", required = True)
])
def remove_annotations(args):
    project = ChildProject(args.source)
    errors, warnings = project.validate(ignore_files = True)

    if len(errors) > 0:
        print("validation failed, {} error(s) occured".format(len(errors)), file = sys.stderr)
        sys.exit(1)

    am = AnnotationManager(project)
    am.read()
    am.remove_set(args.set)

@subcommand([
    arg("dataset", help = "dataset to install. Should be a valid repository name at https://github.com/LAAC-LSCP. (e.g.: solomon-data)"),
    arg("--destination", help = "destination path", required = False, default = ""),
    arg("--storage-hostname", dest = "storage_hostname", help = "ssh storage hostname (e.g. 'foberon')", required = False, default = "")
])
def import_data(args):
    """import and configures a datalad dataset"""

    import datalad.api
    import datalad.distribution.dataset

    if args.destination:
        destination = args.destination
    else:
        destination = os.path.splitext(os.path.basename(args.dataset))[0]

    datalad.api.install(source = args.dataset, path = destination)

    ds = datalad.distribution.dataset.require_dataset(
        destination,
        check_installed = True,
        purpose = 'configuration'
    )

    cmd = 'setup'
    if args.storage_hostname:
        cmd += ' "{}"'.format(args.storage_hostname)

    datalad.api.run_procedure(spec = cmd, dataset = ds)

@subcommand([
    arg("source", help = "source data path"),
    arg("--stats", help = "stats to retrieve (comma-separated)", required = False, default = "")
])
def stats(args):
    project = ChildProject(args.source)

    errors, warnings = project.validate()

    if len(errors) > 0:
        print("validation failed, {} error(s) occured".format(len(errors)), file = sys.stderr)
        sys.exit(1)

    stats = project.get_stats()
    args.stats = args.stats.split(',') if args.stats else []

    for stat in stats:
        if not args.stats or stat in args.stats:
            print("{}: {}".format(stat, stats[stat]))

@subcommand([
    arg("source", help = "source data path"),
    arg("--profile", help = "which audio profile to use", default = ""),
    arg("--force", help = "overwrite if column exists", action = 'store_true')
])
def compute_durations(args):
    """creates a 'duration' column into metadata/recordings"""
    project = ChildProject(args.source)

    errors, warnings = project.validate()

    if len(errors) > 0:
        print("validation failed, {} error(s) occured".format(len(errors)), file = sys.stderr)
        sys.exit(1)

    if 'duration' in project.recordings.columns:
        if not args.force:
            print("duration exists, aborting")
            return
        
        project.recordings.drop(columns = ['duration'], inplace = True)

    durations = project.compute_recordings_duration(profile = args.profile).dropna()

    recordings = project.recordings.merge(durations[durations['filename'] != 'NA'], how = 'left', left_on = 'filename', right_on = 'filename')
    recordings.to_csv(os.path.join(project.path, 'metadata/recordings.csv'), index = False)

def main():
    register_pipeline('zooniverse', ZooniversePipeline)
    register_pipeline('convert', ConversionPipeline)

    args = parser.parse_args()
    args.func(args)