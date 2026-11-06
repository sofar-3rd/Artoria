import pytest

from app.rag.interfaces.validation import validate_branch, validate_name, validate_repo_url, validate_subdir


@pytest.mark.parametrize("name", ["docs", "ops-runbooks", "kb_1", "运维手册", "A" * 64])
def test_good_names(name):
    assert validate_name(name) == name


@pytest.mark.parametrize("name", ["", " ", "a b", "a/b", "a\nb", "x" * 65, "../x", "a;b", "a\x00b", "名 字"])
def test_bad_names(name):
    with pytest.raises(ValueError):
        validate_name(name)


@pytest.mark.parametrize("branch", ["main", "release/1.0", "feat/x_y-z", "v1.2.3"])
def test_good_branches(branch):
    assert validate_branch(branch) == branch


@pytest.mark.parametrize("branch", ["", "-b", "--config=x", "a..b", "a b", "a;rm", "/abs", "x" * 101])
def test_bad_branches(branch):
    with pytest.raises(ValueError):
        validate_branch(branch)


@pytest.mark.parametrize(
    "url",
    ["https://github.com/o/r.git", "ssh://git@host/o/r.git", "git://host/r.git", "git@github.com:o/r.git"],
)
def test_remote_urls_are_accepted_as_they_are(url):
    assert validate_repo_url(url) == url


@pytest.mark.parametrize(
    "url",
    ["--upload-pack=touch /tmp/x", "-u", "", "   ", "http://insecure/r.git", "ext::sh -c id", "file:///etc", "ftp://h/r"],
)
def test_dangerous_or_unsupported_urls_are_refused(url):
    with pytest.raises(ValueError):
        validate_repo_url(url, local_root="/srv/docs")


@pytest.mark.parametrize("url", ["dir:/etc", "/usr/share/doc", "/tmp", "dir:", "docs"])
def test_local_paths_are_refused_when_no_local_root_is_configured(url):
    with pytest.raises(ValueError):
        validate_repo_url(url)


def test_local_paths_inside_the_configured_root_are_accepted(tmp_path):
    inner = tmp_path / "team" / "docs"
    inner.mkdir(parents=True)
    assert validate_repo_url(str(inner), local_root=str(tmp_path)) == f"dir:{inner.resolve()}"
    assert validate_repo_url(f"dir:{tmp_path}", local_root=str(tmp_path)) == f"dir:{tmp_path.resolve()}"


def test_local_paths_cannot_escape_the_root(tmp_path):
    root = tmp_path / "root"
    (root / "ok").mkdir(parents=True)
    (tmp_path / "root-evil").mkdir()
    for url in (str(tmp_path), str(tmp_path / "root-evil"), f"{root}/../root-evil", "/etc"):
        with pytest.raises(ValueError, match="must be inside"):
            validate_repo_url(url, local_root=str(root))


def test_a_symlink_inside_the_root_pointing_outside_is_refused(tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir(); outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="must be inside"):
        validate_repo_url(str(root / "link"), local_root=str(root))


@pytest.mark.parametrize("subdir,expected", [("", ""), ("docs", "docs"), ("/docs/", "docs"), ("a/b", "a/b"), ("  docs  ", "docs")])
def test_good_subdirs(subdir, expected):
    assert validate_subdir(subdir) == expected


@pytest.mark.parametrize("subdir", ["../x", "a/../../x", "..", "a\nb", "a\x00b"])
def test_bad_subdirs(subdir):
    with pytest.raises(ValueError):
        validate_subdir(subdir)
