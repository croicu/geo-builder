import pytest


@pytest.fixture(autouse=True)
def setup_test():
    yield

@pytest.fixture(scope="function", autouse=True)
def suite_run(tmp_path, request):
    yield # run tests

