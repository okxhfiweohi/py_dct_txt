import json
import math
import re
import unicodedata
from functools import lru_cache
from typing import Final, Union

import yaml

try:
    YamlLoader = yaml.CSafeLoader
    YamlDumper = yaml.CSafeDumper
    YAML_DUMPER_WIDTH = 2147483647
except:
    YamlLoader = yaml.SafeLoader
    YamlDumper = yaml.SafeDumper
    YAML_DUMPER_WIDTH = float("inf")



class FastScalarParser:
    _FLOAT_REGEX = re.compile(r"^[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?$")
    _INT_REGEX = re.compile(r"^[-+]?\d+$")
    _OCTAL_REGEX = re.compile(r"^0o[0-7]+$", re.IGNORECASE)
    _HEX_REGEX = re.compile(r"^0x[0-9a-f]+$", re.IGNORECASE)
    _BINARY_REGEX = re.compile(r"^0b[01]+$", re.IGNORECASE)
    _INF_REGEX = re.compile(r"^[+-]?\.inf$", re.IGNORECASE)
    _NAN_REGEX = re.compile(r"^\.nan$", re.IGNORECASE)
    _BOOL_MAP = {
        "true": True,
        "false": False,
        "True": True,
        "False": False,
        "TRUE": True,
        "FALSE": False,
    }
    _BOOL_SET = frozenset(_BOOL_MAP.keys())
    _NULL_SET = frozenset({"null", "Null", "NULL", "~"})
    _SPECIAL_CHARS = frozenset(":{}[]&*#?|-<>=!%@\\'\"")
    _SPECIAL_CHARS_BITMAP = [0] * 128
    for ch in _SPECIAL_CHARS:
        if ord(ch) < 128:
            _SPECIAL_CHARS_BITMAP[ord(ch)] = 1
    for i in range(32):
        _SPECIAL_CHARS_BITMAP[i] = 1

    EMPTY_RESULT: Final = tuple()

    @classmethod
    def parse(cls, s: str) -> Union[int, float, bool, str, None, tuple[()]]:
        s = s.strip()
        # not scalar
        if s and s[0] in ("{", "[", "!"):
            return cls.EMPTY_RESULT

        if not s:
            return None
        if s in cls._NULL_SET:
            return None
        if s in cls._BOOL_SET:
            return cls._BOOL_MAP[s]

        # quoted
        first_char = s[0]
        if len(s) >= 2 and first_char == s[-1]:
            content = s[1:-1]
            if first_char == "'":
                return cls._parse_single_quoted(content)
            elif first_char == '"':
                return cls._parse_double_quoted(content, s)

        # number
        result = cls._parse_number(s)
        if result is not cls.EMPTY_RESULT:
            return result

        # unquoted
        bitmap = cls._SPECIAL_CHARS_BITMAP
        for ch in s:
            code = ord(ch)
            if code < 128 and bitmap[code]:
                return cls.EMPTY_RESULT

        return s

    @classmethod
    def _parse_number(cls, s: str):
        """解析数字类型"""
        # 检查特殊浮点数
        if cls._INF_REGEX.match(s):
            return math.inf if s[0] != "-" else -math.inf
        if cls._NAN_REGEX.match(s):
            return math.nan

        # 检查进制数
        if len(s) > 2:
            if s[1] in ("o", "O") and cls._OCTAL_REGEX.match(s):
                return int(s, 8)
            if s[1] in ("x", "X") and cls._HEX_REGEX.match(s):
                return int(s, 16)
            if s[1] in ("b", "B") and cls._BINARY_REGEX.match(s):
                return int(s, 2)

        # 检查整数
        if cls._INT_REGEX.match(s):
            try:
                return int(s)
            except (ValueError, OverflowError):
                pass

        # 检查浮点数
        if cls._FLOAT_REGEX.match(s):
            try:
                return float(s)
            except (ValueError, OverflowError):
                pass
        return cls.EMPTY_RESULT

    _INVALID_SQ_RE = re.compile(r"(?<!')'(?!')")
    _INVALID_DQ_RE = re.compile(r'(?<!\\)"')

    @classmethod
    def _parse_single_quoted(cls, s: str):
        if cls._INVALID_SQ_RE.search(s):
            return cls.EMPTY_RESULT
        return s.replace("''", "'")

    _YAML2JSON_ESCAPE_MAP = {
        r"\a": r"\u0007",
        r"\e": r"\u001B",
        r"\v": r"\u000B",
        r"\0": r"\u0000",
    }
    _YAML_U8_ESCAPE_RE = re.compile(r"\\U([0-9a-fA-F]{8})")
    _YAML_OCT_ESCAPE_RE = re.compile(r"\\([0-7]{1,3})")

    @classmethod
    def _parse_double_quoted(cls, s: str, raw: str):
        if not s:
            return s
        if cls._INVALID_DQ_RE.search(s):
            return cls.EMPTY_RESULT
        if "\\" not in s:
            return s
        temp = raw
        for yaml_esc, json_esc in cls._YAML2JSON_ESCAPE_MAP.items():
            temp = temp.replace(yaml_esc, json_esc)
        # → 对应Unicode字符
        # 处理\UXXXXXXXX
        temp = cls._YAML_U8_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), temp)
        # 处理\ooo
        temp = cls._YAML_OCT_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 8)), temp)
        return json.loads(temp)


def _represent_none(dumper: yaml.CSafeDumper, _):
    return dumper.represent_scalar("tag:yaml.org,2002:null", "_NULL")


class CustomSafeDumper(YamlDumper):  # pyright: ignore[reportGeneralTypeIssues]
    pass


CustomSafeDumper.add_representer(type(None), _represent_none)


def yaml_flow_dumps(data) -> str:
    result = yaml.dump(
        data,
        # stream,
        Dumper=CustomSafeDumper,
        # 不换行
        default_flow_style=True,
        width=YAML_DUMPER_WIDTH,
        # 省引号
        default_style=None,
        allow_unicode=True,
        # 取消缩进（行内无需）
        indent=0,
        sort_keys=False,
    )
    return (
        result.strip().replace(": !!null '_NULL'", "").replace("!!null '_NULL'", "null")
    )


def yaml_flow_loads(yaml_str) -> dict:
    return yaml.load(yaml_str, Loader=YamlLoader)


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


@lru_cache(maxsize=128)
def _normalize_to_ascii(s: str) -> str:
    normalized = unicodedata.normalize("NFKD", s)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def normalize_to_ascii(s: str):
    return _normalize_to_ascii(s)
