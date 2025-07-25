import shutil

import pytest
from unearth import Link

from pdm.models.markers import EnvSpec
from pdm.models.specifiers import PySpecSet
from pdm.pytest import Distribution
from tests import FIXTURES


def test_add_package(project, working_set, dev_option, pdm):
    pdm(["add", *dev_option, "requests"], obj=project, strict=True)
    group = project.pyproject.dependency_groups["dev"] if dev_option else project.pyproject.metadata["dependencies"]

    assert group[0] == "requests>=2.19.1"
    locked_candidates = project.get_locked_repository().candidates
    assert locked_candidates["idna"].version == "2.7"
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package in working_set


def test_add_package_no_lock(project, working_set, dev_option, pdm):
    pdm(["add", *dev_option, "--frozen-lockfile", "-v", "requests"], obj=project, strict=True)
    group = project.pyproject.dependency_groups["dev"] if dev_option else project.pyproject.metadata["dependencies"]

    assert group[0] == "requests>=2.19.1"
    assert not project.lockfile.exists()
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package in working_set


def test_add_command(project, pdm, mocker):
    do_add = mocker.patch("pdm.cli.commands.add.Command.do_add")
    pdm(["add", "requests"], obj=project)
    do_add.assert_called_once()


def test_add_package_to_custom_group(project, working_set, pdm):
    pdm(["add", "requests", "--group", "test"], obj=project, strict=True)

    assert "requests" in project.pyproject.metadata["optional-dependencies"]["test"][0]
    locked_candidates = project.get_locked_repository().candidates
    assert locked_candidates["idna"].version == "2.7"
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package in working_set


def test_add_package_to_custom_dev_group(project, working_set, pdm):
    pdm(["add", "requests", "--group", "test", "--dev"], obj=project, strict=True)

    dependencies = project.pyproject.dependency_groups["test"]
    assert "requests" in dependencies[0]
    locked_candidates = project.get_locked_repository().candidates
    assert locked_candidates["idna"].version == "2.7"
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package in working_set


@pytest.mark.usefixtures("vcs")
def test_add_editable_package(project, working_set, pdm):
    # Ensure that correct python version is used.
    project.environment.python_requires = PySpecSet(">=3.6")
    pdm(["add", "--dev", "demo"], obj=project, strict=True)
    pdm(["add", "-de", "git+https://github.com/test-root/demo.git#egg=demo"], obj=project, strict=True)

    group = project.pyproject.dev_dependencies["dev"]
    assert group == ["-e git+https://github.com/test-root/demo.git#egg=demo"]
    assert not project.pyproject.dependency_groups
    locked_candidates = project.get_locked_repository().candidates
    assert locked_candidates["demo"].prepare(project.environment).revision == "1234567890abcdef"
    assert working_set["demo"].link_file
    assert locked_candidates["idna"].version == "2.7"
    assert "idna" in working_set

    pdm(["sync", "--no-editable"], obj=project, strict=True)
    assert not working_set["demo"].link_file


@pytest.mark.usefixtures("vcs", "working_set")
def test_add_editable_package_to_metadata_forbidden(project, pdm):
    project.environment.python_requires = PySpecSet(">=3.6")
    result = pdm(["add", "-v", "-e", "git+https://github.com/test-root/demo.git#egg=demo"], obj=project)
    assert "PdmUsageError" in result.stderr
    result = pdm(["add", "-v", "-Gtest", "-e", "git+https://github.com/test-root/demo.git#egg=demo"], obj=project)
    assert "PdmUsageError" in result.stderr


@pytest.mark.usefixtures("working_set", "vcs")
def test_non_editable_override_editable(project, pdm):
    project.environment.python_requires = PySpecSet(">=3.6")
    url = "git+https://github.com/test-root/demo.git#egg=demo"
    pdm(["add", "--dev", "-e", url], obj=project, strict=True)
    pdm(["add", "--dev", url], obj=project, strict=True)
    assert not project.get_dependencies("dev")[0].editable


@pytest.mark.usefixtures("working_set", "vcs")
def test_add_editable_normal_dev_dependency(project, pdm):
    project.environment.python_requires = PySpecSet(">=3.6")
    url = "git+https://github.com/test-root/demo.git#egg=demo"
    pdm(["add", "--dev", "-e", url], obj=project, strict=True)
    pdm(["add", "-d", "urllib3"], obj=project, strict=True)
    pdm(["add", "-d", "idna"], obj=project, strict=True)
    dev_group = project.pyproject.settings["dev-dependencies"]["dev"]
    pep735_group = project.pyproject.dependency_groups["dev"]
    assert dev_group == ["-e git+https://github.com/test-root/demo.git#egg=demo"]
    assert pep735_group == ["urllib3>=1.22", "idna>=2.7"]


@pytest.mark.usefixtures("working_set", "vcs")
def test_add_dev_dependency_with_existing_editables_group(project, pdm):
    project.environment.python_requires = PySpecSet(">=3.6")
    url = "git+https://github.com/test-root/demo.git#egg=demo"
    pdm(["add", "-dG", "editables", "-e", url], obj=project, strict=True)
    pdm(["add", "-d", "urllib3"], obj=project, strict=True)
    pdm(["add", "-dG", "named", "idna"], obj=project, strict=True)
    assert "editables" in project.pyproject.settings["dev-dependencies"]
    assert "dev" in project.pyproject.dependency_groups
    assert "named" in project.pyproject.dependency_groups
    editables_group = project.pyproject.settings["dev-dependencies"]["editables"]
    pep735_group = project.pyproject.dependency_groups["dev"]
    pep735_named_group = project.pyproject.dependency_groups["named"]
    assert editables_group == ["-e git+https://github.com/test-root/demo.git#egg=demo"]
    assert "editables" not in project.pyproject.dependency_groups
    assert pep735_group == ["urllib3>=1.22"]
    assert pep735_named_group == ["idna>=2.7"]


@pytest.mark.usefixtures("working_set")
def test_add_remote_package_url(project, dev_option, pdm):
    project.environment.python_requires = PySpecSet(">=3.6")
    url = "http://fixtures.test/artifacts/demo-0.0.1-py2.py3-none-any.whl"
    pdm(["add", *dev_option, url], obj=project, strict=True)
    group = project.pyproject.dependency_groups["dev"] if dev_option else project.pyproject.metadata["dependencies"]
    assert group[0] == f"demo @ {url}"


def test_add_no_install(project, working_set, pdm):
    pdm(["add", "--no-sync", "requests"], obj=project, strict=True)
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package not in working_set


@pytest.mark.usefixtures("repository")
def test_add_package_save_exact(project, pdm):
    pdm(["add", "--save-exact", "--no-sync", "requests"], obj=project, strict=True)
    assert project.pyproject.metadata["dependencies"][0] == "requests==2.19.1"


@pytest.mark.usefixtures("repository")
def test_add_package_save_wildcard(project, pdm):
    pdm(["add", "--save-wildcard", "--no-sync", "requests"], obj=project, strict=True)
    assert project.pyproject.metadata["dependencies"][0] == "requests"


@pytest.mark.usefixtures("repository")
def test_add_package_save_minimum(project, pdm):
    pdm(["add", "--save-minimum", "--no-sync", "requests"], obj=project, strict=True)
    assert project.pyproject.metadata["dependencies"][0] == "requests>=2.19.1"


def test_add_package_update_reuse(project, repository, pdm):
    pdm(["add", "--no-sync", "--save-wildcard", "requests", "pytz"], obj=project, strict=True)

    locked_candidates = project.get_locked_repository().candidates
    assert locked_candidates["requests"].version == "2.19.1"
    assert locked_candidates["chardet"].version == "3.0.4"
    assert locked_candidates["pytz"].version == "2019.3"

    repository.add_candidate("pytz", "2019.6")
    repository.add_candidate("chardet", "3.0.5")
    repository.add_candidate("requests", "2.20.0")
    repository.add_dependencies(
        "requests",
        "2.20.0",
        [
            "certifi>=2017.4.17",
            "chardet<3.1.0,>=3.0.2",
            "idna<2.8,>=2.5",
            "urllib3<1.24,>=1.21.1",
        ],
    )
    pdm(["add", "--no-sync", "--save-wildcard", "requests"], obj=project, strict=True)
    locked_candidates = project.get_locked_repository().candidates
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.4"
    assert locked_candidates["pytz"].version == "2019.3"


def test_add_package_update_eager(project, repository, pdm):
    pdm(["add", "--no-sync", "--save-wildcard", "requests", "pytz"], obj=project, strict=True)

    locked_candidates = project.get_locked_repository().candidates
    assert locked_candidates["requests"].version == "2.19.1"
    assert locked_candidates["chardet"].version == "3.0.4"
    assert locked_candidates["pytz"].version == "2019.3"

    repository.add_candidate("pytz", "2019.6")
    repository.add_candidate("chardet", "3.0.5")
    repository.add_candidate("requests", "2.20.0")
    repository.add_dependencies(
        "requests",
        "2.20.0",
        [
            "certifi>=2017.4.17",
            "chardet<3.1.0,>=3.0.2",
            "idna<2.8,>=2.5",
            "urllib3<1.24,>=1.21.1",
        ],
    )
    pdm(["add", "--no-sync", "--save-wildcard", "--update-eager", "requests"], obj=project, strict=True)
    locked_candidates = project.get_locked_repository().candidates
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.5"
    assert locked_candidates["pytz"].version == "2019.3"


def test_add_package_with_mismatch_marker(project, working_set, pdm):
    env = project.environment
    env.__dict__["spec"] = EnvSpec.from_spec("==3.11", "macos", "cpython")
    pdm(["add", "requests", "pytz; platform_system!='Darwin'"], obj=project, strict=True)
    assert "pytz" not in working_set


def test_add_dependency_from_multiple_parents(project, working_set, pdm):
    env = project.environment
    env.__dict__["spec"] = EnvSpec.from_spec("==3.11", "macos", "cpython")
    pdm(["add", "requests", "chardet; platform_system!='Darwin'"], obj=project, strict=True)
    assert "chardet" in working_set


def test_add_packages_without_self(project, working_set, pdm):
    project.environment.python_requires = PySpecSet(">=3.6")
    pdm(["add", "--no-self", "requests"], obj=project, strict=True)
    assert project.name not in working_set


@pytest.mark.usefixtures("working_set")
def test_add_package_unconstrained_rewrite_specifier(project, pdm):
    project.environment.python_requires = PySpecSet(">=3.6")
    pdm(["add", "--no-self", "django"], obj=project, strict=True)
    locked_candidates = project.get_locked_repository().candidates
    assert locked_candidates["django"].version == "2.2.9"
    assert project.pyproject.metadata["dependencies"][0] == "django>=2.2.9"

    pdm(["add", "--no-self", "--unconstrained", "django-toolbar"], obj=project, strict=True)
    locked_candidates = project.get_locked_repository().candidates
    assert locked_candidates["django"].version == "1.11.8"
    assert project.pyproject.metadata["dependencies"][0] == "django>=1.11.8"


@pytest.mark.usefixtures("working_set", "vcs")
def test_add_cached_vcs_requirement(project, mocker, pdm):
    project.environment.python_requires = PySpecSet(">=3.6")
    url = "git+https://github.com/test-root/demo.git@1234567890abcdef#egg=demo"
    built_path = FIXTURES / "artifacts/demo-0.0.1-py2.py3-none-any.whl"
    wheel_cache = project.make_wheel_cache()
    cache_path = wheel_cache.get_path_for_link(Link(url), project.environment.spec)
    if not cache_path.exists():
        cache_path.mkdir(parents=True)
    shutil.copy2(built_path, cache_path)
    downloader = mocker.patch("unearth.finder.unpack_link")
    builder = mocker.patch("pdm.builders.WheelBuilder.build")
    pdm(["add", "--no-self", url], obj=project, strict=True)
    lockfile_entry = next(p for p in project.lockfile["package"] if p["name"] == "demo")
    assert lockfile_entry["revision"] == "1234567890abcdef"
    downloader.assert_not_called()
    builder.assert_not_called()


@pytest.mark.usefixtures("repository")
def test_add_with_dry_run(project, pdm):
    result = pdm(["add", "--dry-run", "requests"], obj=project, strict=True)
    project.pyproject.reload()
    assert not project.get_dependencies()
    assert "requests 2.19.1" in result.stdout
    assert "urllib3 1.22" in result.stdout


def test_add_with_prerelease(project, working_set, pdm):
    pdm(["add", "--prerelease", "--save-compatible", "urllib3"], obj=project, strict=True)
    assert working_set["urllib3"].version == "1.23b0"
    assert project.pyproject.metadata["dependencies"][0] == "urllib3<2,>=1.23b0"


def test_add_editable_package_with_extras(project, working_set, pdm):
    project.environment.python_requires = PySpecSet(">=3.6")
    dep_path = FIXTURES.joinpath("projects/demo")
    pdm(["add", "-dGdev", "-e", f"{dep_path.as_posix()}[security]"], obj=project, strict=True)
    assert f"-e {dep_path.as_uri()}#egg=demo[security]" in project.use_pyproject_dependencies("dev", True)[0]
    assert "demo" in working_set
    assert "requests" in working_set
    assert "urllib3" in working_set


@pytest.mark.usefixtures("repository")
def test_add_dependency_with_extras(project, pdm):
    project.environment.python_requires = PySpecSet(">=3.6")
    pdm(["add", "requests[security]", "--no-sync"], obj=project, strict=True)
    locked_repo = project.get_locked_repository()
    extra_package = next(p for p in locked_repo.packages.values() if p.candidate.identify() == "requests[security]")
    assert extra_package.dependencies == ["pyOpenSSL>=0.14", "requests==2.19.1"]
    # test adding new package won't add duplicate dependencies
    pdm(["add", "pytz", "--no-sync"], obj=project, strict=True)
    locked_repo = project.get_locked_repository()
    extra_package = next(p for p in locked_repo.packages.values() if p.candidate.identify() == "requests[security]")
    assert extra_package.dependencies == ["pyOpenSSL>=0.14", "requests==2.19.1"]


def test_add_package_with_local_version(project, repository, working_set, pdm):
    repository.add_candidate("foo", "1.0a0+local")
    pdm(["add", "-v", "foo"], obj=project, strict=True)
    assert working_set["foo"].version == "1.0a0+local"
    dependencies, _ = project.use_pyproject_dependencies("default")
    assert dependencies[0] == "foo>=1.0a0"


def test_add_group_to_lockfile(project, working_set, pdm):
    pdm(["add", "requests"], obj=project, strict=True)
    assert project.lockfile.groups == ["default"]
    pdm(["add", "--group", "tz", "pytz"], obj=project, strict=True)
    assert project.lockfile.groups == ["default", "tz"]
    assert "pytz" in working_set


def test_add_group_to_lockfile_without_package(project, working_set, pdm):
    project.add_dependencies(["requests"])
    project.add_dependencies(["pytz"], to_group="tz")
    pdm(["install"], obj=project, strict=True)
    assert "pytz" not in working_set
    assert project.lockfile.groups == ["default"]
    pdm(["add", "--group", "tz"], obj=project, strict=True)
    assert project.lockfile.groups == ["default", "tz"]
    assert "pytz" in working_set


def test_add_update_reuse_installed(project, working_set, repository, pdm):
    working_set["foo"] = Distribution("foo", "1.0.0")
    repository.add_candidate("foo", "1.0.0")
    repository.add_candidate("foo", "1.1.0")
    pdm(["add", "--update-reuse-installed", "foo"], obj=project, strict=True)
    locked_candidates = project.get_locked_repository().candidates
    assert locked_candidates["foo"].version == "1.0.0"


def test_add_update_reuse_installed_config(project, working_set, repository, pdm):
    working_set["foo"] = Distribution("foo", "1.0.0")
    repository.add_candidate("foo", "1.0.0")
    repository.add_candidate("foo", "1.1.0")
    project.project_config["strategy.update"] = "reuse-installed"
    pdm(["add", "foo"], obj=project, strict=True)
    locked_candidates = project.get_locked_repository().candidates
    assert locked_candidates["foo"].version == "1.0.0"


def test_add_disable_cache(project, pdm, working_set):
    cache_dir = project.cache_dir
    pdm(["--no-cache", "add", "requests"], obj=project, strict=True)
    assert "requests" in working_set

    files = [file for file in cache_dir.rglob("*") if file.is_file()]
    assert not files


@pytest.mark.usefixtures("working_set")
def test_add_dependency_with_direct_minimal_versions(project, pdm, repository):
    pdm(["lock", "-S", "direct_minimal_versions"], obj=project, strict=True)
    repository.add_candidate("pytz", "2019.6")
    pdm(["add", "django"], obj=project, strict=True)
    all_candidates = project.get_locked_repository().candidates
    assert "django>=1.11.8" in project.pyproject.metadata["dependencies"]
    assert all_candidates["django"].version == "1.11.8"
    assert all_candidates["pytz"].version == "2019.6"


def test_add_group_with_normalized_name(project, pdm, working_set):
    project.pyproject.dependency_groups.update({"foo_bar": ["requests"]})
    project.pyproject.write()
    pdm(["lock"], obj=project, strict=True)
    assert "foo-bar" in project.lockfile.groups
    pdm(["sync", "-G", "foo.bar"], obj=project, strict=True)
    assert "requests" in working_set
    result = pdm(["add", "-G", "foo-bar", "pytz"], obj=project)
    assert result.exit_code != 0
    assert "Group foo-bar already exists in another non-normalized form" in result.stderr


@pytest.mark.usefixtures("working_set")
def test_add_to_dependency_group_with_include(project, pdm):
    from pdm.formats.base import make_array

    project.pyproject.dependency_groups.update({"tz": ["pytz"], "web": make_array([{"include-group": "tz"}])})
    project.pyproject.write()
    pdm(["add", "-Gweb", "requests"], obj=project, strict=True)
    assert project.pyproject.dependency_groups["web"] == [{"include-group": "tz"}, "requests>=2.19.1"]
