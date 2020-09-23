from ChildProject.ChildProject import ChildProject
import os
import glob

def test_import():
    project = ChildProject("examples/valid_raw_data")
    project.import_data("examples/project")

    assert os.path.exists("examples/project"), "project folder was not created"

    assert all([
        os.path.exists(os.path.join("examples/project", f))
        for f in ['scripts', 'doc']
    ]), "not all folders were successfully created"
    
    assert(all([
        open(f, "r+").read() == open(os.path.join("examples/project/", f.replace("examples/valid_raw_data/", ""))).read()
        for f in glob.glob("examples/valid_raw_data/**.*") 
    ])), "not all files were successfully copied"