import fnmatch
def _is_ignored(path_str, ignores):
    for pat in ignores:
        if fnmatch.fnmatch(path_str, pat) or fnmatch.fnmatch(path_str.split('/')[-1], pat):
            return True
    return False

print(_is_ignored('foo/bar.txt', ['*.txt']))
