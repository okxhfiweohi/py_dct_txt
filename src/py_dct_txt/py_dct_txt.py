"""Main module."""

import json
import re
import sys
from collections import defaultdict
from collections.abc import Collection, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    TextIO,
    TypeAlias,
)

from .utils import (
    extract_inline_comments,
    normalize_to_ascii,
    split_by_first_sep,
    yaml_flow_dumps,
    yaml_flow_loads,
)


@dataclass
class DctTxtItem:
    k: str = ""
    anchor: str = ""
    comment_before: list[str] = field(default_factory=list)
    comment_after: list[str] = field(default_factory=list)
    l: list[str] = field(default_factory=list)
    s: str | None = None
    v: list | dict | str | int | float | None | Any = None
    kvs: dict = field(default_factory=dict)


DctTxtListItem: TypeAlias = tuple[str, str, str, str, list[str]]
DctTxtList: TypeAlias = list[DctTxtListItem]


class DctTxt:
    LINE_SEPARATOR_PATTERN = re.compile(r"(:=|=>|>>|<>)")

    def read_as_list(self, fp: TextIO | Iterable[str]):
        res: DctTxtList = []
        for row in fp:
            first = ""
            comments, code = extract_inline_comments(row.rstrip())
            if row.startswith("/*"):
                if comments:
                    first = comments.pop(0)
            res.append(
                self.format_list_item(
                    (
                        first,
                        *split_by_first_sep(self.LINE_SEPARATOR_PATTERN, code),
                        comments,
                    )
                )
            )
        return res

    def _merge_item(self, dst: DctTxtItem, other: DctTxtItem):
        if other.k:
            dst.k = other.k
        if other.anchor:
            dst.anchor = other.anchor
        if other.comment_before:
            dst.comment_before.extend(other.comment_before)
        if other.comment_after:
            dst.comment_after.extend(other.comment_after)
        if other.l:
            dst.l.extend(other.l)
        if other.s:
            dst.s = other.s
        if other.v is not None:
            dst.v = other.v
        if len(other.kvs):
            dst.kvs.update(other.kvs)
        return dst

    def _run_script(
        self, list_item: DctTxtListItem, d: dict[str, DctTxtItem], g: dict
    ) -> bool | None:
        return False

    def _bind_value(self, current: DctTxtItem, list_item: DctTxtListItem):
        _, _, c_sep, c_v, _ = list_item
        try:
            match c_sep:
                case ":=":
                    current.l = list(map(lambda v: v.strip(), c_v.split("||")))
                case "=>":
                    current.s = c_v.strip()
                case ">>":
                    current.v = yaml_flow_loads("{v: " + c_v + "}")["v"]
                case "<>":
                    current.kvs = yaml_flow_loads("{" + c_v + "}")
                case _:
                    pass
        except Exception as e:
            print(e, file=sys.stderr)

    def load_dict(self, dct_list: DctTxtList):
        g = {}
        d: dict[str, DctTxtItem] = {}
        last_key = ""
        anchor = ""
        using_anchor = 0
        for item in dct_list:
            c_cf, c_k, _, _, c_ca = item
            if c_k:
                using_anchor = 0
                anchor = ""
                last_key = c_k
            else:
                using_anchor += 1
                anchor = f"{last_key}\t_{using_anchor:05d}"
            current = DctTxtItem(
                k=c_k,
                anchor=anchor,
                comment_before=[c_cf] if c_cf else [],
                comment_after=c_ca,
            )
            bindable: bool | None = True
            if c_cf.startswith("/*!"):
                bindable = self._run_script(item, d, g)
            if bindable is False:
                continue
            self._bind_value(current, item)
            key = c_k or anchor
            if key in d:
                d[key] = self._merge_item(d[key], current)
            else:
                d[key] = current
        return d, g

    def read_as_dict(self, fp: TextIO | Iterable[str]):
        ls = self.read_as_list(fp)
        return self.load_dict(ls)

    def dump_dict(self, dct: dict[str, DctTxtItem]):
        res: DctTxtList = []
        for item in dct.values():
            for cmt in item.comment_before:
                res.append((cmt, item.k, "", "", []))
            if item.l:
                res.append(("", item.k, ":=", " || ".join(item.l), []))
            if item.s:
                res.append(("", item.k, "=>", item.s, []))
            if len(item.kvs):
                res.append(("", item.k, "<>", yaml_flow_dumps(item.kvs)[1:-1], []))
            if item.v is not None:
                v = yaml_flow_dumps(item.v).strip()
                if v.endswith("\n..."):
                    v = v[:-4]
                v = v.strip()
                res.append(("", item.k, ">>", v, []))
            if item.comment_after:
                c_cf, _, c_sep, c_v, _ = (
                    res.pop()
                    if res and res[-1][1] == item.k
                    else ("", "", "", "", None)  # None will be ignored (_)
                )
                res.append((c_cf, item.k, c_sep, c_v, item.comment_after))
        return res

    def get_list_batch(self, l: DctTxtList, batch_size=1000, max_extra=10):
        n = len(l)
        i = 0
        while i < n:
            end = min(n, i + batch_size)
            if end < n and max_extra > 0:
                last_key = l[end - 1][1]
                extra_end = end
                max_extra_end = min(n, i + batch_size + max_extra + 2)
                while extra_end < max_extra_end and l[extra_end][1] == last_key:
                    extra_end += 1
                if extra_end - i <= batch_size + max_extra:
                    end = extra_end
            yield l[i:end]
            i = end

    def save_list(self, l: DctTxtList, fp: TextIO | None = None, *, batch_size=10000):
        lines = []
        for item in l:
            first_comment, key, sep, value, inline_comments = item

            parts = []
            if first_comment:
                parts.append(first_comment)
            if key:
                parts.append(key)
            if sep:
                parts.extend([sep, value])
            elif value:
                ...
            if inline_comments:
                parts.extend(inline_comments)
            lines.append(" ".join(parts).rstrip())
        if fp is not None:
            for i in range(0, len(lines), batch_size):
                batch = lines[i : i + batch_size]
                fp.write("\n".join(batch))
                if i + batch_size < len(lines):
                    fp.write("\n")
        return lines

    def save_dict(
        self, dct: dict[str, DctTxtItem], fp: TextIO | None = None, *, batch_size=10000
    ):
        ls = self.dump_dict(dct)
        return self.save_list(ls, fp, batch_size=batch_size)

    def format_list_item(self, item: DctTxtListItem):
        comment_first, k, sep, v, comment_others = item
        if comment_first.startswith("/*!"):
            comment_first = "/*! " + comment_first[3:-2].strip() + " */"
        elif comment_first:
            comment_first = "/* " + comment_first[2:-2].strip() + " */"

        new_comment_others = []
        for c in comment_others:
            if not c or len(c) <= 4:
                continue
            c = v[2:-2].strip()
            if c:
                new_comment_others.append(f"/* {c} */")

        return (comment_first, k.strip(), sep, v, new_comment_others)


NestedDict = dict[str, dict[str, DctTxtItem]]


class DctTxtStore:
    @classmethod
    def transpose_dict(cls, nested_dict: NestedDict) -> NestedDict:
        res = defaultdict(dict)

        for outer_key, inner_dict in nested_dict.items():
            for inner_key, value in inner_dict.items():
                res[inner_key][outer_key] = value

        return dict(res)

    @classmethod
    def file_line_iter(cls, files: list[Path]) -> Iterator[str]:
        assert all(path.is_file() for path in files)
        for path in files:
            with open(path, encoding="utf-8") as f:
                yield from f

    GROUP_NAME_PATTERN = re.compile(r"^([^/]+?)(?:__\d+)?\.dct\.txt$")

    @classmethod
    def extract_groupname(cls, filename: str):
        match = cls.GROUP_NAME_PATTERN.match(filename)
        if match:
            return match.group(1)
        return "unknown"

    saved_info_filename = "_dct_txt_info.json"

    def __init__(self, *, serializer: DctTxt | None = None) -> None:
        self.read_files: set[Path] = set()
        self.saved_files: set[Path] = set()
        self.serializer = DctTxt() if serializer is None else serializer

    def load(self, path: Path):
        files: list[Path] = []
        if path.exists():
            if path.is_dir():
                files.extend(sorted(path.glob("**/*.dct.txt")))
                self.read_files.update(path.glob(f"**/{self.saved_info_filename}"))
            elif path.is_file() and path.name.endswith(".dct.txt"):
                files.append(path)
        file_groups = defaultdict(list)
        for file in files:
            file_groups[self.extract_groupname(file.name)].append(file)
        file_groups = dict(file_groups)
        group_dict: NestedDict = {}
        for name, group in file_groups.items():
            data, _ = self.serializer.read_as_dict(self.file_line_iter(group))
            if len(data) == 0:
                continue
            group_dict[name] = data
        self.read_files.update(files)
        key_dict = self.transpose_dict(group_dict)
        return key_dict

    def create_index_map(self, keys: Collection[str]) -> dict[str, list[str]]:
        if len(keys) < 1000:
            return {"": list(keys)}
        res = defaultdict(list)
        for key in keys:
            first = normalize_to_ascii(key[0])
            first = first[0] if first else "#"
            res[first.lower() if first.isascii() and first.isalpha() else "#"].append(
                key
            )
        res: dict[str, list[str]] = dict(res)
        return res

    def save(self, key_dict: NestedDict, path: Path, *, batch_size=5000):
        index_map = self.create_index_map(key_dict.keys())
        for index, keys in index_map.items():
            index_path = path / index
            idx_key_dict = {k: key_dict[k] for k in keys}
            idx_group_dict = self.transpose_dict(idx_key_dict)
            for name, group in idx_group_dict.items():
                group_l = self.serializer.dump_dict(group)
                if len(group_l):
                    index_path.mkdir(parents=True, exist_ok=True)
                for i, batch in enumerate(
                    self.serializer.get_list_batch(group_l, batch_size)
                ):
                    if not batch:
                        continue
                    if not name:
                        name = "default"
                    first_file_key = next((v[1] for v in batch if v[1]), None)
                    last_file_key = next((v[1] for v in reversed(batch) if v[1]), None)
                    file_i = f"__{i}" if i > 0 else ""
                    file_path = index_path / f"{name}{file_i}.dct.txt"
                    with open(file_path, "w", encoding="utf-8") as f:
                        self.serializer.save_list(batch, f)
                    self.saved_files.add(file_path)
                    info_file = index_path / self.saved_info_filename
                    if info_file.is_file():
                        with open(info_file) as f:
                            info = json.load(f)
                    else:
                        info = {}
                    info[name + file_i] = {
                        "start": first_file_key,
                        "end": last_file_key,
                        "total": len(batch),
                    }
                    with open(info_file, "w") as f:
                        json.dump(info, f, ensure_ascii=False, indent=4)
                    self.saved_files.add(info_file)

    def clean(self):
        old_files = self.read_files - self.saved_files
        for p in old_files:
            p.unlink(missing_ok=True)

    @classmethod
    def clean_empty_folder(cls, path: Path):
        if not path.is_dir():
            return
        for folder in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if folder.is_dir() and folder != path:
                if not any(folder.iterdir()):
                    try:
                        folder.rmdir()
                    except Exception:
                        pass


def add_item(key_dict: NestedDict, group: str, item: DctTxtItem):
    key = item.k or item.anchor
    if not key:
        key = item.anchor = f"\t~{len(key_dict)}"
    if key not in key_dict:
        key_dict[key] = {}
    key_dict[key][group] = item


def merge_key_dicts(dst: NestedDict, *others: NestedDict):
    dct = DctTxt()
    for other in others:
        for key, groups in other.items():
            if key not in dst and len(groups):
                dst[key] = {}
            for group_name, item in groups.items():
                dst[key][group_name] = (
                    dct._merge_item(dst[key][group_name], item)
                    if group_name in dst[key]
                    else item
                )
