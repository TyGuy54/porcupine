import pathlib
import shutil
import subprocess
import sys
from functools import partial

import pytest

from porcupine import get_paned_window, tabs, utils
from porcupine.plugins import directory_tree as plugin_module
from porcupine.plugins.directory_tree import DirectoryTree, focus_treeview


@pytest.fixture
def tree():
    [tree] = [
        w
        for w in utils.get_children_recursively(get_paned_window())
        if isinstance(w, DirectoryTree)
    ]
    for child in tree.get_children(""):
        tree.delete(child)
    yield tree


def test_adding_nested_projects(tree, tmp_path):
    def get_paths():
        return [tree.get_path(project) for project in tree.get_children()]

    (tmp_path / "a" / "b").mkdir(parents=True)
    assert get_paths() == []
    tree.add_project(tmp_path / "a")
    assert get_paths() == [tmp_path / "a"]
    tree.add_project(tmp_path / "a" / "b")
    assert get_paths() == [tmp_path / "a" / "b", tmp_path / "a"]
    tree.add_project(tmp_path)
    assert get_paths() == [tmp_path, tmp_path / "a" / "b", tmp_path / "a"]


@pytest.mark.skipif(sys.platform == "win32", reason="rmtree can magically fail on windows")
def test_deleting_project(tree, tmp_path, tabmanager, monkeypatch):
    def get_project_names():
        return [tree.get_path(project).name for project in tree.get_children()]

    (tmp_path / "a").mkdir(parents=True)
    (tmp_path / "b").mkdir(parents=True)
    (tmp_path / "a" / "README").touch()
    (tmp_path / "b" / "README").touch()
    a_tab = tabs.FileTab.open_file(tabmanager, tmp_path / "a" / "README")
    b_tab = tabs.FileTab.open_file(tabmanager, tmp_path / "b" / "README")

    tabmanager.add_tab(a_tab)
    assert get_project_names() == ["a"]
    tabmanager.close_tab(a_tab)
    shutil.rmtree(tmp_path / "a")
    tabmanager.add_tab(b_tab)
    assert get_project_names() == ["b"]
    tabmanager.close_tab(b_tab)


def test_autoclose(tree, tmp_path, tabmanager, monkeypatch):
    def get_project_names():
        return [tree.get_path(project).name for project in tree.get_children()]

    (tmp_path / "a").mkdir(parents=True)
    (tmp_path / "b").mkdir(parents=True)
    (tmp_path / "c").mkdir(parents=True)
    (tmp_path / "a" / "README").touch()
    (tmp_path / "b" / "README").touch()
    (tmp_path / "c" / "README").touch()
    a_tab = tabs.FileTab.open_file(tabmanager, tmp_path / "a" / "README")
    b_tab = tabs.FileTab.open_file(tabmanager, tmp_path / "b" / "README")
    c_tab = tabs.FileTab.open_file(tabmanager, tmp_path / "c" / "README")
    monkeypatch.setattr(plugin_module, "MAX_PROJECTS", 2)

    assert get_project_names() == []

    tabmanager.add_tab(a_tab)
    assert get_project_names() == ["a"]
    tabmanager.add_tab(b_tab)
    assert get_project_names() == ["b", "a"]
    tabmanager.add_tab(c_tab)
    assert get_project_names() == ["c", "b", "a"]

    tabmanager.close_tab(b_tab)
    assert get_project_names() == ["c", "a"]
    tabmanager.close_tab(c_tab)
    assert get_project_names() == ["c", "a"]
    tabmanager.close_tab(a_tab)
    assert get_project_names() == ["c", "a"]


@pytest.mark.skipif(shutil.which("git") is None, reason="git not found")
def test_added_and_modified_content(tree, tmp_path, monkeypatch, dont_run_in_thread):
    monkeypatch.chdir(tmp_path)

    subprocess.check_call(["git", "init", "--quiet"], stdout=subprocess.DEVNULL)
    tree.add_project(tmp_path)

    pathlib.Path("a").write_text("a")
    pathlib.Path("b").write_text("b")
    subprocess.check_call(["git", "add", "a", "b"])
    pathlib.Path("b").write_text("lol")
    [project_id] = tree.get_children()

    tree.refresh_everything()
    assert set(tree.item(project_id, "tags")) == {"project", "dir", "git_modified"}

    subprocess.check_call(["git", "add", "a", "b"])
    tree.refresh_everything()
    assert set(tree.item(project_id, "tags")) == {"project", "dir", "git_added"}


@pytest.mark.skipif(shutil.which("git") is None, reason="git not found")
def test_merge_conflict(tree, tmp_path, monkeypatch, dont_run_in_thread):
    monkeypatch.chdir(tmp_path)

    # Resulting output of 'git log --graph --oneline --all':
    #
    #    * 84dca05 (HEAD -> b) b
    #    | * 9dbd837 (master) a
    #    |/
    #    * e16c2a7 initial
    run = partial(subprocess.run, stdout=subprocess.DEVNULL, shell=True, check=True)
    run("git init --quiet")
    run("git config user.name foo")  # not --global, will stay inside repo
    run("git config user.email foo@bar.baz")
    pathlib.Path("file").write_text("initial")
    run("git add file")
    run("git commit -m initial")
    pathlib.Path("file").write_text("a")
    run("git add file")
    run("git commit -m a")
    run("git checkout --quiet -b b HEAD~")  # can't use HEAD^ because ^ is special in windows
    pathlib.Path("file").write_text("b")
    run("git add file")
    run("git commit -m b")
    run("git merge master", check=False)  # Git returns status 1 when merge conflict occurs

    tree.add_project(tmp_path)
    [project_id] = tree.get_children()
    tree.refresh_everything()
    assert set(tree.item(project_id, "tags")) == {"project", "dir", "git_mergeconflict"}


def test_select_file(tree, monkeypatch, tmp_path, tabmanager, dont_run_in_thread):
    (tmp_path / "a").mkdir(parents=True)
    (tmp_path / "b").mkdir(parents=True)
    (tmp_path / "a" / "README").touch()
    (tmp_path / "b" / "README").touch()
    (tmp_path / "b" / "file1").touch()
    (tmp_path / "b" / "file2").touch()

    a_readme = tabs.FileTab.open_file(tabmanager, tmp_path / "a" / "README")
    b_file1 = tabs.FileTab.open_file(tabmanager, tmp_path / "b" / "file1")
    b_file2 = tabs.FileTab.open_file(tabmanager, tmp_path / "b" / "file2")
    tabmanager.add_tab(a_readme)
    tabmanager.add_tab(b_file1)
    tabmanager.add_tab(b_file2)
    tree.update()

    tabmanager.select(a_readme)
    tree.update()
    assert tree.get_path(tree.selection()[0]) == tmp_path / "a"

    tabmanager.select(b_file1)
    tree.update()
    assert tree.get_path(tree.selection()[0]) == tmp_path / "b"

    # Simulate user opening selected item
    tree.item(tree.selection()[0], open=True)
    tree.event_generate("<<TreeviewOpen>>")
    tree.update()
    assert tree.get_path(tree.selection()[0]) == tmp_path / "b" / "file1"

    tabmanager.select(b_file2)
    tree.update()
    assert tree.get_path(tree.selection()[0]) == tmp_path / "b" / "file2"

    b_file2.save_as(tmp_path / "b" / "file3")
    tree.update()
    assert tree.get_path(tree.selection()[0]) == tmp_path / "b" / "file3"

    tabmanager.close_tab(a_readme)
    tabmanager.close_tab(b_file1)
    tabmanager.close_tab(b_file2)


def test_focusing_treeview_with_keyboard_updates_selection(tree, tmp_path, dont_run_in_thread):
    (tmp_path / "README").touch()
    (tmp_path / "hello.py").touch()
    tree.add_project(tmp_path, refresh=False)
    focus_treeview(tree)
    assert tree.selection()
