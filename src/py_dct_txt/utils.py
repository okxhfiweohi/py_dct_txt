import re
import unicodedata
from functools import lru_cache

import yaml


def _represent_none(dumper: yaml.SafeDumper, _):
    return dumper.represent_scalar("tag:yaml.org,2002:null", "_NULL")


yaml.SafeDumper.add_representer(type(None), _represent_none)


def yaml_flow_dumps(data) -> str:
    return (
        yaml.safe_dump(
            data,
            # 不换行
            default_flow_style=True,
            width=float("inf"),
            # 省引号
            default_style=None,
            allow_unicode=True,
            # 取消缩进（行内无需）
            indent=0,
            sort_keys=False,
        )
        .strip()
        .replace(": !!null '_NULL'", "")
        .replace("!!null '_NULL'", "null")
    )


def yaml_flow_loads(yaml_str) -> dict:
    return yaml.safe_load(
        yaml_str,
    )


_inline_comment_pattern = re.compile(r"/\*.*?\*/")


def extract_inline_comments(s: str):
    comments: list[str] = _inline_comment_pattern.findall(s)
    code = _inline_comment_pattern.sub("", s)
    return comments, code


def split_by_first_sep(sep_group: re.Pattern, s: str) -> tuple[str, str, str]:
    """
    Args:
        sep_group: 包含一个捕获组的分割符正则(编译)
    Returns:
        三元组 (前缀, 分隔符, 后缀)
        如果没有分隔符，返回 (原串, "", "")
    """
    parts = sep_group.split(s, maxsplit=1)
    return (parts[0], parts[1], parts[2]) if len(parts) == 3 else (s, "", "")


@lru_cache
def normalize_to_ascii(s: str):
    normalized = unicodedata.normalize("NFKD", s)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")
