from ChildProject.ChildProject import ChildProject

def test_valid_project():
    project = ChildProject()
    project.raw_data_path = "examples/valid_raw_data"
    test = project.validate_input_data()

    assert len(test['errors']) == 0, "valid input validation failed (expected to pass)"
    assert len(test['warnings']) == 1, "expected 1 warning, got {}".format(len(test['warnings']))

def test_invalid_project():
    project = ChildProject()
    project.raw_data_path = "examples/invalid_raw_data"
    test = project.validate_input_data()
    assert len(test['errors']) > 0, "valid input validation passed (expected to fail)"